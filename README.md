# draftiq — snake draft prediction engine

A Monte Carlo draft engine for a 15-team, full-PPR snake league. It does not
rank players and stop. It simulates the rest of the draft against a model of
the other 14 teams, plays each candidate pick forward to a finished roster,
simulates that roster week by week, and recommends whatever maximises expected
season-long startable points.

Built for a league where the draft slot is unknown until draft day, so every
report covers all 15 slots.

## Quick start

```bash
pip install -r requirements.txt

python -m draftiq fetch                # refresh the public data feeds
python -m draftiq plan                 # full pre-draft report set (~2 min)
python -m draftiq odds --slot 7        # survival odds for your picks
python -m draftiq live --slot 7        # draft-day assistant
```

`python -m draftiq plan` writes into `reports/`:

| File | What it is |
|------|-----------|
| `DRAFT_PLAN.md` | Master report: slot rankings, the positional bet, targets and fades, tier cliffs, per-slot round 1 |
| `slot_01.md` … `slot_15.md` | Round-by-round plan and survival odds for one draft slot |
| `BOARD.md` | Tiered value board |
| `cheatsheet.csv` | Same board, for a spreadsheet or your phone |

## How it works

**1. Data.** Two independent public feeds, cached to `data/` so draft day never
depends on the network:

- [Sleeper](https://api.sleeper.com) season projections — full projected stat
  lines, injury designations, and Sleeper's own ADP.
- [Fantasy Football Calculator](https://fantasyfootballcalculator.com) ADP —
  aggregated from thousands of real mock drafts, with dispersion and bye weeks.

**2. Scoring.** Projections are scored from raw stat components under your
league's exact rules, so nothing is inherited from a different format. Change
`league.json` and the entire board, replacement level and strategy follow.

**3. Availability.** The feed already prices injuries into its totals — a back
on IR is projected far below his healthy rate — so the availability estimate is
*not* applied to the season total a second time. Instead it spreads those points
across the weeks a player is actually active, which is what makes a bye week
cost something and bench depth worth anything.

**4. Replacement level.** Derived from real starter demand at 15 teams, with
FLEX seats allocated greedily to whichever position offers the best remaining
player. This is what makes a TE1 and a WR3 comparable.

**5. Market blend.** The model's VOR is shrunk toward the value implied by ADP,
fitted as a monotone curve over thousands of real drafts. One projection source
is fragile; the crowd is not. Controlled by `market_weight`.

**6. Tiers.** A tier break is cut where the probability that the next player
outscores the current one falls below 42% — so a tier is literally a group you
should be indifferent between, rather than a gap someone eyeballed.

**7. Opponent model.** Each simulated team drafts off its own noisy board, with
persistent per-team preferences, hard positional caps, diminishing interest in a
position already stocked, and rising urgency to fill empty starting slots. That
last rule is what reproduces positional runs and the late kicker/defense rush
that a pure ADP model never generates.

**8. Recommendations.** For each candidate: force the pick, play out the rest of
the draft many times, and score the finished roster with a vectorized week-by-week
lineup simulation including byes, injuries and waiver backfill. Values are
*conditional on the player actually reaching you* — enforced by rejection
sampling, so at slot 15 you are never advised to take someone who will be gone.

## Reading a recommendation

```
   2243 ( +9.4) avail= 14%  Jonathan Taylor (RB-IND)  | only 14% to reach you; +21 pts vs waiting at RB
```

- **2243** — expected finished-roster points if you take him *and he is there*
- **(+9.4)** — how much better than the next-best option
- **avail=14%** — probability he lasts to your pick
- **+21 pts vs waiting** — VONA: what you give up at this position by waiting a round

Take the highest name on the list who is actually on the board.

## Configuration

Copy the active settings to `league.json` and edit:

```bash
python -c "from draftiq.config import preset; preset('frat').to_json(__import__('pathlib').Path('league.json'))"
```

Presets: `frat` (15-team full PPR, the default), `half_ppr`, `standard`,
`te_premium`, `superflex`.

Knobs worth knowing:

| Setting | Effect |
|---------|--------|
| `market_weight` | 0 = pure ADP board, 1 = ignore the market. Default 0.35 |
| `adp_noise_scale` | How chaotic the simulated room is. Raised above 1.0 because a home league reaches more than a mock draft does |
| `team_bias_share` | How much of a team's board is a fixed preference vs. fresh noise |
| `playoff_weight` | Extra weight on weeks 15–17 in roster valuation |

## News overrides

`data/news_overrides.json` is the hook for anything the feeds lag on — a beat
report, a suspension, a backfield timeshare. Availability, points and volatility
can each be overridden per player, with a note that shows up on the board.
**Re-check it the morning of the draft**; it is the one part of the system that
does not update itself.

## Tests

```bash
python -m unittest discover -s tests -v
```

44 tests covering snake-order arithmetic, scoring rules, name joining across
sources, isotonic regression, replacement-level demand, the lineup optimizer
(bye weeks, depth, flex filling, waiver backfill) and simulator invariants
(legal rosters, positional caps, monotone survival, rejection sampling).

## Limitations

Worth knowing before you trust it:

- **The positional bet is the biggest assumption.** The projection source is
  systematically higher on WRs and lower on RBs than the market. That is one
  directional call that moves every recommendation, and `DRAFT_PLAN.md` states
  it explicitly rather than dressing it up as many independent sleepers.
- **ADP comes from public mock drafts**, which are more orderly than a real home
  league. `adp_noise_scale` partly compensates; it cannot fully.
- **Fantasy Football Calculator publishes 8/10/12/14-team ADP, not 15.** Overall
  pick numbers are used directly — close, but not exact.
- **Projections are one source's view.** The market blend limits the damage from
  a single bad projection, but a genuinely wrong depth-chart read propagates.
- **Nothing here models in-season management**, which decides more leagues than
  the draft does.
