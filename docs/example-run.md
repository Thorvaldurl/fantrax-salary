# Example run

A walk through what `--gameweek 0 --dry-run` actually produces, with real
player names and numbers instead of an abstract description of what the model
does. Every figure below comes from a real run against the committed data —
see [Reproduce this](#reproduce-this) at the end to check them yourself.

Current as of: 20% projection / 60% last season / 15% / 5% season weights,
`blank_zero_seasons`, `adp_fallback`, and `rate_shrinkage` all on, 2,500 floor.

---

## The top of the pool

| Player | Position | Old salary | New salary |
| --- | --- | --- | --- |
| Bruno Fernandes | M | 15,000 | 15,000 |
| Erling Haaland | F | 12,500 | 11,900 |
| Elliot Anderson | M | 12,000 | 11,800 |
| James Tarkowski | D | 11,500 | 11,500 |
| Bruno Guimaraes | M | 11,600 | 11,400 |
| Gabriel Magalhaes | D | 11,600 | 11,400 |
| Declan Rice | M | 11,800 | 11,400 |
| Bukayo Saka | M,F | 11,500 | 11,300 |

Bruno Fernandes sits at the 15,000 ceiling — the model can't price him any
higher no matter how far ahead of the field his score is, because the band
caps out at the best score in the pool.

## The pool overall

| | |
| --- | --- |
| Current total | 2,604,600 |
| After this run | 2,836,900 (+8.9%) |
| At the 2,500 floor | 248 of 709 players (35%) |

## Biggest movers

**Risers** are mostly players parked at the 2,000 template minimum despite a
real 2025-26 record — the model catching up to data that was always there,
not anything new about this run:

| Player | Position | Old salary | New salary | Change |
| --- | --- | --- | --- | --- |
| Liam Kitching | D | 2,000 | 6,700 | +4,700 |
| Dara O'Shea | D | 2,000 | 6,500 | +4,500 |
| Matt Grimes | M | 2,000 | 6,300 | +4,300 |
| Milan van Ewijk | D | 2,000 | 6,300 | +4,300 |
| Lukas Hornicek | G | 2,000 | 6,200 | +4,200 |

**Fallers** are two different things: last year's breakouts the projection
still rates too highly, and — new in this run — a single-game fluke that
`rate_shrinkage` now catches (Walter Benitez, explained below):

| Player | Position | Old salary | New salary | Change |
| --- | --- | --- | --- | --- |
| Valentino Livramento | D | 13,500 | 10,000 | −3,500 |
| Dominic Solanke | F | 8,400 | 6,200 | −2,200 |
| **Walter Benitez** | **G** | **6,400** | **4,400** | **−2,000** |
| Jarrad Branthwaite | D | 9,000 | 7,000 | −2,000 |
| Alejandro Garnacho | M,F | 7,000 | 5,100 | −1,900 |

---

## Three mechanisms, one at a time

### Players with no history: draft ADP fills the gap

A Fantrax export gives a player who wasn't in the league last season a
literal `0.0`, indistinguishable from "played and was useless." For anyone
with **no completed season at all**, `adp_fallback` prices them off where the
league's own draft has them instead — fitted from the pool each run, capped
at pick 250, shrunk 0.7×:

| Player | Position | ADP | Salary |
| --- | --- | --- | --- |
| Bobby Thomas | D | 188.7 | 4,800 |
| Tarik Muharemovic | D | 189.9 | 4,600 |
| Abdul Fatawu | F | 166.3 | 4,500 |
| Hayden Hackney | M | 153.7 | 4,500 |
| Johan Manzambi | M | 78.1 | 4,500 |
| Oliver McBurnie | F | 97.2 | 4,500 |

Without this, every one of these prices at the 2,500 floor instead. Full
reasoning in the README's
["Players who have never played here"](../README.md#players-who-have-never-played-here).

### Small samples: a real rate, or noise?

A rate stat (FP/G) measured over a handful of games is mostly noise, and it
cuts both ways — a great one-game substitute appearance looks identical to a
season sustained at that rate, and a good player who was rotated or injured
looks exactly as bad as one who is genuinely poor.

**Walter Benitez is the clean real example.** His entire 2025-26 was one
appearance, at exactly 10.00 FP/G — the single best rate in the whole pool
that year, purely because one great game is indistinguishable from a great
season when nothing else is known. `rate_shrinkage` pulls it toward what a
typical goalkeeper does, weighted by how little evidence backs it up:
shrinkage alone accounts for −700 of his −2,000 total move (5,100 → 4,400;
the rest of the drop is the season reweight, described in the README).

The correction runs both directions — a bad one-game sample gets pulled *up*
toward the positional average too, not left looking like a bust — and it's
deliberately narrow: a player with a real, substantial season
(`shrinkage_min_games`, 10+ games) keeps their own rate exactly as reported.
Bruno Fernandes's 9.79 FP/G, the pool's best genuine full-season rate, is
completely untouched by this.

**Not every low price is a small sample, though — see Rio Ngumoha below.**

### The floor is not one population

37% of players land at the 2,500 floor is a big enough share to ask what's
actually in it. It turns out to be two very different situations, collapsed
into an identical price:

**183 players have no signal at all** — no completed season, no ADP inside
the first 250 picks. This is the floor doing exactly its job:

| Player | Position | Salary |
| --- | --- | --- |
| Chuba Akpom | F | 2,500 |
| Sean Steur | M | 2,500 |
| Dermot Mee | G | 2,500 |
| Tom Proctor | M | 2,500 |
| Brandon Austin | G | 2,500 |

**65 players have a real, if modest, 2025-26 record** and still price
identically to the players above. Rio Ngumoha is the clearest case: 69.42
FPts at 3.65 FP/G over roughly 19 games — the **34th percentile** of players
who actually played last season. A real rotation player, not an unknown.

| Player | Position | 2025-26 FPts | FP/G | Salary |
| --- | --- | --- | --- | --- |
| Ao Tanaka | M | 94.43 | 3.37 | 2,500 |
| Andrey Santos | M | 83.26 | 3.08 | 2,500 |
| Rio Ngumoha | F | 69.42 | 3.65 | 2,500 |
| Jorrel Hato | D | 60.34 | 2.74 | 2,500 |
| Wilfried Gnonto | F | 59.68 | 2.59 | 2,500 |

**`rate_shrinkage` deliberately doesn't touch this.** At 19 games, Ngumoha's
own rate is a reliable-enough sample, not noise — shrinking it would
manufacture a correction that isn't there. His low price comes from his
*cumulative* total, and that's genuinely low because he played about half a
season — real information, not a data gap.

What his case actually exposes is a granularity problem at the bottom of the
scale: "nothing is known" and "a real but below-average season" get priced
the same. That's the same mechanism project issue #1 complains about from the
other direction (the floor one-way-ratcheting the pool total up) — this is
what it looks like from below. Not addressed here; recorded so it isn't
mistaken for something this run already fixed.

---

## Reproduce this

Compute and print the full report without writing any files:

```bash
python -m fantrax_salary.cli --gameweek 0 --dry-run
```

Swap in whatever gameweek you're actually pricing. The report covers the
same ground as above — scale, pool total, position breakdown, ADP-priced
newcomers, biggest movers — for whatever data currently sits in `data/`.

Against live Fantrax data instead of the checked-in CSVs:

```bash
python -m fantrax_salary.cli --gameweek 0 --dry-run --source api
```

Drop `--dry-run` only when ready to write `output/SalGW<N>.csv` and upload it.
