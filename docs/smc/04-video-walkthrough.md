# The source video, frame by frame

**Provenance.** A YouTube course, "The Only Day Trading Plan You Need in 2026" (16:52), supplied by the
project owner as 48 numbered frames in story order. The frames are not committed and not reproduced here;
this is a summary of what the sequence teaches, in the order it teaches it, because that order is the
lesson. Everything below is what the material states, with the code's position noted where it differs.

## What it names

Five concepts, listed twice in the video as its syllabus: **supply and demand**, **change of character**,
**market direction**, **order blocks**, **top-down analysis**. It is a *day-trading* plan by its own
definition — positions opened and closed inside the same trading day, nothing held overnight.

## The three factors that make a zone valid

Stated as a slide of its own and then shown three times over as a diagram: **inefficiency (FVG)**,
**break of structure (BOS)**, and **pushed distance**. The third panel is the one worth zooming in on: it
marks "start" and "end" arrows either side of the rally away from a demand zone and captions the distance
between them "great pushed distance".

That is a criterion the code does not have at all, and it is named as one of three equal factors. A zone
is not qualified by having left a gap and broken structure; it also has to have travelled a long way
before coming back.

## The core of the video: when a change of character is *invalid*

Roughly a third of the runtime goes to this, and it is the part every earlier deck only gestured at. Two
things look exactly like a reversal at the moment of the break, and both are traps:

**1. A liquidity hunt.** When a major swing low sits inside an obvious liquidity area — a visible pool of
retail stop-losses — a break below it is *manipulation*, not a reversal. The video draws the pool, circles
the break as manipulation, then crosses out the "CHoCH" label in red and shows price going straight back
inside the range and continuing. The signature is a wick below the level followed by immediate recovery.

**2. Fair value gap mitigation.** Stated as a rule on its own slide: **always check the left side of the
chart for unfilled fair value gaps before accepting a change of character.** If the drop is price coming
back to fill an old imbalance, the apparent reversal is a rebalancing event and the trend resumes.

So the discriminator is not the candle that broke — it is *what sits to the left of it*. Unfilled gaps and
visible stop clusters on the left mean "not a reversal". That is the single most actionable rule in the
material, and it is the layer the code entirely lacks.

## Order blocks

Defined as refined supply and demand zones where the significant pressure originated — and drawn
concretely: the box is **the single candle immediately before the displacement move, taken wick to wick**,
with the imbalance sitting above the move out of it. Measured against the frames: in `S31`/`S32` the box
matches that candle's own high-to-low to within 1–3 px, and on the real 1h chart in `S43` the same holds at
29 pips. This is exactly what the code calls a zone (one candle, wick to wick).

> **Correction (superseded reading).** An earlier version of this file said "the last **opposite-coloured**
> candle before the impulse" and called it confirmed three times over. Across all 48 frames the material
> never says "opposite-coloured", and in `S31`/`S32` the candle the box is pinned to is drawn the *same*
> colour as the impulse. The frames support *the single candle before the move*; the colour constraint was
> ours. See [`spec.md` §2.2](spec.md) for the measurements, and §2.1 there for the separate, larger object
> this is often confused with — the macro zone band.

The video also undercuts its own tool, on a slide of its own: *order blocks do not always work; they are
not guarantees, but potential trading areas where price may show predictable behaviour.*

## Top-down analysis: which timeframe does what

Shown twice at two different scales, which is itself informative — the principle is fixed even though the
timeframes are not (1-hour → 15-minute in one example, daily → 1-hour → 15-minute in the other;
daily → 4-hour → 1-hour in the worked example). The division of labour is consistent:

- **higher timeframe** — the breakout and the key level (context)
- **lower timeframe** — the order block, the rejection off it, and the entry

The three-panel frame is the only place in the whole sequence with an explicit **"Entry"** marker.

## The worked example — and it fails

The final stretch is a real chart, USD/JPY on FXCM via TradingView, walked from the daily down:

1. **Daily**: resistance ~158.6, support ~149.8.
2. **Daily**: an order block ~154.4–155.7 with an FVG, inside that range.
3. **4-hour**: price fell from ~158 to ~151.2, then rallied back into the order block. A "4H level" at
   ~151.3 is marked.
4. **1-hour**: the daily order block across the top; a *1-hour* order block ~153.4–153.7 with an FVG below
   it; and a planned long — down out of the daily order block, into the 1-hour order block and its gap,
   then bounce.
5. **What actually happened**: price kept going. It fell through the 1-hour order block, into the gap, a
   bearish change of character formed with its own new order block, and price ran on to the 4-hour level
   at ~151.3. **The planned long was wrong.**
6. The video closes on: *patience is one of the most valuable skills a trader can develop; waiting for
   high-quality setups is not a choice but a discipline that must be mastered.*

That ending is worth taking at face value. The material's own worked example is a setup that did not work,
taught as such — which is more honest than the supply-and-demand decks' closing slides, and it is the
opposite of a track record. **The video contains no broker markers, no entry/stop/target lines and no
profit figure anywhere**: the annotations are hand-drawn teaching overlays. So it documents the method and
not its results — the "79.13% over 115 trades" claim lives in a different deck and has nothing behind it
here.

## What this changes for the code

Nothing in the current implementation is contradicted; two things are confirmed (the one-candle order block
and the strict gap definition) and the identification layer is confirmed as the gap, now with names:

| the material's rule | the code |
|---|---|
| control is a state: demand or supply, flipping on a valid CHoCH | **absent** — no state at all |
| a CHoCH is invalid if a stop cluster sits to the left | **absent** — any close beyond a level is a breakout |
| a CHoCH is invalid if an unfilled FVG sits to the left | **absent** — same |
| pushed distance is one of three factors making a zone valid | **absent** |
| higher timeframe gives the level, lower gives the entry | **absent** — one timeframe throughout |
| order blocks are "not guarantees" | the code treats a zone as an opportunity with no quality grade |

Every replay figure this project has produced was measured without the three invalidation rules, which is
to say it counted traps as setups. Those numbers describe a derivative, not this method.
