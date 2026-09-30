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

---
## ADR-3: The supply-and-demand method is evaluated on gold (2026-09-28)
- **Status:** accepted
- **Context:** The user chose gold for this strategy ("i prefer gold on this strategy"). That agrees with the visual evidence: both decks' worked examples describe gold, and the charts they draw — a tight base, then four oversized one-way candles with non-overlapping wicks, then a long overlapping return — are the shape of a volatile trending market on a fast chart. Measured against the data already held, 15-minute EUR/USD does not print that shape at all (the longest same-direction run over 72 bars was four candles with bodies `0.00079, 0.00032, 0.00013, 0.00054`, which is the chop the decks draw as invalid).
- **Decision:** XAU/USD (`frxXAUUSD` on Deriv) is the instrument this method is tested on. Verified, not assumed: the existing recorder captures it unchanged — `record-deriv --symbol frxXAUUSD` wrote 20 ticks at ~4129 on 2026-09-28 — so the instrument switch needs **no new adapter**, because the recorder, the bar builders, `structure.py` and the trade harness are all instrument-agnostic.
- **Consequences:** The EUR/USD recordings stay as the control instrument rather than the subject; a result that appears on gold and not on EUR/USD is a statement about the instrument, which is exactly the hypothesis the visual evidence raised. Nothing about `SupplyDemand` was tuned to EUR/USD, so its parameters carry over unchanged. The binding constraint is no longer *which* instrument but *how much* data: gold's own history can be pulled from the broker rather than recorded (see the parking lot), and paging that history is rate-limited, so a large sample has to be paced rather than fetched in a burst.

---
## ADR-4: A replay shares one settling rule, and compares to its control by the difference (2026-09-30)
- **Status:** accepted
- **Context:** A review of the Sonnet sessions' work found two defects of the same kind — a measurement that was right when written and then quietly wrong. (1) `risk_replay.py` copied the harness's settle-on-the-next-tick rule; when `Decision.duration` later landed in `harness._run_segment` the copy went stale, so a multi-tick strategy was graded against the wrong tick there. (2) The forex verdict tested the strategy's interval against the random control's *point* hit rate, treating an estimate as exact and over-calling both POSITIVE and Worse. A third suspected defect — that `risk_replay` should skip a refused bet and carry on, as the live runner does — was investigated and **rejected**: the bet sequence comes from the unguarded strategy, so bets after a refusal belong to a path that would not exist (a live strategy that is refused never sees an outcome and re-asks for the same stake).
- **Decision:** (1) Anything that settles a decision outside `harness._run_segment` calls `harness.settling_index` rather than re-deriving the rule; a session replay ends at the first guard refusal, and says why beside the `break`. (2) A verdict against a random control is read from the interval of the **difference** (`stats.difference_interval`), never from the strategy's interval against the control's point rate. `plain_words` uses the same reading.
- **Consequences:** Any future replay (new contract, new harness) must take its settle tick from `settling_index`, so a change to settlement is made in one place. Verdict wording changed: the strings now carry the gap's interval; the prefixes the CLI matches on (`No directional edge`, `NO VERDICT`) are unchanged. Re-running the EUR/USD capture under the new rule: engulfing-bar and inside-bar read no edge, pin-bar reads worse than the control (-0.109 to -0.037). An earlier logged figure — engulfing-bar 0.385 against a 0.473 control — does **not** reproduce on the current `live-eurusd-20260928.jsonl` (0.383 vs 0.388); it was taken from a snapshot, so treat it as unverified until re-measured.
