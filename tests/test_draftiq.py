"""Tests for the parts of the engine where a silent error would be invisible.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftiq.board import (Board, Player, compute_replacement_levels,
                           isotonic_decreasing)
from draftiq.config import LeagueConfig, Roster, Scoring, preset
from draftiq.lineup import RosterEvaluator
from draftiq.risk import build_risk_profile
from draftiq.scoring import score_stat_line
from draftiq.simulator import DraftSimulator, DraftState
from draftiq.sources import join_key, normalize_name, normalize_team


def make_player(name, position, points, adp=50.0, bye=0, availability=1.0,
                volatility=0.3, team="XXX", vor=None) -> Player:
    risk = build_risk_profile(position)
    risk.availability = availability
    risk.volatility = volatility
    p = Player(name=name, position=position, team=team, bye=bye,
               points=points, ppg=points / 17.0, risk=risk, adp=adp)
    p.vor = points if vor is None else vor
    return p


class TestSnakeOrder(unittest.TestCase):
    def setUp(self):
        self.cfg = LeagueConfig(teams=15, rounds=15)

    def test_first_slot_picks(self):
        picks = self.cfg.picks_for_slot(1)
        self.assertEqual(picks[:4], [1, 30, 31, 60])

    def test_last_slot_picks(self):
        picks = self.cfg.picks_for_slot(15)
        self.assertEqual(picks[:4], [15, 16, 45, 46])

    def test_every_pick_owned_exactly_once(self):
        owned = [p for slot in range(1, 16) for p in self.cfg.picks_for_slot(slot)]
        self.assertEqual(sorted(owned), list(range(1, self.cfg.total_picks + 1)))

    def test_slot_for_pick_inverts_picks_for_slot(self):
        for slot in range(1, 16):
            for pick in self.cfg.picks_for_slot(slot):
                self.assertEqual(self.cfg.slot_for_pick(pick), slot)

    def test_slot_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            self.cfg.picks_for_slot(16)


class TestScoring(unittest.TestCase):
    def test_full_ppr_receptions_count(self):
        stats = {"rec": 100.0, "rec_yd": 1200.0, "rec_td": 8.0}
        ppr = score_stat_line(stats, "WR", Scoring(rec=1.0))
        half = score_stat_line(stats, "WR", Scoring(rec=0.5))
        self.assertAlmostEqual(ppr - half, 50.0)
        self.assertAlmostEqual(ppr, 100 + 120 + 48)

    def test_te_premium_only_applies_to_te(self):
        stats = {"rec": 80.0}
        scoring = Scoring(rec=1.0, rec_bonus_te=0.5)
        self.assertAlmostEqual(score_stat_line(stats, "TE", scoring), 120.0)
        self.assertAlmostEqual(score_stat_line(stats, "WR", scoring), 80.0)

    def test_qb_line_includes_interceptions_and_fumbles(self):
        stats = {"pass_yd": 4000.0, "pass_td": 30.0, "pass_int": 12.0,
                 "rush_yd": 300.0, "rush_td": 3.0, "fum_lost": 4.0}
        got = score_stat_line(stats, "QB", Scoring())
        self.assertAlmostEqual(got, 160 + 120 - 24 + 30 + 18 - 8)

    def test_kicker_uses_precomputed_total(self):
        stats = {"pts_ppr": 140.0, "pts_half_ppr": 140.0, "pts_std": 140.0}
        self.assertAlmostEqual(score_stat_line(stats, "K", Scoring()), 140.0)

    def test_empty_stat_line_returns_none(self):
        self.assertIsNone(score_stat_line({}, "WR", Scoring()))


class TestNameJoining(unittest.TestCase):
    def test_punctuation_and_suffixes_normalise(self):
        self.assertEqual(normalize_name("Ja'Marr Chase"), "jamarr chase")
        self.assertEqual(normalize_name("Marvin Harrison Jr."), "marvin harrison")
        self.assertEqual(normalize_name("Amon-Ra St. Brown"), "amon ra st brown")

    def test_join_key_separates_positions(self):
        self.assertNotEqual(join_key("Seattle", "DEF"), join_key("Seattle", "WR"))

    def test_team_aliases(self):
        self.assertEqual(normalize_team("JAC"), "JAX")
        self.assertEqual(normalize_team("WSH"), "WAS")
        self.assertEqual(normalize_team(None), "FA")


class TestIsotonic(unittest.TestCase):
    def test_output_is_non_increasing(self):
        xs = [10, 3, 12, 5, 8, 1, 4]
        out = isotonic_decreasing(xs)
        self.assertEqual(len(out), len(xs))
        for a, b in zip(out, out[1:]):
            self.assertGreaterEqual(a + 1e-9, b)

    def test_already_decreasing_is_unchanged(self):
        xs = [9.0, 7.0, 5.0, 2.0]
        self.assertEqual(isotonic_decreasing(xs), xs)

    def test_mean_is_preserved(self):
        xs = [4.0, 9.0, 1.0, 6.0]
        self.assertAlmostEqual(sum(isotonic_decreasing(xs)), sum(xs))


class TestReplacementLevels(unittest.TestCase):
    def test_replacement_tracks_starter_demand(self):
        cfg = LeagueConfig(teams=10, rounds=15,
                           roster=Roster(qb=1, rb=2, wr=3, te=1, flex=1, k=1, dst=1))
        players = []
        for pos, count in (("QB", 40), ("RB", 80), ("WR", 100), ("TE", 40),
                           ("K", 40), ("DEF", 40)):
            for i in range(count):
                players.append(make_player(f"{pos}{i}", pos, 300.0 - i))
        rep = compute_replacement_levels(players, cfg)
        # 10 teams x 1 QB means the 11th QB (300-10) is replacement level.
        self.assertAlmostEqual(rep["QB"], 290.0)
        # RB demand is 20 dedicated starters plus any flex seats it wins.
        self.assertLessEqual(rep["RB"], 280.0)
        self.assertGreater(rep["WR"], 0.0)

    def test_flex_goes_to_the_deeper_position(self):
        cfg = LeagueConfig(teams=10, rounds=15,
                           roster=Roster(qb=1, rb=2, wr=3, te=1, flex=1, k=1, dst=1))
        players = []
        for i in range(80):
            players.append(make_player(f"RB{i}", "RB", 300.0 - i * 5))   # steep
        for i in range(80):
            players.append(make_player(f"WR{i}", "WR", 300.0 - i * 0.5))  # flat
        for pos in ("QB", "TE", "K", "DEF"):
            for i in range(30):
                players.append(make_player(f"{pos}{i}", pos, 100.0 - i))
        rep = compute_replacement_levels(players, cfg)
        # WRs stay valuable much deeper, so flex seats should go there,
        # pushing WR replacement further down the list than RB's.
        self.assertGreater(rep["WR"], rep["RB"])


class TestRiskModel(unittest.TestCase):
    def test_injury_status_lowers_availability(self):
        healthy = build_risk_profile("RB")
        hurt = build_risk_profile("RB", injury_status="IR")
        self.assertLess(hurt.availability, healthy.availability)

    def test_old_running_backs_are_less_available(self):
        young = build_risk_profile("RB", years_exp=2)
        old = build_risk_profile("RB", years_exp=10)
        self.assertLess(old.availability, young.availability)

    def test_rookies_are_more_volatile(self):
        rookie = build_risk_profile("WR", years_exp=0, adp=60, adp_stdev=10)
        vet = build_risk_profile("WR", years_exp=5, adp=60, adp_stdev=10)
        self.assertGreater(rookie.volatility, vet.volatility)

    def test_overrides_win(self):
        prof = build_risk_profile("RB", override={"availability": 0.5, "note": "hi"})
        self.assertAlmostEqual(prof.availability, 0.5)
        self.assertEqual(prof.note, "hi")

    def test_availability_is_bounded(self):
        prof = build_risk_profile("RB", override={"availability": 5.0})
        self.assertLessEqual(prof.availability, 1.0)


class TestRosterEvaluator(unittest.TestCase):
    def setUp(self):
        self.cfg = LeagueConfig(teams=10, rounds=15, weeks=17, playoff_weight=1.0,
                                roster=Roster(qb=1, rb=2, wr=3, te=1, flex=1,
                                              k=1, dst=1, bench=5))
        self.rep = {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0, "K": 0.0, "DEF": 0.0}
        self.ev = RosterEvaluator(self.cfg, self.rep, sims=200, seed=3)

    def _full_roster(self, availability=1.0, bye=0):
        spec = [("QB", 1), ("RB", 2), ("WR", 3), ("TE", 1), ("K", 1), ("DEF", 1)]
        out = []
        for pos, n in spec:
            for i in range(n):
                out.append(make_player(f"{pos}{i}", pos, 170.0, bye=bye,
                                       availability=availability))
        return out

    def test_perfect_availability_sums_starters(self):
        roster = self._full_roster()
        # 9 players at 10 ppg for 17 weeks; the flex slot has nobody left and
        # falls back to a waiver value of zero.
        self.assertAlmostEqual(self.ev.mean_value(roster), 9 * 10.0 * 17, places=4)

    def test_bye_week_costs_exactly_one_week(self):
        roster = self._full_roster()
        roster[0] = make_player("QBbye", "QB", 170.0, bye=5, availability=1.0)
        expected = 9 * 10.0 * 17 - 10.0
        self.assertAlmostEqual(self.ev.mean_value(roster), expected, places=4)

    def test_depth_adds_value_when_starters_get_hurt(self):
        base = self._full_roster(availability=0.6)
        backup = make_player("RB_backup", "RB", 170.0, availability=0.6)
        thin = self.ev.mean_value(base, sims=600)
        deep = self.ev.mean_value(base + [backup], sims=600)
        self.assertGreater(deep, thin)

    def test_fourth_tight_end_is_worthless(self):
        # The FLEX must already be occupied, otherwise a spare TE legitimately
        # fills it and is worth something.
        base = self._full_roster() + [make_player("FlexWR", "WR", 170.0,
                                                  availability=1.0)]
        spare = [make_player(f"TEx{i}", "TE", 90.0, availability=1.0) for i in range(3)]
        self.assertAlmostEqual(self.ev.mean_value(base + spare),
                               self.ev.mean_value(base), places=3)

    def test_flex_is_filled_by_best_remaining(self):
        base = self._full_roster()
        strong = make_player("FlexWR", "WR", 340.0, availability=1.0)  # 20 ppg
        got = self.ev.mean_value(base + [strong])
        self.assertAlmostEqual(got, 9 * 10.0 * 17 + 20.0 * 17, places=4)

    def test_waiver_backfill_beats_scoring_zero(self):
        rep = dict(self.rep, RB=170.0)
        ev = RosterEvaluator(self.cfg, rep, sims=100, seed=3)
        self.assertGreater(ev.mean_value([]), 0.0)

    def test_empty_roster_is_finite(self):
        self.assertGreaterEqual(self.ev.mean_value([]), 0.0)


class TestDraftSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = LeagueConfig(teams=10, rounds=15,
                               roster=Roster(qb=1, rb=2, wr=3, te=1, flex=1,
                                             k=1, dst=1, bench=5))
        players = []
        adp = 1.0
        # Interleave positions so ADP order is realistic rather than blocked.
        for i in range(60):
            for pos in ("RB", "WR", "WR", "QB", "TE", "K", "DEF"):
                players.append(make_player(f"{pos}_{i}", pos, 300.0 - adp,
                                           adp=adp, bye=(i % 14) + 1,
                                           vor=300.0 - adp))
                adp += 1.0
        rep = {"QB": 100.0, "RB": 100.0, "WR": 100.0, "TE": 100.0,
               "K": 50.0, "DEF": 50.0}
        for i, p in enumerate(players, 1):
            p.overall_rank = i
        cls.board = Board(players, cls.cfg, rep)
        cls.sim = DraftSimulator(cls.board, cls.cfg, seed=5)

    def test_rollout_fills_a_legal_roster(self):
        state = DraftState(self.cfg)
        roster = self.sim._rollout(state, my_slot=4, rng=np.random.default_rng(1))
        self.assertEqual(len(roster), self.cfg.rounds)
        counts = {}
        for idx in roster:
            pos = self.sim.positions[idx]
            counts[pos] = counts.get(pos, 0) + 1
        for pos, need in self.cfg.roster.required_slots().items():
            self.assertGreaterEqual(counts.get(pos, 0), need,
                                    f"no legal starter at {pos}: {counts}")

    def test_positional_caps_are_respected(self):
        state = DraftState(self.cfg)
        roster = self.sim._rollout(state, my_slot=1, rng=np.random.default_rng(2))
        counts = {}
        for idx in roster:
            pos = self.sim.positions[idx]
            counts[pos] = counts.get(pos, 0) + 1
        self.assertLessEqual(counts.get("K", 0), self.cfg.roster.max_k)
        self.assertLessEqual(counts.get("QB", 0), self.cfg.roster.max_qb)

    def test_no_player_is_drafted_twice(self):
        state = DraftState(self.cfg)
        result = self.sim.simulate(state, my_slot=3, sims=5, evaluate=False)
        self.assertTrue(np.all(result.acquired <= 1.0 + 1e-9))

    def test_survival_is_monotone_across_your_picks(self):
        state = DraftState(self.cfg)
        result = self.sim.simulate(state, my_slot=5, sims=120, evaluate=False)
        picks = result.my_picks
        for a, b in zip(picks, picks[1:]):
            self.assertTrue(np.all(result.survival[b] <= result.survival[a] + 1e-9),
                            "a player cannot become more available later")

    def test_early_adp_players_survive_less_than_late_ones(self):
        state = DraftState(self.cfg)
        result = self.sim.simulate(state, my_slot=8, sims=150, evaluate=False)
        surv = result.survival[result.my_picks[0]]
        early = surv[:5].mean()
        late = surv[100:120].mean()
        self.assertLess(early, late)

    def test_forced_pick_is_honoured_when_available(self):
        state = DraftState(self.cfg)
        target = 0  # the very first name off the board
        result = self.sim.simulate(state, my_slot=1, sims=6, forced_first=target,
                                   evaluate=False, require_forced=True)
        self.assertGreater(result.sims, 0)
        self.assertAlmostEqual(result.acquired[target], 1.0)

    def test_rejection_sampling_gives_up_on_impossible_picks(self):
        # Slot 10 cannot have the consensus 1.1 player fall to them.
        state = DraftState(self.cfg)
        result = self.sim.simulate(state, my_slot=10, sims=20, forced_first=0,
                                   evaluate=False, require_forced=True,
                                   max_attempts_factor=2)
        self.assertLessEqual(result.sims, 20)
        self.assertGreater(result.attempts, 0)

    def test_already_drafted_players_stay_drafted(self):
        state = DraftState(self.cfg)
        state.record(0, 2)
        state.record(1, 3)
        result = self.sim.simulate(state, my_slot=5, sims=10, evaluate=False)
        surv = result.survival[result.my_picks[0]]
        self.assertEqual(surv[0], 0.0)
        self.assertEqual(surv[1], 0.0)


class TestDraftState(unittest.TestCase):
    def setUp(self):
        self.cfg = LeagueConfig(teams=15, rounds=15)

    def test_record_and_undo(self):
        state = DraftState(self.cfg)
        state.record(4, 2)
        self.assertEqual(state.next_pick, 2)
        self.assertEqual(state.roster_of(2), [4])
        self.assertEqual(state.undo(), 4)
        self.assertEqual(state.next_pick, 1)
        self.assertIsNone(state.undo())

    def test_double_draft_is_rejected(self):
        state = DraftState(self.cfg)
        state.record(4, 2)
        with self.assertRaises(ValueError):
            state.record(4, 3)

    def test_copy_is_independent(self):
        state = DraftState(self.cfg)
        state.record(1, 1)
        clone = state.copy()
        clone.record(2, 2)
        self.assertEqual(len(state.order), 1)
        self.assertEqual(len(clone.order), 2)

    def test_round_advances_with_picks(self):
        state = DraftState(self.cfg)
        for i in range(15):
            state.record(i, self.cfg.slot_for_pick(i + 1))
        self.assertEqual(state.current_round, 2)


class TestConfigRoundTrip(unittest.TestCase):
    def test_json_round_trip(self):
        import tempfile
        cfg = preset("te_premium")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "league.json"
            cfg.to_json(path)
            back = LeagueConfig.from_json(path)
        self.assertEqual(back.teams, cfg.teams)
        self.assertAlmostEqual(back.scoring.rec_bonus_te, 0.5)
        self.assertEqual(back.roster.starters, cfg.roster.starters)

    def test_superflex_preset_adds_a_qb_slot(self):
        cfg = preset("superflex")
        self.assertEqual(cfg.roster.superflex, 1)
        self.assertEqual(cfg.roster.flex, 0)


class TestRealBoardIntegration(unittest.TestCase):
    """End-to-end against the cached feeds, skipped if they aren't present."""

    @classmethod
    def setUpClass(cls):
        from draftiq.board import build_board
        from draftiq.sources import DATA_DIR
        if not (DATA_DIR / "sleeper_projections_2026.json").exists():
            raise unittest.SkipTest("run `python -m draftiq fetch` first")
        cls.cfg = preset("frat")
        cls.board = build_board(cls.cfg)

    def test_board_is_populated_and_ordered(self):
        self.assertGreater(len(self.board), 300)
        vors = [p.vor for p in self.board]
        self.assertEqual(vors, sorted(vors, reverse=True))

    def test_every_position_has_a_replacement_level(self):
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            self.assertGreater(self.board.replacement[pos], 0.0, pos)

    def test_lookup_handles_punctuation(self):
        self.assertIsNotNone(self.board.get("Jamarr Chase"))
        self.assertIsNotNone(self.board.get("Ja'Marr Chase"))

    def test_top_players_have_real_market_data(self):
        for p in self.board.top(25):
            self.assertLess(p.adp, self.cfg.total_picks, p.name)

    def test_ppg_reproduces_the_season_total(self):
        for p in self.board.top(50):
            active = self.cfg.weeks * max(p.availability, 0.40)
            self.assertAlmostEqual(p.ppg * active, p.points, places=3)

    def test_resolve_handles_draft_board_formatting(self):
        cases = {
            "Jahmyr Gibbs": "Jahmyr Gibbs",
            "J. Gibbs": "Jahmyr Gibbs",
            "Gibbs DET RB": "Jahmyr Gibbs",
            "A. St. Brown": "Amon-Ra St. Brown",
            "Ja'Marr Chase": "Ja'Marr Chase",
            "Chase Brown CIN RB": "Chase Brown",
            "Bijan Robinson Atl RB Q": "Bijan Robinson",
        }
        for text, expected in cases.items():
            player, _ = self.board.resolve(text)
            self.assertIsNotNone(player, text)
            self.assertEqual(player.name, expected, text)

    def test_resolve_matches_team_defenses(self):
        for text in ("Ravens D/ST", "Baltimore D/ST"):
            player, _ = self.board.resolve(text)
            self.assertIsNotNone(player, text)
            self.assertEqual(player.position, "DEF")
            self.assertEqual(player.team, "BAL")

    def test_resolve_reports_ambiguity_instead_of_guessing(self):
        player, alts = self.board.resolve("McCaffrey")
        self.assertIsNone(player)
        self.assertGreater(len(alts), 1)

    def test_resolve_returns_nothing_for_junk(self):
        player, alts = self.board.resolve("Zzz Nobody")
        self.assertIsNone(player)
        self.assertEqual(alts, [])

    def test_recommendation_only_offers_reachable_players(self):
        from draftiq.recommend import Recommender
        rec = Recommender(self.board, self.cfg, seed=3)
        result = rec.recommend(DraftState(self.cfg), my_slot=15, sims=25, width=6)
        self.assertTrue(result.candidates)
        for c in result.candidates:
            self.assertGreater(c.p_available, 0.0, c.player.name)
            self.assertGreater(c.value, 0.0)


if __name__ == "__main__":
    unittest.main()
