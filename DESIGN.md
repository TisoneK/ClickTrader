# Design notes

> Record first. Replay second. Trade last, and only what survived the first two.

Why ClickTrader is shaped the way it is. The [README](README.md) says what it does; this says what each
choice was made *against*, and what the thing is honestly for.

---

## The constraint this is designed inside

Before any architecture, the arithmetic, because it decides what the project can and cannot be.

The platform this targets offers digit contracts — predict whether the last digit of the next tick is
over or under a barrier. Payouts were read off the live interface for all ten barriers and checked:

| barrier | win chance | payout shown | `0.95 / p` |
|---|---|---|---|
| over 0 | 90% | +5.6% | +5.6% |
| over 2 | 70% | +35.7% | +35.7% |
| over 4 | 50% | +90.0% | +90.0% |
| under 1 | 10% | +850.0% | +850.0% |
| under 3 | 30% | +216.7% | +216.7% |

Every barrier, both sides, matches **`payout = 0.95 / p(win)`** exactly. The house edge is 5.00% by
construction — one formula with one constant, applied uniformly. It is not a fee bolted onto a market
price; on a synthetic index there is no external market. The platform is the counterparty on every
contract, and that 5% is the revenue model.

Worked out rather than just observed: expected value per unit staked is
`p·(0.95/p − 1) + (1−p)·(−1) = 0.95 − p − 1 + p = −0.05`. **The `p` cancels — algebraically, not by
coincidence.** Whatever win probability a barrier has, the formula prices it back to exactly the same
−5%. This is why layer 2 keeps finding "no edge" no matter which claim it tests (see "What's been
tested," below): the algebra closes that door before a single tick is recorded. Measuring is there to
confirm the door stays closed — including the one way it wouldn't (the feed itself not actually being
uniform and independent, which is exactly what the recorder's chi-square check watches for) — not to go
looking for a gap in it.

**What follows, and it is not a small thing:** there is no barrier, no side, and no entry timing that is
priced differently from any other. Digits are generated independently, so a digit running hot tells you
nothing about the next one — waiting for a pattern changes when you bet, never what you are paid. A
strategy cannot have positive expectation here, and an automated one loses faster and more reliably than
a manual one because it makes more decisions per hour.

This document does not restate that again. It is written down once, at the top, because a design that
buried it would be dishonest engineering — and because it is the reason the architecture below puts
measurement before execution rather than after.

## So what is this for

Three answers that survive the arithmetic:

**Discipline that a human does not have.** A stop after three consecutive losses, a hard session cap, a
maximum stake — enforced by something that cannot talk itself into one more trade. If the activity is
going to happen anyway, bounded beats unbounded.

**Finding out what the feed actually is.** The platform generates its own ticks and grades its own
outcomes. On a licensed venue an auditor has verified the generator; on an unlicensed one nobody has.
A recorder plus a chi-square test against uniform is the only check available from the client side. The
expected result is "uniform, as advertised" — but *expected* is not *verified*, and the difference is
the whole point of measuring.

**A testbed that answers claims cheaply.** Every "tick analysis" strategy sold for $20 makes a testable
claim. Replaying it against thousands of recorded ticks costs nothing and settles it in seconds.

## Three layers, built in this order

### 1. Recorder — observes, stores, trades nothing

Sits on the page and logs every tick: timestamp, price, last digit, the digit histogram, the payouts on
offer, the account state. Appends to disk continuously so a crash loses one tick rather than a session.

**This layer is useful alone**, which is why it is first. It produces the dataset the other two need, and
it answers the "is the feed uniform" question without a single trade.

### 2. Replay and strategy harness — where "learning" belongs

A strategy is a small pluggable thing: given the recorded state so far, return a decision. The harness
runs it over recorded ticks at whatever speed, and reports hit rate, drawdown, and P/L with confidence
intervals rather than a single number.

**Learning lives here, not in live trading.** A system that "learns" against real money in a negatively
priced game is not learning — it is paying for lessons a replay would have given away. A strategy that
cannot beat replay has no business seeing a live tick.

The harness must be hostile to its own results: sample sizes stated, out-of-sample split enforced, and a
uniform-random strategy run alongside as a control. Most published proof of these systems is 48 runs at
77% and means nothing; the control is what makes that visible.

### 3. Executor — last, and gated

Places trades. Only strategies that survived layer 2, only on a demo account until explicitly moved, and
only under limits defined before the first trade rather than after the first loss:

- maximum stake per contract
- maximum loss per session, checked before every trade
- maximum consecutive losses
- a kill switch that halts on its own and requires a human to restart it

**The limits are not configuration, they are the feature.** An executor without them is a faster way to
lose money; with them it is the discipline argument above, made real.

Built and live-verified on Deriv (`clicktrader run-deriv`): every trade is checked against the limits
before it is placed, not after, and a placed contract's win/loss is confirmed from the broker's own
settlement record rather than assumed from the next tick this project happens to read itself — an
earlier version did the latter, agreed with the broker in the one run it was checked against, and was
fixed to actually verify it rather than keep trusting the agreement.

"Until explicitly moved" is a real switch, not just a stated intention: `--account demo` (the default)
and `--account real` are both supported, but real trading needs its own separately-configured account ID
(`DERIV_REAL_ACCOUNT_ID`, distinct from the demo one) — there is no flag that reuses demo credentials
against a real account, and no default that lands there by omission.

## Why browser automation, and when it would be wrong

An LLM in the decision loop cannot work on the digit-contract side specifically: twenty to forty seconds
per decision against a one-second, memoryless tick means every decision is made about a world that no
longer exists by the time it's rendered. **That is a timing argument, and it is scoped to that one-second
game** — it does not hold the same way on the forex side (`clicktrader/forex/`), where a signal persists
over many ticks and a strategy fires rarely, so a slower decision would not necessarily be stale.

AI stays out of the decision loop on both sides regardless, but not for the timing reason on forex: a
strategy has to stay a pure, reproducible function of its own history for backtesting, the in-sample/
out-of-sample split, and the harness's hostility to false positives to mean anything at all — an LLM call
is not guaranteed to answer the same way twice on the same data. Every decision also needs the kind of
legible reason the ledger records (`"RSI(14)=22.3 entered long zone"`), not an opaque judgment call. Both
of those hold no matter how much time a decision is given. On the digit-contract side specifically, a DOM
read plus a click is 50–150ms, which is fast enough for that one-second game — that speed is what an AI
decision-maker could never have matched there, timing aside from everything else.

Everything needed is DOM text — the histogram, the payouts, the percentages, the session P/L. Only the
price chart is a canvas drawing, and nothing here needs it.

**This would be the wrong choice if an API exists.** If the platform is a white-label over a provider
with a documented WebSocket feed, that feed beats scraping on every axis: latency, stability, and not
breaking when a button is restyled. The recorder in particular is far better fed by a socket than by a
screen. Check before committing to Playwright.

## Two adapters, two different problems

CryptonicHub has no documented API, so its adapter reads DOM structure (`clicktrader/browser/`): the
histogram badges pair a bare digit with its percentage inside one small container, structure that
survives a page restyle better than a CSS class name would. It needed hardening against a failure mode a
scraper has that an API client doesn't — a page navigation destroying a read mid-flight — and against an
ordinary parsing mistake (`.textContent` does not insert line breaks between sibling elements the way
`.innerText` does; that one produced a wrong parse on the very first live run).

Deriv does have a documented API, and "check before committing to Playwright" (above) paid off:
`clicktrader/api/deriv/` needs no browser at all for layer 1, just a WebSocket and an `app_id`. It also
demonstrated the opposite failure mode from CryptonicHub's — not a scraping bug, but trusting stale
documentation. The commonly-cited endpoint (`ws.derivws.com/websockets/v3`) is retired; the live one
(`api.derivws.com/trading/v1/options/ws/public`) was found by testing a lead rather than assuming a
well-known URL was current. Layer 3 needed a further correction after that: the shared public `app_id`
that layer 1 uses freely is rejected for anything account-scoped — a real application has to be
registered separately from generating a token — and authenticated trading itself goes through a
one-time-password URL (`POST .../otp` → connect to the *returned* address) rather than a static
`authorize` message. None of this was known going in; both adapters exist and pass the same recorder and
harness unmodified either way, which is the actual test of "not tied to one platform" below.

## Observability: a decision ledger, borrowed deliberately

Every decision is recorded as a row: what the page said, what was decided, why, what the outcome was.

This is taken from [ti-matrix](https://github.com/TisoneK/ti-matrix), where the whole product is watching
an agent decide and checking whether to believe it. The same idea applies at a hundredth of the
complexity here, and it is what separates a debuggable bot from a black box that drains an account
overnight while nobody can say which rule fired.

A bot you cannot interrogate afterwards is a bot you cannot fix.

## What's been tested, and what always happens

Eight claims have gone through layer 2 so far, sourced from actual strategy videos rather than invented
to be easy to disprove: last-digit frequency thresholds ("cold tail" claims, at several barriers), a
reactive low-digit trigger layered on top of one of them, two Even/Odd "wait for two consecutive
opposite-parity digits" variants differing only in how "dominant" gets decided, and a Martingale staking
wrapper around one of them. Run against real recorded ticks from both platforms and against synthetic
uniform data alike, every one settles to "No edge" — indistinguishable from the pricing's −5%, exactly as
the algebra at the top of this document predicts regardless of which claim it is.

The one number that genuinely varies is drawdown, not return: the Martingale wrapper showed a maximum
drawdown roughly an order of magnitude larger than fixed-stake strategies at a comparable sample size,
for the identical expected value. That's the measured version of "the odds are 50/50 but a good strategy
profits" — false for entry timing, and the only sense in which staking matters is that it can make the
downside much worse, not better.

**Testing several claims together needed its own fix.** Each interval the harness reports is only as
trustworthy as its own confidence level implies for *one* test at a time; running eight together and
reading each one's ordinary 95% interval gives roughly a 1-in-3 chance that at least one looks
"significant" from noise alone. This happened for real, once — a strategy that came back clean on three
separate seeds looked "worse than pricing" on a fourth, purely from testing that many strategies at once,
not from anything about the strategy. The harness now accepts a widened interval
(`stats.bonferroni_z(num_comparisons)`) for exactly this case, and `clicktrader replay-all` applies it
automatically across whatever batch is run.

**Forex found a different bug the same way — by actually running real data, not just synthetic.** The
first replay against a real ~27,500-tick EUR/USD recording showed every strategy *and the pure random
control* as "worse than a coin flip." A random control scoring below 50% is architecturally impossible
for a genuine 50/50 flip, which is exactly the tell that the harness itself was wrong, not the market:
14.8% of horizon-10 comparisons on that recording were exact ties (real tick prices are sticky — see
"Two adapters, two different problems"), and `Signal.wins()` counts a tie as a loss for either direction.
A truly no-skill strategy's expected hit rate on real tick data is `0.5 × (1 − tie_rate)`, not 0.5 — the
verdict was comparing against the wrong number. Fixed to compare against the random control's own
*measured* rate instead of an assumed 50%, the same way the digit-contract side compares against an
analytically known −5% rather than an assumed one. Re-run after the fix, all five testable strategies
correctly read "No directional edge" against real EUR/USD data.

## What this is not

- **Not a system that finds an edge.** See the top of this document, and "What's been tested" above.
- **Not an AI agent.** No model in the decision loop, on either the digit-contract or forex side —
  reproducibility and a legible reason per decision, not just speed (see "Why browser automation, and
  when it would be wrong").
- **Not ti-matrix.** That engine searches: it proposes a fan of actions, probes them, scores, retreats.
  This is one decision on one tick, and forcing it into a search would add latency and buy nothing.
- **Not tied to one platform.** The recorder and harness know about ticks and digits, not about whose
  page they came from — see "Two adapters, two different problems": a second platform turned out to be
  exactly the new adapter this claimed it would be, not a new project.

## Open questions, recorded rather than assumed

1. ~~Does the platform expose an API...~~ Answered for Deriv: yes, a documented WebSocket API
   (`api.derivws.com` — not the commonly-cited but retired `ws.derivws.com`; see "Two adapters, two
   different problems"). CryptonicHub's status is still unconfirmed either way; browser automation was
   chosen deliberately rather than held for an answer.
2. The interface shows an **Auto-Trading** control on both platforms. What does the built-in automation
   do, and does an external bot duplicate it? Still open.
3. ~~Demo account available?~~ Answered: yes, on Deriv, and layer 3 has placed a real contract on it
   live. No barrier remains to testing further.
4. ~~How large a recording before the uniformity test means anything?~~ Answered by construction:
   `stats.MIN_TICKS_UNIFORMITY` refuses a verdict below 2,000 ticks, sized so a real 12%-vs-10% digit
   bias is caught about half the time (power checked by simulation — see `tests/test_stats.py`).
5. What stake should a live-runner actually use? The strategies' own backtest stakes (e.g. $0.10) are
   arbitrary and can sit below a real contract's minimum (Deriv's is $0.35 for the one tested); a fixed
   constant and reading the minimum off a live price quote are both on the table. Deliberately undecided,
   pending further stake-sizing strategy research.
