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

## Looking at what the engine sees

```bash
clicktrader smc-chart recordings/forex/live-eurusd-20260928.jsonl chart.png --minutes 5 --bars 160
```

draws the bars with every level band, unfilled gap and swing point the engine holds laid on top
(`clicktrader/smc/render.py`; the colour legend is `render.LEGEND`; no dependencies, no text in the image).
Until this existed nothing the engine found had ever been compared with a picture. **Use it before changing
any detection rule and again after**: the EUR/USD chart showed in one look that level clusters were chaining
into bands as tall as the whole range, which the mean-price representation had hidden for the life of the
package. A level is now drawn — and broken — as a band around the candles that formed it (`LiquidityPool.low`
/ `.high` / `.far_edge`): a floor runs from its lowest wick to the top of the lowest member body, mirrored for
a ceiling, and a break means leaving the band through its far edge rather than touching its middle.

What it does **not** settle, and should not be tuned by eye alone (rule 3 above): on a consolidation the
engine now draws several overlapping bands where a person would circle one zone, and it gives a 120-bar-old
level the same weight as yesterday's. Whether overlapping bands merge and whether recency matters are
judgements the material leaves to the trader; they need the trader's own reference examples.

