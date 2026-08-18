# Notes for agentic coding tools

This file is for an AI agent picking up work in this repo — conventions,
gotchas, and traps that aren't obvious from reading the code once. For what
the project *does* and how a human runs it, read [README.md](README.md)
first; this file assumes that context and doesn't repeat it.

---

## Before touching `model.py`

**Every change to the scoring arithmetic must be a config-flagged, default-on
behaviour, not a silent edit** — the pattern already used throughout is
`blank_zero_seasons`, `adp_fallback`, `rate_shrinkage`. This isn't a style
preference: `tests/test_model.py` pins the *original* script's output exactly
via `reference_implementation.py`, using a `cfg` fixture with every new flag
switched off and `config.LEGACY_SEASONS` for the weights. If you change
default arithmetic without a flag, that test breaks and it's *supposed to* —
add the flag, keep the oracle guarded, and let the new behaviour live in
`current_cfg` (flags on) instead. This is what makes a future scoring change
provably deliberate rather than accidental, which is a stated design goal of
the whole refactor — don't erode it for convenience.

**Validate against the real committed data before calling anything done, not
just synthetic unit tests.** Twice in this repo's history a change that
looked correct in isolation broke under the real data's actual distribution:

- A first attempt at small-sample shrinkage shrank *every* player, not just
  small samples. On synthetic test data with a handful of rows this looked
  fine. Against the real 709-player pool it compressed the whole
  `normalise()` scale (min-max over the whole column) and nearly re-broke the
  exact case it was built to fix — a small-sample player's *relative*
  position moved the wrong way even though their own raw number improved.
- The same attempt also shrank the *projection* season's FP/G, because
  `FPts / FP-per-G` looks like a games-played count for any season — but for
  the projection slot (`config.seasons[0]`) it's an artefact of whatever a
  forecast happens to divide to, not a real sample size. For one player this
  implied a fake "2 games played" and crushed their number for no reason.

Both are now documented as comments in `model.shrink_rates` at the point they
matter, specifically so the mistake isn't repeated. The general lesson: any
transform that touches the *extremes* of a column interacts with
`normalise()`'s global min-max scaling in ways that are easy to miss by
reasoning about one player at a time. Run `python -m fantrax_salary.cli
--gameweek 0 --dry-run` and spot-check a handful of real names (a known
star, a known fringe player, a known small-sample player) before trusting a
change.

---

## Fantrax's undocumented API — traps that cost real time here

The client lives in `fantrax_salary/api.py`; this is what wasn't obvious
getting there.

- **`getPlayerProfile` (per-player game logs) throttles hard and silently.**
  Under load it doesn't error — it returns HTTP 200 with an *empty* payload,
  which looks exactly like a bug in your own parsing code. The actual signal
  is `pageError.text` on the raw response: `"You're viewing player profiles
  too quickly. Please slow down and try again shortly."` Check for that
  explicitly; don't assume silence means "no data for this player." Once
  tripped, it does not clear quickly — spacing requests out further doesn't
  help once you're already rate-limited, only waiting does.
- **`getPlayerStats`, grouped by position, is the better tool for
  category-level data and is not throttled.** Pass `positionOrGroup` as one
  of `POS_701`/`POS_702`/`POS_703`/`POS_704` (F/M/D/G) with
  `scoringCategoryType: "5"` ("Tracked") and you get every raw scoring
  category's *season total* for that whole position group — the entire
  league in 4 requests instead of one per player. Querying `positionOrGroup:
  "ALL"` truncates the response to a handful of summary columns; you only get
  the full category breakdown by asking for one position group at a time.
  This isn't documented anywhere Fantrax publishes — it was found by
  inspecting what the site's own UI calls when you filter to a single
  position and expand "Scoring Category: Extra/Tracked". See
  `analysis/scoring_review/README.md` for the full account.
- **A dual-eligible player scores differently per position query.** Someone
  listed "D,M" comes back once from the `POS_703` query and once from
  `POS_702`, and Fantrax scores each copy under *that query's* position rates
  — not the same FPts twice. Deduplicate by the player's *primary* listed
  position (first in the template's Position column, same convention
  `sources.py` uses) or you'll double-count them and price half the copies
  under the wrong rules.
- **Games played isn't a CSV column, but it's exact from what is.**
  `round(FPts / FP-per-G)` reconstructs true GP with zero mismatches,
  verified against 414 real players from an endpoint that reports GP
  directly. Don't add a new data source just to get this.
- **A season CSV's `0.0` doesn't mean "scored zero."** It means "not in the
  league that season" as often as not — Fantrax exports every current-pool
  player for every season file. `model.blank_zero_seasons` exists because of
  this; don't reintroduce a raw `.fillna(0)` anywhere in the scoring path.

---

## Workflow conventions actually followed in this repo's history

- **Feature branch → PR → merge → delete branch → checkout+pull main**, every
  time, for anything that touches `fantrax_salary/` or its tests. Direct
  pushes to `main` have only been done for pure-documentation changes, and
  only when explicitly asked for.
- **GitHub issue #2 is the live scoring backlog** — treat it as the source of
  truth for what's fixed vs. open, and update it (a comment, not editing the
  original report) when something in it changes state, rather than
  duplicating a status list in the README where it'll drift. It already has
  drifted once; that's why this file exists.
- **Numbers quoted in prose (READMEs, docstrings, issue comments) go stale
  the moment the model changes.** Every specific number in `README.md` was
  re-derived from a live run while auditing it, not assumed to still be
  correct because it was correct once — do the same before trusting a quoted
  figure, especially after touching `model.py` or `config.py`'s defaults.

---

## Repo-specific mechanics

- Python 3.9, single `venv/` at the repo root (already gitignored). No other
  environment managers in use.
- `analysis/scoring_review/` is a standalone investigation with its own small
  scoring engine (`scoring.py`) and cached data — it does **not** import from
  or get imported by `fantrax_salary/`. Don't assume changes to
  `fantrax_salary/model.py`'s scoring affect it, and vice versa; they
  answer different questions (salary pricing vs. league scoring-setting
  balance) using different, independently-validated engines.
- This machine's OpenSSL/LibreSSL mismatch prints a `NotOpenSSLWarning` on
  every `requests` import — harmless noise, not a real problem; existing
  shell examples in this codebase's history pipe through
  `grep -v Warning` when the output needs to be clean for a demo.
- `output/` is gitignored on purpose (see README's Layout section) — never
  commit anything under it, including when demonstrating a run's results to
  someone.
