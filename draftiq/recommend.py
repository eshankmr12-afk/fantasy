"""The pick recommender: one-ply lookahead over Monte Carlo draft rollouts.

Most draft tools rank players and stop. That is the wrong objective. What you
actually want to maximise is the expected value of your *finished roster*, and
that depends on who will still be on the board at your next pick.

For every candidate, this module forces that pick, plays the rest of the draft
out many times against the opponent model, and scores the resulting roster with
the weekly lineup simulator. The winner is the pick with the best expected
finished roster - which naturally produces the behaviour you want without any
of it being hard-coded:

* it waits on a player the simulations say will fall back to you,
* it takes the last member of a collapsing tier early,
* it stops paying for a position it has already filled,
* and it values a scarce position above a marginally better player.

`VONA` (value over next available) is reported alongside as the intuitive
explanation: how much you lose at that position by waiting one round.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from .board import Board, Player
from .config import LeagueConfig
from .lineup import RosterEvaluator
from .simulator import DraftSimulator, DraftState


@dataclass
class Candidate:
    """One option at the current pick, with everything needed to justify it."""

    player: Player
    value: float              # expected finished-roster points GIVEN we get him
    delta: float              # vs. the best alternative
    p10: float
    p90: float
    p_available: float        # P(he is still on the board when this pick arrives)
    survival_next: float      # P(still available at our next pick)
    vona: float               # value lost at this position by waiting a round
    tier_remaining: int       # players left in his tier
    tier_survival: float      # P(at least one of his tier survives to next pick)
    reason: str = ""

    @property
    def name(self) -> str:
        return self.player.name


@dataclass
class Recommendation:
    pick: int
    round: int
    slot: int
    candidates: List[Candidate]
    sims: int
    next_pick: Optional[int] = None

    @property
    def best(self) -> Candidate:
        return self.candidates[0]

    @property
    def back_to_back(self) -> bool:
        """True at the turn, where two picks arrive together."""
        return self.next_pick is not None and self.next_pick - self.pick <= 2


class Recommender:
    def __init__(self, board: Board, config: LeagueConfig,
                 simulator: Optional[DraftSimulator] = None,
                 evaluator: Optional[RosterEvaluator] = None,
                 seed: int = 11):
        self.board = board
        self.config = config
        self.evaluator = evaluator or RosterEvaluator(config, board.replacement)
        self.sim = simulator or DraftSimulator(board, config, self.evaluator, seed=seed)

    # -- candidate generation ----------------------------------------------
    def _shortlist(self, state: DraftState, my_slot: int, width: int) -> List[int]:
        """Plausible picks worth spending simulation budget on.

        Anyone far below the board's best available is not a real option, but we
        deliberately include the best player at each position so a scarcity
        argument can still surface a lower-ranked name.
        """
        taken = set(state.taken)
        available = [i for i in range(self.sim.n) if i not in taken]
        if not available:
            return []

        counts: Dict[str, int] = {}
        for idx in state.roster_of(my_slot):
            counts[self.sim.positions[idx]] = counts.get(self.sim.positions[idx], 0) + 1

        by_value = sorted(available, key=lambda i: -self.sim.upside[i])
        shortlist = [i for i in by_value
                     if counts.get(self.sim.positions[i], 0)
                     < self.sim.max_at.get(self.sim.positions[i], 99)][:width]

        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            if counts.get(pos, 0) >= self.sim.max_at.get(pos, 99):
                continue
            best = next((i for i in by_value if self.sim.positions[i] == pos), None)
            if best is not None and best not in shortlist:
                shortlist.append(best)
        return shortlist

    # -- headline API -------------------------------------------------------
    def recommend(self, state: DraftState, my_slot: int, sims: int = 90,
                  width: int = 12, top: int = 8,
                  min_availability: float = 0.04) -> Recommendation:
        """Rank the options at the current pick by expected finished-roster value.

        Candidates are conditioned on actually being available when the pick
        arrives. That matters when planning ahead of the draft: at slot 15 the
        question is never "is Ja'Marr Chase the best player", it is "who will
        be there, and which of them builds the best roster".
        """
        # One shared survival pass, so every candidate is judged against the
        # same picture of what the rest of the league is about to do.
        baseline = self.sim.simulate(state, my_slot, sims=max(sims, 150),
                                     evaluate=False)
        my_picks = baseline.my_picks
        this_pick = my_picks[0] if my_picks else state.next_pick
        next_pick = my_picks[1] if len(my_picks) > 1 else None
        survival_here = baseline.survival.get(this_pick, np.ones(self.sim.n))
        survival_next = (baseline.survival[next_pick] if next_pick
                         else np.zeros(self.sim.n))

        shortlist = [i for i in self._shortlist(state, my_slot, width * 3)
                     if survival_here[i] >= min_availability][:width]
        if not shortlist:
            raise ValueError("no players available")

        results: List[Candidate] = []
        for idx in shortlist:
            sim_result = self.sim.simulate(state, my_slot, sims=sims,
                                           forced_first=idx, evaluate=True,
                                           require_forced=True)
            player = self.sim.player(idx)
            results.append(Candidate(
                player=player,
                value=float(sim_result.values.mean()),
                delta=0.0,
                p10=float(np.percentile(sim_result.values, 10)),
                p90=float(np.percentile(sim_result.values, 90)),
                p_available=float(survival_here[idx]),
                survival_next=float(survival_next[idx]),
                vona=self._vona(idx, survival_next),
                tier_remaining=self._tier_remaining(idx, state),
                tier_survival=self._tier_survival(idx, state, survival_next),
            ))

        results.sort(key=lambda c: -c.value)
        runner_up = results[1].value if len(results) > 1 else results[0].value
        gap = (next_pick - this_pick) if next_pick else 0
        for c in results:
            c.delta = c.value - runner_up
            c.reason = self._explain(c, gap)

        return Recommendation(
            pick=this_pick,
            round=(this_pick - 1) // self.config.teams + 1,
            slot=my_slot,
            candidates=results[:top],
            sims=sims,
            next_pick=next_pick,
        )

    # -- supporting metrics -------------------------------------------------
    def _vona(self, idx: int, survival_next: np.ndarray) -> float:
        """Expected drop-off at this position between now and our next pick.

        The value we expect to have available at the position one round from
        now is the survival-weighted best remaining player; VONA is how much
        better this player is than that.
        """
        pos = self.sim.positions[idx]
        same = [i for i in range(self.sim.n)
                if self.sim.positions[i] == pos and self.sim.upside[i] > 0]
        same.sort(key=lambda i: -self.sim.vor[i])

        # Probability each player is the best of his position still on the
        # board next time: he survives and everyone better than him does not.
        expected, none_better = 0.0, 1.0
        for i in same:
            p = float(survival_next[i])
            expected += none_better * p * self.sim.vor[i]
            none_better *= (1.0 - p)
            if none_better < 1e-4:
                break
        return float(self.sim.vor[idx] - expected)

    def _tier_peers(self, idx: int, state: DraftState) -> List[int]:
        player = self.sim.player(idx)
        taken = set(state.taken)
        return [i for i in range(self.sim.n)
                if i not in taken
                and self.sim.players[i].position == player.position
                and self.sim.players[i].tier == player.tier]

    def _tier_remaining(self, idx: int, state: DraftState) -> int:
        return len(self._tier_peers(idx, state))

    def _tier_survival(self, idx: int, state: DraftState,
                       survival_next: np.ndarray) -> float:
        """P(at least one player of this tier is still there at our next pick)."""
        peers = self._tier_peers(idx, state)
        if not peers:
            return 0.0
        none = 1.0
        for i in peers:
            none *= (1.0 - float(survival_next[i]))
        return 1.0 - none

    def _explain(self, c: Candidate, gap: int) -> str:
        """A short, human-readable justification for the recommendation."""
        bits: List[str] = []
        if c.p_available < 0.5:
            bits.append(f"only {c.p_available * 100:.0f}% to reach you")
        # At the turn your next pick is one or two slots later, so "he'll last"
        # is trivially true and says nothing about whether to wait.
        if gap > 2:
            if c.survival_next < 0.15:
                bits.append(f"gone by your next pick ({c.survival_next * 100:.0f}% to last)")
            elif c.survival_next > 0.65:
                bits.append(f"can wait, {c.survival_next * 100:.0f}% to last")
        if c.tier_remaining <= 2 and c.tier_survival < 0.5:
            bits.append(f"last of tier {c.player.tier} at {c.player.position}")
        if c.vona > 12:
            bits.append(f"+{c.vona:.0f} pts vs waiting at {c.player.position}")
        if c.player.edge > 15 and c.player.times_drafted > 150:
            bits.append(f"market is {c.player.edge:.0f} pts light on him")
        if c.player.risk and c.player.risk.injury_status:
            bits.append(f"{c.player.risk.injury_status.lower()}")
        return "; ".join(bits)

    # -- "who should I take at each slot" ----------------------------------
    def slot_report(self, my_slot: int, sims: int = 250) -> Dict:
        """Full-draft outlook for one draft position, before the draft starts."""
        state = DraftState(self.config)
        result = self.sim.simulate(state, my_slot, sims=sims, evaluate=True)
        rec = self.recommend(state, my_slot, sims=max(60, sims // 3))

        rounds = []
        for r, counts in enumerate(result.pick_counts, start=1):
            total = sum(counts.values()) or 1
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:4]
            rounds.append({
                "round": r,
                "pick": self.config.picks_for_slot(my_slot)[r - 1],
                "options": [(self.sim.player(i), n / total) for i, n in top],
            })

        return {
            "slot": my_slot,
            "picks": self.config.picks_for_slot(my_slot),
            "value_mean": float(result.values.mean()),
            "value_p10": float(np.percentile(result.values, 10)),
            "value_p90": float(np.percentile(result.values, 90)),
            "first_pick": rec,
            "rounds": rounds,
            "survival": result.survival,
            "sims": sims,
        }
