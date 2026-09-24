# ClickTrader

Browser automation for digit-contract trading on synthetic-index platforms — built record-first, so a
strategy has to survive replay against real recorded ticks before it is allowed near a live one.

No AI in the decision loop. A language model needs twenty to forty seconds to decide; the tick is gone in
one. A DOM read and a click is 50–150 milliseconds, which is the whole reason this is browser automation
and not an agent.

> **Status: design only.** Nothing is built yet. [DESIGN.md](DESIGN.md) is the contract the code will be
> written against — including the arithmetic that decides what this project can honestly be.

---

## Three layers, built in this order

**1. Recorder** — sits on the page and logs every tick: price, last digit, the digit histogram, the
payouts on offer, account state. Trades nothing. Useful on its own, because it answers whether the feed
is what it claims to be without risking anything.

**2. Replay and strategy harness** — runs a strategy over thousands of recorded ticks in seconds, with
sample sizes stated, an out-of-sample split enforced, and a random strategy alongside as a control. This
is where a claim gets tested. A strategy that cannot beat replay has no business seeing a live tick.

**3. Executor** — places trades, only for strategies that survived layer 2, only on a demo account until
explicitly moved, and only inside limits defined before the first trade: maximum stake, maximum session
loss, maximum consecutive losses, and a kill switch that requires a human to restart it.

The limits are not configuration. They are the feature.

## Read this before using it

The payouts on these contracts are `0.95 / p(win)` — checked at all ten barriers, both sides. That is a
5% house edge by construction, identical everywhere, and the digits are independent so no entry timing
changes it. This tool is built to **measure** that honestly and to **bound** the activity, not to beat it.
[DESIGN.md](DESIGN.md) sets out what follows from that.

## Decision ledger

Every decision is a row: what the page said, what was decided, why, what happened. Borrowed from
[ti-matrix](https://github.com/TisoneK/ti-matrix), where watching a system decide — and being able to
check whether to believe it — is the whole product. A bot you cannot interrogate afterwards is a bot you
cannot fix.

## License

MIT
