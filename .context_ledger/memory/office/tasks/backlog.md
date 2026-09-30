# Backlog (work queue — actionable items only)

The queue of work a session can pick up and **do**. One row per item, in
its priority table. It is a queue, not a knowledge base: the test for a
row is "can an agent start on this and finish it?" If the answer is no —
it's a finding, an open question, an advisory "should we…?", a deferred
"someday" idea — it belongs in [`parking-lot.md`](parking-lot.md), not
here. Writing discoveries into the backlog is how a queue turns into a
57-row document nobody can work from.

**Done = delete the row. Stale = delete the row.** The backlog holds
open, actionable work only. When an item is finished, delete its row —
the completion record is the finishing session's `agents/sessions.md`
entry and the commit, never a tombstone here. When an item stops
mattering, delete it too; if it still carries information worth keeping,
move it to the parking lot first. Git history keeps every removed row,
so deleting loses nothing. (The one thing you must not do is delete a row
whose work is genuinely still open and recorded nowhere else — a row
vanishing from the diff with no session entry or promotion behind it is a
dropped handoff, not cleanup. Legacy checkbox-format backlogs:
`ledger-mem closeout` sweeps checked-off `- [x]` tombstones a session
left behind — dry run by default; `--confirm` deletes.)

**The queue is capped at ~20 rows** (`backlog_cap` in
`workflows/history.conf`; `ledger-mem check` warns past it). Twenty is a
working set, not a limit to fill. When you'd add a 21st actionable item,
prune one first: the lowest-value open row goes to the parking lot
(deferred, still valuable) or is deleted (no longer relevant) — never a
row you can't justify dropping. A queue you can hold in your head beats
a comprehensive one you can't.

**Only actionable work, and context lives where the work is.** Every row
gets a stable **ID** — `B-<added YYYY-MM-DD>-<n>`, n = that date's next
sequence in the file — and a **Summary** cell that says what to *do*, not
everything known about it. A fresh agent should be able to start from the
one line; the deep context belongs in the linked issue, PR, ADR, or
parking-lot finding the row points at, not packed into the cell. Keep
status qualifiers short ("partial", "blocked on X"). Don't append
research narrative to a row to "preserve" it — that's the parking lot's
job.

**Priority is the table an item sits in (High / Medium / Low), and it is
dynamic.** Only the top of the queue really matters — when you start a
session, the handful of High rows (roughly the top 3–5) are the work; the
rest is context, and a row that has sat in Low for many sessions is a
candidate for the parking lot, not a permanent resident. When unsure
between two tables, pick the lower one; promoting a row later is cheap,
and a backlog where everything is High says nothing.

This backlog belongs to the **current office**. When the office closes,
open items do not carry over implicitly — the closing session re-seeds
into the new office's backlog **only items with an active owner or a
clear next step**; everything else is recorded in the permanent record
(`history/office-<NNN>.md`, "Open threads") or parked. A re-seeded row
describes the work in plain words and never cites the old office's
session numbers or codenames.

Full spec: `.context_ledger/core/schemas/ledger-schema.md` →
"The backlog: a capped work queue" and "The parking lot".

## Open Items

### High Priority

*(none currently)*

### Medium Priority

| ID | Summary |
|----|---------|
| B-2026-09-30-1 | **Mostly done (S010, ADR-5) — remaining: the owner's own markup of a chart to compare with the drawing; the daily→4H→1H chain; Fibonacci/lowest-strongest/level-stack filters.** Earlier note: **Partly done (S010):** the macro band now exists — `LiquidityPool.low/high` from the member candles, a break = leaving through the far edge, cluster span capped at one typical candle range, `clicktrader smc-chart` to look at the result. **Still open:** replace the remaining invented constants with comparisons (`band_bands=1.0`, the `4×band` link limit in `key_zones`, `min_touches=2`, `strength=2`), decide whether overlapping bands merge and whether recency weights a level (both need the trader's reference examples, P-2026-09-30-8). Original text: Implement the **macro supply/demand band** as the level, keeping the single-candle order block as its refinement for entry and stop — the material draws two objects at two scales and the code built only the small one. Evidence and measurements: P-2026-09-30-4 and `docs/smc/spec.md` §2.1–§2.2. This is the known cause of "2 levels in view" on a chart a human reads as full of structure. Same change should remove the three invented constants (pushed distance, momentum candle, band width) and replace each *comparative* with a comparison against the chart's own visible window, per `docs/smc/README.md` §"How a perception becomes code" rule 2. |
| B-2026-09-27-1 | Record the quoted payout + contract terms alongside each Deriv forex tick (extend layer 1 using `api/deriv/trading.py`'s existing `proposal` flow), so the harness can compute EV instead of only hit rate. Without it no positive-EV claim on the Deriv side is even measurable — `forex/harness.py` says so in its own docstring, and `api/deriv/ticks.py::tick_record_from_message` currently stores price+digit only while the CryptonicHub adapter does capture payouts. Rationale + sources: P-2026-09-27-2. |
| B-2026-09-25-1 | Harness: parameter sweeps tuned on in-sample only (e.g. trying several `window`/`threshold` values for `ColdTailOverUnder`/`ParityCounterTrend` and picking the best on in-sample before an out-of-sample check) — half of the original B-2026-09-24-3; the multiple-comparisons half is done (`stats.bonferroni_z`, `replay-all`, 99d03d9) |

### Low Priority

| ID | Summary |
|----|---------|

<!-- TEMPLATE — add one ACTIONABLE row to the matching priority table
     (a finding, question, or someday idea goes in parking-lot.md instead):
| B-<YYYY-MM-DD>-<n> | <what to DO, one line, pointing at the issue/PR/
      parking-lot finding for detail — not the full context> |
-->
