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
- **Task:** All three layers built, tested, and live-verified end to end on Deriv (CryptonicHub has layers 1-2 only, by choice). Two live runs done (45 then 46 real demo trades) — both correctly treated as too small to mean anything (n far below the ~500 the harness requires), which itself demonstrated the point: results swung from +0.3% to -14.8% return per stake between them, pure sample-size noise around the same -5% truth. Three follow-up fixes then done, one at a time, each its own commit:
  1. **Multiple-comparisons correction** (99d03d9): `stats.bonferroni_z` + `replay()`'s new `z` param + `clicktrader replay-all` — widens the confidence interval when testing a batch of strategies, so a batch verdict is as hostile to false positives as a single verdict is meant to be. Verified against a real Monte Carlo simulation, not just a table lookup.
  2. **Broker-verified settlement** (564b002): `trading.get_contract_status`/`wait_for_settlement` poll Deriv's own `proposal_open_contract` until "won"/"lost" rather than self-grading from our own tick stream. This simplified `executor.py` (deleted the `_PendingBet` deferred-settlement machinery entirely — settlement is now synchronous, right after buying).
  3. **DESIGN.md documentation pass** (b0f899d): the -5% EV algebraic proof, a new "Two adapters, two different problems" section (the real lessons from each platform), a new "What's been tested, and what always happens" section (all 8 strategies converge to no edge; the multiple-comparisons near-miss), and open questions marked resolved where they now are.
  Also fixed along the way: `run-deriv` had zero console output while running (looked frozen) — added a live `on_row` callback; and the broker's real account balance was being fetched but discarded — now shown via `get_balance` (a one-off, non-subscribed request, not `subscribe:1`, to avoid interleaving with other request/response calls on the same connection).
- **Status:** open — no blockers. Loose end still open by design (not an oversight): live stake sizing for a real-runner is deliberately undecided, pending the user's own further research into staking-strategy videos (separate track, not started).
