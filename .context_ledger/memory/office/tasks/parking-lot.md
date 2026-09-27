# Parking Lot (deferred knowledge — not a queue)

The backlog is a work queue you act on; this file is the knowledge base
you **don't** act on yet. Research findings, open design questions,
advisory "should we…?" items, deferred work, and someday ideas live here
so the backlog stays a queue an agent can actually work from. Nothing
here is urgent, nothing here is capped, and nothing here blocks a gate.
The record of a finding is its own row plus the commit / session entry
that produced it; git history keeps every row, so promoting or dropping
one loses nothing.

**One rule keeps the two files honest: a parking-lot row is not a task.**
If an item becomes actionable — it now has a clear next step and someone
to take it — **promote** it: cut the row here, add an actionable row to
`backlog.md` (a fresh `B-` ID, one line, pointing back at this row's `P-`
ID if the context matters), and leave it here only as a one-line
"→ promoted to B-… " stub if you want the breadcrumb. An item that turns
out to be wrong or moot is just deleted — history remembers it.

Every row gets a stable **ID** — `P-<added YYYY-MM-DD>-<n>`, n = that
date's next sequence in the file — and a **Summary** cell with enough
context that a future session can pick it up cold. Keep status
qualifiers in the text ("advisory", "needs a decision", "blocked on X",
"deferred by owner"). There is **no cap** here and **no priority** —
items are grouped by *kind*, because the whole point is that these are
not competing for the top of a queue.

This file belongs to the **current office**. When the office closes, the
parking lot is **not** re-seeded wholesale: the closing session promotes
what is now actionable into the new backlog and records the rest in the
permanent record (`history/office-<NNN>.md`, "Open threads"). A cold
idea earns its way into the next office by becoming work, not by being
copied.

Full spec: `.context_ledger/core/schemas/ledger-schema.md` →
"The parking lot".

## Findings

What we learned that isn't work yet — observations, measurements, root
causes, "the current design does X because Y".

| ID | Summary |
|----|---------|
| P-2026-09-27-1 | The three candlestick forex strategies (`EngulfingBar`, `PinBar`, `InsideBar`, shipped 4c6724a/b3f7be0) cannot be judged on the current 41,632-tick EUR/USD recording at their designed `bar_size=10`: all land `NO VERDICT` (418/343/114 out-of-sample bets vs the 500 gate). Forcing more signals by shrinking the bar clears the gate but changes the strategy, and shows no edge — engulfing-bar bs3 "No directional edge" (0.362 vs control 0.362), bs5 "Worse than the random control" (0.335 vs 0.372); pin-bar bs3 no edge (0.337 vs 0.369), bs5 worse (0.340 vs 0.386); inside-bar never clears 500 at any bar size (114–154). Note the raw hit rates (~0.33–0.44) are not the −5% story: ~15% of horizons end in a tie, which counts as a loss for either direction and drags the control down with it, which is why the harness compares against the measured control. The bs10 question needs a longer capture: ~50k ticks total (≈14–17 h) — `record-deriv recordings/forex/live-eurusd-20260928.jsonl --symbol frxEURUSD --ticks 60000`. |

## Open questions

Advisory questions, decisions still up for grabs, "should we…?" — a
question is not a task until it has an owner and a next step (then it
becomes a backlog row or an ADR in `plans/decisions.md`).

| ID | Summary |
|----|---------|
| P-2026-09-24-1 | Platform identified from user-supplied screenshots: "CryptonicHub Trader" (Volatility 10 (1s) Index, digit contracts — Over/Under, Even/Odd, Match/Differs; built-in "Auto-Trading" panel visible, DESIGN.md open question 2). No API confirmed either way; user has chosen to proceed with browser automation (Playwright) rather than hold for an API check — decided, not deferred. |
| P-2026-09-24-2 | Demo account available? DESIGN.md open question 3 — ANSWERED: yes, a Deriv demo account with a $10,000 USD starting balance (ID kept in `.env`, not this public repo), confirmed by placing a real demo contract live (see 8bc36a5). → promoted to B-2026-09-24-5/6 and layer 3 code (trading.py), no longer open. |
| P-2026-09-25-1 | What stake should a live-runner actually use, long-term? The live-runner (`executor.py`/`run-deriv`) exists now and takes `--min-stake` as a required CLI arg (a fixed constant, user-supplied each run — $0.35 confirmed live for DIGITOVER/1HZ10V/1-tick) — that's today's answer, not the final one. Whether to keep a fixed constant or read the minimum off a live `proposal` response is deliberately still undecided, pending the user's own stake-sizing strategy research (separate track, videos not yet provided). |

## Deferred work

Real tasks, consciously parked — not now, but keepable. This is where a
backlog row goes when the cap forces a prune and the item still matters:
out of the queue, not into the void.

| ID | Summary |
|----|---------|

## Someday

Loose ideas with no owner and no hook yet. The lowest-pressure shelf.

| ID | Summary |
|----|---------|

<!-- TEMPLATE — add one row to the matching section:
| P-<YYYY-MM-DD>-<n> | <enough context that a future session can pick
      this up cold — status qualifiers in the text; promote to the
      backlog when it becomes actionable> |
-->
