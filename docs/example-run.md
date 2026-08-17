# Example run

What a gameweek-0 run actually produces, so the numbers below can be checked
against a fresh run rather than taken on faith. All figures are from a real
`--gameweek 0` run against the committed data
(`python -m fantrax_salary.cli --gameweek 0 --dry-run`), current as of this
weighting (20% projection / 60% last season / 15% / 5%, `blank_zero_seasons`,
`adp_fallback`, and `rate_shrinkage` all on, 2,500 floor).

Run it yourself and compare — see [Preview a run](#preview-a-run) below.

---

## Top of the pool

| Player | Position | Old salary | New salary |
| --- | --- | --- | --- |
| Bruno Fernandes | M | 15,000 | 15,000 |
| Erling Haaland | F | 12,500 | 11,900 |
| Elliot Anderson | M | 12,000 | 11,800 |
| James Tarkowski | D | 11,500 | 11,500 |
| Bruno Guimaraes | M | 11,600 | 11,400 |
| Gabriel Magalhaes | D | 11,600 | 11,400 |
| Declan Rice | M | 11,800 | 11,400 |

Bruno Fernandes sits at the 15,000 ceiling — the model can't price him any
higher regardless of how much better his score is than the field, because the
band caps out at the best score in the pool.

## Biggest movers

Risers are mostly players who were parked at the 2,000 template minimum with
a real 2025-26 record behind them — the model catching up to data that was
always there, not anything new in this change:

| Player | Position | Old salary | New salary | Change |
| --- | --- | --- | --- | --- |
| Liam Kitching | D | 2,000 | 6,700 | +4,700 |
| Dara O'Shea | D | 2,000 | 6,500 | +4,500 |
| Matt Grimes | M | 2,000 | 6,300 | +4,300 |
| Milan van Ewijk | D | 2,000 | 6,300 | +4,300 |
| Lukas Hornicek | G | 2,000 | 6,200 | +4,200 |

Fallers are a mix of two different things, both explained below: last year's
breakouts the projection still rates highly, and single-game flukes that
`rate_shrinkage` now catches.

| Player | Position | Old salary | New salary | Change |
| --- | --- | --- | --- | --- |
| Valentino Livramento | D | 13,500 | 10,000 | −3,500 |
| Dominic Solanke | F | 8,400 | 6,200 | −2,200 |
| **Walter Benitez** | **G** | **6,400** | **4,400** | **−2,000** |
| Jarrad Branthwaite | D | 9,000 | 7,000 | −2,000 |
| Alejandro Garnacho | M,F | 7,000 | 5,100 | −1,900 |

## Newcomers priced from draft ADP

Players with no completed Premier League season, priced from where the
league's own draft has them rather than the bottom of the pool
(`adp_fallback`, capped at pick 250, shrunk 0.7×):

| Player | Position | ADP | Salary |
| --- | --- | --- | --- |
| Bobby Thomas | D | 188.7 | 4,800 |
| Tarik Muharemovic | D | 189.9 | 4,600 |
| Abdul Fatawu | F | 166.3 | 4,500 |
| Hayden Hackney | M | 153.7 | 4,500 |
| Johan Manzambi | M | 78.1 | 4,500 |
| Oliver McBurnie | F | 97.2 | 4,500 |

Without this, every one of these would price at the 2,500 floor — Fantrax's
export gives them a literal `0.0` for a season they weren't in the league,
indistinguishable from "played and was useless." See the README's
["Players who have never played here"](../README.md#players-who-have-never-played-here)
for the full reasoning.

## Small-sample shrinkage

**Walter Benitez, from the fallers table above, is the clearest real example.**
His entire 2025-26 was one appearance, at exactly 10.00 FP/G — the single
best rate in the whole pool that season, purely because a great one-game
sample is indistinguishable from a great *season* to a model that only looks
at the rate. `rate_shrinkage` pulls it toward what a typical goalkeeper does,
weighted by how little evidence backs it up: shrinkage alone accounts for
−700 of his −2,000 move (5,100 → 4,400; the rest is the reweight described
below).

The correction runs both ways — a good player who had one bad game is pulled
back *up* toward the positional average, not left looking like a bust — and
it's deliberately narrow: a player with a real, substantial season (10+
games) keeps their own rate untouched. The scale's best full-season rate,
Bruno Fernandes at 9.79 FP/G, is completely unaffected by this change. See
`model.shrink_rates` for the mechanics, including an incidental benefit: the
pool's normalisation range used to be set by two single-game outliers; it's
now anchored on genuine full-season performances instead.

## At the floor

**37% of the pool floors to 2,500, and it is not one population.** Two very
different situations get collapsed into the identical price, which is worth
knowing before reading too much into any one floored player:

**183 players (74% of the floor) have no signal at all** — no completed
season, no ADP inside the first 250 picks. This is the floor doing its job:
there is genuinely nothing to price them on.

| Player | Position | Salary |
| --- | --- | --- |
| Chuba Akpom | F | 2,500 |
| Sean Steur | M | 2,500 |
| Dermot Mee | G | 2,500 |
| Tom Proctor | M | 2,500 |
| Brandon Austin | G | 2,500 |

**65 players (26% of the floor) have a real, if modest, 2025-26 record —**
and price identically to the players above despite that. Rio Ngumoha is the
clearest case: 69.42 FPts at 3.65 FP/G over roughly 19 games, which sits at
the **34th percentile** of players who played last season — a real rotation
player, not an unknown.

| Player | Position | 2025-26 FPts | FP/G | Salary |
| --- | --- | --- | --- | --- |
| Ao Tanaka | M | 94.43 | 3.37 | 2,500 |
| Andrey Santos | M | 83.26 | 3.08 | 2,500 |
| Rio Ngumoha | F | 69.42 | 3.65 | 2,500 |
| Jorrel Hato | D | 60.34 | 2.74 | 2,500 |
| Wilfried Gnonto | F | 59.68 | 2.59 | 2,500 |

`rate_shrinkage` (above) does not fix this, and honestly, it shouldn't try
to: at 19 games, Ngumoha's own rate is a reliable-enough sample, not noise —
shrinking it would manufacture a correction that isn't there. His price is
low mainly because his *cumulative* FPts is low, and that's a genuine
consequence of appearing in only about half the season, which is real
information, not a data gap. What's actually happening is that the 2,500
floor is where "genuinely no signal" and "real but below-average" get
collapsed into one price — a granularity problem at the bottom of the scale,
distinct from anything fixed here. It's the same mechanism issue #1 in the
project backlog complains about from the other direction (the floor
one-way-ratcheting the pool up); this is what it looks like from below.

---

## Preview a run

Compute and print the full report without writing any files:

```bash
python -m fantrax_salary.cli --gameweek 0 --dry-run
```

Swap in whatever gameweek you're actually pricing. The report shows the same
sections as above — scale, pool total, position breakdown, ADP-priced
newcomers, biggest movers — for the live data currently in `data/`, so it's
the way to check "what would this actually do" before committing to an
upload.

To see it against live Fantrax data instead of the checked-in CSVs:

```bash
python -m fantrax_salary.cli --gameweek 0 --dry-run --source api
```

Drop `--dry-run` only when ready to write `output/SalGW<N>.csv` and upload it.
