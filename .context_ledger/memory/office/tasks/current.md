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
  - Six strategies now registered (`clicktrader.forex.strategies.REGISTRY`): `random-direction` (control), `ma-crossover`, and four standard technical-indicator claims added in 8ad5c9e — `rsi-mean-reversion`, `macd-momentum`, `bollinger-mean-reversion`, `ema-trend`. All share one "fire only when the long/short/neutral zone changes" bookkeeping helper. New `clicktrader/forex/indicators.py` (SMA/EMA/RSI/MACD/Bollinger, cross-checked against known reference behavior — a strictly rising series drives RSI to 100, etc.).
  - **A cross-project reference slip happened and was caught by the user, then fixed** (428de1e): early docstrings named a separate, unrelated project of the user's as the source of these indicators. That project is private/unrelated and this repo is public — no reference to another of the user's projects belongs here, regardless of how accurate it would be. Full-tree grep confirmed clean afterward. Worth remembering as a standing rule, not just a one-off fix: describe techniques generically (e.g. "the standard RSI formula"), never cite where a private project happened to also implement something standard.
  - Confirmed live: `record-deriv --symbol frxEURUSD` (or any forex pair) works through the **existing, unmodified** layer-1 pipeline — zero new code needed for recording itself. A background recording of real EUR/USD ticks has been running (`recordings/forex/live-eurusd.jsonl`, ~5,400 ticks as of last check); all six strategies run correctly against it and correctly report NO VERDICT (still below the 500-bet threshold for any of them).
  - **`--account demo|real` added to `run-deriv`** (045a72a), at the user's explicit request — this project isn't purely for testing, so the real-money path needed to actually be reachable, not just supported by `get_otp_url` underneath with no CLI exposure. `--account real` requires its own separate `DERIV_REAL_ACCOUNT_ID` (never falls back to the demo ID), prints an explicit warning banner, and is gated by the same required, no-default `RiskGuard` limits either way. Default remains `demo`.
- **Status:** open. Next: let the real EUR/USD recording keep accumulating, then run `forex-replay` for a real read once there's enough data. No forex live-trading/executor code exists yet (only the digit-contract side has one) — deliberately not started until the directional-accuracy question has a real answer from real data.
