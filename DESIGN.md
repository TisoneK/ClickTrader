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

## Why browser automation, and when it would be wrong

An LLM in the decision loop cannot work here — twenty to forty seconds per decision against a
one-second tick means every decision is made about a world that no longer exists. There is no AI in this
loop, and that is a design decision rather than a limitation: a DOM read plus a click is 50–150ms, which
is fast enough.

Everything needed is DOM text — the histogram, the payouts, the percentages, the session P/L. Only the
price chart is a canvas drawing, and nothing here needs it.

**This would be the wrong choice if an API exists.** If the platform is a white-label over a provider
with a documented WebSocket feed, that feed beats scraping on every axis: latency, stability, and not
breaking when a button is restyled. The recorder in particular is far better fed by a socket than by a
screen. Check before committing to Playwright.

## Observability: a decision ledger, borrowed deliberately

Every decision is recorded as a row: what the page said, what was decided, why, what the outcome was.

This is taken from [ti-matrix](https://github.com/TisoneK/ti-matrix), where the whole product is watching
an agent decide and checking whether to believe it. The same idea applies at a hundredth of the
complexity here, and it is what separates a debuggable bot from a black box that drains an account
overnight while nobody can say which rule fired.

A bot you cannot interrogate afterwards is a bot you cannot fix.

## What this is not

- **Not a system that finds an edge.** See the top of this document.
- **Not an AI agent.** No model in the loop, by design.
- **Not ti-matrix.** That engine searches: it proposes a fan of actions, probes them, scores, retreats.
  This is one decision on one tick, and forcing it into a search would add latency and buy nothing.
- **Not tied to one platform.** The recorder and harness know about ticks and digits, not about whose
  page they came from. A second platform should be a new adapter, not a new project.

## Open questions, recorded rather than assumed

1. Does the platform expose an API, or is it a white-label over one that does?
2. The interface already shows an **Auto-Trading** control. What does the built-in automation do, and
   does an external bot duplicate it?
3. Demo account available? Layer 3 does not go live without one first.
4. How large a recording before the uniformity test means anything? (Thousands, not hundreds — and the
   harness should refuse to report on a sample too small rather than print a misleading number.)
