"""Command line interface.

    python -m draftiq fetch                 refresh the public data feeds
    python -m draftiq board                 print the value board
    python -m draftiq plan                  generate the full pre-draft report set
    python -m draftiq slot --slot 7         deep-dive one draft position
    python -m draftiq odds --slot 7         survival odds for your picks
    python -m draftiq live --slot 7         interactive draft-day assistant
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

from .board import Board, build_board
from .config import LeagueConfig, preset
from .recommend import Recommender
from .reports import (REPORT_DIR, write_board_markdown, write_cheatsheet_csv,
                      write_draft_plan, write_slot_report)
from .simulator import DraftSimulator, DraftState
from . import sources

CONFIG_PATH = Path(__file__).resolve().parent.parent / "league.json"


def load_config(path: Optional[str], preset_name: str) -> LeagueConfig:
    target = Path(path) if path else CONFIG_PATH
    if target.exists():
        return LeagueConfig.from_json(target)
    return preset(preset_name)


def _setup(args) -> tuple[LeagueConfig, Board, Recommender]:
    config = load_config(args.config, args.preset)
    board = build_board(config, Path(args.data_dir))
    recommender = Recommender(board, config, seed=args.seed)
    return config, board, recommender


# --- commands -------------------------------------------------------------

def cmd_fetch(args) -> int:
    config = load_config(args.config, args.preset)
    summary = sources.refresh_all(config.season, Path(args.data_dir))
    print(f"Sleeper projections: {summary['sleeper_players']} players")
    for key, value in summary.items():
        if key.startswith("ffc_"):
            print(f"{key}: {value['players']} players from "
                  f"{value['drafts']:,} drafts ({value['window']})")
    return 0


def cmd_board(args) -> int:
    config, board, _ = _setup(args)
    print(f"{config.name}: {len(board)} players")
    print("Replacement level: " +
          "  ".join(f"{k} {v:.0f}" for k, v in board.replacement.items()))
    print()
    players = board.by_position(args.position) if args.position else board.top(args.limit)
    header = (f"{'#':>4} {'player':24s} {'pos':4s} {'tm':4s} {'bye':>3} "
              f"{'proj':>6} {'ppg':>5} {'av':>5} {'adp':>6} {'VOR':>6} {'T':>3}")
    print(header)
    print("-" * len(header))
    for p in players[:args.limit]:
        print(f"{p.overall_rank:4d} {p.name[:24]:24s} {p.position + str(p.pos_rank):4s} "
              f"{p.team:4s} {p.bye or 0:3d} {p.points:6.0f} {p.ppg:5.1f} "
              f"{p.availability:5.2f} {p.adp:6.1f} {p.vor:6.0f} {p.tier:3d}")

    if args.export:
        out = Path(args.out)
        csv_path = write_cheatsheet_csv(board, out / "cheatsheet.csv")
        md_path = write_board_markdown(board, config, out / "BOARD.md")
        print(f"\nWrote {csv_path} and {md_path}")
    return 0


def cmd_plan(args) -> int:
    config, board, recommender = _setup(args)
    out = Path(args.out)
    slots = [args.slot] if args.slot else None

    def progress(slot: int) -> None:
        print(f"  simulating slot {slot}/{config.teams} ...", flush=True)

    print(f"Generating draft plan ({args.sims} sims per slot). This takes a minute.")
    path = write_draft_plan(board, config, recommender, out_dir=out, sims=args.sims,
                            data_dir=Path(args.data_dir), slots=slots,
                            progress=progress)
    write_cheatsheet_csv(board, out / "cheatsheet.csv")
    write_board_markdown(board, config, out / "BOARD.md")
    print(f"\nWrote {path}")
    print(f"Wrote {out / 'BOARD.md'}, {out / 'cheatsheet.csv'}, "
          f"and per-slot plans in {out}/")
    return 0


def cmd_slot(args) -> int:
    config, board, recommender = _setup(args)
    out = Path(args.out) / f"slot_{args.slot:02d}.md"
    report = write_slot_report(board, config, recommender, args.slot, out,
                               sims=args.sims, watchlist=board.top(24))
    print(f"Slot {args.slot}: picks {report['picks']}")
    print(f"Expected roster value {report['value_mean']:.0f} "
          f"({report['value_p10']:.0f}-{report['value_p90']:.0f})")
    print("\nRound 1 priority:")
    for c in report["first_pick"].candidates[:6]:
        print(f"  {c.value:7.0f}  P(avail) {c.p_available * 100:3.0f}%  "
              f"{c.player.label:30s} {c.reason}")
    print(f"\nWrote {out}")
    return 0


def cmd_odds(args) -> int:
    config, board, recommender = _setup(args)
    state = DraftState(config)
    result = recommender.sim.simulate(state, args.slot, sims=args.sims, evaluate=False)
    picks = result.my_picks[:args.rounds]
    print(f"Slot {args.slot}: P(player still available) at your picks\n")
    print(f"{'player':26s} {'pos':4s} {'adp':>6} " +
          " ".join(f"{'#' + str(p):>6}" for p in picks))
    for p in board.top(args.limit):
        idx = recommender.sim.index(p)
        if idx is None:
            continue
        cells = " ".join(f"{result.survival[k][idx] * 100:5.0f}%" for k in picks)
        print(f"{p.name[:26]:26s} {p.position + str(p.pos_rank):4s} {p.adp:6.1f} {cells}")
    return 0


def _apply_taken(board: Board, sim: DraftSimulator, config: LeagueConfig,
                 state: DraftState, names: List[str], my_slot: int,
                 mine: List[str]) -> List[str]:
    """Replay a list of drafted names into a draft state.

    Picks are attributed by snake order; `mine` force-assigns players to us for
    when the transcript and the real draft have drifted. Names that cannot be
    resolved are returned so they can be reported loudly - a missed pick leaves
    a drafted player on the board and can poison the recommendation.
    """
    problems: List[str] = []
    forced = set()
    for raw in mine:
        player, alts = board.resolve(raw)
        if player is None:
            problems.append(f"{raw!r} (yours): " + (
                "ambiguous - " + ", ".join(a.label for a in alts) if alts
                else "no match"))
            continue
        forced.add(player.key)

    for raw in names:
        player, alts = board.resolve(raw)
        if player is None:
            problems.append(f"{raw!r}: " + (
                "ambiguous - " + ", ".join(a.label for a in alts) if alts
                else "no match"))
            continue
        idx = sim.index(player)
        if idx is None or idx in state.taken:
            problems.append(f"{raw!r}: already recorded, skipped")
            continue
        slot = my_slot if player.key in forced else config.slot_for_pick(state.next_pick)
        state.record(idx, slot)
    return problems


def cmd_advise(args) -> int:
    """One-shot advice from a full list of who is off the board."""
    config, board, recommender = _setup(args)
    sim = recommender.sim
    state = DraftState(config)

    taken = [t.strip() for t in (args.taken or "").split(",") if t.strip()]
    mine = [t.strip() for t in (args.mine or "").split(",") if t.strip()]
    if args.taken_file:
        taken += [ln.strip() for ln in Path(args.taken_file).read_text().splitlines()
                  if ln.strip() and not ln.startswith("#")]

    problems = _apply_taken(board, sim, config, state, taken, args.slot, mine)
    if problems:
        print("!! UNRESOLVED - fix these, the board may be wrong:")
        for p in problems:
            print(f"   {p}")
        print()

    roster = [sim.player(i) for i in state.roster_of(args.slot)]
    counts: dict = {}
    for p in roster:
        counts[p.position] = counts.get(p.position, 0) + 1
    need = {pos: n - counts.get(pos, 0)
            for pos, n in config.roster.required_slots().items()
            if n - counts.get(pos, 0) > 0}

    print(f"{len(state.order)} players off the board. "
          f"Pick {state.next_pick} (round {state.current_round}) is "
          f"{'YOURS' if config.slot_for_pick(state.next_pick) == args.slot else 'slot ' + str(config.slot_for_pick(state.next_pick))}.")
    print(f"\nYour roster ({len(roster)}):")
    for p in sorted(roster, key=lambda p: (p.position, -p.vor)):
        print(f"   {p.position}{p.pos_rank:<4} {p.name:24s} bye {p.bye or '?':<3} "
              f"proj {p.points:.0f}")
    if roster:
        value = recommender.evaluator.evaluate(roster)
        print(f"   projected startable points: {value.mean:.0f} "
              f"({value.floor:.0f}-{value.ceiling:.0f})")
    print(f"   still need: {need or 'starters full'}")

    try:
        rec = recommender.recommend(state, args.slot, sims=args.sims, width=args.width)
    except ValueError as exc:
        print(f"\n{exc}")
        return 1

    turn = "  (back-to-back picks - you can take two)" if rec.back_to_back else ""
    print(f"\nRECOMMENDATION for pick {rec.pick} (round {rec.round}){turn}")
    for i, c in enumerate(rec.candidates[:args.top], 1):
        flag = "=>" if i == 1 else "  "
        print(f" {flag} {c.value:7.0f} ({c.delta:+6.1f})  {c.player.label:30s} "
              f"T{c.player.tier} ADP {c.player.adp:5.1f}")
        if c.reason:
            print(f"           {c.reason}")
    return 0


def cmd_live(args) -> int:
    """Interactive draft-day board. Mark picks as they happen, get advice."""
    config, board, recommender = _setup(args)
    sim = recommender.sim
    state = DraftState(config)
    my_slot = args.slot

    def show_help() -> None:
        print("""
Type every pick in draft order as it happens. The snake order is known, so
each name is attributed to whichever team is on the clock - including you.

Commands:
  <name>            record the next pick (auto-attributed by draft order)
  me <name>         force the pick onto YOUR roster (use if the order drifts)
  status            whose pick is on the clock
  best              recommendation for your next pick
  odds [n]          survival odds for the top n available players
  roster            your roster so far
  board [pos] [n]   best available, optionally by position
  undo              undo the last pick
  slot N            change your draft slot
  quit
""")

    def on_the_clock() -> int:
        return config.slot_for_pick(state.next_pick)

    def resolve(text: str):
        hits = board.search(text)
        available = [p for p in hits if sim.index(p) not in state.taken]
        if not available:
            print(f"  no available player matching {text!r}")
            return None
        if len(available) > 1 and sources.normalize_name(available[0].name) != \
                sources.normalize_name(text):
            print("  ambiguous - did you mean:")
            for p in available[:5]:
                print(f"    {p.label} (ADP {p.adp:.1f})")
            return None
        return available[0]

    def do_best() -> None:
        try:
            rec = recommender.recommend(state, my_slot, sims=args.sims, width=args.width)
        except ValueError as exc:
            print(f"  {exc}")
            return
        turn = " (back-to-back picks)" if rec.back_to_back else ""
        print(f"\n  Pick {rec.pick} (round {rec.round}), slot {my_slot}{turn}")
        for i, c in enumerate(rec.candidates[:6], 1):
            flag = "*" if i == 1 else " "
            print(f"  {flag} {c.value:7.0f} ({c.delta:+5.1f})  {c.player.label:28s} "
                  f"T{c.player.tier} ADP {c.player.adp:5.1f}  {c.reason}")
        print()

    print(f"{config.name} - live draft, slot {my_slot}")
    print(f"Your picks: {config.picks_for_slot(my_slot)}")
    show_help()
    do_best()

    while True:
        try:
            raw = input(f"[pick {state.next_pick}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        cmd, _, rest = raw.partition(" ")
        cmd, rest = cmd.lower(), rest.strip()

        if cmd in ("quit", "exit", "q"):
            return 0
        if cmd in ("help", "?"):
            show_help()
        elif cmd == "best":
            do_best()
        elif cmd == "roster":
            mine = [sim.player(i) for i in state.roster_of(my_slot)]
            for p in sorted(mine, key=lambda p: (p.position, -p.vor)):
                print(f"  {p.position}{p.pos_rank:<3} {p.name:24s} bye {p.bye or '?':<3} "
                      f"proj {p.points:.0f}")
            if mine:
                value = recommender.evaluator.evaluate(mine)
                print(f"  projected startable points: {value.mean:.0f} "
                      f"({value.floor:.0f}-{value.ceiling:.0f})")
        elif cmd == "board":
            parts = rest.split()
            pos = parts[0].upper() if parts and parts[0].upper() in (
                "QB", "RB", "WR", "TE", "K", "DEF") else None
            n = int(parts[-1]) if parts and parts[-1].isdigit() else 12
            pool = board.by_position(pos) if pos else list(board)
            shown = 0
            for p in pool:
                if sim.index(p) in state.taken:
                    continue
                print(f"  {p.position}{p.pos_rank:<3} T{p.tier} {p.name:24s} "
                      f"ADP {p.adp:6.1f} VOR {p.vor:5.0f}")
                shown += 1
                if shown >= n:
                    break
        elif cmd == "odds":
            n = int(rest) if rest.isdigit() else 15
            result = sim.simulate(state, my_slot, sims=300, evaluate=False)
            picks = result.my_picks[:5]
            print("  " + " " * 26 + " ".join(f"{'#' + str(p):>6}" for p in picks))
            count = 0
            for p in board:
                idx = sim.index(p)
                if idx in state.taken or idx is None:
                    continue
                cells = " ".join(f"{result.survival[k][idx] * 100:5.0f}%" for k in picks)
                print(f"  {p.name[:24]:24s} {p.position:3s} {cells}")
                count += 1
                if count >= n:
                    break
        elif cmd == "undo":
            idx = state.undo()
            print(f"  undid {sim.player(idx).label}" if idx is not None
                  else "  nothing to undo")
        elif cmd == "slot":
            if rest.isdigit() and 1 <= int(rest) <= config.teams:
                my_slot = int(rest)
                print(f"  slot set to {my_slot}: picks {config.picks_for_slot(my_slot)}")
            else:
                print(f"  slot must be 1..{config.teams}")
        elif cmd == "status":
            clock = on_the_clock()
            who = "YOU" if clock == my_slot else f"slot {clock}"
            print(f"  pick {state.next_pick} (round {state.current_round}): {who}")
        elif cmd == "me":
            player = resolve(rest)
            if player:
                clock = on_the_clock()
                if clock != my_slot:
                    # Recording your own pick out of turn means the transcript
                    # has drifted from the real draft; say so rather than
                    # silently building a roster that cannot happen.
                    print(f"  warning: pick {state.next_pick} belongs to slot "
                          f"{clock}, not you. Recorded as yours anyway - if that "
                          f"is wrong, `undo` and check you have logged every pick.")
                state.record(sim.index(player), my_slot)
                print(f"  YOU drafted {player.label}")
                do_best()
        else:
            player = resolve(raw)
            if player:
                # Attribute the pick to whichever slot is actually on the clock.
                clock = on_the_clock()
                state.record(sim.index(player), clock)
                who = "YOU drafted" if clock == my_slot else "off the board:"
                print(f"  pick {state.next_pick - 1} - {who} {player.label}")
                if on_the_clock() == my_slot:
                    do_best()
    return 0


# --- entrypoint -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="draftiq",
                                     description="Snake draft prediction engine")
    parser.add_argument("--config", help="path to a league JSON config")
    parser.add_argument("--preset", default="frat",
                        help="league preset when no config file exists")
    parser.add_argument("--data-dir", default=str(sources.DATA_DIR))
    parser.add_argument("--out", default=str(REPORT_DIR))
    parser.add_argument("--seed", type=int, default=11)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="refresh the public data feeds")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("board", help="print the value board")
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--position")
    p.add_argument("--export", action="store_true")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("plan", help="generate the full pre-draft report set")
    p.add_argument("--sims", type=int, default=250)
    p.add_argument("--slot", type=int, help="limit to one slot")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("slot", help="deep-dive one draft position")
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--sims", type=int, default=300)
    p.set_defaults(func=cmd_slot)

    p = sub.add_parser("odds", help="survival odds for your picks")
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--sims", type=int, default=400)
    p.add_argument("--rounds", type=int, default=6)
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_odds)

    p = sub.add_parser("advise", help="one-shot advice from the full drafted list")
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--taken", default="", help="comma-separated, in draft order")
    p.add_argument("--taken-file", help="one name per line, in draft order")
    p.add_argument("--mine", default="", help="comma-separated, force onto your roster")
    p.add_argument("--sims", type=int, default=100)
    p.add_argument("--width", type=int, default=12)
    p.add_argument("--top", type=int, default=6)
    p.set_defaults(func=cmd_advise)

    p = sub.add_parser("live", help="interactive draft-day assistant")
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--sims", type=int, default=60)
    p.add_argument("--width", type=int, default=10)
    p.set_defaults(func=cmd_live)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
