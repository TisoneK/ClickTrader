# Running the engine live on the demo account

**Everything here uses virtual money.** `run-smc` has two modes and neither can touch a real account: paper mode
places nothing, and `--place` opens its session with `require_demo=True` and reads only `DERIV_DEMO_ACCOUNT_ID`.
There is no real-money path in this repository and none should be added on the strength of a demo result.

## Step 1 — paper first (needs no credentials, places nothing)

```bash
clicktrader run-smc --symbol R_100 --minutes 1 --higher-minutes 5 15 --max-trades 10 --max-seconds 14400
```

It pulls 1,000 one-minute bars of history so it starts with a chart rather than a blank screen, then reads the live
feed. Every two minutes it says what it sees; when the engine arms a plan it says `PAPER plan taken (nothing placed)` and
follows it with the real ticks to its stop or target. Results go to `recordings/smc-paper-trades.jsonl`.

What paper **cannot** show: slippage, the broker's Multipliers commission, and a fill at the stop that is not at the
stop. Read paper results as "what the engine would have done", never as the account's.

## Step 2 — the demo account, small and capped

Check `.env` has `DERIV_API_TOKEN`, `DERIV_APP_ID` and `DERIV_DEMO_ACCOUNT_ID`, then:

```bash
clicktrader run-smc --place --symbol R_100 --stake 1 --multiplier 100 --max-trades 3 --max-seconds 7200
```

- One position at a time, each with its stop and target attached by the broker.
- `--max-loss-per-trade` (default: the stake) refuses a plan whose stop is worth more than that on the exposure.
- The caps stop the loop; **Ctrl-C also stops the loop but positions already open keep their stop and target on the
  broker** — close them by hand in DTrader (Positions → Close) if you want them gone.
- Results go to `recordings/smc-demo-trades.jsonl`.

## Step 3 — ask whether the evidence is enough

```bash
clicktrader smc-readiness recordings/smc-demo-trades.jsonl recordings/smc-paper-trades.jsonl
```

It says, in plain words, what the logs show. It reports **READY** only with at least 500 *placed* demo trades and a 95%
interval on the mean result per unit risked that sits wholly above zero; paper trades never count toward that, because
they carry no costs. Exit code 0 means READY, 1 means not.

## What to expect, honestly

- **Three trades prove nothing.** The project's own bar is 500 settled trades before it reads a result, and on the data
  it holds the engine arms a handful of trades per day per instrument, so that is weeks of running, not an afternoon.
- **Nothing here has been validated.** The hindsight outcomes in `docs/evidence/` are tiny samples (3 wins of 4 zone trades
  on one afternoon of R_100, 0 wins of 2 on EUR/USD); the engine has been compared with only two markups, both made by an
  agent, not the owner.
- The strategy "fills" when price reaches a zone or block, and the runner then buys **at market** on that tick: expect
  slippage against the level the plan was written at.
- Gold's market closes 21:00–22:00 GMT daily; the volatility indices trade around the clock. If the broker refuses a
  multiplier for a symbol, the error is printed and nothing is placed.
