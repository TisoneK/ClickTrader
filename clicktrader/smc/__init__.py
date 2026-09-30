"""Smart Money Concepts, as its own material lays it out: components, an engine, and an operating manual.

It is a package rather than a module because the source is three separable concerns with a pipeline
between them — raw components feed the engine, the engine's state feeds the assembly — and because the
structure is the cheapest way to keep the code honest about that. Each module may import the one below it
and never the reverse, so a future reader can compare the layering here against `docs/smc/` and see a
divergence instead of having to hunt for one.

- `components.py` — supply and demand zones, order blocks, fair value gaps. The raw materials.
- `engine.py` — market control as a two-state machine, change of character, liquidity pools, and the two
  things that invalidate a change of character. Market physics.
- `quality.py` — the three factors that make a zone valid: inefficiency, break of structure, pushed
  distance. A scorecard.
- `strategy.py` — top-down alignment and execution. The operating manual.

**A known wrinkle:** swings, gaps and zones come from `clicktrader.forex.structure`, which is a shared
primitive that happens to live under a package named for one asset class. That name is a leftover — the
module is about price, not currencies — and it is left alone for now on the rule that renaming a package
is churn that buys nothing measurable. Worth tidying one day, deliberately, on its own.
"""
