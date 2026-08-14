# Fantrax salary update

Recalculates player salaries for the **Fullorðnir menn í fýlu** EPL league and
writes the CSV that gets uploaded back into Fantrax.

Players are scored from their fantasy points across several seasons, weighted
toward the most recent, and each salary then moves part of the way toward that
score's implied value. Nobody's salary jumps in one step.

---

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

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
| `seasons[].weight` | 0.70 / 0.25 / 0.04 / 0.01 | How much each season counts |

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
