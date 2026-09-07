"""Fetch and cache the public data feeds the engine runs on.

Two independent public sources are used:

* **Sleeper season projections** - a full projected stat line per player for the
  season, plus injury status and Sleeper's own ADP. This is what we score.
* **Fantasy Football Calculator ADP** - average draft position aggregated from
  thousands of real mock drafts, with a standard deviation, high/low and bye
  week. This is the market signal and the basis of the opponent model.

Both are cached to `data/` so a draft-day run never depends on the network.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SLEEPER_PROJECTIONS = (
    "https://api.sleeper.com/projections/nfl/{season}"
    "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
    "&position[]=TE&position[]=K&position[]=DEF&order_by=pts_ppr"
)
FFC_ADP = (
    "https://fantasyfootballcalculator.com/api/v1/adp/{fmt}"
    "?teams={teams}&year={season}&position=all"
)

USER_AGENT = "draftiq/1.0 (fantasy draft research)"


def _get_json(url: str, retries: int = 4, timeout: int = 60) -> dict | list:
    """GET JSON with exponential backoff on transient network failures."""
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"failed to fetch {url}: {last}")


# --- Name normalisation ---------------------------------------------------

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PUNCT = re.compile(r"[^a-z ]")
_TEAM_ALIASES = {
    "JAC": "JAX", "WSH": "WAS", "LA": "LAR", "OAK": "LV", "SD": "LAC",
    "STL": "LAR", "ARZ": "ARI", "BLT": "BAL", "HST": "HOU", "CLV": "CLE",
}


def normalize_name(name: str) -> str:
    """Canonical player-name key for joining across sources.

    Lowercases, strips punctuation and generational suffixes, so that
    "Ja'Marr Chase", "JaMarr Chase" and "Marvin Harrison Jr." all join cleanly.
    """
    s = _PUNCT.sub("", name.lower().replace(".", "").replace("'", "").replace("-", " "))
    parts = [p for p in s.split() if p and p not in _SUFFIXES]
    return " ".join(parts)


def normalize_team(team: Optional[str]) -> str:
    if not team:
        return "FA"
    t = team.upper().strip()
    return _TEAM_ALIASES.get(t, t)


def join_key(name: str, position: str) -> str:
    """Join key including position, so a WR and a DEF can't collide."""
    return f"{normalize_name(name)}|{position.upper()}"


# --- Fetchers -------------------------------------------------------------

def fetch_sleeper_projections(season: int, cache_dir: Path = DATA_DIR,
                              refresh: bool = False) -> List[dict]:
    """Season-long projected stat lines for every offensive player + K/DEF."""
    path = cache_dir / f"sleeper_projections_{season}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    data = _get_json(SLEEPER_PROJECTIONS.format(season=season))
    if not isinstance(data, list):
        raise RuntimeError("unexpected Sleeper payload shape")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def fetch_ffc_adp(season: int, fmt: str = "ppr", teams: int = 14,
                  cache_dir: Path = DATA_DIR, refresh: bool = False) -> dict:
    """Real-mock-draft ADP with dispersion statistics.

    FFC exposes team counts of 8/10/12/14; 14 is the closest available to a
    15-team league. ADP is reported as an overall pick number, which is the
    scale the engine works in, so the small team-count mismatch mostly affects
    the cosmetic ``round.pick`` formatting rather than the values we consume.
    """
    path = cache_dir / f"ffc_adp_{fmt}_{teams}_{season}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    data = _get_json(FFC_ADP.format(fmt=fmt, teams=teams, season=season))
    if not isinstance(data, dict) or "players" not in data:
        raise RuntimeError("unexpected FFC payload shape")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def load_news_overrides(cache_dir: Path = DATA_DIR) -> Dict[str, dict]:
    """Hand-curated, news-driven adjustments keyed by normalised name.

    This is the hook for information the statistical feeds lag on: a beat
    reporter's snap-share note, a suspension, a backfield timeshare. See
    `data/news_overrides.json` for the schema and current entries.
    """
    path = cache_dir / "news_overrides.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    entries = raw.get("players", raw) if isinstance(raw, dict) else raw
    out: Dict[str, dict] = {}
    for item in entries:
        out[normalize_name(item["name"])] = item
    return out


def refresh_all(season: int, cache_dir: Path = DATA_DIR) -> dict:
    """Pull every feed fresh. Returns a summary for the CLI to print."""
    proj = fetch_sleeper_projections(season, cache_dir, refresh=True)
    summary = {"sleeper_players": len(proj)}
    for fmt in ("ppr", "half-ppr", "standard"):
        adp = fetch_ffc_adp(season, fmt=fmt, cache_dir=cache_dir, refresh=True)
        summary[f"ffc_{fmt}"] = {
            "players": len(adp["players"]),
            "drafts": adp.get("meta", {}).get("total_drafts"),
            "window": f"{adp.get('meta', {}).get('start_date')} to "
                      f"{adp.get('meta', {}).get('end_date')}",
        }
    return summary
