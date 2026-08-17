# Fantrax salary update

Recalculates player salaries for the **Fullorðnir menn í fýlu** EPL league and
writes the CSV that gets uploaded back into Fantrax.

Players are scored from their fantasy points across several seasons, weighted
toward the most recent, and each salary then moves part of the way toward that
score's implied value. Nobody's salary jumps in one step.

> **Note:** the pre-refactor version of this project (the original flat
> script, before the restructuring into the `fantrax_salary` package) is kept
> on the [`archive/legacy-main`](../../tree/archive/legacy-main) branch for
> reference. It is not maintained and should not be built on.

---

## Quick start

**First time only** — create the environment and install the dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Every time after** — the `venv` folder already exists, so just activate it:

```bash
source venv/bin/activate
```

On Windows that last line is `venv\Scripts\activate` instead.

You are in the environment when your prompt is prefixed with `(venv)`. It lasts
for that terminal window only, so it has to be re-run each time you open a new
one. `deactivate` leaves it; deleting the `venv` folder and repeating the
first-time steps rebuilds it from scratch if it ever gets into a bad state.

Then, each gameweek:

```bash
python -m fantrax_salary.cli --gameweek 3
```

This writes three files into `output/`:

| File | What it is |
| --- | --- |
| `SalGW3.csv` | **The upload file.** Fantrax → League → Commissioner → Player Salaries → Import |
| `SalGW3.xlsx` | Full working sheet — every intermediate column, for eyeballing |
| `SalGW3.report.txt` | The run report, saved alongside |

Look at the report before uploading. To see it without writing anything:

```bash
python -m fantrax_salary.cli --gameweek 3 --dry-run
```

---

## The weekly routine

1. **Download the commissioner template.** Fantrax → League → Commissioner →
   Player Salaries → Export. Save it over `data/template/blank_2026-27.csv`.
   This file is both the list of players to price *and* the exact layout the
   upload must be in, so it is never reshaped.
2. **Download the current stats.** Fantrax → Players, with **All players**
   selected — not just available. Save over `data/current/gw1.csv`.

   > **Check the Stats dropdown.** It defaults to **"Projected - Season"**,
   > which is Fantrax's *forecast of the whole season*, not results. Once the
   > season has started you want **"2026-27 - YTD"**. An export taken on the
   > default looks completely normal, so the run warns if the file implies far
   > more football than has actually been played.
3. **Run it** with `--gameweek N` and read the report.
4. **Upload** `output/SalGWN.csv` back into Fantrax.

Or skip steps 2 and 3's staleness risk entirely with `--source api` — see below.

---

## Which source should I use?

```bash
python -m fantrax_salary.cli --gameweek 3               # csv (default)
python -m fantrax_salary.cli --gameweek 3 --source api  # live from Fantrax
```

**`csv`** reads the hand-exported files in `data/`. Reproducible, offline, and
the only mode whose numbers match historical runs.

**`api`** pulls the same statistics live. No manual downloads and nothing can go
stale — but the numbers differ, for a reason worth understanding:

> Each Fantrax season is a *separate league* with its own scoring settings, and
> an export is always scored under the rules of the league it came from. The
> checked-in `2425.csv` was exported from the 2024-25 league, so it is scored
> under *that* season's rules. Requesting 2024-25 through the current league
> instead returns the same matches re-scored under **today's** rules — which is
> what you actually want when comparing seasons. The two differ by about 3
> fantasy points per player on average, and they disagree for 258 of the 361
> players present in both.

So `api` is the more *correct* input and `csv` is the more *reproducible* one.
The default stays `csv` until a scoring change is deliberately adopted.

---

## Configuration

Everything tunable lives in `fantrax_salary/config.py` with a name and a
comment. Nothing in `model.py` contains a bare number.

To change values without editing code, copy `config.example.json` and pass it:

```bash
cp config.example.json config.json
python -m fantrax_salary.cli --config config.json --gameweek 3
```

Precedence is **defaults → config file → CLI flags**.

| Setting | Default | Meaning |
| --- | --- | --- |
| `salary_target_min` | 4,000 | Salary earned by a league-average score |
| `salary_target_max` | 15,000 | Salary earned by the best score in the pool |
| `salary_floor` | 2,500 | Nothing may be priced below this |
| `damping` | 0.5 | Fraction of the gap to the target applied per run |
| `seasons[].weight` | 0.20 / 0.60 / 0.15 / 0.05 | How much each season counts |
| `blank_zero_seasons` | `true` | Read a 0-point, 0-per-game season as "was not here" |
| `adp_fallback` | `true` | Use draft ADP to price players with no record |
| `adp_weight` | 0.25 | How much ADP counts, when it counts at all |
| `adp_max_pick` | 250 | Past this pick ADP is ignored as uninformative |
| `adp_shrinkage` | 0.7 | Pull-back applied to the fitted ADP curve |

---

## Players who have never played here

A Fantrax export lists every player in the current pool for every season, so
someone who was not in the league last year comes back as a literal `0.0`
rather than a blank. Scored as written, "did not play" is indistinguishable
from "played and was useless" — and **324 of the 709 players in the current
pool** are in that position, including everyone at the promoted clubs.

Two settings deal with this, and both can be turned off:

- **`blank_zero_seasons`** treats a season of 0 points in 0 games as missing.
  The weight renormalisation already in the model then prices the player on
  whatever they *do* have, instead of averaging them against a zero.
- **`adp_fallback`** brings in the league's own draft. Average draft position
  is the only independent read available on a player with no Premier League
  record, and it is available before a ball is kicked. The ADP-to-output curve
  is fitted from the pool on every run rather than hard-coded, so it
  re-calibrates each season.

ADP is deliberately limited. It is used only for players with no completed
season, only inside the first `adp_max_pick` picks, and only at
`adp_weight`. Past the end of the draft everyone shares an ADP near the bottom
of the list and 62% of them never play a minute, so reading value into those
numbers just lifts third-choice goalkeepers off the floor.

This matters most at **gameweek 0**, because that run's salaries are the ones
the draft is played with.

---

## Results, not projections

The heaviest input used to be Fantrax's preseason projection, at 70%. It is now
20%, with 60% on last season's actual results.

The projection is not neutral. Moving weight onto real results drops
goalkeepers by around 2,500 (Petrovic 10,500 → 8,000, Martinez 9,500 → 6,800)
and lifts attackers (Haaland 10,800 → 11,900) — it was stacking a second
positional bias on top of the one already present in the scoring system, which
[`docs/scoring-review.md`](docs/scoring-review.md) measures.

It is not dropped to zero because the promoted clubs have no Premier League
record at all, and the projection is the only thing standing between their
squads and the floor. At 0% the number of floored players rises to 335, against
264 at the current weighting and 295 under the old one.

**During the season, the fix is the export, not the config** — take the
"- YTD" view rather than "Projected - Season" (see the weekly routine above)
and the current-season slot becomes real results automatically. For
`--source api`, change the `2627` season's `api_code` from
`PROJECTION_0_926_SEASON` to `SEASON_926_YEAR_TO_DATE`.

---

## Does the cap still bind?

The league is 10 teams, a 15-man squad (2 GK + 13 OF), and a 100,000 salary
cap. For the draft to involve any real choices, the best possible squad has to
cost *more* than the cap — otherwise everyone buys the same team and the draft
is just turn order.

At the current weighting:

| | |
| --- | --- |
| Best possible 15 | 166,300 — **166% of the cap** |
| Cheapest legal 15 | 37,500 — 38% |
| All 150 rostered players | 1,162,200 — **116% of all ten caps** |

So a manager can afford roughly **half** the distance from the worst legal
squad to the best, and the league collectively cannot buy the whole desirable
pool — good players are left on the market. That is the intended behaviour.

Worth re-checking if the roster size, cap, or floor ever change: at a 25-man
squad the 2,500 floor alone would commit 62,500 of the 100,000 cap, and the
affordable share collapses from ~50% to ~17%.

---

## Layout

```
fantrax_salary/
  config.py    every tunable number, one place
  model.py     the scoring and salary maths (pure; no I/O)
  sources.py   loading inputs — csv and api produce the same frame
  api.py       Fantrax client
  validate.py  input checks that run before anything is computed
  report.py    the run report
  cli.py       argument parsing and orchestration
data/
  template/    commissioner spreadsheets (the upload skeleton)
  seasons/     completed-season exports
  current/     the in-progress season export
tests/
  reference_implementation.py   the original script, kept as a test oracle
  test_model.py                 asserts the refactor changed no numbers
output/        generated; git-ignored
```

`output/` is deliberately **not** committed. Results are reproducible from their
inputs, and committing them is exactly how the repo previously ended up with a
`SalGW1.csv` that no longer matched the data that produced it.

---

## Validation

Checks run before any salary is computed, because a wrong or half-downloaded
file otherwise produces plausible-looking numbers rather than an error:

- the template has the expected columns, no duplicate ids, numeric salaries
- every season actually matched some players — a wholly unmatched file is fatal
- no player is left without stats in any season
- stats files are warned about when stale, or older than the template they are
  being joined to

Problems stop the run; warnings do not. `--force` overrides problems, but it
**cannot** override the final guard: if any player would be written without a
salary, the upload file is not produced at all.

---

## Tests

With the environment active:

```bash
pip install -r requirements-dev.txt
pytest
```

The original script is preserved at `tests/reference_implementation.py` and used
as the oracle: the suite asserts the restructured pipeline reproduces its output
exactly, salary for salary. That is what makes this refactor safe to trust, and
what will make a future scoring change provably deliberate.

---

## When the API breaks

The statistics come from `/fxpa/req`, the internal RPC the Fantrax web app uses.
It is not a published contract. Every request carries a client version, and the
server rejects stale ones with `STALE_CLIENT` — this **will** happen eventually,
after some Fantrax deploy.

The error tells you the fix:

```bash
python -m fantrax_salary.cli --discover-api-version
```

That reads the live site's JavaScript bundle, extracts candidate versions, and
returns the first one the server actually accepts. Put it in your config as
`api_version`. (The documented `/fxea/general/*` API is stable but has no
statistics endpoint at all, so it cannot be used instead.)

To see which seasons the league can serve:

```bash
python -m fantrax_salary.cli --list-seasons
```

---

## Known issues with the scoring

The model's *arithmetic* is unchanged by the current restructuring, but several
weaknesses are documented and open — pool-wide salary inflation, a strong
positional bias, outlier sensitivity, and the fact that the highest-weighted
input is Fantrax's **projections** rather than results. See the repository
issues before changing any weights.
