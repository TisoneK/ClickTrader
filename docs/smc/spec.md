# Specification — the SMC day-trading method

**What this document is.** A reference-grade statement of what the material *specifies*, what it merely
*draws*, and what it *leaves to the eye*. It exists so that a future implementer cannot fill a gap in the
method with a rule of their own invention without that substitution being visible on the page.

**Source of the *Stated* and *Shown* columns.** A YouTube course, "The Only Day Trading Plan You Need in
2026" (16:52), supplied by the project owner as 48 numbered frames (`S01`–`S48`, story order). The frames
are not committed and not reproduced here. Everything in **Stated** and **Shown** is a paraphrase or a
measurement of those frames; anything else is marked as ours.

**Source of everything else.** The sibling files in this directory — [`README.md`](README.md),
[`01-components.md`](01-components.md), [`02-engine.md`](02-engine.md),
[`03-operating-manual.md`](03-operating-manual.md), [`04-video-walkthrough.md`](04-video-walkthrough.md) —
which summarise the same author's *deck* material. Where those files and the frames disagree, the frames
win and this document says so.

**How to read each concept.** Three parts, never mixed:

- **Stated** — the rule in words, as the material says it. Numbers and names exactly.
- **Shown** — the drawn geometry, measured in candle terms. Every claim cites a frame.
- **Not specified** — the judgement the material leaves open, with *no test stated anywhere*. Never
  filled in here.

A "judgement with no stated test" is not a gap to be plugged later. It is the single most important thing
this document records, because inventing a number for one is how the previous implementation quietly
became a different strategy (see §3).

---

## 1. Which frames are real charts and which are teaching diagrams

Evidence from a TradingView capture is worth more than evidence from a schematic: geometry measured off a
real chart is bounded by real candles, geometry measured off a drawing is bounded by whatever the
illustrator chose.

| frames | kind | instrument / timeframe |
|---|---|---|
| `S10`, `S11`, `S12` | **real chart** | EUR/USD, 1h, OANDA (TradingView header + axis + session times) |
| `S20` | **real chart** | EUR/USD, 1h, FXCM |
| `S38`, `S39` | **real chart** | USD/JPY, 1D, FXCM (Nov–Mar window) |
| `S40`, `S41` | **real chart** | USD/JPY, 4h, FXCM (Feb 14–27) |
| `S42`–`S47` | **real chart** | USD/JPY, 1h, FXCM (Feb 8–18) |
| `S48` | **real chart** (+ text overlay) | USD/JPY, 1h, FXCM — same chart as `S47`, with the closing callout on top |
| `S04`, `S05` | synthetic | line chart, supply/demand rails |
| `S06`, `S07` | synthetic | candlestick chart, demand-zone band |
| `S25` | synthetic | candlestick chart, supply + demand bands |
| `S14`, `S26`, `S27`, `S28`, `S29` | synthetic | line chart, BOS / CHOCH / control |
| `S15`, `S16`, `S17`, `S18`, `S19`, `S21` | synthetic | candlestick chart, liquidity pool + FVG |
| `S01`, `S09` | synthetic | the three-panel "Trading Concepts" diagram |
| `S02` | synthetic | syllabus + order-block/BOS sketch |
| `S23`, `S24` | synthetic | control blobs / ticked zones |
| `S31`, `S32`, `S33` | synthetic | order-block diagram |
| `S34`, `S36` | synthetic | top-down diagrams (graph-paper background) |
| `S03`, `S08`, `S13`, `S16`, `S22`, `S30`, `S33`, `S35`, `S37` | text only | slide (`S16` and `S22` are text callouts drawn over the schematic of the frame before) |

**Consequence for the reader:** the order block is the only object the material draws *both* on a
synthetic diagram (`S31`, `S32`) and on a real chart at the same scale (`S43`, `S46`, `S47`), and the two
agree (§2.2). The macro zone band is drawn nearly always on schematics — `S01`, `S06`, `S07`, `S25` are
the evidence base, and it is thin.

---

## 2. The concepts

### 2.1 Supply and demand zones — the macro band

**Stated.** A demand zone is where buyers stepped in aggressively, a supply zone where sellers dominated.
`S25` labels the two bands simply "Supply" and "Demand". `S01` calls the demand band a "Strong Demand
Area" and a "Potential turning point", and captions the move away from it as "Great pushed distance".
`S04`/`S05` present the same objects as a ladder: three demand rails in a rising market, three supply rails
in a falling one, each drawn at a swing pivot. Zones are used again later as the thing control flips
between (`S28` marks an "Unmitigated Demand" band, drawn as one very long horizontal rail).

**Shown.**

- `S01`, left panel — the zone is a **plain grey horizontal band, 65 px tall**, drawn at the lows of a
  cluster of **5 base candles**, running from the left edge of that cluster forward in time to well past
  the last candle on the panel. Its **top edge sits exactly at the low of the lowest candle's body**; its
  **bottom edge sits just below that candle's wick tip** (wick low 814, band bottom 817). The 5-candle
  cluster is followed by one large displacement candle (wick-to-wick 378→736, i.e. 358 px) and one small
  candle. So in that panel the band is **~1.2× the origin candle's body and ~0.6× its full wick range**,
  and it covers *the lower wicks* of the cluster, not any single candle.
- `S01`, right panel — the same object: band 58 px tall, top edge at the wick low of the candle that ends
  the base, bottom edge just below the lowest wick, extending right across the whole panel.
- `S06`/`S07` — the same band again, on a chart with no axis: **66 px tall**, top edge at the level where
  the base candles' bodies end, bottom edge just below the lowest wick of the cluster, left edge flush
  with the first candle of the base, right edge running to the right-hand end of the drawn price. A
  slightly lighter sub-rectangle is nested at the band's left end, one candle wide — the origin candle,
  restated. In `S07` the same band is still on screen and price returns into it (the retest).
- `S04`/`S05` — drawn on a line chart (no candles, so no candle-relative geometry is available): each rail
  is a thin horizontal bar beginning at the pivot and extending right, of differing lengths; the circles in
  `S05` mark the pivots the rails start from.
- `S25` — both bands drawn together: a pink supply band across the highs of the cluster that made the peak,
  a teal demand band across the lows of the cluster that made the trough, each extended far to the right
  (supply to the panel edge, demand past it).

**Not specified.** Which cluster of candles qualifies; how far apart the zone's edges must be; how many
pivots count as "obvious"; whether a zone is invalidated by being traded through; how far forward in time
a zone remains live. The material draws bands of roughly one candle-body height at the lows and nothing in
the frames states a rule for either edge. `S01`'s captions call the reaction "based on historical
aggression" and the zone a "potential turning point" — a judgement, not a test.

---

### 2.2 Order blocks — the single-candle refinement

**Stated.** `S30`: order blocks are *refined supply and demand zones where significant buying or selling
pressure originated*. `S33`, on a slide of its own: they do not always work — they are not guarantees, but
potential trading areas where price may show predictable behaviour. `S02` labels the same object "Order
Block" and draws it in the same breath as a "Bos".

**Shown** (this is the part the frames settle, and it settles it twice, at two different scales):

- `S31`, `S32` (synthetic). The box is a rectangle with its **left edge immediately after one single
  candle** and its vertical edges pinned to that candle: measured at x=1100 the box spans y 655→768, and
  the candle at x 732–768 spans y 658→767 — a **1–3 px match, i.e. the box is that candle's wick-to-wick
  range exactly**. No other candle in the neighbourhood matches (the candle before it spans 627→765). The
  box runs forward in time to the right of the panel. A yellow circle is drawn around that candle and its
  neighbours; a thin white outline is drawn on the box's first candle. In `S32` price returns and reacts
  inside the box, and the box is still drawn exactly as before.
  *Note on colour:* the candle the box is pinned to in `S31`/`S32` is drawn in the same colour as the
  impulse candle, **not** the opposite colour. See the disagreement note immediately below.
- `S43` (real chart, USD/JPY 1h). The "1h Order Block" is a grey band **29 pips tall** (153.36→153.65),
  drawn forward in time, with a **blue rounded-rectangle highlight wrapping exactly one candle** (x 813–824)
  whose own wick-to-wick range is 153.36→153.66. The box's vertical edges equal that candle's high and low.
- `S39` (real chart, USD/JPY daily). The "Order Block" is a pink rectangle **138 pips tall** (154.12→155.50)
  drawn forward in time from the area where the decline began. On a daily chart one candle is ~100–140
  pips, so this is one daily candle's range seen at a coarser scale — the same object. **Its top edge does
  not coincide with the high of any candle within a few bars of its left edge**, so unlike `S31`/`S43` this
  particular box cannot be pinned to a named candle by measurement; treat it as approximately one candle.
- `S46`/`S47` (real chart, USD/JPY 1h). A new **grey** "Order Block" box after the reversal, spanning
  about **153.34 → 153.61** (27 pips; y 360→432 in the frame), with its lower edge marked by a dashed line and
  its left edge at the candle that began the down-move. *Correction (S010):* an earlier version of this
  bullet described the **pink** fill (153.77 → 153.34) as the order block. It is not: the pink and teal
  rectangles share one x-range (1168→1602) and butt against each other at 153.34 — that is a TradingView
  position box, not a zone (see §2.11).
- `S42`–`S45` (real chart, USD/JPY 1h). A **"Daily Order Block"** drawn as a pink band across the top of
  the 1h chart (154.2 up to ~154.8, clipped by the frame), i.e. the daily object re-drawn on a lower
  timeframe and extended forward. `S43` places a second, lower "1h Order Block" beneath it, and a white
  "FVG" line immediately above that lower box.

**Scale statement (the point of concept 2.1 vs 2.2).** These are **two different objects at two different
scales**, and the material draws them differently:

| | macro supply/demand zone | order block |
|---|---|---|
| drawn in | `S01`, `S04`–`S07`, `S25`, `S28` | `S31`–`S33`, `S39`, `S43`, `S46`, `S47` |
| shape | a thin band at the **lows of a cluster** of candles | the wick-to-wick range of **one candle** |
| vertical extent | covers the cluster's lower wicks; ~one candle body tall | exactly one candle's high-to-low |
| horizontal extent | starts at the cluster, runs forward | starts after the one candle, runs forward |
| what it is for | the area where price may react | tightening the stop (deck; **not stated in the frames**, see §2.11) |

**Not specified.** Which single candle to pick when two candidates sit side by side; whether the candidate
must be opposite-coloured (see the disagreement note); whether the box is the candle's full wick range or
its body on timeframes other than 1h; whether an order block expires after first touch; whether an order
block must sit inside a macro zone. None of this is stated anywhere in the 48 frames.

> **Disagreement with an existing doc — flagged.** `04-video-walkthrough.md` says the order-block box
> "covers **the last opposite-coloured candle** before the impulse" and calls that reading "confirmed three
> times over". Across all 48 frames the material never says "opposite-coloured", and in `S31`/`S32` the box
> is measured onto the candle **immediately before the impulse**, which on that diagram is drawn the same
> colour as the impulse. What the frames support is *the single candle immediately before the displacement
> move, drawn wick to wick*. "Last opposite-coloured candle" is a stronger claim than the frames carry.
>
> **Scope of that disagreement (S010, after reading all six decks first-hand).** It concerns the *video's*
> frames only. The three supply-and-demand decks **do** say it, in words, repeatedly: "the very last
> opposite-colored (red) candle immediately before the buying frenzy" (Ultimate S&D, origin slides), "the
> previous opposite-colored candle" (Supply & Demand, drafting slide), "drawn strictly wick-to-wick on the
> preceding opposite-colored candle" (Institutional SOP, item 5). So for the S&D method the opposite-colour
> rule is the material's, and `SupplyDemand` now applies it (`_last_opposite_candle`). For the SMC order
> block the frames still carry only "the candle before the displacement".

---

### 2.3 Inefficiency / fair value gaps (FVG)

**Stated.** `S01` labels the region "Inefficiency", annotates it "Imbalance", and marks the box "FVG"; the
`S08` slide lists Inefficiency as the first of three factors; `S02`/`S37` list the concepts that depend on
it. `S20` shows three of them on a real EUR/USD chart with no text at all. `S22` states the only rule about
them (see §2.8).

**Shown.**

- `S01`, left panel — **two dashed horizontal lines, not a filled box**: upper at y 492–493, lower at
  y 702–703, drawn from just after the impulse to the right edge of the panel. The upper line is at the
  **low of the third candle** of the sequence (that candle's range 411→488); the lower line is at the
  **high of the first candle** (its range 704→814). The displacement candle sits between them, its wick
  range 378→736 spanning both lines. This is the strict three-candle reading, and it is drawn as such.
- `S10` (real chart, EUR/USD 1h). The FVG is drawn as a **filled pale rectangle** y 510→614 =
  **1.15349→1.15545, ~19 pips**; x 823→1310. Measured against the candles: candle 1 (x 817–830) has high
  1.15335, candle 3 (x 855–870) has low 1.15549 — so the box is exactly the gap between candle 1's high and
  candle 3's low, minus line thickness. **It is the strict, no-wick-overlap version.**
- `S20` (real chart, EUR/USD 1h) — **three FVG boxes**, each a filled rectangle with no label but "FVG":
  1.16864→1.16707 (~16 pips), 1.16595→1.16479 (~12 pips), 1.16324→1.16121 (~20 pips). Each begins at its
   impulse candle and runs forward to a different x — the right edges do not coincide with the chart edge.
- `S31` (synthetic) — the gap is marked by a single **white horizontal line** at the top of the big green
  candle (candle 1), with the word FVG to its right; the gap region above is empty.
- `S43` (real chart) — the FVG is drawn as a **single white horizontal line** at 153.65, x 837→1516, sitting
  exactly on the top edge of the 1h order block below it.
- `S46`/`S47` (real chart) — the FVG is a **filled teal rectangle** whose top edge (153.34) is a dashed
  line coinciding with the order block's lower edge, with a second dashed line at 153.17 inside it; the
  "FVG" label sits between the two dashed lines, and the teal fill continues down past the lower dashed
  line to the bottom of the chart. **The material does not state why the fill extends below its own lower
  boundary**; this is a drawing convention that could not be resolved from the frames.
- `S36`, 15-min panel — *(corrected S010, after viewing the frame)* the teal rectangle is **not** a
  higher-timeframe FVG. It is half of a **long position box**: teal target zone above (y 303→637), pink stop
  zone below (y 638→725), sharing one x-range, with the "Entry" arrow at their junction and a "$" bracket
  marking the risk. In the 1H panel the grey "FVG" box is the gap. The box is ~334 px of reward against ~87 px
  of risk, about **1 : 3.8** — the same drawing as the short box in `S46`/`S47`, in a synthetic schematic.

**Not specified.** Whether a gap is still "unfilled" when price wicks into it but does not close inside it
(the frames draw both a wick-only touch in `S21` and a body-through in `S12`); how old a gap may be; how
many gaps on the left of the chart must be checked; whether partial fills count. The material's rule is
"check the left side of the chart" — a scan, with no stated stopping condition.

---

### 2.4 Break of structure (BOS)

**Stated.** `S01` and `S08` name it "Break of Structure (Bos)" and "Breakout of Structure" respectively;
`S01` labels the dashed level "Market Structure". `S10`, `S14`, `S15`, `S19`, `S26`, `S28` and `S02` all
draw a "Bos" level. `S08` lists it as the second of the three factors.

**Shown.**

- `S01`, middle panel — a **dashed horizontal line at the high of a prior swing** (its left end sits on
  that swing's wick top; it runs right to the candle whose body crosses it), labelled "Bos". The demand
  band below is drawn the same way as in §2.1, and the caption calls it a "Strong Demand Area".
- `S01`, right panel — the same dashed-level device appears on the left half of the panel at the earlier
  swing high.
- `S10` (real chart) — a **solid black horizontal line at 1.15676**, drawn from a short vertical drop at the
  prior swing high and running right to where price closes above it. Price then continues up, and the
  demand band and FVG sit below the line.
- `S14` (synthetic, "An Imperfect Trend") — five **green dashed lines**, each at a swing high, each spanning
  only from that high to the *next* high, so the reader sees the ladder of higher highs; yellow triangles
  mark every swing high and low. One line in the middle of the sequence is drawn **red, not green**, with
  an arrow and the label "False Change of character".
- `S26`, `S27`, `S28` (synthetic, line chart) — the same device: green dashed "Bos" lines at swing highs,
  each spanning one leg.
- `S02` — a "Bos" dashed line above an "Order Block" box; `S15`/`S19` — a "Bos" dashed line above a later
  "Bos" structure.

**Not specified.** What counts as the structure being broken — a close beyond, a wick beyond, a body
beyond. The frames consistently draw the dashed level at a swing extreme and the break as the candle that
crosses it; they never state the test, and the drawn crossings include both wick-only and body-through
cases. Also unspecified: how many swings constitute "structure", and whether the level must be a major
swing or any local swing.

---

### 2.5 Pushed distance

**Stated.** `S01` and `S08` name it "Pushed distance" / "Pushed Distance" as the third of three factors
that qualify a zone. `S01`'s panel labels the start and the end of the move and captions the space between
them "Great pushed distance".

**Shown.**

- `S01`, right panel — an explicit measuring instrument: the word **"Start"** at the bottom with an arrow
  pointing **up into the demand band** (the base of the rally); the word **"End"** at the top with an arrow
  pointing **down onto the top of the last candle drawn**; and a **white dashed diagonal** running from
  inside the band up along the rally to that top candle. The measurement is therefore **the distance from
  the zone to the highest point the move reached before returning** — not the size of any single candle,
  not the duration.
- `S01`, left panel — the same idea is carried by the long grey arrow drawn from the base of the demand
  band up the whole rally, ending in an arrowhead at the top.
- `S26` (line chart) — each leg carries a rotated label along it (which, read closely, is the letters
  "FVG", rotated to follow the slope), so the leg is annotated with *what it left behind*, not with how big
  it was.

**Not specified — this is the largest unnamed judgement in the material.** What makes a distance "great"
is stated nowhere: no multiple of a candle range, no percentage, no ATR, no number of candles, no lookback
window. The caption on `S01` is literally a judgement ("Great"), and `S01` gives no comparator to measure it
against. Any numeric threshold for pushed distance is an invention.

---

### 2.6 Market control — a two-state idea

**Stated.** `S02` and `S37` both list "Market Direction" in the syllabus, and `S24` is chaptered "Who is in
Control?" — but the material **never states the two-state rule in words on any frame**. It is shown only.
`S28` captions one state with the words "Supply has taken control" and points an arrow at the price that
follows. `S29` closes the sequence with question marks at both ends of the drawn range.

**Shown.**

- `S23` (**synthetic, "Who is in Control?"**) — the whole idea in one picture: two large **rounded blob
  overlays**, a green one covering a rising leg and a dark maroon one covering the falling leg that follows
  it, **overlapping in the middle** where the sequence turns. Yellow triangles mark every swing high and
  low inside both. The blobs are drawn over the candles, not bounded by them: they extend above the highest
  wick and below the lowest.
- `S24` — the same chart with **three rectangles laid over it, each carrying a green tick**: two in the
  rising half and one in the falling half. Each rectangle is **split horizontally into two tints** — green
  above / maroon below for the two in the rising half, maroon above / green below for the one in the
  falling half. Each rectangle's upper edge sits at a swing high and its lower edge below a swing low, and
  the tint boundary falls between them, roughly a third of the way up. The ticks mark the zones that
  "worked".
- `S28` — the state change drawn on a line chart: three blue "Supply" rails across the highs, a red dashed
  "Choch" line, an arrow labelled "Supply has taken control" pointing down at the decline, and an arrow
  labelled "Unmitigated Demand" pointing down at a long teal demand rail that runs the width of the chart.

**Not specified.** What makes one blob a state rather than just a trend; how far back the state extends;
what the exact tint boundary in `S24` means (it is a drawing artefact — the frames never name it); whether
both states can coexist; whether the state resets. The material treats control as a single binary fact
about the recent past and never gives a rule for reading it off a chart.

---

### 2.7 Change of character (CHOCH)

**Stated.** `S13` heads the next section "Invalid Change of Character" and lists two invalidators — see
§2.8. The syllabus names it in `S02` ("Change of Character") and `S37`. `S12`, `S15`, `S17`, `S21`, `S27`
and `S46` all draw a "Choch" line. `S17` and `S21` show the word **crossed out in red**; `S15`/`S16` show
it surviving only as a liquidity sweep; `S12` shows it holding.

**Shown.**

- `S12` (real chart, EUR/USD 1h) — a **dashed dark horizontal line at 1.15220**, i.e. at the **lower edge**
  of the demand band drawn in `S10` (band 1.15218→1.15328). It spans from the zone forward to the candle
  that closes through it; price then runs down to ~1.1475 without recovering. The line is drawn at the
  zone's **floor**, not its ceiling.
- `S27`, `S28` — the same device on a line chart: a red dashed "Choch" line at a prior swing low inside the
  range, spanning the range, broken by the decline.
- `S46` (real chart, USD/JPY 1h) — a **solid dark-red line at 153.27**, x 831→1138, drawn at a prior swing
  low; the word "Choch" sits under it. Price had already gone through it, and the frame then adds the new
  order block and FVG above (§2.2, §2.3).
- `S15`/`S17`/`S18`/`S21` (synthetic) — the CHOCH line is a **green horizontal line** at the swing low,
  labelled both "$Liquidity Pool$" and "Choch", running from the swing low rightward to the break point. A
  yellow circle is drawn around the break; `S16` captions it "Manipulation"; `S18` adds an arrow back to
  the line labelled "Back inside the range"; `S17`/`S21` strike the word out.
- `S19` — "$ Liquidity $" lines at **both** a prior swing high and a prior swing low, i.e. the pools sit on
  both sides of the range.

**Not specified.** The one thing the material never states is the break test itself: whether a CHOCH is a
close beyond the level, a wick beyond, or a body beyond, and over how many candles. In `S15` the break is a
**wick** below the line followed by an immediate recovery; in `S12` and `S46` it is a body through with no
recovery. The frames show both and state no discriminator other than what is on the left (§2.8).

---

### 2.8 The invalidators — liquidity sweep and FVG mitigation

**Stated** (the two, and only two, things the material states as rules about invalidating a CHOCH):

1. **Liquidity sweep** — `S16`, on a callout over the chart of `S15`: when a *major swing low* sits within
   a *liquidity area*, a break below that level is often just a liquidity sweep rather than a true market
   reversal. `S13` names this "Liquidity Hunt".
2. **FVG mitigation** — `S22`, on a callout over the chart of `S21`: always check the left side of the
   chart for **unfilled fair value gaps**. `S13` names this "Fair Value Gap Mitigation".

Both are stated as guidance ("often", "always check"), not as thresholds.

**Shown.**

- `S15` → `S18` (synthetic, the sweep). The green pool line is drawn as **two nearly-coincident horizontal
  lines** at y=645 and y=647 — each starting at the swing low it marks (x≈623 and x≈886) and both running
  right to the break at x≈1387. It is drawn at the swing low that produced the earlier rally. Price returns,
  a candle **wicks below the line**, and the recovery candle closes back above it; `S18`'s arrow labels the
  state "Back inside the range". The line stops at the break — it is not extended further right. A white
  diagonal labelled "Continuation" then runs up through the following candles. The drawn signature is
  therefore: **the level is pierced by a wick, the body returns inside, and the move continues in the
  original direction**.
- `S19` (synthetic) — the same chart with the liquidity marked at *both* extremes, above and below, making
  the point that the pools exist on both sides of the range.
- `S21` (synthetic, the gap fill). A **large teal FVG box** is drawn over the retest area: measured, the
  box's top edge sits at y=654 and the red "Choch" line immediately on top of it at y=647–652, so **the
  box's top edge *is* the CHOCH level**; the box then extends 100 px downward and right across
  x 603→1562, i.e. far to the **right** as well as over the origin of the move. A label "Swing low" with
  an arrow points at that same top edge. The "Choch" label is crossed out. Reading: the low that looked
  like a structural break is sitting on top of an unfilled gap, so the drop into it is mitigation, not
  reversal. Note that the gap here is drawn **overlapping and to the right of** the break, not only to its
  left, even though `S22`'s rule says to look on the left.
- `S14` (synthetic, "An Imperfect Trend") — the surrounding context slide: a normal trend drawn as a ladder
  of green lines, with one intermediate line drawn red and labelled a false change of character. The
  message is that a false CHOCH looks exactly like a real one until the left side is checked.

**Not specified.** "Major swing low", "liquidity area" and "unfilled" are all judgements with no stated
test:
- **Liquidity area** — not defined. `S15`/`S19` draw it as a horizontal level at a swing low or high, but
  no rule states how many touches, how equal the highs/lows must be, or how far back to look.
- **Major** — no definition; the frames draw one level and call it major.
- **Unfilled** — no rule for whether a wick touch counts (see §2.3).
- Neither rule constrains *how many* other candidate invalidators must be absent, nor what to do when both
  are present.

---

### 2.9 The validator matrix — true reversal vs sweep vs gap fill

**Stated.** The frames **never draw a matrix and never state one in words.** What they contain is one
worked example of each of the three outcomes, all three showing the same visual event at the moment of the
break. `02-engine.md`'s three-row table is the deck's, not the video's — flagged so nobody attributes the
table to these 48 frames.

**Shown** — the three instances the frames actually draw:

| instance | frame(s) | what is drawn at the break | what is drawn to the left | what price does next |
|---|---|---|---|---|
| **true reversal** | `S12` (real, EUR/USD 1h) | dashed line at the demand band's lower edge 1.15220; body closes through | the demand band it came from, no unfilled gap under it | falls to ~1.1475 with no recovery |
| **liquidity sweep** | `S15`–`S18` (synthetic) | green line at a prior swing low; **wick** below, body back above | the level is itself the visible stop cluster; `S19` adds a second pool above | reverses inside the range and continues up |
| **FVG mitigation** | `S21`/`S22` (synthetic) | "Choch" line struck out; a teal FVG box whose top edge *is* the swing-low level | an **unfilled fair value gap**, drawn over and to the right of the break | resumes the original direction |

**Not specified.** The matrix has no measurable entry conditions in the frames. Which of "clean structure
behind it", "consolidation", "imperfect trend", "obvious stop cluster" applies is exactly what the material
leaves to the eye. The frames give three examples and two admonitions, no test.

---

### 2.10 Top-down analysis — which timeframe does what

**Stated.** `S35`, on its own slide: the technique combines multiple timeframes to gain a complete
understanding of market conditions. `S34` heads a slide "Top-down Analysis". `S02`/`S37` list it in the
syllabus.

**Which pairs the material actually uses — three different ones, and it never picks:**

| frame | scale chain | what each panel draws |
|---|---|---|
| `S34` (synthetic) | **1H → 15m** | left: the whole move with a pink "Key Level" band across its low and a "Breakout" dashed level above; right: the same area refined, with a grey "OB" box and a "Rejection" arrow coming off it |
| `S36` (synthetic, three panels) | **Daily → 1H → 15min** | Daily: the "Breakout" of a dashed structure level and the pink "Key Level" band. 1H: a grey "FVG" box and a "Rejection" arrow. 15min: the pink key level with a "$" bracket and the teal higher-timeframe box above it, and the only **"Entry"** marker in the whole video |
| `S38`–`S47` (real, worked example) | **Daily → 4H → 1H** | Daily: resistance and support lines, then a daily "Order Block" box and an FVG line. 4H: the same daily order block re-drawn over the 4h chart, plus a "4H level" line. 1H: the daily order block across the top, an FVG line, a "1h Order Block" box, and then the reversal |

**What the division of labour is:** the material **never states it in words**. It is only visible in what
each panel draws, and the pattern is consistent across the two synthetic examples and the real one:
the **highest timeframe supplies the key level and the breakout context**; the **lowest timeframe supplies
the order block and the entry trigger**; the middle panel, when there is one, supplies the gap/rejection.
`03-operating-manual.md`'s three-row "goal / output" table is the deck's wording, not the video's.

**Not specified.** Which chain to use — the material shows three different ones and never fixes one.
Whether the timeframes must be adjacent (1H→15m) or may skip. What to do when the timeframes disagree.
Whether the chain is re-derived each day.

**A measured inconsistency inside the worked example** (reported, not resolved): the *same* two daily
levels are re-drawn by hand on different charts at different prices.
- Daily resistance: **158.35** on the daily (`S38`), but **157.48** on the 4h (`S40`, `S41`).
- Daily support: **149.52** on the daily (`S38`), **149.72** on the 4h.
- The "4H level": **150.71** on the 4h chart (`S41`), **151.52** on the 1h chart (`S42`–`S48`).

The drawn lines are hand-placed and are not consistent across frames; no frame states a number.

> **Disagreement with an existing doc — flagged.** `04-video-walkthrough.md` records "Daily: resistance
> ~158.6, support ~149.8", "an order block ~154.4–155.7 with an FVG" and "A '4H level' at ~151.3". Measured
> off the frames: resistance 158.35, support 149.52; the daily order-block box spans **154.12→155.50** and
> the daily FVG is drawn as a **single line at 152.91**; the 4H level is 150.71 on the 4h chart and 151.52
> on the 1h chart. The frames win.

---

### 2.11 Execution

**Stated — in the frames.** Very little, and this matters:

- `S36`'s 15-min panel carries the **only "Entry" marker in the entire video**: an arrow pointing up at the
  junction of a **long position box** — teal target above, pink stop below (*corrected S010: an earlier
  version called the teal rectangle a higher-timeframe box, and said no frame draws a stop or target; `S36`,
  `S46` and `S47` all do*). The marker is a *place*, not a rule — no order type, no price, no trigger
  condition — but the box beside it shows where the stop and the target sit relative to it.
- `S44` draws the intended trade as a **single annotated path**: a line coming down out of the daily order
  block into the 1h order block box, then turning and rising — the planned long.
- `S45` draws what happened: price went through the 1h order block and kept falling.
- `S46` adds the CHOCH line, a **new order block**, an FVG, and **a short position box** (below).
- `S47` (16:05 of 16:52, chapter "Real Chart Example") is the same chart with the decline drawn in: price
  falls out of the new order block and runs to the "4H level", touching it at the right edge.
- `S48`, the closing slide: patience is one of the most valuable skills a trader can develop, and waiting
  for high-quality setups is a discipline that must be mastered, not a choice.
- `S03` defines the plan as a *day-trading* plan: positions are opened and closed within the same trading
  day, with nothing held overnight.

**Stated — not in the frames.** The three-step execution sequence, the **limit order placed at the order
block**, the **stop placed just above the order block's wick**, the **minimum 1:2 risk-to-reward** and the
**next-macro-level target** appear in `03-operating-manual.md` and in the deck material that file
summarises. **None of the 48 frames contains the words stop, limit, risk, reward, ratio, target or 1:2**, and no frame
draws a *limit* order. *Correction (S010): an earlier version of this section said there is no stop line, no
target line and no ratio drawn on any chart. That was wrong.* `S46` and `S47` carry a TradingView-style
**short position box**: a pink rectangle above the entry and a teal rectangle below it, sharing one x-range.
Measured off the frames (pixel rows against the right-hand price axis, 154.80 at y=34 and 151.30 at y≈990):

| part | frame rows | price | what it is |
|---|---|---|---|
| pink (risk) | y 314 → 431 | **153.78 → 153.34** | the stop zone: its top is **above the order block's top (153.61)**, i.e. above the wick |
| entry | y 432 | **153.34** | the order block's lower edge / the FVG's top edge — the dashed line |
| teal (reward) | y 434 → 925 | **153.34 → 151.54** | the target zone, ending on the blue **"4H level"** line (151.52) |

That is **about 43 pips of risk against about 180 of reward — roughly 1 : 4.2**, not 1:2. Two things follow.
The target *is* the next higher-timeframe level, and this is now **shown in the frames**, not only stated in
the deck. And the 1:2 is a *minimum* in the deck's wording, so a 1:4 example does not contradict it. The box is
a **hand-drawn overlay, placed with hindsight** (it is drawn after the short has already happened), so it is
evidence of what the author *means* by a stop and a target, and is not evidence that the trade was taken.

**Shown** (the geometry, for the planned long): in `S43` the origin candle is drawn as a
single 1h candle 29 pips tall, and the box's lower edge (153.36) is where price was expected to react;
`S44`'s path returns to that lower edge. In `S36` the entry is drawn at the junction of the long box's stop and target zones, about 1 : 3.8 by
measurement (S010 correction to an earlier reading of it as a coincidence of a higher-timeframe box edge and
a key-level band).

**Not specified.** Without the deck text: where the stop goes, what the minimum reward is, whether the
entry is a limit or a market order, what the target is, how the target relates to the higher timeframe,
and what to do when the order block is traded through. With the deck text, the numbers exist (1:2, the
wick) but they are **not evidenced by these frames**, so an implementer should record which source each
number came from.

---

### 2.12 Patience and overtrading

**Stated.** `S48`: patience is one of the most valuable skills a trader can develop; waiting for
high-quality setups is not simply a choice but a discipline that must be mastered. `S33` supplies the
corresponding caution about the tool itself: order blocks do not always work and are not guarantees.
`S13`–`S22` — roughly a third of the runtime — is given over to breaks that *look* like reversals and are
not, which is the same argument stated with examples.

**Shown.** `S48` is a text callout over the real USD/JPY 1h chart. *Correction (S010): an earlier version
said the chart has no entry/stop/target and that the worked example "did not work".* Half of that is true and
half is not. The **planned long failed** (`S44`→`S45`, price ran through the 1h order block). What the video
then draws (`S46`/`S47`) is a **short** from the new order block, with stop above it and target on the 4H level,
and `S47` shows price reaching that target. So the example ends in a *winning* position box — drawn with
hindsight, with no broker marker and no profit figure, which is why it is a teaching overlay and not a track
record. The patience slide's own point still stands: the long was the wrong read, and the method's answer was to
wait for the change of character rather than to keep the long.

**Not specified.** No frequency, no maximum trades per day, no minimum time between setups, no quality
score. The material states "wait for high quality" and defines quality only by the §2.4–§2.9 concepts, none
of which carry a numeric threshold.

---

## 3. Rules for implementers

Restated compactly from [`README.md` §"How a perception becomes code"](README.md) — **that section is the
source and the authority**; this is a pointer, not a replacement.

1. **If the source states it, implement it as stated.** Transcribe, and check the transcription against
   the material rather than against intuition. In this method that means the strict no-wick-overlap gap,
   the order block as the single candle, the two invalidations, and — if you take them from the deck rather
   than the video — the limit entry, the stop at the wick and the 1:2 floor.
2. **If the word is comparative — big, far, clean, obvious, great — decode it as a comparison, never as a
   constant.** A comparison is against the chart's own visible window: "in the top tenth of the bars in
   view" represents the perception; "at least 0.6 of its own range" is a rule of somebody else's invention
   wearing the same name. An absolute threshold is legitimate only where the source gives the number.
   *Pushed distance (§2.5) is the live case: the material says "great" and gives no comparator.*
3. **If the source leaves it to the eye, it is absent and must be marked absent — never filled in.** "Clean
   structure to the left", "obvious liquidity", "major swing low", "unfilled" and "great pushed distance"
   are judgements with no stated test anywhere in the material. Leave the criterion out and say so, or
   recover it from labelled reference examples; do not choose a threshold here.

This already failed once in this repository: "great pushed distance" became "at least three candle ranges",
and that single invented constant was the whole difference between an engine that never fired in six weeks
of data and one that fires.

---

## 4. What the current code does and does not implement

*Rewritten by S010 after the analyst (`clicktrader/smc/analyst.py`) was built and run on real EUR/USD and gold
bars; it replaces an earlier table that was assembled from prose and said most of this was absent.* Read the
picture (`clicktrader smc-chart`) before trusting any row.

| concept (§) | frames | what the code does now |
|---|---|---|
| Supply/demand zone band (§2.1) | `S01`, `S04`–`S07`, `S25`, `S28` | **Implemented.** A level is a band around the candles that formed it (lowest wick to lowest body bottom for a floor, as `S01` draws it), overlapping bands merged, alive until a bar *closes* through the far edge, then deleted. Drawn faded by how many times the market turned there. |
| Order block (§2.2) | `S30`–`S33`, `S39`, `S43`, `S46`, `S47` | **Implemented** as the single candle before the leg, wick to wick; the last opposite-coloured candle (the three S&D decks say so in words; the frames do not contradict it). |
| Inefficiency / FVG (§2.3) | `S01`, `S10`, `S20`, `S31`, `S43`, `S46` | **Implemented**, strict no-wick-overlap; open until price trades back into it. |
| Break of structure (§2.4) | `S01`, `S02`, `S10`, `S14`, `S15`, `S19`, `S26`–`S28` | **Implemented** as a close through the trend's last extreme (continuation), reported as `BOS`. |
| Pushed distance (§2.5) | `S01`, `S08` | **Measured and reported, not gated.** The material judges it by eye and gives no number; gating on one is the invented-constant failure. Shown in each opportunity's reason. |
| Market control, two states (§2.6) | `S23`, `S24`, `S28` | **Implemented.** Seeded by the first clear structure, then flips only on a true change of character. Shown as the strip along the top of the drawing. |
| Change of character (§2.7) | `S12`, `S15`, `S17`, `S21`, `S27`, `S46` | **Implemented**: a close through the last swing the current control has to hold. |
| Liquidity-sweep invalidation (§2.8) | `S15`–`S19` | **Implemented as wick-through-and-close-back** (`SWEEP`, red). It does *not* use the "visible stop cluster to the left" test; that is a judgement the material leaves to the eye. A sweep no longer uses the level up: a later close through it is a fresh break. |
| FVG-mitigation invalidation (§2.8) | `S21`, `S22` | **Implemented** (`GAP FILL`, orange) — but it **has not fired once** on the EUR/USD or gold bars read so far, so the path is tested on fixtures only. |
| Validator matrix (§2.9) | `S12`, `S15`–`S22` | **Implemented**: every break is one of BOS, CHOCH, SWEEP, GAP FILL, with its reason. |
| Top-down alignment (§2.10) | `S34`, `S36`, `S38`–`S47` | **Partly.** A veto only: the slower clock's structure (default 60 min over 15 min) must not contradict the trade. The daily → 4H → 1H chain is not built; the recordings are days long, not months. |
| Daily / macro levels (§2.10) | `S38`, `S39` | **Approximated**: the target is the nearest opposing level on the same chart that leaves the 1:2 floor. There are no daily levels to use. |
| Limit entry at the order block (§2.11) | deck; `S36` Entry marker | **Implemented**: entry at the block edge nearest price (bottom of a supply block, top of a demand block). |
| Stop at the wick (§2.11) | `S46`/`S47`, deck | **Implemented**: beyond the block's far wick. |
| Minimum 1:2 risk-to-reward (§2.11) | deck; `S36`, `S46`/`S47` | **Enforced**: no level leaving 1:2 means the opportunity is rejected as `NO ROOM`. |
| Take profit at the next macro level (§2.11) | `S46`/`S47`, deck | **Approximated** as above. |
| Zone dies on a close beyond its far edge; first tap only; no falling knife | Institutional deck pp. 7–8, Ultimate deck p. 8 | **Implemented** (`DEAD`, first-tap fill, `KNIFE` = the reaching bar is as large as the impulse's median body — a comparison, not a constant). |
| Patience / overtrading (§2.12) | `S48`, `S33` | **Now consistent.** A few true opportunities per few hundred 15-minute bars: EUR/USD 276 bars → 14 CHOCH, 4 armed; gold 287 bars → 14 CHOCH, 3 armed. |

**What is still absent or only approximate, stated plainly:** Fibonacci 61.8 confluence, "lowest = strongest",
the level stack / flip zone, the daily → 4H → 1H chain, the left-side stop-cluster test, and any judgement the
material leaves to the eye (`docs/smc/README.md`, rule 3). **What has still not been done:** compare the drawing
with the owner's own markup of a chart — the reference examples that rule 3 says are the only legitimate source
for the criteria nobody wrote down.
