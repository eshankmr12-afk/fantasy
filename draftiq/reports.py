"""Report generation: the pre-draft deliverables.

Because the draft slot is unknown until the day, the plan has to cover all of
them. This module produces:

* `DRAFT_PLAN.md`  - slot-by-slot strategy, survival odds, and the rules that
                     hold no matter where you end up picking.
* `BOARD.md`       - the tiered value board with notes.
* `cheatsheet.csv` - the same board, importable into a spreadsheet.
* `slot_XX.md`     - a round-by-round plan for one specific draft slot.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .board import Board, Player
from .config import LeagueConfig
from .recommend import Recommendation, Recommender
from .simulator import DraftState
from . import sources

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"

# Players the market barely drafts produce noisy edges; require real sample.
MIN_DRAFTS_FOR_EDGE = 150


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _provenance(config: LeagueConfig, data_dir: Path) -> List[str]:
    """Where the numbers came from, so the report can be audited later."""
    lines = [f"- Generated: {dt.datetime.now():%Y-%m-%d %H:%M}"]
    proj = data_dir / f"sleeper_projections_{config.season}.json"
    if proj.exists():
        lines.append(f"- Projections: Sleeper {config.season} season projections "
                     f"(cached {dt.datetime.fromtimestamp(proj.stat().st_mtime):%Y-%m-%d})")
    for path in sorted(data_dir.glob(f"ffc_adp_*_{config.season}.json")):
        meta = json.loads(path.read_text()).get("meta", {})
        lines.append(
            f"- ADP: Fantasy Football Calculator {meta.get('type')} - "
            f"{meta.get('total_drafts'):,} real drafts, "
            f"{meta.get('start_date')} to {meta.get('end_date')}"
        )
    overrides = data_dir / "news_overrides.json"
    if overrides.exists():
        raw = json.loads(overrides.read_text())
        lines.append(f"- News overrides: {len(raw.get('players', []))} manual "
                     f"adjustments, last updated {raw.get('_updated', 'unknown')}")
    return lines


# --- Board reports --------------------------------------------------------

def write_cheatsheet_csv(board: Board, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["overall_rank", "name", "pos", "pos_rank", "tier", "team", "bye",
                    "proj_points", "ppg", "availability", "adp", "adp_stdev",
                    "vor", "vor_model", "vor_market", "edge", "times_drafted", "notes"])
        for p in board:
            w.writerow([p.overall_rank, p.name, p.position, p.pos_rank, p.tier,
                        p.team, p.bye, round(p.points, 1), round(p.ppg, 2),
                        round(p.availability, 3), round(p.adp, 1),
                        round(p.adp_stdev, 1), round(p.vor, 1),
                        round(p.vor_model, 1), round(p.vor_market, 1),
                        round(p.edge, 1), p.times_drafted, " ".join(p.notes)])
    return path


def write_board_markdown(board: Board, config: LeagueConfig, path: Path,
                         depth: int = 200) -> Path:
    lines = [f"# Value board - {config.name}", ""]
    lines += [f"Full PPR" if config.scoring.rec == 1.0 else
              f"{config.scoring.rec} PPR",
              f"{config.teams} teams, {config.rounds} rounds, "
              f"{config.roster.starters} starters.", ""]
    lines.append("Replacement level (points a freely available starter provides):")
    lines.append("")
    lines.append("| " + " | ".join(board.replacement) + " |")
    lines.append("|" + "---|" * len(board.replacement))
    lines.append("| " + " | ".join(f"{v:.0f}" for v in board.replacement.values()) + " |")
    lines.append("")

    lines += ["## Overall", "",
              "| # | Player | Pos | Tier | Bye | Proj | ADP | VOR | Notes |",
              "|---|--------|-----|------|-----|------|-----|-----|-------|"]
    for p in board.top(depth):
        note = " ".join(p.notes)[:60]
        lines.append(
            f"| {p.overall_rank} | {p.name} | {p.position}{p.pos_rank} | "
            f"T{p.tier} | {p.bye or '-'} | {p.points:.0f} | {p.adp:.1f} | "
            f"{p.vor:.0f} | {note} |")

    lines += ["", "## By position (tiered)", ""]
    for pos in ("RB", "WR", "TE", "QB", "K", "DEF"):
        group = [p for p in board.by_position(pos)][:40]
        if not group:
            continue
        lines += [f"### {pos}", ""]
        current = None
        for p in sorted(group, key=lambda p: (p.tier, -p.vor)):
            if p.tier != current:
                current = p.tier
                lines.append(f"**Tier {p.tier}**")
            lines.append(f"- {p.name} ({p.team}, bye {p.bye or '?'}) - "
                         f"proj {p.points:.0f}, ADP {p.adp:.1f}, VOR {p.vor:.0f}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def market_inefficiencies(board: Board, config: LeagueConfig,
                          count: int = 15) -> Dict:
    """Where the model and the market disagree, split into two very different bets.

    Raw edge is dominated by a *position-level* disagreement: the projection
    source is systematically higher on one position than the market is. That is
    a single directional bet on positional value, not a list of individual
    sleepers, and presenting it as the latter would be misleading. So the edge
    is decomposed into the position's median (the systematic bet) and each
    player's deviation from it (the genuinely player-specific view).
    """
    pool = [p for p in board
            if p.times_drafted >= MIN_DRAFTS_FOR_EDGE
            and p.adp <= config.total_picks
            and p.position in ("QB", "RB", "WR", "TE")]

    bias: Dict[str, float] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        group = [p.edge for p in pool if p.position == pos]
        if group:
            bias[pos] = float(np.median(group))

    relative = [(p, p.edge - bias.get(p.position, 0.0)) for p in pool]
    return {
        "bias": bias,
        "pool_size": len(pool),
        "targets": sorted(relative, key=lambda t: -t[1])[:count],
        "fades": sorted(relative, key=lambda t: t[1])[:count],
    }


def tier_cliffs(board: Board, config: LeagueConfig) -> List[dict]:
    """Where each position falls off, and roughly when that happens in the draft."""
    out = []
    for pos in ("RB", "WR", "TE", "QB"):
        group = sorted(board.by_position(pos), key=lambda p: -p.vor)[:60]
        by_tier: Dict[int, List[Player]] = {}
        for p in group:
            by_tier.setdefault(p.tier, []).append(p)
        for tier in sorted(by_tier)[:6]:
            members = by_tier[tier]
            if not members:
                continue
            out.append({
                "position": pos,
                "tier": tier,
                "count": len(members),
                "last_adp": max(p.adp for p in members),
                "mean_vor": sum(p.vor for p in members) / len(members),
                "members": members,
            })
    return out


# --- Simulation reports ---------------------------------------------------

def _render_recommendation(rec: Recommendation, limit: int = 6) -> List[str]:
    lines = ["| Player | Pos | ADP | P(available) | Roster value | vs next | Why |",
             "|--------|-----|-----|--------------|--------------|---------|-----|"]
    for c in rec.candidates[:limit]:
        lines.append(
            f"| **{c.player.name}** | {c.player.position}{c.player.pos_rank} | "
            f"{c.player.adp:.1f} | {_pct(c.p_available)} | {c.value:.0f} "
            f"({c.p10:.0f}-{c.p90:.0f}) | {c.delta:+.1f} | {c.reason or '-'} |")
    return lines


def write_slot_report(board: Board, config: LeagueConfig, recommender: Recommender,
                      slot: int, path: Path, sims: int = 250,
                      watchlist: Optional[List[Player]] = None) -> dict:
    """Round-by-round plan and survival odds for one draft slot."""
    report = recommender.slot_report(slot, sims=sims)
    picks = report["picks"]

    lines = [f"# Slot {slot} plan - {config.name}", "",
             f"Your picks: {', '.join(str(p) for p in picks)}", "",
             f"Expected finished-roster value: **{report['value_mean']:.0f}** "
             f"(10th-90th percentile {report['value_p10']:.0f}-{report['value_p90']:.0f}) "
             f"over {report['sims']} simulated drafts.", "",
             "## Round 1: who to take", ""]
    lines += _render_recommendation(report["first_pick"])
    lines += ["", "Take the highest name on that list who is actually on the board.", ""]

    lines += ["## Round-by-round: what the simulations do", "",
              "| Round | Pick | Most likely choices |",
              "|-------|------|---------------------|"]
    for r in report["rounds"]:
        opts = ", ".join(f"{p.name} ({p.position}) {_pct(f)}" for p, f in r["options"])
        lines.append(f"| {r['round']} | {r['pick']} | {opts} |")

    if watchlist:
        lines += ["", "## Survival odds at your picks", "",
                  "Probability each player is still on the board when your pick arrives.", ""]
        header_picks = picks[:6]
        lines.append("| Player | Pos | ADP | " +
                     " | ".join(f"#{p}" for p in header_picks) + " |")
        lines.append("|--------|-----|-----|" + "----|" * len(header_picks))
        for pl in watchlist:
            idx = recommender.sim.index(pl)
            if idx is None:
                continue
            cells = []
            for pick in header_picks:
                surv = report["survival"].get(pick)
                cells.append(_pct(float(surv[idx])) if surv is not None else "-")
            lines.append(f"| {pl.name} | {pl.position} | {pl.adp:.1f} | "
                         + " | ".join(cells) + " |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return report


def write_draft_plan(board: Board, config: LeagueConfig, recommender: Recommender,
                     out_dir: Path = REPORT_DIR, sims: int = 250,
                     data_dir: Path = sources.DATA_DIR,
                     slots: Optional[List[int]] = None,
                     progress=None) -> Path:
    """The master report: every slot, plus slot-independent strategy."""
    out_dir.mkdir(parents=True, exist_ok=True)
    slots = slots or list(range(1, config.teams + 1))

    watchlist = [p for p in board.top(40)]
    slot_reports: Dict[int, dict] = {}
    for slot in slots:
        if progress:
            progress(slot)
        slot_reports[slot] = write_slot_report(
            board, config, recommender, slot,
            out_dir / f"slot_{slot:02d}.md", sims=sims, watchlist=watchlist[:24])

    edges = market_inefficiencies(board, config)
    cliffs = tier_cliffs(board, config)

    lines = [f"# Draft plan - {config.name}", ""]
    lines += _provenance(config, data_dir)
    lines += ["",
              f"**Format:** {config.teams} teams, {config.rounds} rounds, "
              f"{'full PPR' if config.scoring.rec == 1.0 else f'{config.scoring.rec} PPR'}, "
              f"lineup {config.roster.qb}QB/{config.roster.rb}RB/{config.roster.wr}WR/"
              f"{config.roster.te}TE/{config.roster.flex}FLEX/"
              f"{config.roster.k}K/{config.roster.dst}DST.", ""]

    lines += ["## How to use this", "",
              "1. Find your slot's section below (or open `slot_XX.md`).",
              "2. At each pick, take the highest player on that slot's list who is",
              "   still on the board. The list is already ordered by what it does to",
              "   your *finished roster*, not by raw ranking.",
              "3. During the draft run `python -m draftiq live --slot N` to update the",
              "   board as players come off it and get live recommendations.", ""]

    # -- Slot comparison
    lines += ["## Which slot is best", "",
              "Expected finished-roster value from each draft position, over "
              f"{sims} simulated drafts each. Differences of a few points are noise.", "",
              "| Slot | Picks 1-3 | Expected value | 10th-90th pct | Likely R1 pick |",
              "|------|-----------|----------------|---------------|----------------|"]
    ranked = sorted(slot_reports.items(), key=lambda kv: -kv[1]["value_mean"])
    for slot, rep in ranked:
        first = rep["first_pick"].candidates[0] if rep["first_pick"].candidates else None
        picks = ", ".join(str(p) for p in rep["picks"][:3])
        lines.append(
            f"| **{slot}** | {picks} | {rep['value_mean']:.0f} | "
            f"{rep['value_p10']:.0f}-{rep['value_p90']:.0f} | "
            f"{first.player.name if first else '-'} |")
    best, worst = ranked[0], ranked[-1]
    lines += ["",
              f"Spread between the best slot ({best[0]}) and the worst ({worst[0]}) is "
              f"{best[1]['value_mean'] - worst[1]['value_mean']:.0f} points of expected "
              f"roster value - about "
              f"{(best[1]['value_mean'] - worst[1]['value_mean']) / config.weeks:.1f} "
              f"points a week. Slot matters far less than the picks you make from it.", ""]

    # -- Slot-independent strategy
    lines += ["## Rules that hold at every slot", ""]

    # -- the position-level bet, stated separately and up front
    bias = edges["bias"]
    ordered_bias = sorted(bias.items(), key=lambda kv: -kv[1])
    lines += ["### The one big bet: positional value", "",
              "Before any individual player, the model disagrees with the market at the "
              "*position* level. Median edge over "
              f"{edges['pool_size']} well-sampled players:", "",
              "| Pos | Median edge vs market |", "|-----|----------------------|"]
    for pos, value in ordered_bias:
        lines.append(f"| {pos} | {value:+.0f} |")
    high, low = ordered_bias[0], ordered_bias[-1]
    lines += ["",
              f"Read that as one directional call, not many: the projections are "
              f"{high[1] - low[1]:.0f} points higher on **{high[0]}** than on "
              f"**{low[0]}** relative to where the market drafts them. In practice it "
              f"means letting the room pay up for {low[0]}s and taking {high[0]}s a "
              f"little earlier than ADP. If you think that call is wrong, lower "
              f"`market_weight` in `league.json` and the whole board moves with it.", ""]

    lines += ["### Player-specific targets", "",
              "Edge *after* removing the position-level bet above, so these are genuine "
              "views on individual players rather than the same positional call "
              f"repeated. Restricted to players drafted in at least "
              f"{MIN_DRAFTS_FOR_EDGE} of the sampled mock drafts.", "",
              "| Player | Pos | Team | ADP | Proj | Edge vs position | Note |",
              "|--------|-----|------|-----|------|------------------|------|"]
    for p, rel in edges["targets"]:
        lines.append(f"| {p.name} | {p.position}{p.pos_rank} | {p.team} | {p.adp:.1f} | "
                     f"{p.points:.0f} | {rel:+.0f} | {' '.join(p.notes)[:50]} |")

    lines += ["", "### Player-specific fades", "",
              "| Player | Pos | Team | ADP | Proj | Edge vs position | Note |",
              "|--------|-----|------|-----|------|------------------|------|"]
    for p, rel in edges["fades"]:
        lines.append(f"| {p.name} | {p.position}{p.pos_rank} | {p.team} | {p.adp:.1f} | "
                     f"{p.points:.0f} | {rel:+.0f} | {' '.join(p.notes)[:50]} |")

    lines += ["", "### Tier cliffs", "",
              "Where each position falls off. The ADP column is roughly the pick by "
              "which the tier is gone - if you are on the clock near it and want that "
              "tier, this is your last chance.", "",
              "| Pos | Tier | Players | Gone by ~pick | Avg VOR |",
              "|-----|------|---------|---------------|---------|"]
    for c in cliffs:
        names = ", ".join(p.name for p in c["members"][:5])
        lines.append(f"| {c['position']} | {c['tier']} | {c['count']} ({names}) | "
                     f"{c['last_adp']:.0f} | {c['mean_vor']:.0f} |")

    # -- Per-slot detail
    lines += ["", "## Slot-by-slot round 1", ""]
    for slot in slots:
        rep = slot_reports[slot]
        lines += [f"### Slot {slot} (picks {', '.join(str(p) for p in rep['picks'][:4])} ...)",
                  "", f"Expected roster value {rep['value_mean']:.0f}. "
                  f"Full plan: [`slot_{slot:02d}.md`](slot_{slot:02d}.md)", ""]
        lines += _render_recommendation(rep["first_pick"], limit=4)
        lines.append("")

    lines += ["## Method", "",
              "- **Projections** are scored from raw projected stat lines under this "
              "league's exact rules, so nothing is borrowed from a different format.",
              "- **Availability** is modelled separately from the season total. The feed "
              "already prices injuries into its totals, so the availability estimate is "
              "used to spread those points across the weeks a player is actually active "
              "- which is what makes bench depth worth anything.",
              "- **Replacement level** comes from real starter demand at "
              f"{config.teams} teams, with FLEX allocated to whichever position offers "
              "the best remaining player. That is why a TE1 and a WR3 are comparable here.",
              "- **Market blend** shrinks the model toward the value implied by ADP. A "
              "single projection source is fragile; thousands of real drafts are not.",
              "- **Tiers** break where the probability that the next player outscores "
              "the current one drops below 42% - a tier is a group you should be "
              "indifferent between.",
              "- **Opponent model**: each simulated team drafts off its own noisy board "
              "with persistent preferences, positional caps, and rising urgency to fill "
              "empty starting slots. That reproduces positional runs and late kicker "
              "and defense behaviour.",
              "- **Recommendations** force each candidate, play the draft out to the "
              "end many times, and score the finished roster with a week-by-week "
              "lineup simulation including byes and injuries. Values are conditional "
              "on the player actually reaching you.", "",
              "### Honest limitations", "",
              "- ADP comes from public mock drafts, which are more predictable than a "
              "15-team home league where people reach for their own players. The "
              "`adp_noise_scale` setting is raised above 1.0 to partly account for that.",
              "- Fantasy Football Calculator publishes 8/10/12/14-team ADP, not 15. Pick "
              "numbers are used directly, which is close but not exact.",
              "- Projections are one source's view. The market blend limits the damage "
              "from any single bad projection, but a genuinely wrong depth-chart read "
              "will still propagate.",
              "- Nothing here models in-season management, which decides more leagues "
              "than the draft does.",
              "- The positional bet above is the single largest assumption in the "
              "report. It comes from one projection source's view of how many points "
              "each position will score, and if that view is wrong, every "
              "recommendation shifts with it.", ""]

    path = out_dir / "DRAFT_PLAN.md"
    path.write_text("\n".join(lines) + "\n")
    return path
