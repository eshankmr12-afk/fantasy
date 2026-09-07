# Draft plan - Frat League (15-team full PPR)

- Generated: 2026-09-07 21:29
- Projections: Sleeper 2026 season projections (cached 2026-09-07)
- ADP: Fantasy Football Calculator Half-PPR - 2,879 real drafts, 2026-08-31 to 2026-09-05
- ADP: Fantasy Football Calculator PPR - 7,430 real drafts, 2026-08-29 to 2026-09-05
- ADP: Fantasy Football Calculator Non-PPR - 1,606 real drafts, 2026-08-29 to 2026-09-05
- News overrides: 10 manual adjustments, last updated 2026-09-07

**Format:** 15 teams, 15 rounds, full PPR, lineup 1QB/2RB/3WR/1TE/1FLEX/1K/1DST.

## How to use this

1. Find your slot's section below (or open `slot_XX.md`).
2. At each pick, take the highest player on that slot's list who is
   still on the board. The list is already ordered by what it does to
   your *finished roster*, not by raw ranking.
3. During the draft run `python -m draftiq live --slot N` to update the
   board as players come off it and get live recommendations.

## Which slot is best

Expected finished-roster value from each draft position, over 300 simulated drafts each. Differences of a few points are noise.

| Slot | Picks 1-3 | Expected value | 10th-90th pct | Likely R1 pick |
|------|-----------|----------------|---------------|----------------|
| **5** | 5, 26, 35 | 2316 | 2286-2352 | Jahmyr Gibbs |
| **6** | 6, 25, 36 | 2316 | 2283-2355 | Jahmyr Gibbs |
| **4** | 4, 27, 34 | 2312 | 2287-2338 | Jahmyr Gibbs |
| **3** | 3, 28, 33 | 2311 | 2288-2333 | Jahmyr Gibbs |
| **2** | 2, 29, 32 | 2307 | 2282-2333 | Jahmyr Gibbs |
| **7** | 7, 24, 37 | 2306 | 2272-2346 | Jahmyr Gibbs |
| **1** | 1, 30, 31 | 2304 | 2280-2329 | Jahmyr Gibbs |
| **8** | 8, 23, 38 | 2296 | 2260-2334 | Jahmyr Gibbs |
| **9** | 9, 22, 39 | 2281 | 2243-2319 | Bijan Robinson |
| **10** | 10, 21, 40 | 2271 | 2230-2313 | Christian McCaffrey |
| **11** | 11, 20, 41 | 2259 | 2218-2300 | Christian McCaffrey |
| **12** | 12, 19, 42 | 2242 | 2206-2287 | Christian McCaffrey |
| **13** | 13, 18, 43 | 2230 | 2197-2268 | Christian McCaffrey |
| **14** | 14, 17, 44 | 2221 | 2191-2253 | Christian McCaffrey |
| **15** | 15, 16, 45 | 2216 | 2187-2246 | Jonathan Taylor |

Spread between the best slot (5) and the worst (15) is 100 points of expected roster value - about 5.9 points a week. Slot matters far less than the picks you make from it.

## Rules that hold at every slot

### The one big bet: positional value

Before any individual player, the model disagrees with the market at the *position* level. Median edge over 147 well-sampled players:

| Pos | Median edge vs market |
|-----|----------------------|
| WR | +12 |
| TE | +2 |
| QB | -7 |
| RB | -13 |

Read that as one directional call, not many: the projections are 25 points higher on **WR** than on **RB** relative to where the market drafts them. In practice it means letting the room pay up for RBs and taking WRs a little earlier than ADP. If you think that call is wrong, lower `market_weight` in `league.json` and the whole board moves with it.

### Player-specific targets

Edge *after* removing the position-level bet above, so these are genuine views on individual players rather than the same positional call repeated. Restricted to players drafted in at least 150 of the sampled mock drafts.

| Player | Pos | Team | ADP | Proj | Edge vs position | Note |
|--------|-----|------|-----|------|------------------|------|
| Bijan Robinson | RB2 | ATL | 2.2 | 325 | +42 |  |
| Jayden Reed | WR32 | GB | 97.1 | 198 | +29 |  |
| Malik Willis | QB22 | MIA | 180.7 | 261 | +28 |  |
| Parker Washington | WR27 | JAX | 66.9 | 212 | +26 |  |
| Sam LaPorta | TE5 | DET | 87.1 | 196 | +25 |  |
| Jahmyr Gibbs | RB1 | DET | 1.4 | 331 | +22 |  |
| Christian Watson | WR28 | GB | 61.8 | 208 | +21 |  |
| Mike Evans | WR22 | SF | 58.7 | 222 | +20 |  |
| Ja'Marr Chase | WR2 | CIN | 3.6 | 311 | +19 |  |
| Brian Thomas | WR30 | JAX | 73.7 | 195 | +18 |  |
| Nico Collins | WR6 | HOU | 22.1 | 262 | +17 |  |
| Puka Nacua | WR1 | LAR | 3.4 | 312 | +16 |  |
| Ladd McConkey | WR20 | LAC | 37.2 | 228 | +15 |  |
| D'Andre Swift | RB18 | CHI | 46.8 | 208 | +15 |  |
| Brock Bowers | TE1 | LV | 29.9 | 254 | +14 |  |

### Player-specific fades

| Player | Pos | Team | ADP | Proj | Edge vs position | Note |
|--------|-----|------|-----|------|------------------|------|
| Josh Jacobs | RB44 | GB | 65.0 | 87 | -85 |  |
| Zach Charbonnet | RB52 | SEA | 144.7 | 67 | -66 |  |
| Dontayvion Wicks | WR88 | PHI | 161.2 | 70 | -65 |  |
| Alvin Kamara | RB55 | NO | 158.0 | 63 | -59 |  |
| Tyler Allgeier | RB49 | ARI | 149.6 | 77 | -56 |  |
| Woody Marks | RB47 | HOU | 143.5 | 84 | -52 |  |
| Mike Washington | RB45 | LV | 146.8 | 98 | -36 |  |
| De'Zhaun Stribling | WR57 | SF | 130.3 | 128 | -28 |  |
| Dallas Goedert | TE17 | PHI | 117.9 | 136 | -28 |  |
| DJ Moore | WR31 | BUF | 49.5 | 179 | -27 |  |
| Jerry Jeudy | WR60 | CLE | 152.3 | 120 | -27 |  |
| Jeremiyah Love | RB15 | ARI | 28.4 | 201 | -26 | Preseason ankle; beat reporters put Week 1 at roug |
| Breece Hall | RB16 | NYJ | 32.7 | 198 | -23 | Groin injury Aug 18, told to miss 2-3 weeks of pra |
| Joe Burrow | QB4 | CIN | 54.2 | 296 | -22 |  |
| Daniel Jones | QB26 | IND | 175.3 | 213 | -21 |  |

### Tier cliffs

Where each position falls off. The ADP column is roughly the pick by which the tier is gone - if you are on the clock near it and want that tier, this is your last chance.

| Pos | Tier | Players | Gone by ~pick | Avg VOR |
|-----|------|---------|---------------|---------|
| RB | 1 | 2 (Jahmyr Gibbs, Bijan Robinson) | 2 | 172 |
| RB | 2 | 1 (Christian McCaffrey) | 6 | 142 |
| RB | 3 | 8 (Jonathan Taylor, James Cook, De'Von Achane, Chase Brown, Saquon Barkley) | 21 | 107 |
| RB | 4 | 1 (Ashton Jeanty) | 19 | 90 |
| RB | 5 | 8 (Javonte Williams, Kyren Williams, Jeremiyah Love, Breece Hall, Travis Etienne) | 51 | 62 |
| RB | 6 | 2 (Bucky Irving, Quinshon Judkins) | 51 | 51 |
| WR | 1 | 2 (Puka Nacua, Ja'Marr Chase) | 4 | 163 |
| WR | 2 | 4 (Jaxon Smith-Njigba, Amon-Ra St. Brown, CeeDee Lamb, Nico Collins) | 22 | 132 |
| WR | 3 | 8 (Justin Jefferson, Drake London, A.J. Brown, George Pickens, Chris Olave) | 31 | 101 |
| WR | 4 | 8 (Zay Flowers, Garrett Wilson, Tee Higgins, Tetairoa McMillan, Emeka Egbuka) | 59 | 82 |
| WR | 5 | 6 (Terry McLaurin, Luther Burden, Jameson Williams, Rome Odunze, Parker Washington) | 67 | 63 |
| WR | 6 | 2 (Davante Adams, Brian Thomas) | 74 | 51 |
| TE | 1 | 1 (Brock Bowers) | 30 | 97 |
| TE | 2 | 1 (Trey McBride) | 28 | 87 |
| TE | 3 | 1 (Colston Loveland) | 48 | 62 |
| TE | 4 | 2 (Tyler Warren, Sam LaPorta) | 87 | 43 |
| TE | 5 | 1 (Harold Fannin) | 73 | 29 |
| TE | 6 | 8 (Kyle Pitts, Tucker Kraft, Travis Kelce, George Kittle, Dalton Kincaid) | 129 | 15 |
| QB | 1 | 1 (Josh Allen) | 28 | 83 |
| QB | 2 | 2 (Lamar Jackson, Drake Maye) | 51 | 46 |
| QB | 3 | 8 (Joe Burrow, Jalen Hurts, Jayden Daniels, Dak Prescott, Caleb Williams) | 100 | 23 |
| QB | 4 | 2 (Jaxson Dart, Bo Nix) | 114 | 11 |
| QB | 5 | 7 (Patrick Mahomes, Matthew Stafford, Jared Goff, Kyler Murray, Jordan Love) | 156 | -1 |
| QB | 6 | 2 (Sam Darnold, Malik Willis) | 181 | -17 |

## Slot-by-slot round 1

### Slot 1 (picks 1, 30, 31, 60 ...)

Expected roster value 2304. Full plan: [`slot_01.md`](slot_01.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 100% | 2304 (2276-2333) | +6.7 | gone by your next pick (0% to last); last of tier 1 at RB; +108 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 100% | 2297 (2269-2326) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +94 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 100% | 2284 (2255-2310) | -13.2 | gone by your next pick (0% to last); last of tier 2 at RB; +71 pts vs waiting at RB; questionable |
| **Puka Nacua** | WR1 | 3.4 | 100% | 2275 (2250-2302) | -21.7 | gone by your next pick (0% to last); last of tier 1 at WR; +74 pts vs waiting at WR; market is 28 pts light on him; questionable |

### Slot 2 (picks 2, 29, 32, 59 ...)

Expected roster value 2307. Full plan: [`slot_02.md`](slot_02.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 100% | 2307 (2282-2330) | +6.3 | gone by your next pick (0% to last); last of tier 1 at RB; +105 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 100% | 2301 (2274-2324) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +92 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 100% | 2288 (2262-2310) | -12.9 | gone by your next pick (0% to last); last of tier 2 at RB; +68 pts vs waiting at RB; questionable |
| **Puka Nacua** | WR1 | 3.4 | 48% | 2276 (2247-2305) | -24.2 | only 48% to reach you; gone by your next pick (0% to last); last of tier 1 at WR; +73 pts vs waiting at WR; market is 28 pts light on him; questionable |

### Slot 3 (picks 3, 28, 33, 58 ...)

Expected roster value 2311. Full plan: [`slot_03.md`](slot_03.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 100% | 2312 (2289-2339) | +7.4 | gone by your next pick (0% to last); last of tier 1 at RB; +100 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 100% | 2305 (2275-2337) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +87 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 100% | 2292 (2268-2319) | -13.1 | gone by your next pick (0% to last); last of tier 2 at RB; +63 pts vs waiting at RB; questionable |
| **Ja'Marr Chase** | WR2 | 3.6 | 11% | 2278 (2249-2309) | -27.3 | only 11% to reach you; gone by your next pick (0% to last); last of tier 1 at WR; +69 pts vs waiting at WR; market is 31 pts light on him; questionable |

### Slot 4 (picks 4, 27, 34, 57 ...)

Expected roster value 2312. Full plan: [`slot_04.md`](slot_04.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 97% | 2315 (2287-2342) | +8.5 | gone by your next pick (0% to last); last of tier 1 at RB; +92 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 100% | 2306 (2280-2336) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +79 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 99% | 2296 (2273-2320) | -10.3 | gone by your next pick (0% to last); last of tier 2 at RB; +55 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 100% | 2262 (2235-2291) | -44.6 | gone by your next pick (0% to last); +43 pts vs waiting at RB |

### Slot 5 (picks 5, 26, 35, 56 ...)

Expected roster value 2316. Full plan: [`slot_05.md`](slot_05.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 78% | 2318 (2286-2352) | +10.1 | gone by your next pick (0% to last); last of tier 1 at RB; +86 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 93% | 2308 (2280-2341) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +73 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 100% | 2299 (2275-2330) | -8.5 | gone by your next pick (0% to last); last of tier 2 at RB; +49 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 100% | 2258 (2234-2290) | -49.8 | gone by your next pick (0% to last); +37 pts vs waiting at RB |

### Slot 6 (picks 6, 25, 36, 55 ...)

Expected roster value 2316. Full plan: [`slot_06.md`](slot_06.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 49% | 2317 (2287-2350) | +6.0 | only 49% to reach you; gone by your next pick (0% to last); last of tier 1 at RB; +83 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 76% | 2311 (2287-2347) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +70 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 98% | 2298 (2263-2330) | -13.4 | gone by your next pick (0% to last); last of tier 2 at RB; +46 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 100% | 2263 (2232-2298) | -47.8 | gone by your next pick (0% to last); +34 pts vs waiting at RB |

### Slot 7 (picks 7, 24, 37, 54 ...)

Expected roster value 2306. Full plan: [`slot_07.md`](slot_07.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 29% | 2322 (2289-2354) | +6.4 | only 29% to reach you; gone by your next pick (0% to last); last of tier 1 at RB; +81 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 52% | 2316 (2285-2350) | +0.0 | gone by your next pick (0% to last); last of tier 1 at RB; +68 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 95% | 2295 (2257-2337) | -20.8 | gone by your next pick (0% to last); last of tier 2 at RB; +44 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 100% | 2263 (2235-2298) | -52.6 | gone by your next pick (0% to last); +32 pts vs waiting at RB |

### Slot 8 (picks 8, 23, 38, 53 ...)

Expected roster value 2296. Full plan: [`slot_08.md`](slot_08.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jahmyr Gibbs** | RB1 | 1.4 | 11% | 2321 (2290-2355) | +12.6 | only 11% to reach you; gone by your next pick (0% to last); last of tier 1 at RB; +79 pts vs waiting at RB |
| **Bijan Robinson** | RB2 | 2.2 | 29% | 2308 (2278-2341) | +0.0 | only 29% to reach you; gone by your next pick (0% to last); last of tier 1 at RB; +66 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 93% | 2291 (2261-2324) | -16.7 | gone by your next pick (0% to last); last of tier 2 at RB; +42 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 97% | 2254 (2219-2285) | -53.7 | gone by your next pick (0% to last); +30 pts vs waiting at RB |

### Slot 9 (picks 9, 22, 39, 52 ...)

Expected roster value 2281. Full plan: [`slot_09.md`](slot_09.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Bijan Robinson** | RB2 | 2.2 | 13% | 2304 (2274-2336) | +12.8 | only 13% to reach you; gone by your next pick (0% to last); last of tier 1 at RB; +65 pts vs waiting at RB; market is 29 pts light on him |
| **Christian McCaffrey** | RB3 | 5.7 | 82% | 2291 (2253-2327) | +0.0 | gone by your next pick (0% to last); last of tier 2 at RB; +41 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 95% | 2253 (2223-2286) | -37.7 | gone by your next pick (0% to last); +29 pts vs waiting at RB |
| **James Cook** | RB5 | 10.4 | 95% | 2240 (2208-2275) | -51.2 | gone by your next pick (1% to last) |

### Slot 10 (picks 10, 21, 40, 51 ...)

Expected roster value 2271. Full plan: [`slot_10.md`](slot_10.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Christian McCaffrey** | RB3 | 5.7 | 63% | 2285 (2258-2313) | +37.4 | gone by your next pick (0% to last); last of tier 2 at RB; +39 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 88% | 2248 (2214-2280) | +0.0 | gone by your next pick (0% to last); +27 pts vs waiting at RB |
| **James Cook** | RB5 | 10.4 | 93% | 2232 (2200-2268) | -16.4 | gone by your next pick (2% to last) |
| **Saquon Barkley** | RB8 | 16.1 | 98% | 2231 (2203-2257) | -17.4 | - |

### Slot 11 (picks 11, 20, 41, 50 ...)

Expected roster value 2259. Full plan: [`slot_11.md`](slot_11.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Christian McCaffrey** | RB3 | 5.7 | 39% | 2281 (2245-2316) | +41.4 | only 39% to reach you; gone by your next pick (0% to last); last of tier 2 at RB; +37 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 79% | 2240 (2212-2269) | +0.0 | gone by your next pick (0% to last); +25 pts vs waiting at RB |
| **James Cook** | RB5 | 10.4 | 90% | 2227 (2200-2255) | -13.1 | gone by your next pick (7% to last) |
| **De'Von Achane** | RB6 | 11.2 | 95% | 2225 (2193-2254) | -15.2 | gone by your next pick (10% to last) |

### Slot 12 (picks 12, 19, 42, 49 ...)

Expected roster value 2242. Full plan: [`slot_12.md`](slot_12.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Christian McCaffrey** | RB3 | 5.7 | 27% | 2272 (2243-2305) | +32.6 | only 27% to reach you; gone by your next pick (0% to last); last of tier 2 at RB; +37 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 60% | 2240 (2216-2268) | +0.0 | gone by your next pick (0% to last); +24 pts vs waiting at RB |
| **Derrick Henry** | RB9 | 16.5 | 100% | 2231 (2209-2257) | -8.8 | can wait, 85% to last |
| **De'Von Achane** | RB6 | 11.2 | 94% | 2225 (2196-2256) | -14.6 | - |

### Slot 13 (picks 13, 18, 43, 48 ...)

Expected roster value 2230. Full plan: [`slot_13.md`](slot_13.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Christian McCaffrey** | RB3 | 5.7 | 15% | 2273 (2246-2304) | +41.0 | only 15% to reach you; gone by your next pick (0% to last); last of tier 2 at RB; +36 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 41% | 2232 (2205-2265) | +0.0 | only 41% to reach you; gone by your next pick (0% to last); +23 pts vs waiting at RB |
| **Derrick Henry** | RB9 | 16.5 | 99% | 2228 (2200-2259) | -4.1 | can wait, 91% to last |
| **Saquon Barkley** | RB8 | 16.1 | 93% | 2223 (2197-2253) | -9.0 | - |

### Slot 14 (picks 14, 17, 44, 47 ...)

Expected roster value 2221. Full plan: [`slot_14.md`](slot_14.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Christian McCaffrey** | RB3 | 5.7 | 7% | 2273 (2246-2299) | +39.1 | only 7% to reach you; gone by your next pick (0% to last); last of tier 2 at RB; +34 pts vs waiting at RB; questionable |
| **Jonathan Taylor** | RB4 | 7.2 | 23% | 2234 (2207-2256) | +0.0 | only 23% to reach you; gone by your next pick (2% to last); +21 pts vs waiting at RB |
| **Derrick Henry** | RB9 | 16.5 | 100% | 2228 (2201-2255) | -5.4 | can wait, 99% to last |
| **De'Von Achane** | RB6 | 11.2 | 86% | 2223 (2199-2250) | -10.5 | - |

### Slot 15 (picks 15, 16, 45, 46 ...)

Expected roster value 2216. Full plan: [`slot_15.md`](slot_15.md)

| Player | Pos | ADP | P(available) | Roster value | vs next | Why |
|--------|-----|-----|--------------|--------------|---------|-----|
| **Jonathan Taylor** | RB4 | 7.2 | 17% | 2239 (2212-2269) | +13.3 | only 17% to reach you; +21 pts vs waiting at RB |
| **Derrick Henry** | RB9 | 16.5 | 99% | 2226 (2194-2256) | +0.0 | - |
| **De'Von Achane** | RB6 | 11.2 | 75% | 2224 (2197-2248) | -1.8 | - |
| **Saquon Barkley** | RB8 | 16.1 | 84% | 2222 (2198-2248) | -4.0 | - |

## Method

- **Projections** are scored from raw projected stat lines under this league's exact rules, so nothing is borrowed from a different format.
- **Availability** is modelled separately from the season total. The feed already prices injuries into its totals, so the availability estimate is used to spread those points across the weeks a player is actually active - which is what makes bench depth worth anything.
- **Replacement level** comes from real starter demand at 15 teams, with FLEX allocated to whichever position offers the best remaining player. That is why a TE1 and a WR3 are comparable here.
- **Market blend** shrinks the model toward the value implied by ADP. A single projection source is fragile; thousands of real drafts are not.
- **Tiers** break where the probability that the next player outscores the current one drops below 42% - a tier is a group you should be indifferent between.
- **Opponent model**: each simulated team drafts off its own noisy board with persistent preferences, positional caps, and rising urgency to fill empty starting slots. That reproduces positional runs and late kicker and defense behaviour.
- **Recommendations** force each candidate, play the draft out to the end many times, and score the finished roster with a week-by-week lineup simulation including byes and injuries. Values are conditional on the player actually reaching you.

### Honest limitations

- ADP comes from public mock drafts, which are more predictable than a 15-team home league where people reach for their own players. The `adp_noise_scale` setting is raised above 1.0 to partly account for that.
- Fantasy Football Calculator publishes 8/10/12/14-team ADP, not 15. Pick numbers are used directly, which is close but not exact.
- Projections are one source's view. The market blend limits the damage from any single bad projection, but a genuinely wrong depth-chart read will still propagate.
- Nothing here models in-season management, which decides more leagues than the draft does.
- The positional bet above is the single largest assumption in the report. It comes from one projection source's view of how many points each position will score, and if that view is wrong, every recommendation shifts with it.

