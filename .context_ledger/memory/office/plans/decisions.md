# Architectural Decisions (append-only, ADR-style)

Decisions already made — future agents respect these rather than
relitigating them. To reverse one, append a new ADR that supersedes it.

<!-- TEMPLATE — copy below the last entry:
---
## ADR-N: <short title> (YYYY-MM-DD)
- **Status:** accepted | superseded by ADR-M
- **Context:** <what forced the decision>
- **Decision:** <what was decided>
- **Consequences:** <trade-offs accepted; what future agents must respect>
-->

---
## ADR-1: Platform-agnostic core first, stdlib only (2026-09-24)
- **Status:** accepted
- **Context:** The target platform, its DOM, and whether it has an API are all open (DESIGN.md open questions 1–3), but most of the three layers depends on none of that.
- **Decision:** Build model, recorder storage, stats, harness, ledger and limits as a pure-Python, zero-dependency package (`clicktrader/`); page/feed adapters come later behind `TickRecord`. Prices are stored as displayed strings, never floats (trailing zeros are digits). Contracts settle on the next tick. The harness's out-of-sample split cannot be turned off, and every replay runs a random control.
- **Consequences:** Adapters must produce `TickRecord` with the price string exactly as shown. Report thresholds (`MIN_TICKS_UNIFORMITY=2000`, `MIN_BETS_REPORT=500`) are pinned by tests — the 2000-tick power claim is checked by simulation in `tests/test_stats.py`; change the docstring and test together.

---
## ADR-2: Stop/target trades are graded in R against each trade's own mirror (2026-09-28)
- **Status:** accepted
- **Context:** The user asked for the "sneaky pivot" range method to be built — a chart method whose whole shape is an entry, a stop and a target. Layer 2 could not grade that: a decision carried only a direction and a horizon (`forex/model.py`), grading was one comparison of two prices (`forex/harness.py`), and a method can be right about direction and still be stopped out. The review that scoped this recorded the gap before any code was written, and the user chose to close it rather than deform the method into a fixed-horizon direction call.
- **Decision:** A second decision type (`TradePlan`: direction, stop, target — **no** entry price, which the harness reads off the tick the decision was made on so a strategy cannot claim an entry it did not get), a second strategy protocol and registry, a second harness (`forex/trade_harness.py`) and a second CLI command (`forex-trade-replay`). Outcome is **expectancy in R**, 1R being the distance from entry to the stop. The control is the **mirror** of each trade — opposite direction, same tick, same two distances — graded from the same decision so the pairing is exact. The verdict reads the **paired** difference between a trade and its mirror, not either absolute expectancy. Trades that reach neither level before the segment ends are excluded and counted, never marked to market.
- **Consequences:** The two forex families stay deliberately separate — different modules, registries, commands and verdicts that are not comparable — so nothing has to `isinstance`-check its way through a replay. Three limits are now load-bearing and must stay stated wherever this mode is reported: (1) a tick grid coarse enough for one tick to jump a level gives *both* a trade and its mirror a positive absolute expectancy, which is measured in the tests and is why the absolute number is never the answer; (2) no control can separate a real edge from a sample that merely trended the method's way — flipping the direction does not remove a trend, and only a fresh period or instrument does; (3) the expectancy interval assumes independent trades, so a strategy firing on every tick (overlapping trades) gets an interval narrower than its sample deserves. The mode's own evidence state is recorded in DESIGN.md rather than left implied: built and tested, and zero trades on every recording the project holds.
