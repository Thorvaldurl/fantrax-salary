# Example run

What a gameweek-0 run actually produces, so the numbers below can be checked
against a fresh run rather than taken on faith. All figures are from a real
`--gameweek 0` run against the committed data
(`python -m fantrax_salary.cli --gameweek 0 --dry-run`), current as of this
weighting (20% projection / 60% last season / 15% / 5%, `blank_zero_seasons`
and `adp_fallback` both on, 2,500 floor).

Run it yourself and compare — see [Preview a run](#preview-a-run) below.

---

## Top of the pool

| Player | Position | Old salary | New salary |
| --- | --- | --- | --- |
| Bruno Fernandes | M | 15,000 | 15,000 |
| Erling Haaland | F | 12,500 | 11,900 |
| Elliot Anderson | M | 12,000 | 11,800 |
| James Tarkowski | D | 11,500 | 11,600 |
| Gabriel Magalhaes | D | 11,600 | 11,500 |
| Declan Rice | M | 11,800 | 11,500 |
| Bukayo Saka | M,F | 11,500 | 11,400 |

Bruno Fernandes sits at the 15,000 ceiling — the model can't price him any
higher regardless of how much better his score is than the field, because the
band caps out at the best score in the pool.

## Biggest movers

Risers are mostly players who were parked at the 2,000 template minimum with
a real 2025-26 record behind them — the model catching up to data that was
always there, not anything new in this change:

| Player | Position | Old salary | New salary | Change |
| --- | --- | --- | --- | --- |
| Liam Kitching | D | 2,000 | 6,600 | +4,600 |
| Dara O'Shea | D | 2,000 | 6,400 | +4,400 |
| Matt Grimes | M | 2,000 | 6,300 | +4,300 |
| Lukas Hornicek | G | 2,000 | 6,200 | +4,200 |
| Milan van Ewijk | D | 2,000 | 6,200 | +4,200 |

Fallers are mostly last year's breakouts the projection still rates highly,
now pulled back toward what they actually did over a full season:

| Player | Position | Old salary | New salary | Change |
| --- | --- | --- | --- | --- |
| Valentino Livramento | D | 13,500 | 10,100 | −3,400 |
| Dominic Solanke | F | 8,400 | 6,400 | −2,000 |
| Jarrad Branthwaite | D | 9,000 | 7,200 | −1,800 |
| Alejandro Garnacho | M,F | 7,000 | 5,300 | −1,700 |
| Wesley Fofana | D | 7,400 | 6,000 | −1,400 |

## Newcomers priced from draft ADP

Players with no completed Premier League season, priced from where the
league's own draft has them rather than the bottom of the pool
(`adp_fallback`, capped at pick 250, shrunk 0.7×):

| Player | Position | ADP | Salary |
| --- | --- | --- | --- |
| Bobby Thomas | D | 188.7 | 4,700 |
| Tarik Muharemovic | D | 189.9 | 4,500 |
| Johan Manzambi | M | 78.1 | 4,400 |
| Oliver McBurnie | F | 97.2 | 4,400 |
| Abdul Fatawu | F | 166.3 | 4,300 |
| Hayden Hackney | M | 153.7 | 4,300 |

Without this, every one of these would price at the 2,500 floor — Fantrax's
export gives them a literal `0.0` for a season they weren't in the league,
indistinguishable from "played and was useless." See the README's
["Players who have never played here"](../README.md#players-who-have-never-played-here)
for the full reasoning.

## At the floor

Players with no usable signal anywhere — no season record, no ADP inside the
first 250 picks (or no ADP at all):

| Player | Position | Salary |
| --- | --- | --- |
| Malachi Hardy | D | 2,500 |
| Nilson Angulo | M,F | 2,500 |
| Jeremy Monga | M,F | 2,500 |
| Rio Ngumoha | F | 2,500 |
| Aidan Dausch | F | 2,500 |

This is currently **37% of the pool** — the largest known weakness left in
the model (issue #3: no small-sample shrinkage, and issue #1: the floor is
what drives most of the remaining pool inflation). Not addressed by this
change; flagged here rather than hidden.

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
