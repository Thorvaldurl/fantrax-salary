# Scoring system review

**Nothing here is implemented by this repo.** Scoring is a Fantrax league
setting. This is the evidence for deciding it deliberately.

> **Revised.** This document originally argued that the scoring imbalance was
> urgent because a legal lineup could field zero forwards. **That was wrong** —
> the roster rules were confirmed in the Fantrax UI and every position has a
> minimum of one. The original text flagged this as the one assumption that
> could overturn its conclusion, and it did. See
> [What the first version got wrong](#what-the-first-version-got-wrong).
>
> **Second revision: the changes below are no longer proposals.** Defender
> clean sheet 4 → 3, effective clearances 0.15 → 0.12, and the goalkeeper
> Goals-Against sign fix are all **live**, confirmed directly against the
> Fantrax API. Every number in this document is now measured **exactly**
> against real reported FPts — the earlier delta-approximation method (needed
> because banded categories couldn't be reconstructed from season totals) is
> no longer necessary, because re-pulling live data after a scoring change
> turned out to just work: Fantrax re-scores historical seasons under whatever
> rules are currently live, banding included. That was verified, not assumed —
> see [Confirming the live numbers](#confirming-the-live-numbers).

---

## The short version

1. **The adopted change closed 38% of the gap.** Marginal spread **1.25 → 0.77
   FP/G**, measured exactly against live data. The optimal lineup moved from
   1G/4D/5M/**1F** to 1G/2D/5M/**3F** — maxed on forwards, not just legal.
2. **Defenders were not overcorrected.** D is still ahead of F at every depth,
   by a wide margin. What actually happened is subtler: **midfielders pulled
   clearly ahead of defenders** at the elite tier, a crossover that didn't
   exist before. See [Depth beyond the top](#depth-beyond-the-top-where-d-m-and-f-actually-diverge).
3. **Forwards are more accessible than pure-position depth suggests.** 23
   players are M/F dual-eligible, several elite (Saka, Doku, Semenyo), and
   they score identically whether fielded as M or F. The realistic
   forward-slot pool is far healthier than the single-position numbers alone
   imply. See [Multi-position eligibility](#multi-position-eligibility-changes-the-real-forward-pool).
4. **Buffing forwards would have been the wrong instrument** — every forward
   buff tested inflated the top end, while nerfing defenders compressed it.
   [Evidence](#buff-forwards-or-nerf-defenders).
5. The goalkeeper Goals-Against sign bug is **fixed**, confirmed live.

---

## The league's actual rules

Confirmed with the commissioner. **The `getLeagueInfo` API payload does not
match this** — it reports a 25-man roster and exposes no minimums at all, which
is what misled the first version of this document. Trust the table, not the API.

| | |
| --- | --- |
| Teams | 10 |
| Total roster | **15** (of which **2 goalkeepers**) |
| Active players | 11 |
| Position minimums | **at least 1 of every position** |
| Position maximums | 1 G, 5 D, 5 M, 3 F |
| Salary cap | **100,000 per team** |

Two consequences the first version missed entirely:

- **A forward must start.** 1 G + 5 D + 5 M is twelve players, not eleven, so
  the defender-heavy lineup is not even legal. Forwards have guaranteed demand:
  ten of them start every week no matter how the scoring is set.
- **150 players are rostered league-wide** (10 × 15), against a combined budget
  of **1,000,000**. Player #151 is free on waivers. That makes the 150th-best
  player the only meaningful baseline for "what is a player worth" — everything
  below him costs nothing to obtain.

### The market: undrafted players are repriced weekly

Players who go undrafted stay on the market, and **their salary is recomputed
every week by this repo's pipeline. That salary is the opening bid price.**

This is the part that gives the salary model teeth. For rostered players a
salary is a budget line; for the ~560 undrafted players it is the price of
entry, refreshed weekly as form changes. A player who breaks out is repriced up
before anyone can bid cheaply; a player who loses his place drifts down toward
the floor and becomes a bargain.

It also explains why **the number of players sitting exactly at the salary
floor matters**. Every floored player has an identical opening bid, so the
price stops carrying information and the market reverts to whoever clicks
first. Currently 341 of 709 players are at the 2,500 floor. That is the
argument for keeping `adp_max_pick` at 250 rather than lowering it to match the
150-player roster: the wider setting prices 28 newcomers from draft position
instead of 10, and floors 341 players instead of 348.

---

## What the first version got wrong

Worth recording, because the failure mode is reusable.

The API exposes position **maximums** and no minimums. The first version read
that as "no minimums exist", noticed 1 G + 5 D + 5 M = 11, and concluded a
legal XI could contain zero forwards — which made the imbalance look like a
standing instruction to ignore an entire position.

It did flag the risk in writing ("worth confirming in the Fantrax UI, because
the API does not expose minimums... if the league does enforce a minimum
forward count, points 1-3 get much less urgent"), and that is exactly what
happened. The lesson is narrower than "verify assumptions": **an API that
returns only half of a constraint pair will read as an absent constraint**, and
absence is precisely the observation that cannot be trusted from a payload that
was never designed to express it.

The roster size was wrong too — the API says 25, the league runs 15.

---

## Where the asymmetry is written into the settings

Position-specific rules, from the live config:

| Category | G | D | M | F |
| --- | --- | --- | --- | --- |
| Clean sheet on field | 5 | **4** | 1 | **0** |
| Goals (1st/2nd/3rd/4th+) | 25 flat | 4/5/6/7 | 4/5/6/7 | **5/6/7/8** |
| Assists (1st/2nd/3rd+) | 7.5 flat | 3/4/5 | **4/5/6** | 3.5/4.5/5.5 |
| Goals against | banded | −0.5/−1/−1.5 | −0.25/−0.5/−1 | **0** |

Two things stand out before any data is involved:

- **A forward gets nothing for a clean sheet and no penalty for conceding.**
  Their exposure to the defensive half of the game is zero in both directions,
  so they compete on attacking returns alone.
- **A forward is paid *less* per assist than a midfielder** (3.5 vs 4.0) while
  being paid more per goal (5 vs 4). Since midfielders out-assist forwards
  anyway, this compounds rather than offsets.

Everything else — the ~20 volume categories — is `Default`, identical for all
outfielders. That is where the imbalance comes from, and it is invisible in the
settings screen precisely *because* it is symmetrical. The rates are equal; the
opportunities are not.

---

## Two changes went live, in sequence

**First (a colleague's change).** Eight `Default` volume categories were
trimmed ~15–25%:

| Category | Old | New | Ratio |
| --- | --- | --- | --- |
| Interceptions (Int) | 0.20 | 0.15 | 0.75 |
| Tackles Won + Blocked Shots (TkW+BS) | 0.20 | 0.15 | 0.75 |
| Blocked crosses (BC) | 0.13 | 0.10 | 0.77 |
| Duels won (DW) | 0.15 | 0.12 | 0.80 |
| Ball recoveries (BR) | 0.18 | 0.15 | 0.83 |
| Blocked shots (BS) | 0.18 | 0.15 | 0.83 |
| Clearances off line (CLO) | 3.0 | 2.5 | 0.83 |
| Tackles - last man (TLM) | 0.35 | 0.30 | 0.86 |

These are `Default` rates, applying to every outfielder. They narrowed the gap
only because defenders accumulate more of them, not because they target
defenders. Effective clearances and the defender clean sheet were left
untouched — the two largest single contributors — so this change moved the
*numbers* (marginal spread 1.25 → 1.07) without moving the *optimal lineup*
(stayed 1G/4D/5M/1F). It closed the gap without closing it enough to change
what anyone would actually field.

**Second (adopted from this review's recommendation), now also live:**

| Category | Old | New |
| --- | --- | --- |
| Defender clean sheet (CS@D) | 4 | **3** |
| Effective clearances (CLR) | 0.15 | **0.12** |

This is the change [What moves the needle, tested](#what-moves-the-needle-tested)
identified as the best-supported option, and it is the one whose exact,
live-measured effect is reported throughout this document.

---

## A genuine bug in the goalkeeper settings — fixed

Goals Against was banded with the wrong sign on the last band:

```
0-1 goals    0.0 per goal
2-3 goals   -1.0
4-5 goals   -1.5
6-7 goals   -2.0
8+  goals   +3.0     <-- was positive
```

Cumulative, that used to give a keeper who concedes 8 a *better* score than one
who concedes 7, and one who concedes 10 back to par. **Confirmed fixed live**:
the 8+ band now reads `-3.0`.

---

## The data: 2025-26, real matches, real scoring

Recomputed from every 2025-26 player's season category totals (321 players with
10+ games). Methodology for the original delta-based analysis — including why
season totals are exact for flat categories and wrong for banded ones — is in
[`analysis/scoring_review/README.md`](../analysis/scoring_review/README.md).
That method predicted the effect of candidate tweaks before any of them went
live. It is superseded below by an exact measurement, but its predictions are
kept in [What moves the needle, tested](#what-moves-the-needle-tested) because
they are what the decision was actually made from, and because they turned out
to be accurate — see the next section.

### Confirming the live numbers

After the second change went live, `fantrax_salary/api.py` was fixed (it had a
bug independent of this review — a missing `timeframeTypeCode` parameter that
silently served historical-season requests as weekly-projection views) and used
to re-pull real 2025-26 FPts directly. Two things came out of that worth
recording:

- **Fantrax re-scores historical seasons under whatever rules are currently
  live.** Predicted FPts (baseline + the flat-category delta) matched actual
  re-pulled FPts to the penny for 292 of 319 matched players; the remaining 27
  were dual-position players Fantrax now attributes to a different position
  than the cached data assumed, not a scoring error. This means every number
  below is a **direct, exact measurement** — no delta trick, no banded-category
  blind spot. Goals and assists, previously unmeasurable, are now included
  automatically.
- **The delta method's predictions held up well against reality**: it predicted
  a spread of 0.76 and an optimal XI of 1G/3D/5M/2F for this exact change; the
  real number came in at 0.77 and 1G/2D/5M/**3F** — close on the spread, one
  forward more aggressive than predicted on the lineup. The difference is real,
  not noise: elite defenders absorbed the clean-sheet cut harder than the
  flat-category approximation could see coming, which is exactly the kind of
  gap the approximation was known to have.

### The gap, before and after — exact

Marginal starter FP/G — the last player at each position who starts
league-wide, which is the number that decides whether you play a defender or a
forward in your final slot:

| | G | D | M | F | Spread | Optimal XI |
| --- | --- | --- | --- | --- | --- | --- |
| Before any change | 4.92 | 5.63 | 5.24 | 4.38 | 1.25 | 1G/4D/5M/1F |
| After the colleague's change | 4.92 | 5.26 | 4.93 | 4.19 | 1.07 | 1G/4D/5M/1F |
| **After the adopted change (live, exact)** | **4.92** | **4.93** | **4.88** | **4.16** | **0.77** | **1G/2D/5M/3F** |

The colleague's change moved the numbers without moving behaviour. The adopted
change did both: **38% of the original gap closed**, and the optimal lineup
went from the legal minimum of one forward to the legal maximum of three.

---

## What moves the needle, tested

Exact deltas against 2025-26's real matches. "Star inflation" is the change in
the top-10 players' mean value over the 150th-best player — **positive means
the elite got stronger relative to a freely-available player**, which is the
thing to avoid.

| Tweak | Spread | Optimal XI | Gap closed | Star inflation |
| --- | --- | --- | --- | --- |
| *(live baseline)* | 1.07 | 1G/4D/5M/1F | — | — |
| CLR 0.15 → 0.12 | 0.99 | 1G/4D/5M/1F | 0.076 | −0.012 |
| CLR 0.15 → 0.10 | 0.96 | 1G/3D/5M/2F | 0.107 | −0.009 |
| CS(D) 4 → 3 | 0.86 | 1G/3D/5M/2F | 0.206 | −0.003 |
| **CS(D) 4→3 + CLR 0.12** | **0.76** | 1G/3D/5M/**2F** | **0.307** | **−0.024** |
| CS(D) 4 → 2 | 0.73 | 1G/2D/5M/3F | 0.337 | **+0.031** |
| CS(D) 4→2 + CLR 0.12 | 0.76 | 1G/2D/5M/3F | 0.315 | **+0.052** |

Two findings worth stating plainly:

**Clearances are a weak lever.** CLR 0.15→0.12 closes 0.076 of a 1.07 gap. The
defender clean sheet closes **2.7× more** with one number.

**Cutting the clean sheet to 2 is a trap.** It closes the most gap but is the
*worst* option for the top end. It cuts elite defenders so hard (Gabriel
Magalhaes 7.81 → 6.69, Marc Guehi 7.26 → 6.46) that they fall *out* of the
elite tier, leaving the top ten attacker-dominated. Cutting to 3 pulls them
*into* the pack instead of out of it, which is why its star inflation is
roughly zero.

No tweak here makes Bruno Fernandes stronger in absolute terms. His FP/G is
untouched by any clean-sheet change (9.45 → 9.45; he is a midfielder). What
rises in the CS-only rows is replacement level *falling* beneath him — and the
CLR trim is what cancels that out.

---

## Depth beyond the top: where D, M, and F actually diverge

The marginal-spread number answers "is the gap closed", but it collapses each
position to one figure. After the change went live, a natural follow-up
question came up: **did the change overcorrect defenders?** The marginal
number alone can't answer that — it needs the full depth curve, exact,
post-change:

| Depth rank | D FP/G | example | M FP/G | example | F FP/G | example |
| --- | --- | --- | --- | --- | --- | --- |
| 10th-best | 5.75 | Daniel Munoz | 6.49 | Rayan Cherki | 5.21 | Richarlison |
| 20th | 5.41 | Michael Kayode | 5.77 | Morgan Gibbs-White | 4.16 | Eli Kroupi |
| 30th | 5.11 | Nathan Collins | 5.32 | Yankuba Minteh | 3.64 | Brian Brobbey |
| 40th | 4.93 | Matty Cash | 4.88 | Brenden Aaronson | 3.18 | Dan Ndoye |
| 50th | 4.69 | Jarrad Branthwaite | 4.50 | Habib Diarra | 2.79 | Wilson Isidor |
| 60th | 4.51 | Harry Maguire | 4.21 | Rodrigo Bentancur | 2.35 | Liam Delap |

**No, defenders were not overcorrected.** D is ahead of F at every depth
checked, by a wide and fairly constant margin (0.5–1.4 FP/G). The gap that
actually opened up is **D vs M**: before any change the two were essentially
tied at the top (6.35 vs 6.34); now M is clearly ahead through the top 30
(6.49 vs 5.75 at rank 10), and the two only converge around rank 40, with D
even edging back ahead deeper down.

This is a side effect, not the goal. The clean-sheet cut only touched D — M's
clean-sheet rate (`Default`, 1 point) was never part of either change — so all
of M's relative gain at the top is really D's cost, inherited by whichever
position happened to be sitting next to it. If this specific side effect (M
now clearly the strongest position among elite players, where before it was a
tie with D) is worth addressing, the lever is different from the one already
pulled: something that also touches M's edge, or a partial reversal of the CS
cut (e.g. 3 → 3.5) rather than treating the D/F fix as the thing to undo.

What the depth table also shows: **F genuinely collapses faster than either
other position.** From rank 10 to rank 60, D drops 1.24 FP/G and M drops 2.28
(from a far higher peak); F drops from 5.21 to 2.35 — more than half. By rank
20 a rostered forward (4.16) already scores what a 40th-string defender or
midfielder scores. That is the real shape of what remains unaddressed: not
that forwards can't be good, but that the position has almost no depth once
past its best ~15 players.

---

## Multi-position eligibility changes the real forward pool

The depth table above uses each player's single primary position, which
understates what a manager can actually do: **23 players are eligible at both
M and F**, several of them elite —

| Player | GP | FP/G |
| --- | --- | --- |
| Bukayo Saka | 31 | 7.00 |
| Jeremy Doku | 30 | 6.77 |
| Antoine Semenyo | 37 | 6.71 |
| Morgan Rogers | 37 | 6.12 |
| Iliman Ndiaye | 32 | 6.04 |

— and, checked directly against the API, **they score identically whether
queried as M or as F** (confirmed on Saka, Semenyo, Doku, Morgan Rogers and
Iliman Ndiaye — FPts matched to the decimal both ways). That is a materially
different result from the D/M dual-position case documented in
[`analysis/scoring_review/README.md`](../analysis/scoring_review/README.md)
(Matheus Nunes scores 25 points differently as a D than as an M) — for M/F
specifically, there is no hidden penalty for using a flex player in the
forward slot.

That makes the realistic forward-accessible pool much healthier than the
single-position table suggests:

| Pool | Top-20 marginal (2F) | Top-30 marginal (3F) |
| --- | --- | --- |
| Pure F only (66 players) | 4.16 | 3.64 |
| **F-capable: pure F + M/F dual (89 players)** | **5.17** | **4.29** |

Five of the ten best forward-eligible players are M/F flexes (Saka, Doku,
Semenyo, Morgan Rogers, Iliman Ndiaye alongside Haaland, Joao Pedro, Igor
Thiago, Matheus Cunha, Rayan). The mandatory forward slot is cheap to fill
well in practice — the real decision a manager faces is not "is there a
playable forward", it is **whether to spend a Saka-caliber M/F flex on the
forward slot (freeing him from competing for one of only 5 midfield slots) or
keep him at midfield and start a genuinely weak single-position forward
instead.** That is a legitimate roster-construction choice created by the
rules, not a flaw to fix.

---

## Buff forwards or nerf defenders?

The natural instinct is to raise forwards rather than cut defenders — nobody
enjoys having points taken away. **The data says buffing is the wrong
instrument if elite players must not get stronger.**

### Where a buff would land

A buff to a category is distributed exactly the way that category is. Among the
66 qualifying forwards:

| Category | Top-5 share | Top-10 share | Gini |
| --- | --- | --- | --- |
| **Goals** | **26.0%** | **43.5%** | **0.52** |
| Assists | 25.0% | 41.4% | 0.47 |
| Clean sheets | 18.8% | 34.9% | 0.44 |
| Duels won | 18.5% | 32.9% | 0.36 |
| Minutes | 16.2% | 30.7% | 0.35 |

**Goals are the most concentrated statistic in the game.** Paying more per
forward goal sends 26% of the money to five players. That is the definition of
making the stars overpowered, and it is why "just pay forwards more for goals"
does not survive the constraint.

It is also the change that *cannot* be measured exactly here — goals and
assists are banded, and banded categories cannot be reconstructed from season
totals. So it is both the most concentrated option and the least verifiable.

### The one buff that can be measured exactly

Clean sheets are flat, so a forward clean-sheet bonus simulates exactly:

| Tweak | Spread | Optimal XI | Gap closed | Star inflation |
| --- | --- | --- | --- | --- |
| **CS(D) 4→3 + CLR 0.12** *(nerf D)* | 0.76 | 1G/3D/5M/2F | 0.307 | **−0.024** |
| CS(F) 0 → 1 *(buff F)* | 0.83 | 1G/3D/5M/2F | 0.242 | +0.007 |
| CS(F) 0 → 1.5 *(buff F)* | 0.72 | 1G/3D/5M/2F | 0.347 | +0.027 |
| CS(F) 0 → 2 *(buff F)* | 0.60 | 1G/2D/5M/3F | 0.469 | +0.020 |
| CS(D) 4→3 + CS(F) 0→1 *(both)* | 0.62 | 1G/2D/5M/3F | 0.448 | +0.034 |

**Every forward buff inflates the top end. Only the defender nerf compresses
it.** The mechanism is simple once stated: nerfing removes points from elite
defenders, who are themselves in the top ten, so the ceiling comes down with
everyone else. Buffing adds points to elite forwards, who are also in the top
ten, so the ceiling goes up. Adding points to a position always flows hardest
to the best players at that position.

A forward clean-sheet bonus of 1 is the most defensible buff — nearly neutral
on stars (+0.007) and thematically it repairs the real asymmetry noted above,
that forwards have no exposure to the defensive half of the game in either
direction. But it closes less gap than the nerf while still pushing the top end
the wrong way, and stacking it *with* a defender nerf overshoots to a
forward-maxed lineup.

A buff also inflates every score in the league, which makes season-to-season
comparison harder for no analytical gain.

---

## How this interacts with salary

The salary model in `fantrax_salary/` has **no positional term at all** — it
min-max normalises FPts and FP/G across the whole pool and blends them. It is
position-blind by construction, so a positional scoring gap passes straight
through into price.

Numbers below are from a real `--source api` run against the live scoring and
current roster (`output/SalGW0.*`) — the first salary run in this project
priced under the fully-adopted rules across all 4 input seasons, not from the
static per-season CSVs, which had gone stale relative to the scoring change.
That run also surfaced an unrelated finding: `data/template/blank_2026-27.csv`
carries 53 players Fantrax's live pool no longer recognises (confirmed via two
independent endpoints), evidently no longer in the league — a fresh export is
worth taking before the next real commissioner upload.

- **Representation improved**: **14 forwards** now reach the top 150, up from
  12 before the change. Still well short of the 59 defenders and 56
  midfielders who do, which is the scoring gap surfacing as pricing — not
  something the salary model can or should fix on its own.
- **The top 150 costs 117.5% of the 1,000,000 league budget** — down slightly
  from 122.6% pre-change, but the "meaningful number of good players stay on
  the market" objective is still comfortably met.
- **Star players are still not overpriced.** The top player costs **2.53×**
  the 150th player while historically producing on the order of 1.9× as much.
  `salary_target_max` was considered and left at 15,000 — raising it further
  compresses the price/production ratio in the wrong direction and makes elite
  players a worse buy, not a better one.

---

## Decision and outcome

**Adopted and confirmed live:**

- Defender clean sheet 4 → 3
- Effective clearances 0.15 → 0.12
- Goalkeeper Goals-Against sign fix (`+3.0` → `-3.0`)

Together with the colleague's earlier eight-category trim, this closed **38%**
of the original D/F marginal gap (1.25 → 0.77) and moved the optimal lineup
from the legal minimum of one forward to the legal maximum of three. Checked
directly against post-change live data — not predicted, measured.

**Explicitly considered and not adopted:**

- **Clean sheet 4 → 2** — closes more gap but inflates the top end: it cuts
  elite defenders (Gabriel Magalhaes, Marc Guehi) hard enough to push them
  *out* of the elite tier rather than into the pack, leaving the very top of
  the league more attacker-dominated, not less.
- **Raising forward goal or assist rates** — the most concentrated stats in the
  game (goals: top-5 players earn 26% of all forward goals), so a buff there
  sends money disproportionately to the players who should not get stronger.
  Also the one category that couldn't be verified exactly before adoption,
  since goals and assists are banded.
- **Changing clearances alone** — a weak lever on its own, closing only 0.076
  of the pre-adoption 1.07 gap.

**Open, not urgent:** the adopted change created a new D-vs-M crossover at the
elite tier (see [Depth beyond the top](#depth-beyond-the-top-where-d-m-and-f-actually-diverge))
that didn't exist before — M pulled ahead of a near-tie with D, as a side
effect of only D's clean sheet being cut. Worth knowing, not obviously worth
reversing: the D/F gap that motivated this whole review is closed, and
undoing the D/M side effect would mean giving that back.

The real cost of the change, for the record: the defenders who lost the most
FP/G are the best clean-sheet defenders — Gabriel Magalhaes, Marc Guehi,
William Saliba, Ruben Dias. That was the point of the change, and it is worth
having it written down whose value it reallocated.
