"""Turn raw projected stat lines into league-specific fantasy points."""

from __future__ import annotations

from typing import Dict, Optional

from .config import Scoring

# Sleeper's own point totals, by scoring format. Used for K and DEF, whose
# scoring depends on league-specific kicking-distance and points-allowed tiers
# that the raw feed doesn't expose in a reconstructable form.
_SLEEPER_PTS_KEYS = {
    1.0: "pts_ppr",
    0.5: "pts_half_ppr",
    0.0: "pts_std",
}


def _sleeper_fallback_key(scoring: Scoring) -> str:
    """Closest Sleeper pre-computed total for this league's reception value."""
    best = min(_SLEEPER_PTS_KEYS, key=lambda r: abs(r - scoring.rec))
    return _SLEEPER_PTS_KEYS[best]


def score_stat_line(stats: Dict[str, float], position: str,
                    scoring: Scoring) -> Optional[float]:
    """Projected season fantasy points for one player.

    Skill positions are scored from their component stats so any league's rules
    apply exactly. K and DEF fall back to Sleeper's own total, which is a much
    better estimate than reconstructing them from the partial fields available.
    Returns None when there is no usable projection.
    """
    position = position.upper()

    if position in ("K", "DEF"):
        val = stats.get(_sleeper_fallback_key(scoring))
        return float(val) if val is not None else None

    weights = scoring.as_stat_weights()
    if not any(stats.get(k) for k in weights):
        return None

    total = 0.0
    for stat, weight in weights.items():
        value = stats.get(stat)
        if value:
            total += float(value) * weight

    bonus = scoring.reception_bonus(position)
    if bonus:
        total += float(stats.get("rec", 0.0) or 0.0) * bonus

    return total


def games_projected(stats: Dict[str, float], default: float = 17.0) -> float:
    """Games the projection is built on, used to derive per-game rates."""
    gp = stats.get("gp")
    try:
        gp = float(gp)
    except (TypeError, ValueError):
        return default
    return gp if gp > 0 else default
