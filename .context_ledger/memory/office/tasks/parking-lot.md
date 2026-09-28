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
| P-2026-09-27-2 | **Where positive EV could actually exist on these instruments** (full memo + sources: `office/sessions/2026-09-27-7/notes.md`). (a) Digits are algebraically closed, and more strongly than "−5%": `payout = 0.95/p` means the platform prices payout ∝ 1/p, so it never has to know the true probability — no distributional finding about the feed can create a digit edge. (b) For a 0.95 ROI, forex breakeven is 51.28% of *all* bets (ties as losses); the three candlestick strategies' *decisive* win rates are ~39–43%, i.e. unprofitable at any plausible payout, not merely "no better than random". (c) The one avenue not ruled out by algebra: Deriv's **structurally biased** synthetics — Range Break (mean-reverting band; Deriv's own FAQ says channel analysis "may be effective" there, while calling patterns on the other indices "purely coincidental"), Trek (built-in directional bias), Skew Step (80–90% vs 10–20% asymmetric probabilities), Daily Reset / Drift Switching (bull/bear regimes, 10–30 min). If their Rise/Fall ROI is a *fixed* ~90–95% rather than probability-scaled, a biased feed plus a fixed payout is positive EV — and the existing harness would detect it, since the random control rolls its own coin and so does not benefit from drift. (d) Whether the payout is fixed or scaled is the decisive, currently-unmeasured question — see B-2026-09-27-1. |
| P-2026-09-27-3 | **Literature check on short-horizon FX edge** (same memo, §2). Documented predictability exists but is the wrong shape for this product: time-of-day effects in FX returns/order flow (Breedon et al.), intraday time-series momentum across 16 markets (Li et al.) — both hour-scale and small; order flow as the strongest high-frequency driver (Berger et al. Fed IFDP 830; Menkhoff et al. BIS WP 405) — needs an order book, which synthetic indices explicitly lack; modest and model-dependent directional predictability (Chung & Hong 2007). Base rate: regulated-market studies put 70–80% of retail binary options traders at a loss. Net: the EUR/USD capture now running should be *expected* to return "no directional edge" — that is the literature's prediction, and confirming it closes the question rather than discovering anything. |
| P-2026-09-27-1 | **PARTIALLY RESOLVED 2026-09-28 — read the first sentence before the rest.** The ~50k-tick EUR/USD capture this row asked for has now happened: the live `record-deriv` has taken `forex/live-eurusd-20260928.jsonl` past 60,000 ticks. Replayed at the designed `bar_size=10`, family-corrected z=2.39: `engulfing-bar` **597 out-of-sample bets — it clears the 500 gate for the first time — verdict "Worse than the random control"** (hit 0.385, CI 0.339–0.434, against a control of 0.473, CI 0.425–0.522, measured on the same ticks at 600 bets; its in-sample rate 0.336 is worse still, so this is not a tuning artefact). The direction replicates on the independent 2026-09-25 capture (0.368 vs control 0.418, 418 bets, under the gate so no verdict there). `pin-bar` is **23 bets short** (477; 0.413 vs control 0.409 — dead level with it) and needs only a little more capture to become judgeable. `inside-bar` fires far too rarely at this bar size (177 bets) to clear the gate without a much longer capture and is probably not worth chasing. Detail + exact commands: `office/sessions/2026-09-28-9/notes.md`; write-up: `office/reviews/2026-09-28-review.md`. **The original text below describes the earlier 41,632-tick state and is kept for context.** Those three strategies (`EngulfingBar`, `PinBar`, `InsideBar`, shipped 4c6724a/b3f7be0) could not be judged on the then-current recording at their designed `bar_size=10`: all landed `NO VERDICT` (418/343/114 out-of-sample bets vs the 500 gate). Forcing more signals by shrinking the bar clears the gate but changes the strategy, and shows no edge — engulfing-bar bs3 "No directional edge" (0.362 vs control 0.362), bs5 "Worse than the random control" (0.335 vs 0.372); pin-bar bs3 no edge (0.337 vs 0.369), bs5 worse (0.340 vs 0.386); inside-bar never clears 500 at any bar size (114–154). Note the raw hit rates (~0.33–0.44) are not the −5% story: ~15% of horizons end in a tie, which counts as a loss for either direction and drags the control down with it, which is why the harness compares against the measured control. The bs10 question needs a longer capture: ~50k ticks total (≈14–17 h) — `record-deriv recordings/forex/live-eurusd-20260928.jsonl --symbol frxEURUSD --ticks 60000`. |
| P-2026-09-27-4 | **The "Under 7" filter is effectively a never-trade, and that is a property of the filter, not a bug.** Built this session as `ColdLossSetOverUnder(Side.UNDER, 7, max_share=0.20)` — the notes' claim that digits 7, 8 and 9 together run under 20% of recent ticks. Measured on the 7,585-tick CryptonicHub recording, that share is ~30% (which is exactly what uniform digits imply), so a qualifying 100-tick window is a rare excursion: ~1-5% of windows, and not evenly spread in time — **every** qualifying window in that recording sits in its first ~40%, which is why the replay took 83 in-sample bets and exactly 0 out-of-sample and can never clear the 500-bet gate from one such recording. In other words this half of the setup is mostly "do not trade", and where it does trade it is still `NO VERDICT` at this sample size rather than "no edge". The Over 3 mirror (digits 0-3 combined under 37.5%) is far more permissive — ~30% of ticks fire — and does return a real `No edge` on both recordings. Neither number is evidence about anything except how rare the note's own threshold is against this feed. |
| P-2026-09-27-5 | **Multi-tick duration is now replayable, and a longer duration changed nothing measurable — as the algebra requires.** `Decision.duration` (settled at `tick + duration` by `harness._run_segment`, passed through by the live executor) makes Over/Under at 2-5 ticks testable for the first time; before this the harness hard-coded one tick. Replayed at 5 ticks, `cold-loss-set-over-3-5tick` returns `No edge` on the 8,000-tick Deriv recording and reproduces the 1-tick numbers almost exactly. That is the predicted result, not a coincidence: every tick's digit stays uniform and independent, so `p(win)` — and therefore the payout, which is `0.95/p` — is unchanged by the duration, and a longer run merely absorbs a bad single tick that the pricing has already charged for. The claim that a longer duration helps is therefore not merely untested, it is priced away; the capability is worth keeping mainly because it makes that answer cheap to re-ask on any feed, or against Deriv's own quoted terms once payouts are recorded. |
| P-2026-09-28-1 | **No strategy in this repo can express a trade with a stop and a target, so no stop/target method can be judged here at all.** A decision carries only `contract`+`stake`+`reason`+`duration` (`clicktrader/strategies.py:49`) or `direction`+`horizon_ticks` (`clicktrader/forex/model.py:22`) — there is no entry price, stop, target or payoff-multiple field. Grading is one comparison, entry price at tick *i* against exit price at tick *i + horizon* (`clicktrader/forex/harness.py:99-105`), and `Signal.wins` is a bare "is exit above entry" test (`clicktrader/forex/model.py:32-37`): everything between those two prices is discarded. A method whose return comes from *which* of two levels price reached first is therefore not merely untested, it is **inexpressible**. This matters well beyond the two decks that surfaced it, because essentially every retail course method — including every one the user has brought so far — is an entry/stop/target method. Grading one needs a path-dependent, R-multiple mode; see P-2026-09-28-4 for whether to build it. |
| P-2026-09-28-2 | **The two decks the user shared on 2026-09-28, and why neither is testable here (full read-through: `office/sessions/2026-09-28-9/notes.md`, write-up: `office/reviews/2026-09-28-review.md`).** *The Sneaky Pivot Blueprint* (15 slides) is a near-complete mechanical spec — previous-day high/low as the range, the next extremes beyond them as swing lines, sell zone above / buy zone below / do-nothing middle, and a 45-minute three-candle entry at the boundary with the stop under the swing low and the target at the opposite edge — so it is the one of the two that could be coded without inventing rules. *The Supply & Demand Playbook* (14 slides) is not implementable as written: "3+ large candles", "the previous opposite-coloured candle", "defense" and "the biggest seller block" are all visual judgements with no threshold, and those free parameters are exactly how a method gets tuned into looking good (the reason ADR-1 pins an out-of-sample split and B-2026-09-25-1 exists). It also asserts rather than measures ("highest probability strike zones", "risk 2% instead of 1%") and closes on sales-funnel language. Both are stop/target methods (P-2026-09-28-1) and neither has the data (P-2026-09-28-3). |
| P-2026-09-28-3 | **The decks are short of data by a factor of a few hundred, and that is arithmetic, not opinion.** The Sneaky Pivot fires roughly once a day (one range per day, one 45-minute sequence); this repo calls nothing a verdict below 500 out-of-sample bets (`clicktrader/stats.py:19`) and reads only the out-of-sample half of each capture — so the method needs on the order of a thousand instrument-days, i.e. **two to four years of daily 15-minute data**, before it can be judged. On disk today: two calendar days of EUR/USD in total (2026-09-25, 11.6 h / 47 fifteen-minute bars; 2026-09-28, 16.9 h / 68 bars), and they are not consecutive — a weekend apart — so "yesterday's range" exists twice, ever. That is about 1/500 of the requirement. Separately, a mechanics gap sits in the way: `CandleBuilder` groups *ticks* into `bar_size`-tick bars and `Candle` stores no timestamp at all (`clicktrader/forex/candles.py:7-9`, `:17-22`), so nothing here can draw a 15-minute chart, a previous-day high, or a morning session window. The recordings do carry `ts`, so that gap is small and fixable (see B-2026-09-28-1) — but it is a prerequisite, and clearing it would still leave the data short by two orders of magnitude. |
| P-2026-09-28-4 | **Measured: the repo's own candlestick strategy now has a verdict, and it is negative.** On the newly sufficient 60,315-tick EUR/USD capture, `engulfing-bar` at its designed `bar_size=10` took 597 out-of-sample bets and read "Worse than the random control" — 0.385 (CI 0.339–0.434) against a control of 0.473 (CI 0.425–0.522) measured on the same ticks at 600 bets. It reproduces in direction on the independent 2026-09-25 capture (0.368 vs 0.418). **Scope of the claim, stated carefully:** this does *not* refute "an engulfing candle at a supply/demand level confirms a zone" — the implemented `engulfing-bar` fires on the pattern alone, with no zone, level or range context, on tick-count bars rather than 15-minute bars. What it does say is that the naive candlestick-pattern signal on this instrument, taken at face value at its designed parameters, is *below* a coin flip where the data finally became good enough to judge it — a fair prior to carry into any price-action material. Useful mainly as a demonstration that the whole loop (capture → replay → family-corrected verdict) now costs one command. |

## Open questions

Advisory questions, decisions still up for grabs, "should we…?" — a
question is not a task until it has an owner and a next step (then it
becomes a backlog row or an ADR in `plans/decisions.md`).

| ID | Summary |
|----|---------|
| P-2026-09-24-1 | Platform identified from user-supplied screenshots: "CryptonicHub Trader" (Volatility 10 (1s) Index, digit contracts — Over/Under, Even/Odd, Match/Differs; built-in "Auto-Trading" panel visible, DESIGN.md open question 2). No API confirmed either way; user has chosen to proceed with browser automation (Playwright) rather than hold for an API check — decided, not deferred. |
| P-2026-09-24-2 | Demo account available? DESIGN.md open question 3 — ANSWERED: yes, a Deriv demo account with a $10,000 USD starting balance (ID kept in `.env`, not this public repo), confirmed by placing a real demo contract live (see 8bc36a5). → promoted to B-2026-09-24-5/6 and layer 3 code (trading.py), no longer open. |
| P-2026-09-25-1 | What stake should a live-runner actually use, long-term? The live-runner (`executor.py`/`run-deriv`) exists now and takes `--min-stake` as a required CLI arg (a fixed constant, user-supplied each run — $0.35 confirmed live for DIGITOVER/1HZ10V/1-tick) — that's today's answer, not the final one. Whether to keep a fixed constant or read the minimum off a live `proposal` response is deliberately still undecided, pending the user's own stake-sizing strategy research (separate track, videos not yet provided). |
| P-2026-09-28-5 | **Should layer 2 gain a path-dependent (stop/target, R-multiple) grading mode?** The capability gap is real and measured (P-2026-09-28-1): today a strategy can only say "direction, in N ticks", so no entry/stop/target method can be judged. A second grading mode would let a strategy declare an entry, a stop and a target, walk the ticks between them, and report expectancy in R rather than a hit rate — which is the only way to evaluate the shape of method that retail courses actually teach (including both decks the user brought on 2026-09-28). **The trade-offs to decide, not to assume:** it is an architecture change rather than a feature (ADR-1 pins the current harness semantics, including that out-of-sample cannot be switched off and every replay runs a random control — any new mode must keep both); it adds a second notion of "verdict" alongside the hit-rate verdict, and the two are not comparable, so the registry and reporting need to keep them clearly apart; and it needs a payout/ROI assumption to convert R into money, which on the Deriv forex side is exactly the number B-2026-09-27-1 says is not recorded yet. **Honest caveat: building it does not unlock the two decks.** Deck 2 would still be ~500× short of data (P-2026-09-28-3) and Deck 1 is not specifiable. The argument for building it is that it removes a blocker for *every* future stop/target method, not that it rescues these two. Advisory; no owner, no next step yet. |

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
