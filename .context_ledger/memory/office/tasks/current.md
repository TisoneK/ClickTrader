# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

<!-- TEMPLATE — replace everything below this comment:
- **Session:** YYYY-MM-DD — <agent> / <model>
- **Task:** <what is being worked on right now>
- **Status:** blocked (push not permitted from this session; target platform unknown — P-2026-09-24-1) | done | blocked (<blocker>)
-->

- **Session:** 2026-09-24/25 — Amara / claude-sonnet-5
- **Task:** **Digit-contract side (CryptonicHub + Deriv): stable, considered done for now.** All 3 layers built, live-verified (real demo trades placed and broker-settled), 8 strategy claims tested and all converge to "No edge" as the algebra predicts. Three rigor/documentation follow-ups shipped (multiple-comparisons correction, broker-verified settlement replacing self-grading, DESIGN.md now documents all of it). Live stake sizing for a future digit-contract live-runner is deliberately left open, pending the user's own stake-sizing research videos (separate, not-yet-started track).

  **New active thread: forex**, at the user's request, scoped deliberately to the safer end of what Deriv offers (fixed-stake Rise/Fall-style options on a forex underlying — the user chose this explicitly over real leveraged CFD margin trading when given the choice, since they're relying on this session's lead and have limited domain knowledge here). Unlike digit contracts, forex direction has **no algebraic proof either way** — this is genuinely open empirical territory, so pacing is more careful and the harness is honest about not having a verified payout model yet (reports hit rate vs. a 50% coin-flip null, not P/L).
  - `clicktrader/forex/` (1323c84): new package, not an extension of `model.py`/`harness.py` (neither's assumptions hold — no fixed win probability, no one-tick settlement). Reuses `strategies.History` (gained `last_prices()`) and the generic half of `stats.py` directly.
  - First strategy: `MovingAverageCrossover` (the textbook baseline, chosen because it's genuinely standard, not picked to be easy to disprove), fires only on an actual crossing. Control: `RandomDirection`.
  - Confirmed live: `record-deriv --symbol frxEURUSD` (or any forex pair) works through the **existing, unmodified** layer-1 pipeline — zero new code needed for recording itself. A background recording of real EUR/USD ticks is running now (`recordings/forex/live-eurusd.jsonl`).
  - Real forex ticks are much "stickier" than synthetic indices (price often unchanged for several consecutive tick messages) — expected, since real quotes don't refresh on a fixed 1-second RNG schedule the way "(1s)" synthetic indices do.
- **Status:** open. Next: let the real EUR/USD recording accumulate, then run `forex-replay` against it once there's enough data for a real (not synthetic-only) read. No forex live-trading code exists yet — deliberately not started until the directional-accuracy question has a real answer.
