# The SMC trading architecture — reference notes

> **Read [`spec.md`](spec.md) first if you are going to implement anything.** It is the concept-by-concept
> specification: what the material *states*, what it *draws* (measured, frame by frame), and what it
> *leaves to the eye*. This file set explains the method; `spec.md` is what an implementer is held to, and
> the rules it restates in §3 are the reason — a single invented constant is enough to turn this method
> into a different strategy.

Notes on the "Smart Money Concepts" system as its own material lays it out, written up so future sessions
can read the method without needing the source. **Provenance:** a course deck the project owner holds
(named "The 2026 Day Trading Architecture — distilling Smart Money Concepts into a single, executable
daily algorithm"), supplied as a 15-page PDF converted from the original video. The source is not
committed here and is not reproduced: what follows is a summary of the method in this project's own words,
citing the technique by name, on the same reasoning the candlestick work used — facts and methods are not
copyrightable, a course's material is.

**Why these notes exist.** Every measurement in this repo has so far been of a *simplified* version of
this method — the supply/demand SOP deck and the Pure Price Action deck are both thinner than the
architecture they come from. The gap is almost entirely in **signal identification**: which of the
patterns on a chart is a setup and which is a trap. That is what these pages are about, so each file ends
with what the code does today and what it does not.

## The architecture in three pillars

1. **Components — the raw materials.** Supply/demand zones, order blocks, inefficiencies (fair value
   gaps). See [`01-components.md`](01-components.md).
2. **The engine — market physics.** Market control as a two-state machine, change of character, and the
   liquidity sweeps that are *not* changes of character. See [`02-engine.md`](02-engine.md).
3. **The operating manual — assembly.** Top-down analysis across three timeframes, limit-order execution,
   and a minimum 1:2 risk-to-reward. See [`03-operating-manual.md`](03-operating-manual.md).

The system's own claim is that the failure mode of most traders is applying these concepts *disconnected*
— one of them, at random, without the others. Its shape is a pipeline: raw components feed the engine,
the engine's state feeds the operating manual, and the output is one execution setup.

## The two ideas worth carrying away even if nothing else lands

- **A break is not automatically a reversal.** Three different things look identical at the moment of the
  break — a true change of character, a liquidity sweep, and price filling an old imbalance — and telling
  them apart needs the *left* side of the chart, not the candle that broke. `02-engine.md` has the matrix.
- **Everything is measured against what is to the left.** Unmitigated gaps, obvious stop clusters, clean
  versus messy structure. A pattern is not a signal; the same pattern with a different left-hand side is a
  trap.

## How a perception becomes code

This whole package is an attempt to transcribe what an experienced trader sees into something executable, with
the discipline and the emotion left out. That only works if the transcription is *faithful*, and the failure
mode is quiet: a judgement that is not stated anywhere gets replaced by a number, and the number then quietly
becomes the strategy. It happened here — "great pushed distance" became "at least three candle ranges", and
that single invented constant was the whole difference between an engine that never fired in six weeks of data
and one that fires.

So three rules, in order, for turning anything seen into something computed:

1. **If the source states it, implement it as stated.** The gap's strict no-wick-overlap, the order block as the
   single opposite candle, the two invalidations, the 1:2 floor. These are transcriptions and they are checked
   against the material rather than against intuition.
2. **If the word is comparative — big, far, clean, obvious — decode it as a comparison, never as a constant.**
   A trader's sense of a big candle comes from the candles around it, so "in the top tenth of the bars in view"
   is a representation of that perception, while "at least 0.6 of its own range" is a rule of somebody else's
   invention wearing the same name. An absolute threshold is legitimate only where the source gives the number.
3. **If the source leaves it to the eye, it is absent and must be *marked* absent — never filled in.** "Clean
   structure to the left" and "obvious liquidity" are judgements with no stated test. Inventing tests for them
   produces an engine that answers a different question while looking like it answers this one. The honest
   options are to leave the criterion out and say so, or to recover it from reference examples — moments the
   trader calls a signal or a miss, with a sentence saying why. Those examples are the specification for the
   criteria nobody wrote down; a threshold chosen here instead is the thing this section exists to prevent.

The point of stating it: rule 2 is the difference between decoding a perception and replacing it, and rule 3 is
the difference between an honest incomplete engine and a confident wrong one. Both failures have already
happened in this repository once.

## Reading and drawing a chart

```bash
clicktrader smc-chart recordings/forex/live-eurusd-20260928.jsonl chart.png --minutes 15 --bars 150
```

`clicktrader/smc/analyst.py` reads the bars one at a time using only what a person would know at that moment
(a swing is not known until `strength` bars after it), and `smc/draw.py` draws the whole reading **in the
engine's own language**, so a person can disagree with a specific mark instead of with "the engine". Every word
in the picture is a verdict:

| mark | meaning |
|---|---|
| `HH HL LH LL` | swing names, against the previous swing of the same kind |
| blue band | a level (liquidity) while alive — faded by how often the market turned there; deleted when a bar closes through it |
| yellow box | an open fair value gap; it stops at the bar that filled it |
| `BOS` (blue, dashed) | the trend carried on through its last extreme |
| `CHOCH` (green) | a **true** change of character: a close through the level the current control had to hold |
| `SWEEP` (red) | the wick took the stops and the close came back — **not** a reversal |
| `GAP FILL` (orange) | price rebalancing an open gap — **not** a reversal |
| green / rose box `DEMAND`/`SUPPLY` | a **TRUE zone**: the origin of an aggressive move (the last opposite-coloured candle before a run of far-larger-than-usual same-coloured candles, wick to wick) that left a fair value gap and broke structure; `FRESH` until price first comes back, then `USED` (`KNIFE` if it came back violently); deleted (BROKEN) when a bar closes through its far edge |
| grey `X FALSE ...` | a **FALSE zone**: a run that looked like one but failed a rule of the decks' validation matrix, with the rule it failed — `NOT AGGRESSIVE` (ordinary-sized candles), `NO GAP`, `NO BOS`. Drawn while still standing so it can be argued with |
| orange box | the order block: the last opposite-coloured candle before the leg, wick to wick |
| pink / teal boxes | stop zone / target zone of an opportunity the engine would take, `LONG`/`SHORT n.nR`, then `WIN`/`LOSS` (hindsight, never used to decide) or `ARMED` |
| grey `X ...` | an opportunity it **rejected**: `NO ROOM` (no level leaves 1:2), `HTF` (against the slower clock), `KNIFE` (violent approach), `DEAD` (closed through the zone first) |
| top strip | who is in control: teal demand, red supply |

**Levels are not zones.** The blue bands are *levels*: stacks of swing points where the market turned (support / resistance, liquidity). A *zone* is different: the origin of an aggressive move, found and judged by the rules above. Earlier versions drew only levels and found an order block only after a change of character; it now scans for zones continuously and classifies each as TRUE, FALSE or BROKEN.

`smc/strategy.py` trades exactly what this reading calls true, so the picture and the trades cannot disagree.
`--readings` prints the few choices the reading makes that are the project's own (`analyst.READINGS`).

**Use the picture before and after changing any detection rule.** It found, in one look each, four defects the logs
had hidden: level clusters chaining into range-tall bands, a break measured at a band's middle, a sweep using a
level up so the real break two bars later was missed, and break logic switched off whenever the swing labels read
"range".

**Conventions checked against an open-source reference** (the `smart-money-concepts` Python library, read directly
because web search was unavailable): a swing is the extreme of N bars each side; BOS and CHoCH are read from the
sequence of swings, a break that continues the sequence versus one that goes against it; a liquidity level is
several highs or lows within a small range, with a recorded "swept" bar; a fair value gap is the strict
three-candle gap. Those agree with this package. The library's BOS/CHoCH needs a four-swing pattern; this analyst
reads against control instead, which is what the material's own two-state figure describes.

What the drawing does **not** settle, and should not be tuned by eye alone (rule 3 above): whether a person
would circle a level the engine draws, merge two they would not, or ignore one it marks. That needs the owner's own
markup of a chart — the reference examples rule 3 names as the only legitimate source.

**Zoom, drag and a person's own marks.** `--minutes 1 5 15` zooms (one picture per bar size, and a table of the
structure at each), `--from`/`--to` drags to a time window (UTC; the time axis is on the picture), and
`--mark PRICE` overlays a level drawn by hand and says how it compares with the engine's levels. The engine's own
renders, with the exact command and console output beside each, are in [`docs/evidence/`](../evidence/README.md),
including the one comparison with the owner's markup that exists.

**Judging the engine against a person's marks.** Write what you would mark on a chart as JSON (levels, zones,
changes of character, sweeps, trades, no-trade windows; see `docs/evidence/markup/`), then
`clicktrader smc-compare markup.json recording.jsonl` says, for each mark, whether the engine said the same and what
it said instead. The first markup was written by an AI agent, not the owner, and the file says so; the owner's own
marks go in the same format.

**Running it live.** See [`docs/live-demo-test.md`](../live-demo-test.md): paper first (`clicktrader run-smc`, places
nothing), then the demo account (`--place`), then `smc-readiness` for whether the evidence is enough. There is no
real-money path.
