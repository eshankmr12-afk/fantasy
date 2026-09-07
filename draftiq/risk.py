"""Availability and volatility modelling.

Projection feeds publish a *fully healthy* stat line - Sleeper's 2026 file
projects every single player for the full slate. Real drafts are won and lost on
games missed, so the engine explicitly separates:

* **availability** - expected share of the season a player is active for. This
  scales projected points and drives how often a bench player is actually needed.
* **volatility** - dispersion of season-long outcomes, which is what separates a
  safe floor from a league-winning ceiling.

Both are estimated from position, current injury designation, experience and
market uncertainty, then overridden by curated news where we have it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Share of a season an *undrafted-as-healthy* player at each position is
# typically active for, reflecting historical games-missed rates.
BASE_AVAILABILITY = {
    "QB": 0.88,
    "RB": 0.80,
    "WR": 0.85,
    "TE": 0.84,
    "K": 0.97,
    "DEF": 1.00,
}

# Multiplier applied on top of the base rate for a current designation.
INJURY_STATUS_FACTOR = {
    None: 1.00,
    "": 1.00,
    "Healthy": 1.00,
    "Probable": 0.99,
    "Questionable": 0.95,
    "Doubtful": 0.88,
    "Out": 0.90,
    "IR": 0.42,
    "Injured Reserve": 0.42,
    "PUP": 0.55,
    "NA": 0.60,
    "DNR": 0.50,
    "Sus": 0.75,
    "Suspended": 0.75,
    "COV": 0.95,
}

# Season-long coefficient of variation of fantasy points by position.
BASE_VOLATILITY = {
    "QB": 0.22,
    "RB": 0.33,
    "WR": 0.31,
    "TE": 0.34,
    "K": 0.20,
    "DEF": 0.26,
}


@dataclass
class RiskProfile:
    availability: float      # expected share of games active, 0..1
    volatility: float        # coefficient of variation of season points
    injury_status: Optional[str]
    note: str = ""

    @property
    def expected_games(self) -> float:
        return self.availability


def _experience_factor(position: str, years_exp: Optional[float]) -> float:
    """Age proxy. Running backs fall off a cliff; other positions barely move."""
    if years_exp is None:
        return 1.0
    yoe = float(years_exp)
    if position == "RB":
        if yoe >= 9:
            return 0.88
        if yoe >= 7:
            return 0.93
        if yoe == 0:  # rookie RBs are durable but usage-uncertain, not injury-prone
            return 1.01
        return 1.0
    if position in ("WR", "TE"):
        return 0.96 if yoe >= 11 else 1.0
    if position == "QB":
        return 0.95 if yoe >= 14 else 1.0
    return 1.0


def _uncertainty_factor(position: str, years_exp: Optional[float],
                        adp_stdev: Optional[float], adp: Optional[float]) -> float:
    """Extra volatility for players the market itself can't agree on.

    A wide ADP spread means real disagreement about role, and rookies carry
    genuine unknown-usage risk on top of that.
    """
    factor = 1.0
    if years_exp is not None and float(years_exp) == 0:
        factor *= 1.25
    if adp_stdev and adp:
        # Normalise dispersion against ADP: a stdev of 12 picks means something
        # very different at pick 5 than at pick 150.
        relative = float(adp_stdev) / max(float(adp), 8.0)
        factor *= 1.0 + min(relative, 0.9) * 0.45
    else:
        factor *= 1.15  # no market data at all is itself a risk signal
    return factor


def build_risk_profile(position: str,
                       injury_status: Optional[str] = None,
                       years_exp: Optional[float] = None,
                       adp: Optional[float] = None,
                       adp_stdev: Optional[float] = None,
                       override: Optional[dict] = None) -> RiskProfile:
    """Estimate availability and volatility for one player."""
    position = position.upper()
    base = BASE_AVAILABILITY.get(position, 0.85)
    status_factor = INJURY_STATUS_FACTOR.get(injury_status, 0.85)

    availability = base * status_factor * _experience_factor(position, years_exp)
    volatility = (BASE_VOLATILITY.get(position, 0.30)
                  * _uncertainty_factor(position, years_exp, adp_stdev, adp))

    note = ""
    if override:
        note = override.get("note", "")
        if "availability" in override:
            availability = float(override["availability"])
        elif "games_missed" in override:
            # Expressed against a 17-game regular season.
            availability = max(0.0, 1.0 - float(override["games_missed"]) / 17.0)
        if "volatility" in override:
            volatility = float(override["volatility"])
        elif "volatility_multiplier" in override:
            volatility *= float(override["volatility_multiplier"])

    return RiskProfile(
        availability=max(0.05, min(1.0, availability)),
        volatility=max(0.05, min(1.2, volatility)),
        injury_status=injury_status,
        note=note,
    )
