"""Build the valuation board: the single source of truth for player value.

Pipeline
--------
1. Join Sleeper projections to Fantasy Football Calculator ADP.
2. Score every stat line under this league's rules.
3. Estimate expected active weeks, and spread the season total across them to
   get a per-game rate (the feed's totals already price injury risk in, so the
   discount is applied to scheduling, not to the total).
4. Form a consensus ADP from two independent markets.
5. Compute replacement level from actual starter demand, hence VOR.
6. Shrink our VOR toward the market's ADP-implied VOR.
7. Cut tiers where the *probability* one player outscores the next is low.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .config import FLEX_ELIGIBLE, LeagueConfig
from .risk import RiskProfile, build_risk_profile
from .scoring import score_stat_line
from . import sources

# FFC labels kickers PK; everything else already matches Sleeper.
_FFC_POSITION_MAP = {"PK": "K", "DST": "DEF"}

# Players this far past the last pick are treated as undrafted noise.
_UNDRAFTED_PAD = 45

# Tiering asks "are these two players interchangeable?", which is a question
# about our uncertainty in each player's *true mean*, not about the week-to-week
# spread of outcomes. Season-outcome variance is far too wide for that question,
# so it is shrunk to a standard-error-like scale before tiers are cut.
_TIER_SHRINK = 0.45

# Floor on the share of the season used to convert a season total into a
# per-game rate, so a heavily-injured player doesn't get an implausible ppg.
_MIN_ACTIVE_SHARE = 0.40


@dataclass
class Player:
    name: str
    position: str
    team: str
    bye: int = 0

    # Projections -----------------------------------------------------------
    # Expected season fantasy points. The source feed already prices in role and
    # injury expectations - a back on IR is projected far below his healthy rate
    # - so this is an expectation, not a fully-healthy ceiling, and availability
    # must NOT be applied to it a second time.
    points: float = 0.0
    # Points per *active* game. Derived so that ppg * expected active weeks
    # reproduces `points`, which keeps the season total and the week-by-week
    # lineup simulation consistent with each other.
    ppg: float = 0.0
    risk: Optional[RiskProfile] = None

    # Market ----------------------------------------------------------------
    adp: float = 999.0            # consensus overall pick number
    adp_stdev: float = 20.0
    adp_ffc: Optional[float] = None
    adp_sleeper: Optional[float] = None
    times_drafted: int = 0

    # Valuation -------------------------------------------------------------
    vor_model: float = 0.0        # our projection vs. replacement
    vor_market: float = 0.0       # ADP-implied value at that draft slot
    vor: float = 0.0              # blended, the number the engine optimises
    tier: int = 0
    pos_rank: int = 0
    overall_rank: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return sources.join_key(self.name, self.position)

    @property
    def availability(self) -> float:
        return self.risk.availability if self.risk else 1.0

    @property
    def volatility(self) -> float:
        return self.risk.volatility if self.risk else 0.3

    @property
    def points_stdev(self) -> float:
        return self.points * self.volatility

    @property
    def edge(self) -> float:
        """Model value minus market value. Positive = the board is sleeping on him."""
        return self.vor_model - self.vor_market

    @property
    def label(self) -> str:
        return f"{self.name} ({self.position}-{self.team})"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Player {self.label} adp={self.adp:.1f} vor={self.vor:.1f}>"


# --- Statistical helpers --------------------------------------------------

def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def isotonic_decreasing(xs: Sequence[float]) -> List[float]:
    """Pool-adjacent-violators fit of a non-increasing sequence.

    Used to turn noisy (ADP, value) pairs into a monotone "what is a pick at
    this slot worth" curve without assuming a functional form.
    """
    values = [float(x) for x in xs]
    weights = [1.0] * len(values)
    # Stack of (value, weight, count) blocks that are already non-increasing.
    stack: List[List[float]] = []
    for v, w in zip(values, weights):
        block = [v, w, 1.0]
        while stack and stack[-1][0] < block[0]:
            prev = stack.pop()
            total_w = prev[1] + block[1]
            block = [(prev[0] * prev[1] + block[0] * block[1]) / total_w,
                     total_w, prev[2] + block[2]]
        stack.append(block)
    out: List[float] = []
    for value, _w, count in stack:
        out.extend([value] * int(count))
    return out


def _rolling_median(xs: Sequence[float], window: int) -> List[float]:
    n = len(xs)
    half = max(1, window // 2)
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        chunk = sorted(xs[lo:hi])
        out.append(chunk[len(chunk) // 2])
    return out


# --- Board construction ---------------------------------------------------

class Board:
    """The full valuation board for a league."""

    def __init__(self, players: List[Player], config: LeagueConfig,
                 replacement: Dict[str, float]):
        self.players = players
        self.config = config
        self.replacement = replacement
        self._by_key = {p.key: p for p in players}

    # Lookups --------------------------------------------------------------
    def get(self, name: str, position: Optional[str] = None) -> Optional[Player]:
        """Find a player by (possibly sloppy) name, optionally constrained by position."""
        if position:
            return self._by_key.get(sources.join_key(name, position))
        norm = sources.normalize_name(name)
        hits = [p for p in self.players if sources.normalize_name(p.name) == norm]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return max(hits, key=lambda p: p.vor)
        return None

    def search(self, text: str, limit: int = 8) -> List[Player]:
        """Substring search, ranked by value, for the interactive draft board."""
        norm = sources.normalize_name(text)
        if not norm:
            return []
        hits = [p for p in self.players if norm in sources.normalize_name(p.name)]
        hits.sort(key=lambda p: -p.vor)
        return hits[:limit]

    def by_position(self, position: str) -> List[Player]:
        return [p for p in self.players if p.position == position]

    def top(self, n: int = 50) -> List[Player]:
        return self.players[:n]

    def __len__(self) -> int:
        return len(self.players)

    def __iter__(self):
        return iter(self.players)


def _extract_ffc(config: LeagueConfig, data_dir: Path) -> Dict[str, dict]:
    """FFC ADP rows keyed for joining, choosing the format closest to our scoring."""
    fmt = {1.0: "ppr", 0.5: "half-ppr", 0.0: "standard"}[
        min((1.0, 0.5, 0.0), key=lambda r: abs(r - config.scoring.rec))
    ]
    payload = sources.fetch_ffc_adp(config.season, fmt=fmt, cache_dir=data_dir)
    out: Dict[str, dict] = {}
    for row in payload["players"]:
        pos = _FFC_POSITION_MAP.get(row["position"], row["position"])
        row = dict(row, position=pos)
        if pos == "DEF":
            # Team defenses join on team code, not on inconsistent display names.
            out[f"DEF|{sources.normalize_team(row.get('team'))}"] = row
        else:
            out[sources.join_key(row["name"], pos)] = row
    return out


def _team_byes(ffc_rows: Dict[str, dict]) -> Dict[str, int]:
    byes: Dict[str, int] = {}
    for row in ffc_rows.values():
        team = sources.normalize_team(row.get("team"))
        if row.get("bye"):
            byes.setdefault(team, int(row["bye"]))
    return byes


def _consensus_adp(config: LeagueConfig, ffc: Optional[dict],
                   sleeper_adp: Optional[float]) -> tuple[float, float, int]:
    """Blend two independent ADP markets into a mean and a dispersion.

    Disagreement *between* the sources is added to the within-source spread:
    if two markets place a player 20 picks apart, his true draft position is
    genuinely less predictable than either source alone suggests.
    """
    undrafted = config.total_picks + _UNDRAFTED_PAD
    entries: List[tuple[float, float]] = []  # (adp, weight)
    stdevs: List[tuple[float, float]] = []
    times = 0

    if ffc and ffc.get("adp"):
        w = config.ffc_adp_weight
        entries.append((float(ffc["adp"]), w))
        stdevs.append((float(ffc.get("stdev") or 0.0), w))
        times = int(ffc.get("times_drafted") or 0)
    if sleeper_adp is not None and 0 < sleeper_adp < 900:
        entries.append((float(sleeper_adp), config.sleeper_adp_weight))

    if not entries:
        return undrafted, 45.0, 0

    total_w = sum(w for _, w in entries)
    adp = sum(v * w for v, w in entries) / total_w

    within = (sum(s * w for s, w in stdevs) / sum(w for _, w in stdevs)) if stdevs else 0.0
    if not within:
        # No published dispersion: spread grows with ADP, roughly 22% of it.
        within = max(4.0, 0.22 * adp)
    between = abs(entries[0][0] - entries[1][0]) / 2.0 if len(entries) > 1 else 0.0
    stdev = math.sqrt(within ** 2 + between ** 2)

    return adp, max(1.0, stdev), times


def compute_replacement_levels(players: List[Player],
                               config: LeagueConfig) -> Dict[str, float]:
    """Replacement-level points per position, from real starter demand.

    Dedicated slots are counted directly; FLEX slots are allocated greedily to
    whichever position offers the best remaining player, which is how a league
    actually fills them.
    """
    roster = config.roster
    demand = {pos: config.teams * n for pos, n in roster.required_slots().items()}

    pools = {pos: sorted((p.points for p in players if p.position == pos),
                         reverse=True)
             for pos in demand}

    def next_best(pos: str) -> float:
        idx = demand[pos]
        pool = pools[pos]
        return pool[idx] if idx < len(pool) else 0.0

    # Flex (and superflex) demand, awarded one seat at a time to the position
    # whose next-best available player is strongest.
    for _ in range(config.teams * roster.flex):
        best = max(FLEX_ELIGIBLE, key=next_best)
        demand[best] += 1
    for _ in range(config.teams * roster.superflex):
        best = max(tuple(FLEX_ELIGIBLE) + ("QB",), key=next_best)
        demand[best] += 1

    replacement: Dict[str, float] = {}
    for pos, need in demand.items():
        pool = pools[pos]
        if not pool:
            replacement[pos] = 0.0
            continue
        # The first player who is *not* a league-wide starter: the best player
        # you could reasonably expect to find on waivers.
        idx = min(need, len(pool) - 1)
        replacement[pos] = pool[idx]
    return replacement


def _apply_market_blend(players: List[Player], config: LeagueConfig) -> None:
    """Shrink model VOR toward the value the market implies for that draft slot.

    Fits a monotone non-increasing curve of VOR against ADP over players with
    real draft data, then reads each player's market value off that curve. A
    player our model loves but the market buries gets pulled down, and vice
    versa - which is the correct treatment of a single-source projection.
    """
    drafted = [p for p in players if p.times_drafted >= 15 and p.adp < config.total_picks]
    drafted.sort(key=lambda p: p.adp)

    if len(drafted) < 25:
        for p in players:
            p.vor_market = p.vor_model
            p.vor = p.vor_model
        return

    smoothed = _rolling_median([p.vor_model for p in drafted], window=15)
    curve = isotonic_decreasing(smoothed)
    xs = [p.adp for p in drafted]

    def market_value(adp: float) -> float:
        if adp <= xs[0]:
            return curve[0]
        if adp >= xs[-1]:
            # Keep extrapolating downward past the last observed pick. Clamping
            # here would rate an undrafted player above the last drafted one.
            return curve[-1] - 0.05 * (adp - xs[-1])
        lo, hi = 0, len(xs) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if xs[mid] <= adp:
                lo = mid
            else:
                hi = mid
        span = xs[hi] - xs[lo]
        t = 0.0 if span <= 0 else (adp - xs[lo]) / span
        return curve[lo] + t * (curve[hi] - curve[lo])

    w = config.market_weight
    for p in players:
        p.vor_market = market_value(p.adp)
        p.vor = (1.0 - w) * p.vor_model + w * p.vor_market


def _assign_tiers(players: List[Player], break_prob: float = 0.42,
                  max_tier_size: int = 8) -> None:
    """Cut positional tiers where consecutive players stop being interchangeable.

    Rather than eyeballing gaps, a tier break is placed where the probability
    that the next player outscores the current one drops below `break_prob` -
    so a tier is literally "a group of players you should be indifferent between".
    """
    by_pos: Dict[str, List[Player]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)

    for pos, group in by_pos.items():
        group.sort(key=lambda p: -p.vor)
        tier = 1
        size = 0
        for i, p in enumerate(group):
            if i > 0:
                prev = group[i - 1]
                spread = math.hypot(prev.points_stdev, p.points_stdev) * _TIER_SHRINK
                if spread <= 0:
                    prob = 0.0 if p.points < prev.points else 0.5
                else:
                    prob = _norm_cdf((p.points - prev.points) / spread)
                if prob < break_prob or size >= max_tier_size:
                    tier += 1
                    size = 0
            p.tier = tier
            p.pos_rank = i + 1
            size += 1


def build_board(config: LeagueConfig, data_dir: Path = sources.DATA_DIR) -> Board:
    """Assemble the complete valuation board for a league."""
    projections = sources.fetch_sleeper_projections(config.season, data_dir)
    ffc_rows = _extract_ffc(config, data_dir)
    overrides = sources.load_news_overrides(data_dir)
    byes = _team_byes(ffc_rows)

    players: List[Player] = []
    seen: set[str] = set()

    for row in projections:
        meta = row.get("player") or {}
        stats = row.get("stats") or {}
        position = (meta.get("position") or "").upper()
        if position not in ("QB", "RB", "WR", "TE", "K", "DEF"):
            continue

        name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        if not name:
            continue
        team = sources.normalize_team(meta.get("team"))

        projected = score_stat_line(stats, position, config.scoring)
        if projected is None or projected <= 0:
            continue

        key = sources.join_key(name, position)
        if key in seen:
            continue
        seen.add(key)

        ffc = ffc_rows.get(f"DEF|{team}") if position == "DEF" else ffc_rows.get(key)
        sleeper_adp = stats.get({1.0: "adp_ppr", 0.5: "adp_half_ppr", 0.0: "adp_std"}[
            min((1.0, 0.5, 0.0), key=lambda r: abs(r - config.scoring.rec))])
        adp, adp_stdev, times = _consensus_adp(config, ffc, sleeper_adp)

        override = overrides.get(sources.normalize_name(name))
        risk = build_risk_profile(
            position=position,
            injury_status=meta.get("injury_status"),
            years_exp=meta.get("years_exp"),
            adp=adp if adp < config.total_picks else None,
            adp_stdev=ffc.get("stdev") if ffc else None,
            override=override,
        )

        if override and "points_multiplier" in override:
            projected *= float(override["points_multiplier"])

        # Spread the season total over the weeks he is actually expected to be
        # active. The floor stops a player with a tiny availability estimate
        # from being handed an absurd per-game rate.
        active_weeks = config.weeks * max(risk.availability, _MIN_ACTIVE_SHARE)
        player = Player(
            name=name,
            position=position,
            team=team,
            bye=int(ffc["bye"]) if ffc and ffc.get("bye") else byes.get(team, 0),
            points=projected,
            ppg=projected / active_weeks,
            risk=risk,
            adp=adp,
            adp_stdev=adp_stdev,
            adp_ffc=float(ffc["adp"]) if ffc and ffc.get("adp") else None,
            adp_sleeper=float(sleeper_adp) if sleeper_adp and sleeper_adp < 900 else None,
            times_drafted=times,
        )
        if risk.note:
            player.notes.append(risk.note)
        if override and override.get("tag"):
            player.notes.append(f"[{override['tag']}]")
        players.append(player)

    replacement = compute_replacement_levels(players, config)
    for p in players:
        p.vor_model = p.points - replacement.get(p.position, 0.0)

    _apply_market_blend(players, config)
    _assign_tiers(players)

    players.sort(key=lambda p: -p.vor)
    for i, p in enumerate(players, start=1):
        p.overall_rank = i

    return Board(players, config, replacement)
