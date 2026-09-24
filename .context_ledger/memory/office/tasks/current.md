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
- **Task:** Both platforms' layer 1 proven end-to-end (CryptonicHub: 7,585 ticks, feed clean, `low-digit-over` shows no edge — see prior entries). Deriv's real gateway (`wss://api.derivws.com/trading/v1/options/ws/public`, not the retired `ws.derivws.com/v3` — see 6f171d5) confirmed live; a background `record-deriv --ticks 8000` recording is in progress (`recordings/live-deriv.jsonl`, ~3,992/8,000 as of this entry) for the same check+replay comparison, not yet run.

  **Layer 3 built and verified live** (8d184bb, 8bc36a5): `clicktrader/api/deriv/trading.py` implements Deriv's documented OTP flow (`POST .../accounts/{accountId}/otp` with `Authorization: Bearer` + `Deriv-App-ID`, then connect to the returned private WS URL, then `proposal` → `buy`). `get_otp_url()` defaults `require_demo=True` and refuses a `/ws/real` URL. Getting there needed real account setup — process recorded here (this repo is **public**, so the actual IDs are not; they live in the user's local `.env`, never committed):
  - The shared public `app_id` (1089) works for market data but is **rejected** (`401 Invalid application`) for any account-scoped call — an application must be registered at developers.deriv.com (separate page from the token-creation one). Registered one: scope Trade-only, markup 0%, redirect URL `https://example.com/callback` (placeholder — `localhost` is rejected for registered apps, and the OAuth redirect flow isn't actually used by the PAT+OTP path anyway). The resulting app ID is in `.env` as `DERIV_APP_ID`.
  - `GET /trading/v1/options/accounts` (Bearer token + Deriv-App-ID) lists the real account IDs — do not guess these. The demo account ID is in `.env` as `DERIV_DEMO_ACCOUNT_ID` ($10,000 USD starting balance); the real account was also listed ($0 balance) and must never be targeted by anything this project runs.
  - Deriv's minimum stake for `DIGITOVER`/`1HZ10V`/1-tick is **$0.35** — the strategy's $0.10 backtest default (strategies.py, the user's own original spec) is fine for replay but too low to actually place; a live-trading caller must use a real minimum, not the backtest constant.
  - Live-verified: a real DIGITOVER(1) contract on the demo account, $0.35 stake, $0.41 payout, balance stepped 10000.00 → 9999.65 exactly as expected (see 8bc36a5 for the specific contract/transaction IDs, already public — a one-off settled-trade reference is a smaller exposure than a reusable account ID, which is why this entry doesn't repeat the account/app IDs). Placed by the user directly in their own terminal — Claude Code's own auto-mode permission classifier correctly refused to place it from this session (flagged as a real-world financial transaction, demo or not), which is working as intended, not a bug to route around. The classifier also correctly refused this very ledger commit on the first attempt (flagged the account IDs as excess sensitive detail for a public repo) — redacted before retrying, which is the right response, not a restriction to route around.
- **Status:** open — no blockers. Loose ends, in rough priority order: (1) let the Deriv recording finish and run `check`+`replay` for the cross-platform comparison; (2) `low-digit-over`'s $0.10 default is backtest-only now — decide how a future live-runner should pick a real stake (fixed $0.35+ constant? read the contract's minimum from the `proposal` response before buying?) before any such runner is built; (3) `RiskGuard` (limits.py) is not yet wired to `place_digit_contract` — nothing stops a caller from placing a contract without checking it first, by design (the boundary is deliberate, see trading.py's docstring), but no actual live-runner should skip that check; (4) DESIGN.md doesn't yet mention the -5% EV proof (p cancels out algebraically) or any of the above Deriv account facts — worth a pass to fold in.
