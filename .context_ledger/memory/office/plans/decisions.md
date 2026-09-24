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
