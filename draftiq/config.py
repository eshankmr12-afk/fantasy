"""League configuration: scoring rules, roster structure, and engine knobs.

Everything downstream is driven by these dataclasses. Change the league here and
the projections, replacement levels, opponent model and simulations all follow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List

# Positions the engine actually models. Anything else is dropped from the board.
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

# Positions eligible for the FLEX slot.
FLEX_ELIGIBLE = ("RB", "WR", "TE")


@dataclass
class Scoring:
    """Points per statistical event.

    Field names match the raw stat keys returned by the Sleeper projections API
    so scoring is a dot product against a player's projected stat line.
    """

    pass_yd: float = 0.04
    pass_td: float = 4.0
    pass_int: float = -2.0
    pass_2pt: float = 2.0

    rush_yd: float = 0.1
    rush_td: float = 6.0
    rush_2pt: float = 2.0

    rec: float = 1.0  # full PPR
    rec_yd: float = 0.1
    rec_td: float = 6.0
    rec_2pt: float = 2.0

    fum_lost: float = -2.0

    # Per-position reception bonuses, layered on top of `rec`. A TE-premium
    # league sets rec_bonus_te to 0.5; standard leagues leave these at zero.
    rec_bonus_rb: float = 0.0
    rec_bonus_wr: float = 0.0
    rec_bonus_te: float = 0.0

    def as_stat_weights(self) -> Dict[str, float]:
        """Weights keyed by Sleeper stat name, excluding the positional bonuses."""
        d = asdict(self)
        for k in ("rec_bonus_rb", "rec_bonus_wr", "rec_bonus_te"):
            d.pop(k)
        return d

    def reception_bonus(self, position: str) -> float:
        return {
            "RB": self.rec_bonus_rb,
            "WR": self.rec_bonus_wr,
            "TE": self.rec_bonus_te,
        }.get(position, 0.0)


@dataclass
class Roster:
    """Starting lineup and bench structure."""

    qb: int = 1
    rb: int = 2
    wr: int = 3
    te: int = 1
    flex: int = 1
    # A flex slot that also accepts a QB. Non-zero turns the league superflex.
    superflex: int = 0
    k: int = 1
    dst: int = 1
    bench: int = 5

    # Hard caps used by the opponent model so simulated teams don't hoard a
    # position. These are behavioural limits, not league rules.
    max_qb: int = 3
    max_te: int = 3
    max_k: int = 1
    max_dst: int = 2

    @property
    def starters(self) -> int:
        return (self.qb + self.rb + self.wr + self.te + self.flex
                + self.superflex + self.k + self.dst)

    @property
    def total(self) -> int:
        return self.starters + self.bench

    def required_slots(self) -> Dict[str, int]:
        """Non-flex starting slots keyed by position."""
        return {"QB": self.qb, "RB": self.rb, "WR": self.wr, "TE": self.te,
                "K": self.k, "DEF": self.dst}


@dataclass
class LeagueConfig:
    """Full league definition plus the engine's tuning parameters."""

    name: str = "Frat League"
    teams: int = 15
    rounds: int = 15
    season: int = 2026
    # Regular-season fantasy weeks that matter for lineup value.
    weeks: int = 17
    # Fantasy playoff weeks, weighted extra in roster valuation.
    playoff_weeks: List[int] = field(default_factory=lambda: [15, 16, 17])
    playoff_weight: float = 1.6

    scoring: Scoring = field(default_factory=Scoring)
    roster: Roster = field(default_factory=Roster)

    # --- Engine knobs -----------------------------------------------------
    # How much to trust our own projection-derived value vs. the market's
    # ADP-implied value. 1.0 = ignore the market, 0.0 = pure ADP board.
    market_weight: float = 0.35
    # Relative trust in each ADP source when forming a consensus ADP.
    ffc_adp_weight: float = 0.6
    sleeper_adp_weight: float = 0.4
    # Multiplies every player's ADP standard deviation in the opponent model.
    # >1 makes simulated drafts more chaotic (good for a casual home league).
    adp_noise_scale: float = 1.15
    # Extra per-team board idiosyncrasy: fraction of a team's ADP noise that is
    # fixed for the whole draft (a team that "likes" a player likes him all day).
    team_bias_share: float = 0.6

    def picks_for_slot(self, slot: int) -> List[int]:
        """Overall pick numbers (1-indexed) owned by a given snake draft slot."""
        if not 1 <= slot <= self.teams:
            raise ValueError(f"slot {slot} outside 1..{self.teams}")
        picks = []
        for rnd in range(1, self.rounds + 1):
            within = slot if rnd % 2 == 1 else self.teams - slot + 1
            picks.append((rnd - 1) * self.teams + within)
        return picks

    def slot_for_pick(self, overall_pick: int) -> int:
        """Which draft slot owns a given overall pick number."""
        rnd = (overall_pick - 1) // self.teams + 1
        within = (overall_pick - 1) % self.teams + 1
        return within if rnd % 2 == 1 else self.teams - within + 1

    @property
    def total_picks(self) -> int:
        return self.teams * self.rounds

    # --- Serialisation ----------------------------------------------------
    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def from_json(cls, path: Path) -> "LeagueConfig":
        raw = json.loads(Path(path).read_text())
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "LeagueConfig":
        raw = dict(raw)
        raw["scoring"] = Scoring(**raw.get("scoring", {}))
        raw["roster"] = Roster(**raw.get("roster", {}))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


# --- Presets --------------------------------------------------------------

def preset(name: str) -> LeagueConfig:
    """Named league presets. `frat` is this user's league."""
    if name == "frat":
        # 15 teams, 2 co-managers each, full PPR, standard 1QB lineup.
        return LeagueConfig(name="Frat League (15-team full PPR)")
    if name == "half_ppr":
        cfg = LeagueConfig(name="15-team half PPR")
        cfg.scoring.rec = 0.5
        return cfg
    if name == "standard":
        cfg = LeagueConfig(name="15-team non-PPR")
        cfg.scoring.rec = 0.0
        return cfg
    if name == "te_premium":
        cfg = LeagueConfig(name="15-team full PPR, TE premium")
        cfg.scoring.rec_bonus_te = 0.5
        return cfg
    if name == "superflex":
        cfg = LeagueConfig(name="15-team full PPR superflex")
        cfg.roster.flex = 0
        cfg.roster.superflex = 1
        return cfg
    raise KeyError(f"unknown preset {name!r}")
