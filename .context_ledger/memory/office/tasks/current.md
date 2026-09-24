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

- **Session:** 2026-09-24 — Amara / claude-sonnet-5
- **Task:** Both platforms' layer 1 are now proven end-to-end. CryptonicHub: 7,585 real ticks, feed clean (chi2 uniformity p=0.66, lag-1 independence p=0.37), `low-digit-over` (user's Over(1)-after-0/1 claim) replayed with no evidence of an edge — consistent with the pricing math being provably -5% EV regardless of barrier (p cancels out algebraically in `Contract.profit_ratio`'s derivation — worth writing into DESIGN.md, not done yet). Deriv: `clicktrader/api/deriv/` package (connection.py + ticks.py, split ahead of layer 3 per user preference, 8e6ea5c) hit what looked like a platform-wide outage on `wss://ws.derivws.com/websockets/v3` (520s), chased through several wrong theories (outage → US geo-block, ruled out by a Kenya machine hitting the identical error → app_id rate-limit) before the real answer: that URL is simply **retired**. Live gateway is `wss://api.derivws.com/trading/v1/options/ws/public` (found via a lead from Deriv's own support chat, confirmed with a real tick round-trip; same JSON-RPC shape, different host+path) — fixed in 6f171d5, confirmed live (`record-deriv` wrote 15 real ticks at a clean 1s cadence). A Trade-scoped demo API token is already generated and stored in `.env` (untracked); not needed until layer 3, which per Deriv's support chat needs an OTP step (`POST .../otp` → connect to the *returned* WS URL) rather than a static-token `authorize` — different from the old API, worth remembering when layer 3 starts.
- **Status:** open — no blockers. Natural next step: a real Deriv recording (~8,000 ticks, same math as CryptonicHub's checkpoint) via `clicktrader record-deriv recordings/live-deriv.jsonl --symbol 1HZ10V --ticks 8000`, then `check` + `replay --strategy low-digit-over` for a cross-platform comparison against the CryptonicHub result. Not started yet — user's call on whether/when to run it.
