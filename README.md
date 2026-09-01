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

See [`docs/example-run.md`](docs/example-run.md) for what that report actually
looks like — real player prices from the committed data, annotated.

---

## The weekly routine

1. **Download the commissioner template.** Fantrax → League → Commissioner →
   Player Salaries → Export. Save it over `data/template/blank_2026-27.csv`.
   This file is both the list of players to price *and* the exact layout the
   upload must be in, so it is never reshaped. There is no API for this step —
   it is always a manual export, `--source api` or not.
2. **Run it** with `--gameweek N` (the default `--source api` pulls live
   statistics — no further downloads needed) and read the report.
3. **Upload** `output/SalGWN.csv` back into Fantrax.

`--source csv` is still available if you'd rather work offline — see
[Which source should I use?](#which-source-should-i-use) — but it needs a
second manual export (Fantrax → Players, **All players** selected, Stats
dropdown set to **"- YTD"** and not the default "Projected - Season") and,
for any season but the current one, can never be made to reflect a scoring
change no matter how often it's re-exported.

---

## Which source should I use?

```bash
python -m fantrax_salary.cli --gameweek 3               # api (default)
python -m fantrax_salary.cli --gameweek 3 --source csv  # hand-exported files
```

**`api`** pulls live statistics from Fantrax and is now the default. No manual
downloads, and nothing can go stale — because of a reason worth understanding:

> Each Fantrax season is a *separate league* with its own scoring settings, and
> an export is always scored under the rules of the league it came from. The
> checked-in `2425.csv` was exported from the 2024-25 league, so it is scored
> under *that* season's rules, permanently — re-exporting it later doesn't
> help, because that archival league's settings are frozen. Requesting 2024-25
> through the *current* league instead returns the same matches re-scored under
> **today's** rules — which is what you actually want when comparing seasons.
> The two differ by about 3 fantasy points per player on average, and they
> disagreed for 258 of the 361 players present in both, at the time this was
> measured.

**`csv`** reads the hand-exported files in `data/`. Fully offline, and the only
mode that doesn't depend on Fantrax's undocumented internal RPC staying stable
— but for any season except the current one, no amount of re-exporting can make
it reflect a scoring change, since the file it reads from is permanently locked
to that season's own now-archived league. It's kept as an option for that
offline/reproducibility case, not because it's more correct.

The default was `csv` until this project's own scoring review led to an actual
scoring change being adopted — see [`docs/scoring-review.md`](docs/scoring-review.md)
— at which point `csv`'s three older, unfixable-by-re-export seasons (weighted
0.80 of the blended score, see `DEFAULT_SEASONS`) made it the wrong default to
leave in place.

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
| `freeze_rostered` | `true` | Leave players already on a roster at their current salary |
| `rate_shrinkage` | `true` | Regress a small-sample FP/G toward the positional average |
| `shrinkage_k` | 7 | Weight of the prior, in games-played terms |
| `shrinkage_min_games` | 10 | Below this, a season's rate is shrunk; at or above, it's trusted outright |

---

## Players who have never played here

A Fantrax export lists every player in the current pool for every season, so
someone who was not in the league last year comes back as a literal `0.0`
rather than a blank. Scored as written, "did not play" is indistinguishable
from "played and was useless" — and **298 of the 709 players in the current
pool** have no record in any completed season, including everyone at the
promoted clubs.

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

## Rostered players are not repriced

A player already on a manager's roster was bought at a price, and that price
is the term of the deal. Repricing them mid-season moves money around inside a
squad that has already been paid for, so **`freeze_rostered`** holds every
owned player at whatever the template already says and reprices only free
agents — the salary update prices *the market*, not existing contracts.

Owned players are still scored, and still count toward the scale everyone else
is priced against. Dropping them from the pool entirely would reprice the whole
league against a smaller and unrepresentative sample, which is a much bigger
change than the one intended; only the written salary is held.

Rosters come from `/fxea/general/getTeamRosters` — the *documented* API, which
needs no auth and carries no client version, so this particular lookup cannot
be broken by the `STALE_CLIENT` drift that affects the statistics endpoint. It
is a live lookup in both `--source` modes, since there is no roster export to
read offline. If it fails the run stops rather than silently repricing all ten
squads; set `freeze_rostered` to `false` in a config file to reprice everyone
on purpose.

The commissioner template is exported before the rosters are read, so a player
transferred in between shows up as "not in the template" and is warned about —
re-export the template if a squad has changed.

## Small samples

A rate (FP/G) measured over a handful of games is mostly noise, and it cuts
both ways: a player who had one brilliant substitute appearance scores
identically to one who sustained that rate over a full season, and a good
player who was rotated or injured looks exactly as bad as one who is
genuinely poor.

**`rate_shrinkage`** regresses a season's FP/G toward the positional average
whenever the sample is small, weighted by how many games actually back it
up (`adjusted = (FPts + k·prior) / (GP + k)`, the standard form). A player
with a real, substantial season (`shrinkage_min_games` or more) keeps their
own rate untouched — the correction is confined to genuinely small samples,
not applied to everyone.

This does not fix every case that looks like it should be helped. A player
with 15-20 games and a modest rate is not a small sample — their number is
real, and shrinking it would manufacture a correction that isn't there. See
[`docs/example-run.md`](docs/example-run.md#small-sample-shrinkage) for a
worked example of both: a genuine one-game fluke that gets corrected, and a
real-but-modest player who (correctly) doesn't.

---

## Results, not projections

The heaviest input used to be Fantrax's preseason projection, at 70%. It is now
20%, with 60% on last season's actual results.

The projection is not neutral. Moving weight onto real results drops
goalkeepers by around 3,000 (Petrovic 10,500 → 7,700, Martinez 9,500 → 6,500)
and lifts attackers (Haaland 10,800 → 11,900) — it was stacking a second
positional bias on top of the one already present in the scoring system, which
[`docs/scoring-review.md`](docs/scoring-review.md) measures.

It is not dropped to zero because the promoted clubs have no Premier League
record at all, and the projection is the only thing standing between their
squads and the floor. At 0% the number of floored players rises to 336, against
248 at the current weighting and 292 under the old one.

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
| Best possible 15 | 165,000 — **165% of the cap** |
| Cheapest legal 15 | 37,500 — 38% |
| All 150 rostered players | 1,141,700 — **114% of all ten caps** |

So a manager can afford roughly **half** the distance from the worst legal
squad to the best, and the league collectively cannot buy the whole desirable
pool — good players are left on the market. That is the intended behaviour.

Worth re-checking if the roster size, cap, or floor ever change: at a 25-man
squad the 2,500 floor alone would commit 62,500 of the 100,000 cap, and the
affordable share collapses from ~50% to ~19%.

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
  test_model.py                 pins the original arithmetic and tests
                                 everything since (newcomer pricing, ADP
                                 fallback, shrinkage, validation)
docs/
  example-run.md       a real run, annotated, with reproduction steps
  scoring-review.md     league scoring-balance analysis (nothing implemented
                         here — a Fantrax commissioner action, not code)
analysis/
  scoring_review/       the standalone engine + cached data behind the above
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
- players with no stats in any season are counted: a *majority* of the pool
  means the ids do not line up and is fatal, while a minority is just genuine
  newcomers and only warns, since the model already prices them toward the
  floor. It used to be fatal either way, which taught the operator to reach
  for `--force` — and `--force` silences every other check in this list too
- team rosters were actually readable, so existing contracts can be held
- the current-season file doesn't look like a leftover preseason projection
  once games have actually been played (see the weekly routine above)
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
as the oracle: with every setting above switched off (`blank_zero_seasons`,
`adp_fallback`, `rate_shrinkage`, and the original season weights), the suite
asserts the pipeline reproduces its output exactly, salary for salary. A normal
run does not match it — that's the point. Everything that's since made it
diverge deliberately is itself under test, so a future scoring change is
provably intended rather than accidental.

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

The model's arithmetic has been deliberately changed a few times since the
restructuring — the season weights, newcomer pricing, and small-sample
shrinkage above are all departures from the original script, each landed with
the reference-implementation test updated on purpose, so the change is
visible and intended rather than accidental.

What's fixed and what's still open is tracked in
[issue #2](../../issues/2) and kept current there rather than duplicated here,
since a status list in a README drifts out of date exactly like the numbers
above did. Roughly: small-sample shrinkage and the dead tail-season weights
are done; the pool-wide inflation ratchet, positional bias in the *model*
(as opposed to the scoring settings — see `docs/scoring-review.md`), and a
few smaller items are not.
