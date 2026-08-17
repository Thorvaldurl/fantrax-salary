# Scoring system review

**Nothing here is implemented.** Scoring is a Fantrax league setting, not
something this repo can change. This is the answer to "can the scoring be made
more even", with the evidence for it, so the decision can be made deliberately.

The league's live settings were read from `getLeagueInfo`, and every number
below was recomputed from the actual 2025-26 match-by-match category counts
pulled from Fantrax, re-scored under today's rules. So a proposed change is
scored against the same real matches as the current system.

---

## The short version

1. **Defenders out-earn forwards by a wide margin**, and the roster rules let
   you act on it — a legal XI can contain **zero forwards**.
2. The cause is not one setting. It is the **high-volume defensive
   categories** (clearances, recoveries, duels, aerials, blocks) which a
   centre-back banks dozens of times a match and a striker never touches.
3. The **defender clean sheet at 4 points** compounds it.
4. Separately, there is a **straightforward bug** in the goalkeeper settings.

---

## The roster rules matter more than the scoring

From `getLeagueInfo.rosterInfo`:

| | |
| --- | --- |
| Active players | 11 |
| Max active | 1 G, 5 D, 5 M, 3 F |
| Total roster | 25 (14 reserve) |

The payload gives **maximums only — no minimums**. That is the crux: 1 G + 5 D
+ 5 M is exactly 11, so **a valid lineup need contain no forward at all**.

If forwards were required, absolute pricing would be defensible — you would
have to field them whatever they score. They are not required. So a scoring
system that pays defenders more is not a quirk of measurement, it is a
standing instruction to ignore an entire position.

> **Worth confirming in the Fantrax UI**, because the API does not expose
> minimums. If the league does enforce a minimum forward count, points 1-3
> below get much less urgent.

---

## Where the asymmetry is written into the settings

These are the position-specific rules, straight from the league config:

| Category | G | D | M | F |
| --- | --- | --- | --- | --- |
| Clean sheet on field | 5 | **4** | 1 | **0** |
| Goals (1st/2nd/3rd/4th+) | 25 flat | 4/5/6/7 | 4/5/6/7 | **5/6/7/8** |
| Assists (1st/2nd/3rd+) | 7.5 flat | 3/4/5 | **4/5/6** | 3.5/4.5/5.5 |
| Goals against | banded | −0.5/−1/−1.5 | −0.25/−0.5/−1 | **0** |

Two things stand out before any data is involved:

- **A forward gets nothing for a clean sheet and no penalty for conceding.**
  Their only exposure to the defensive half of the game is zero in both
  directions, so they are competing on attacking returns alone.
- **A forward is paid *less* per assist than a midfielder** (3.5 vs 4.0),
  while being paid more per goal (5 vs 4). Since midfielders out-assist
  forwards anyway, this compounds rather than offsets.

Everything else — the ~20 volume categories — is `Default`, identical for all
outfielders. That is where the imbalance actually comes from, and it is
invisible in the settings screen precisely *because* it is symmetrical. The
rates are equal; the opportunities are not.

---

## A genuine bug in the goalkeeper settings

Goals Against is banded, and the last band has the wrong sign:

```
0-1 goals    0.0 per goal
2-3 goals   -1.0
4-5 goals   -1.5
6-7 goals   -2.0
8+  goals   +3.0     <-- positive
```

Cumulative, that gives:

| Goals against | 5 | 6 | 7 | **8** | 9 | **10** |
| --- | --- | --- | --- | --- | --- | --- |
| Points | −5.0 | −7.0 | −9.0 | **−6.0** | −3.0 | **0.0** |

**A keeper who concedes 8 scores better than one who concedes 7**, and one who
concedes 10 is back to par. It is almost certainly meant to be `-3.0`.

This is rare enough that it has probably never decided a match — an 8-goal
game is roughly a once-a-decade event. It costs nothing to fix and should just
be fixed.

---

## The data: 2025-26, real matches, real scoring

Everything below is measured, not estimated — recomputed from every 2025-26
player's season category totals (321 players with 10+ games), scored through a
from-scratch implementation of the league's actual rules read from
`getLeagueInfo`. Methodology, including an honest accounting of where a
season-total shortcut would have been wrong and how that was avoided, is in
[`analysis/scoring_review/README.md`](../analysis/scoring_review/README.md).
Reproduce it with:

```bash
python analysis/scoring_review/simulate.py
```

### The gap is real, and bigger once dual-position players are handled correctly

Mean FP/G for each position's likely starters (the top `10 x typical-slots`
players by position, matching a standard 1-4-4-2ish lineup):

| Position | Starters' mean FP/G |
| --- | --- |
| D | **6.35** |
| M | 6.34 |
| G | 5.24 |
| F | **5.48** |

D and M are effectively tied for the top; F sits almost a full point per game
below D. The spread between the best and worst starting group is **1.25
FP/G** — over a 38-game season, that's the difference between a strong
defender and a mediocre forward *before either has played a match*, purely
from position.

It shows up directly in lineup construction: the highest-scoring **legal**
starting XI from 2025-26 form is **0 G / 5 D / 5 M / 1 F** — the model most
likely to win a head-to-head week fields almost no forwards at all, not
because good forwards don't exist, but because a mediocre defender
out-scores a good forward on category volume alone. (The 0 goalkeepers result
reflects the same absence of a documented minimum flagged above — treat it as
"defenders and midfielders dominate" more than literally "never start a
keeper".)

### Where the gap comes from

Mean points per game contributed by each category, restricted to flat-rate
categories (goals/assists/keeper-GA are banded and excluded here — see the
analysis README for why):

| Category | G | D | M | F | Spread |
| --- | --- | --- | --- | --- | --- |
| Sv (saves) | 1.93 | 0 | 0 | 0 | 1.93 |
| **CS (clean sheet)** | 1.38 | **0.96** | 0.21 | 0 | 1.38 |
| Min (minutes) | 1.79 | 1.49 | 1.28 | 1.04 | 0.75 |
| DW (duels won) | 0 | 0.63 | 0.53 | 0.43 | 0.63 |
| BR (ball recoveries) | 0 | 0.56 | 0.59 | 0.29 | 0.59 |
| CLR (clearances) | 0 | **0.55** | 0.14 | 0.09 | 0.55 |

Saves are goalkeeper-only by nature, not a design choice — set that aside. The
next two rows are the real story: **clean sheets pay defenders 0.96 FP/G on
their own**, nearly 1.4 points/game more than a forward gets from the same
category, and **clearances add another 0.46 FP/G gap** that forwards have no
equivalent counterweight for. Between just those two categories, a defender
banks close to 1.4 FP/G that a forward structurally cannot access — more than
the entire measured D-F gap.

### What moves the needle, tested

Every row below is the *exact* effect of the change on 2025-26's real
matches — not projected, computed as a delta against Fantrax's own reported
FPts (see the analysis README for why that's the trustworthy way to do it):

| Tweak | D | M | F | Spread | Best XI |
| --- | --- | --- | --- | --- | --- |
| *(current)* | 6.35 | 6.34 | 5.48 | 1.25 | 0G/5D/5M/1F |
| A: defensive volume categories x0.85 | 5.84 | 5.89 | 5.19 | 1.04 | 0G/4D/5M/2F |
| B: defensive volume categories x0.70 | 5.34 | 5.43 | 4.90 | 1.01 | 0G/4D/5M/2F |
| **C: defender clean sheet 4 → 2** | **5.76** | 6.34 | 5.48 | **0.86** | 0G/3D/5M/3F |
| D: defender clean sheet 4 → 3 | 6.05 | 6.34 | 5.48 | 1.04 | 0G/4D/5M/2F |
| E: A + C together | 5.24 | 5.89 | 5.19 | 0.77 | 0G/3D/5M/3F |

"Defensive volume categories" is clearances, ball recoveries, duels won,
aerials won, interceptions, blocked shots, tackles+blocks, blocked crosses,
successful dribbles+fouls suffered, accurate crosses, and successful final
third passes — the ~11 flat-rate categories a defender or a deep midfielder
racks up dozens of times a match and a forward almost never touches.

**The single most effective, most surgical change is C: cutting the defender
clean-sheet bonus from 4 points to 2.** One number, in one place in the
scoring config. It closes 31% of the spread on its own, and — unlike scaling
the volume categories — it doesn't touch midfielders or forwards at all, so it
can't have a side effect on a category that wasn't the problem. Scaling the
volume categories (A/B) closes a similar or smaller share of the gap while
depressing forwards' own (smaller) volume-category income too, which is why
it's a blunter instrument for the same result.

Whichever of these is used, expect a real cost: the eight defenders whose
FP/G drops most under a combined change (A+C) lose **1.4–2.0 FP/G**, and
they're specifically the highest clean-sheet defenders — Gabriel Magalhaes,
Marc Guehi, William Saliba, Ruben Dias among them. That's the point of the
change, but it's worth knowing whose value it reallocates before adopting it.

### Recommendation

If narrowing the D/F gap is wanted: **change the defender clean sheet bonus
from 4 to 2 or 3 points** (variant C or D above). It is a single-line change,
its effect is isolated and measured, and 2 gets closer to parity than 3 while
3 is the more conservative option if a smaller move is preferred. Pair it with
the goalkeeper Goals-Against sign fix from the section above regardless of
whether the balance change is adopted — that one has no real downside.

The volume-category scaling (A/B) is a reasonable alternative or complement if
a broader, position-symmetric adjustment feels fairer than singling out one
category, but it moves more surface area for a smaller effect on the specific
imbalance measured here.

Nothing here has been changed in the league's live settings — that's a
Fantrax commissioner action, and, as asked, this is deliberately just the
analysis to make that decision informed rather than a decision made for you.
