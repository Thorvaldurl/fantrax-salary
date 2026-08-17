# Scoring review — supporting analysis

Backs [`docs/scoring-review.md`](../../docs/scoring-review.md). Not part of the
salary pipeline — `fantrax_salary` never imports anything here.

```
scoring.py    a standalone re-implementation of the league's scoring rules,
              parsed straight from data/leagueinfo.json's scoringSystem
simulate.py   positional balance under current scoring, and the effect of
              candidate tweaks, run against data/season_2526_categories.json
data/         cached inputs -- see below
```

Run it from the repo root:

```bash
python analysis/scoring_review/simulate.py
```

## Why the data is cached rather than fetched live

`data/season_2526_categories.json` is every 2025-26 player's season-total
count in every scoring category (goals, tackles, clean sheets, minutes, the
lot), pulled from Fantrax's `getPlayerStats` RPC with `scoringCategoryType=5`
("Tracked") and `positionOrGroup` set to each of G/D/M/F in turn — four
requests for the whole league, not one per player. `data/leagueinfo.json` is
the scoring rules and roster settings from `getLeagueInfo`, trimmed to the
fields this analysis uses.

Getting this data was not straightforward and the trap is worth recording:
Fantrax's **player-profile** endpoint (`getPlayerProfile`, used for individual
game logs) throttles hard after a few hundred requests and answers with a
plain-text warning (`"You're viewing player profiles too quickly"`) rather
than an HTTP error — easy to miss if you're not checking for it, and it does
not clear quickly once tripped. The **stats-table** endpoint used here
(`getPlayerStats`) is a completely different code path and was not
rate-limited at all across this whole pull. If this needs re-running for a
newer season, prefer `getPlayerStats` grouped by position over iterating
`getPlayerProfile` per player — it is both faster (4 requests vs 700+) and
does not risk the throttle.

## The season-total tradeoff, and why it's handled the way it is

Category counts summed over a whole season are **exact** for flat-rate
categories (points per unit — the large majority: tackles, clearances, duels,
minutes, clean sheets, etc.) because order doesn't matter for a sum.

They are **wrong** for the three banded categories — Goals, Assists (Total),
and goalkeeper Goals Against — which reset their point tier every match.
Summing a whole season into one number and running it through the band table
either strings together tiers that were never contiguous in reality, or
collapses many separate "first goal of the match" bonuses into one long run.
Measured effect: reconstructing full-season FPts this way gives a 14% median
error, and one goalkeeper was overstated by +225 points purely from Goals
Against banding.

So `simulate.py` does not use season totals to reconstruct FPts at all.
Instead:

- **Current-scoring balance** comes straight from Fantrax's own reported
  `FPts`/`FP/G` — no reconstruction, so the banding issue cannot enter it.
- **A tweak's effect** is computed as a *delta*: only the tweak's flat-rate
  categories are scored, under current rules and under the proposed rules, and
  the difference is added to the reported FPts. The banded categories are
  identical on both sides of that subtraction and cancel out, so the delta is
  exact even though summing FPts directly would not be.
- Tweaks that touch a banded category (e.g. paying forwards more per goal) are
  therefore reported qualitatively only. Simulating those accurately needs
  per-game logs, which is the endpoint that throttles — a possible future
  follow-up, not attempted here.

## A duplication worth knowing about if you extend this

`getPlayerStats` scores a dual-eligible player (e.g. "D,M") once per position
they're eligible for, under *that position's own rates* — Matheus Nunes shows
up as both a D (247.47 FPts, defender clean-sheet rate) and an M (222.47 FPts,
midfielder rate) for the identical season. `simulate.py` keeps only the copy
matching the player's primary position from the commissioner template (the
same convention `fantrax_salary/sources.py` uses), so nobody is double-counted
and nobody is silently scored under the wrong position's rates.
