# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If you
find a stale in-progress entry here, a prior session died mid-task — its
roster row (if left behind) says who was here; check the session entry
and backlog before starting.

<!-- TEMPLATE — replace everything below this comment:
- **Session:** YYYY-MM-DD — <agent> / <model>
- **Task:** <what is being worked on right now>
- **Status:** blocked (push not permitted from this session; target platform unknown — P-2026-09-24-1) | done | blocked (<blocker>)
-->

- **Session:** 2026-09-27 — Zara / deepseek/deepseek-v4-flash (S008)
- **Task:** The user shared two strategy write-ups — the "Over 3 & Under 7" asymmetric high-probability setups with a 100-tick digit-frequency filter, the "Over 1 / Under 8" mean-reversion setups entered after a digit repeats 2–3 times consecutively, and a Rise/Fall vs Over/Under comparison note. Most of it is already in the repo and already settled (`cold-tail-over-3`, `cold-tail-under-7`, `low-digit-over`, `StreakReversal`; digits are algebraically closed at −5% because the measured payout is `0.95/p` at every barrier). Three things the notes describe are genuinely absent, and the user chose to have all three built and tested: (1) the **bundled** losing-set share filter including the barrier digit (Over 3: digits 0–3 combined under ~37.5%; Under 7: digits 7–9 combined under 20%) versus the shipped per-digit, barrier-excluding `ColdTailOverUnder`; (2) a **repeat-run** reversal (2–3 identical digits in a row, then bet the 80% contract away from them — low run → Over 1, high run → Under 8); (3) **multi-tick duration** (1–5 ticks), which the harness hard-codes to one tick today.
- **Status:** done — shipped `ColdLossSetOverUnder`, `RepeatDigitReversal`, and `Decision.duration` + multi-tick settlement in a8e476b; 223 tests green, both mandatory gates green, five new registry entries replayed on both real recordings (`No edge` or `NO VERDICT` in every case, as the `0.95/p` pricing requires). Findings P-2026-09-27-4 (the Under 7 filter is effectively a never-trade) and P-2026-09-27-5 (multi-tick duration changes nothing measurable) are in the parking lot; neither is actionable work, so the backlog is unchanged.

- **Session:** 2026-09-28 — Lena / deepseek/deepseek-flash (S009)
- **Task:** The user attached two trading decks with no instruction — *The Supply & Demand Playbook* (14 slides) and *The Sneaky Pivot Blueprint* (15 slides, attached twice). Both are image-only PDFs, so they were rendered and read in full; the session's job was then to answer the question they imply: can this project test either of them? Reading each claim against the code and the data, plus re-running the existing forex tooling on the capture that had just landed.
- **Status:** done, and **no product code was written** — that is the finding, not an omission. No verdict was needed on the decks: the Sneaky Pivot deck is a near-complete mechanical spec but needs ~2–4 years of daily 15-minute data to clear the repo's own 500-out-of-sample-bet gate against ~2 days on disk (P-2026-09-28-3), and the Supply & Demand deck is not implementable as written because its rules have no thresholds (P-2026-09-28-2). A separate, larger gap surfaced: the harness cannot express a stop or a target at all, so *no* entry/stop/target method is judgeable here (P-2026-09-28-1, question P-2026-09-28-5). One open thread closed for free on the way past — the 60k-tick EUR/USD capture had arrived, so `engulfing-bar` got its first real verdict at `bar_size=10`: **"Worse than the random control"** (0.385 vs 0.473, 597 bets), replicating in direction on the independent earlier capture (P-2026-09-28-4; P-2026-09-27-1 updated — `pin-bar` is now only 23 bets short). Write-up: `office/reviews/2026-09-28-review.md`; deck-by-deck reading and exact commands: `office/sessions/2026-09-28-9/notes.md`. Backlog gained one row (B-2026-09-28-1, wall-clock/session candles).

**Below — the previous sessions' threads, kept as reference, not as a live task.**

- **Session:** 2026-09-27 — Kwame / deepseek/deepseek-v4-flash (S007)
- **Task:** Validate Femi's three candlestick forex strategies against the real EUR/USD recording; give `record-deriv` live progress output; then (rounds 2–3) add `forex-replay-all` and research where positive EV could actually come from.
- **Status:** done — strategies could not be judged yet (all `NO VERDICT` at shipped `bar_size=10`, filed P-2026-09-27-1); `record-deriv --progress-every` shipped; `forex-replay-all` shipped (forex replay never passed `z` through to the harness); positive-EV research memo at `office/sessions/2026-09-27-7/notes.md`, condensed to P-2026-09-27-2/-3 and B-2026-09-27-1.

- **Session:** 2026-09-26 — Femi / claude-sonnet-5 (S006)
- **Task:** User shared "The Candlestick Trading Bible" PDF and asked whether to fold its notes into the ledger. Declined to transcribe the book itself into the repo (public, MIT-licensed — republishing copyrighted chapters under that license was flagged to the user as a real legal exposure, not a style nitpick; freely-downloadable and citable are not the same as freely-reproducible). Agreed path instead: extract pattern *definitions* as original strategy code, citing the technique by name only. Shipped three: `EngulfingBar`, `PinBar` (4c6724a), and `InsideBar` (b3f7be0) in `clicktrader/forex/strategies.py`, backed by a new `clicktrader/forex/candles.py`.
- **Status:** done. All three confirmed running against the real EUR/USD recording (NO VERDICT in every case).

- **Session:** 2026-09-24/25 — Amara / claude-sonnet-5 (S002)
- **Task:** **Digit-contract side (CryptonicHub + Deriv): stable, considered done for now.** All 3 layers built, live-verified (real demo trades placed and broker-settled), 8 strategy claims tested and all converge to "No edge" as the algebra predicts.
- **Status:** open (roster row stale since 2026-09-26 — logged flaw). New active thread: forex, scoped to fixed-stake Rise/Fall-style options on a forex underlying. Next: let the real EUR/USD recording keep accumulating, then run `forex-replay` for a real read once there's enough data. No forex live-trading/executor code exists yet.
