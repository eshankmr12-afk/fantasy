"""Monte Carlo draft simulation.

The engine's core claim is that you should not draft against a ranking, you
should draft against *what the other 14 teams are about to do*. That requires a
model of those teams, which this module provides:

Opponent model
--------------
Each simulated team drafts off its own noisy version of the consensus board.
Noise is split into a persistent per-team bias - a team that likes a player
likes him all draft - and fresh per-pick noise. On top of that sits roster
logic: hard positional caps, diminishing interest in a position already stocked,
and escalating urgency to fill an empty starting slot as picks run out. That
last rule is what reproduces the late-round kicker and defense runs that a pure
ADP model never generates.

From repeated rollouts we get the two quantities that actually drive decisions:
the probability a player survives to each of your future picks, and the
distribution of season-long roster value that follows from any first choice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .board import Board, Player
from .config import FLEX_ELIGIBLE, LeagueConfig
from .lineup import RosterEvaluator

# Share of a starter's surplus that a backup captures, by depth past the last
# starting slot. A first backup plays when someone ahead is hurt or on bye; a
# third backup essentially never plays.
BENCH_SHARE = {
    "QB": (0.14, 0.03), "RB": (0.40, 0.15), "WR": (0.36, 0.13),
    "TE": (0.13, 0.03), "K": (0.02, 0.01), "DEF": (0.06, 0.02),
}

# Kicker and defense projections have very little year-over-year signal, so
# their nominal edge over replacement is discounted rather than trusted.
LOW_SIGNAL_DISCOUNT = {"K": 0.30, "DEF": 0.45}

# Soft caps for the opponent model: past this many at a position, further picks
# are progressively penalised (in ADP-pick units per extra player).
SOFT_CAP = {"QB": 1, "RB": 4, "WR": 5, "TE": 1, "K": 1, "DEF": 1}
DUP_PENALTY = {"QB": 34.0, "RB": 5.0, "WR": 4.0, "TE": 26.0, "K": 200.0, "DEF": 160.0}

# Candidate window: a real drafter picks from near the top of their board, not
# from all 600 remaining players. Keeps rollouts fast without changing outcomes.
CANDIDATE_WINDOW = 40


@dataclass
class DraftState:
    """Who has been taken so far, and by whom."""

    config: LeagueConfig
    taken: Dict[int, int] = field(default_factory=dict)   # player index -> slot
    order: List[int] = field(default_factory=list)        # player indices, in pick order

    @property
    def next_pick(self) -> int:
        return len(self.order) + 1

    @property
    def current_round(self) -> int:
        return (self.next_pick - 1) // self.config.teams + 1

    def roster_of(self, slot: int) -> List[int]:
        return [idx for idx, s in self.taken.items() if s == slot]

    def record(self, player_index: int, slot: int) -> None:
        if player_index in self.taken:
            raise ValueError("player already drafted")
        self.taken[player_index] = slot
        self.order.append(player_index)

    def undo(self) -> Optional[int]:
        if not self.order:
            return None
        idx = self.order.pop()
        self.taken.pop(idx, None)
        return idx

    def copy(self) -> "DraftState":
        return DraftState(self.config, dict(self.taken), list(self.order))


@dataclass
class SimulationResult:
    """Aggregated output of many draft rollouts."""

    sims: int                                            # rollouts kept
    attempts: int                                        # rollouts run (differs
    #                                                      when rejection sampling)
    my_picks: List[int]                                  # overall pick numbers
    # survival[pick_number][player_index] = P(available when that pick arrives)
    survival: Dict[int, np.ndarray]
    # How often each player ended up on our roster.
    acquired: np.ndarray
    # Season-value distribution of the resulting rosters.
    values: np.ndarray
    # Most common pick at each of our slots: player index -> count.
    pick_counts: List[Dict[int, int]]


class DraftSimulator:
    """Simulates the remainder of a draft many times."""

    def __init__(self, board: Board, config: LeagueConfig,
                 evaluator: Optional[RosterEvaluator] = None,
                 seed: int = 0, universe: Optional[int] = None):
        self.board = board
        self.config = config
        self.evaluator = evaluator or RosterEvaluator(config, board.replacement)
        self.rng = np.random.default_rng(seed)

        # The whole board is in play. Keeping every player indexable means a
        # real draft can never contain a pick the simulator doesn't know about;
        # the per-pick candidate window is what keeps rollouts fast.
        keep = sorted(board.players, key=lambda p: p.adp)
        if universe is not None:
            keep = keep[:universe]
        self.players: List[Player] = keep
        self.index_of: Dict[str, int] = {p.key: i for i, p in enumerate(keep)}

        n = len(keep)
        self.n = n
        self.adp = np.array([p.adp for p in keep])
        self.vor = np.array([p.vor for p in keep])
        self.points = np.array([p.points for p in keep])
        self.positions = [p.position for p in keep]

        # Draft value is an option on a player's outcome, not his mean. A late
        # flier projected below replacement is still worth something because he
        # might break out; a low-variance backup QB with the same projection is
        # not. E[max(0, points - replacement)] captures exactly that, is always
        # positive, and stays comparable across positions.
        spread = np.maximum(np.array([p.points_stdev for p in keep]), 1.0)
        d = self.vor / spread
        pdf = np.exp(-0.5 * d ** 2) / math.sqrt(2.0 * math.pi)
        cdf = np.array([0.5 * (1.0 + math.erf(x / math.sqrt(2.0))) for x in d])
        self.upside = spread * pdf + self.vor * cdf

        sigma = np.array([p.adp_stdev for p in keep]) * config.adp_noise_scale
        self.sigma_team = sigma * np.sqrt(config.team_bias_share)
        self.sigma_pick = sigma * np.sqrt(1.0 - config.team_bias_share)

        self.required = {p: v for p, v in config.roster.required_slots().items() if v > 0}
        self.max_at = {
            "QB": config.roster.max_qb, "TE": config.roster.max_te,
            "K": config.roster.max_k, "DEF": config.roster.max_dst,
            "RB": config.roster.total, "WR": config.roster.total,
        }
        # ADP-sorted index order, used to build each pick's candidate window.
        self.adp_order = list(np.argsort(self.adp))

    # -- translation helpers ------------------------------------------------
    def index(self, player: Player) -> Optional[int]:
        return self.index_of.get(player.key)

    def player(self, index: int) -> Player:
        return self.players[index]

    # -- opponent behaviour -------------------------------------------------
    def _position_adjustment(self, counts: Dict[str, int], picks_left: int) -> Dict[str, float]:
        """Per-position ADP adjustment for one team's roster situation.

        Negative pulls a position up the board (an unfilled starting slot),
        positive pushes it down (already stocked). A blocked position gets an
        effectively infinite penalty.
        """
        unfilled = {pos: max(0, need - counts.get(pos, 0))
                    for pos, need in self.required.items()}
        total_unfilled = sum(unfilled.values())
        flex_open = counts.get("_flex_used", 0) < self.config.roster.flex
        slack = picks_left - total_unfilled

        adj: Dict[str, float] = {}
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            have = counts.get(pos, 0)
            if have >= self.max_at.get(pos, 99):
                adj[pos] = 1e6
                continue
            value = 0.0
            if unfilled.get(pos, 0) > 0:
                value -= 7.0 * unfilled[pos]
                if slack <= 1:
                    # Out of runway: this slot has to be filled right now.
                    value -= 400.0
                elif slack <= 3:
                    value -= 45.0
            else:
                over = have - SOFT_CAP.get(pos, 5)
                if over > 0:
                    value += DUP_PENALTY.get(pos, 10.0) * over
                if total_unfilled > 0 and pos in ("K", "DEF"):
                    # Nobody drafts a kicker while a starting slot sits empty.
                    value += 120.0
                elif flex_open and pos in FLEX_ELIGIBLE:
                    value -= 5.0
            adj[pos] = value
        return adj

    def _opponent_pick(self, available: List[int], counts: Dict[str, int],
                       picks_left: int, team_bias: np.ndarray,
                       rng: np.random.Generator) -> int:
        window = available[:CANDIDATE_WINDOW]
        idx = np.array(window)
        adj = self._position_adjustment(counts, picks_left)
        penalty = np.array([adj[self.positions[i]] for i in window])
        noise = rng.standard_normal(len(window)) * self.sigma_pick[idx]
        score = self.adp[idx] + team_bias[idx] + penalty + noise
        return int(idx[int(np.argmin(score))])

    # -- our behaviour ------------------------------------------------------
    def _my_pick(self, available: List[int], counts: Dict[str, int],
                 picks_left: int) -> int:
        """Fast heuristic policy used inside rollouts.

        Values a player at full VOR while he fills a starting slot, decays him
        toward bench value once that slot is full, and forces the roster to be
        legal when picks run out. Deliberately cheap: the expensive, accurate
        reasoning happens one ply up in `recommend`.
        """
        window = available[:CANDIDATE_WINDOW]
        unfilled = {pos: max(0, need - counts.get(pos, 0))
                    for pos, need in self.required.items()}
        total_unfilled = sum(unfilled.values())
        must_fill = picks_left <= total_unfilled
        flex_used = counts.get("_flex_used", 0)
        flex_open = flex_used < self.config.roster.flex

        legal = [i for i in window
                 if counts.get(self.positions[i], 0) < self.max_at.get(self.positions[i], 99)]
        if not legal:
            # Window is entirely positions we've capped out; look further down.
            legal = [i for i in available
                     if counts.get(self.positions[i], 0)
                     < self.max_at.get(self.positions[i], 99)][:CANDIDATE_WINDOW]
        if not legal:
            return available[0]

        best, best_score = legal[0], -1e18
        for i in legal:
            pos = self.positions[i]
            surplus = self.upside[i] * LOW_SIGNAL_DISCOUNT.get(pos, 1.0)

            if unfilled.get(pos, 0) > 0:
                share = 1.0
            elif flex_open and pos in FLEX_ELIGIBLE:
                share = 0.90
            else:
                depth = counts.get(pos, 0) - self.required.get(pos, 0)
                shares = BENCH_SHARE.get(pos, (0.3, 0.1))
                share = shares[0] if depth <= 1 else shares[1] * (0.4 ** (depth - 2))

            # Upside tiebreak so that among equally worthless players we keep
            # the one with the higher ceiling rather than an arbitrary one.
            score = surplus * share
            if must_fill:
                score += 1e5 if unfilled.get(pos, 0) > 0 else -1e5
            if score > best_score:
                best, best_score = i, score
        return best

    @staticmethod
    def _add_to_counts(counts: Dict[str, int], position: str,
                       required: Dict[str, int], flex_slots: int) -> None:
        counts[position] = counts.get(position, 0) + 1
        if (counts[position] > required.get(position, 0)
                and position in FLEX_ELIGIBLE
                and counts.get("_flex_used", 0) < flex_slots):
            counts["_flex_used"] = counts.get("_flex_used", 0) + 1

    # -- rollouts -----------------------------------------------------------
    def _rollout(self, state: DraftState, my_slot: int, rng: np.random.Generator,
                 forced_first: Optional[int] = None,
                 record: Optional[Dict[int, np.ndarray]] = None,
                 pick_log: Optional[List[Dict[int, int]]] = None,
                 require_forced: bool = False) -> Optional[List[int]]:
        """Play out the rest of the draft once. Returns our final roster.

        With `require_forced`, a rollout in which an opponent takes the forced
        player before our pick arrives is rejected (returns None) rather than
        quietly falling back to another choice. That makes the resulting value
        a clean conditional expectation - "what this roster is worth *given*
        he falls to me" - instead of silently averaging in drafts where we
        never got him at all.
        """
        cfg = self.config
        taken = set(state.taken)
        available = [i for i in self.adp_order if i not in taken]

        counts: Dict[int, Dict[str, int]] = {}
        for slot in range(1, cfg.teams + 1):
            counts[slot] = {}
        for idx, slot in state.taken.items():
            if idx < self.n:
                self._add_to_counts(counts[slot], self.positions[idx],
                                    self.required, cfg.roster.flex)

        my_roster = [i for i, s in state.taken.items() if s == my_slot and i < self.n]
        team_bias = rng.standard_normal((cfg.teams + 1, self.n)) * self.sigma_team[None, :]

        my_pick_number = 0
        picks_made = {s: len(state.roster_of(s)) for s in range(1, cfg.teams + 1)}

        for overall in range(state.next_pick, cfg.total_picks + 1):
            if not available:
                break
            slot = cfg.slot_for_pick(overall)
            picks_left = cfg.rounds - picks_made[slot]
            if picks_left <= 0:
                continue

            if slot == my_slot:
                if record is not None:
                    mask = record.setdefault(overall, np.zeros(self.n))
                    mask[available] += 1.0
                if forced_first is not None and my_pick_number == 0:
                    if forced_first in taken:
                        if require_forced:
                            return None
                        choice = self._my_pick(available, counts[slot], picks_left)
                    else:
                        choice = forced_first
                else:
                    choice = self._my_pick(available, counts[slot], picks_left)
                if pick_log is not None:
                    if len(pick_log) <= my_pick_number:
                        pick_log.append({})
                    pick_log[my_pick_number][choice] = \
                        pick_log[my_pick_number].get(choice, 0) + 1
                my_roster.append(choice)
                my_pick_number += 1
            else:
                choice = self._opponent_pick(available, counts[slot], picks_left,
                                             team_bias[slot], rng)

            taken.add(choice)
            available.remove(choice)
            self._add_to_counts(counts[slot], self.positions[choice],
                                self.required, cfg.roster.flex)
            picks_made[slot] += 1

        return my_roster

    def simulate(self, state: DraftState, my_slot: int, sims: int = 300,
                 forced_first: Optional[int] = None,
                 evaluate: bool = True,
                 require_forced: bool = False,
                 max_attempts_factor: int = 12) -> SimulationResult:
        """Run many rollouts and aggregate survival, acquisitions and value.

        When `require_forced` is set, rollouts are rejection-sampled until
        `sims` of them actually contain the forced pick, subject to an attempt
        cap so a player who essentially never falls to us doesn't spin forever.
        """
        record: Dict[int, np.ndarray] = {}
        pick_log: List[Dict[int, int]] = []
        acquired = np.zeros(self.n)
        values: List[float] = []
        # Recording survival/pick distributions from a forced run would describe
        # a draft we constrained, not the real one, so it is disabled there.
        collect = record if forced_first is None else None
        log = pick_log if forced_first is None else None

        attempts = 0
        max_attempts = sims * max_attempts_factor if require_forced else sims
        while len(values) < sims and attempts < max_attempts:
            attempts += 1
            roster = self._rollout(state, my_slot, self.rng, forced_first,
                                   collect, log, require_forced)
            if roster is None:
                continue
            acquired[roster] += 1.0
            values.append(self.evaluator.mean_value(
                [self.players[i] for i in roster], sims=48) if evaluate else 0.0)

        completed = max(1, len(values))
        my_picks = sorted(record)
        survival = {pick: counts / completed for pick, counts in record.items()}
        return SimulationResult(
            sims=completed,
            attempts=attempts,
            my_picks=my_picks,
            survival=survival,
            acquired=acquired / completed,
            values=np.array(values) if values else np.zeros(1),
            pick_counts=pick_log,
        )

    # -- survival -----------------------------------------------------------
    def survival_table(self, state: DraftState, my_slot: int,
                       sims: int = 400) -> Dict[int, np.ndarray]:
        """P(player available) at each of our remaining picks."""
        result = self.simulate(state, my_slot, sims=sims, evaluate=False)
        return result.survival
