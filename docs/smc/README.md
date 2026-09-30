# The SMC trading architecture — reference notes

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
