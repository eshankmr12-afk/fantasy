"""Roster valuation: what a set of players is actually worth over a season.

A drafted roster is not the sum of its projections. What matters is the points
you can *start*, week by week, once bye weeks and injuries take players off the
board - which is why depth at a scarce position has real value and a fourth
tight end has none.

This module simulates every week of the season for a roster: it draws
availability, fills the lineup optimally, and backfills empty slots at waiver
value. The whole thing is vectorized over (simulations x weeks x players), so a
full evaluation costs about a millisecond and can run inside a draft rollout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np

from .board import Player
from .config import FLEX_ELIGIBLE, LeagueConfig

# A slot you cannot fill is streamed from waivers, not scored as zero. Waiver
# fodder is a bit worse than the draft's replacement level.
WAIVER_DISCOUNT = 0.88


@dataclass
class RosterValue:
    mean: float
    p10: float
    p90: float
    stdev: float

    @property
    def floor(self) -> float:
        return self.p10

    @property
    def ceiling(self) -> float:
        return self.p90


class RosterEvaluator:
    """Scores rosters by simulated startable points over the season."""

    def __init__(self, config: LeagueConfig, replacement: Dict[str, float],
                 sims: int = 160, seed: int = 7):
        self.config = config
        self.sims = sims
        self.rng = np.random.default_rng(seed)

        roster = config.roster
        self.required = {p: n for p, n in roster.required_slots().items() if n > 0}
        self.flex_slots = roster.flex
        self.superflex_slots = roster.superflex

        weeks = np.arange(1, config.weeks + 1)
        self.week_ids = weeks
        w = np.ones(config.weeks, dtype=float)
        for pw in config.playoff_weeks:
            if 1 <= pw <= config.weeks:
                w[pw - 1] = config.playoff_weight
        # Normalised so a roster's score stays on a "season points" scale.
        self.week_weights = w * (config.weeks / w.sum())

        # Per-game waiver value available at each position.
        self.waiver_ppg = {
            pos: max(0.0, replacement.get(pos, 0.0)) / config.weeks * WAIVER_DISCOUNT
            for pos in ("QB", "RB", "WR", "TE", "K", "DEF")
        }
        self.flex_waiver_ppg = max(self.waiver_ppg[p] for p in FLEX_ELIGIBLE)

    # -- core ---------------------------------------------------------------
    def evaluate(self, players: Sequence[Player], sims: int | None = None) -> RosterValue:
        """Distribution of season-long startable points for this roster."""
        sims = sims or self.sims
        weekly = self._weekly_totals(players, sims)          # (sims, weeks)
        season = (weekly * self.week_weights[None, :]).sum(axis=1)
        return RosterValue(
            mean=float(season.mean()),
            p10=float(np.percentile(season, 10)),
            p90=float(np.percentile(season, 90)),
            stdev=float(season.std()),
        )

    def mean_value(self, players: Sequence[Player], sims: int | None = None) -> float:
        """Just the expectation - the objective the optimizer maximizes."""
        sims = sims or self.sims
        weekly = self._weekly_totals(players, sims)
        return float((weekly * self.week_weights[None, :]).sum(axis=1).mean())

    def _weekly_totals(self, players: Sequence[Player], sims: int) -> np.ndarray:
        n_weeks = self.config.weeks
        if not players:
            return np.full((sims, n_weeks), self._empty_lineup_ppg())

        # Fixed descending-value order: greedy lineup filling in this order is
        # optimal for a position-slots-plus-flex structure.
        order = sorted(range(len(players)), key=lambda i: -players[i].ppg)
        ppg = np.array([players[i].ppg for i in order])
        avail = np.array([players[i].availability for i in order])
        byes = np.array([players[i].bye for i in order])
        pos = [players[i].position for i in order]

        n = len(order)
        # active[s, w, i]: player i is healthy and not on bye in week w of sim s.
        healthy = self.rng.random((sims, n_weeks, n)) < avail[None, None, :]
        on_bye = byes[None, None, :] == self.week_ids[None, :, None]
        active = healthy & ~on_bye

        used = np.zeros_like(active)
        totals = np.zeros((sims, n_weeks))

        # 1. Fill dedicated positional slots with the best active players.
        for position, need in self.required.items():
            mask = np.array([p == position for p in pos])
            if not mask.any():
                totals += need * self.waiver_ppg[position]
                continue
            eligible = active & mask[None, None, :]
            rank = np.cumsum(eligible, axis=-1)
            chosen = eligible & (rank <= need)
            used |= chosen
            totals += (chosen * ppg[None, None, :]).sum(axis=-1)
            filled = chosen.sum(axis=-1)
            totals += (need - filled) * self.waiver_ppg[position]

        # 2. FLEX, then SUPERFLEX, from whoever is left.
        for slots, positions, waiver in (
            (self.flex_slots, FLEX_ELIGIBLE, self.flex_waiver_ppg),
            (self.superflex_slots, tuple(FLEX_ELIGIBLE) + ("QB",),
             max(self.flex_waiver_ppg, self.waiver_ppg["QB"])),
        ):
            if slots <= 0:
                continue
            mask = np.array([p in positions for p in pos])
            eligible = active & mask[None, None, :] & ~used
            rank = np.cumsum(eligible, axis=-1)
            chosen = eligible & (rank <= slots)
            used |= chosen
            totals += (chosen * ppg[None, None, :]).sum(axis=-1)
            totals += (slots - chosen.sum(axis=-1)) * waiver

        return totals

    def _empty_lineup_ppg(self) -> float:
        base = sum(n * self.waiver_ppg[pos] for pos, n in self.required.items())
        base += self.flex_slots * self.flex_waiver_ppg
        base += self.superflex_slots * max(self.flex_waiver_ppg, self.waiver_ppg["QB"])
        return base

    # -- helpers used by the draft policy -----------------------------------
    def marginal_value(self, roster: List[Player], candidate: Player,
                       sims: int | None = None) -> float:
        """How much this player adds to an existing roster, in season points."""
        before = self.mean_value(roster, sims)
        after = self.mean_value(list(roster) + [candidate], sims)
        return after - before
