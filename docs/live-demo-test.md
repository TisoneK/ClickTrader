# Running the engine live on the demo account

**Everything here uses virtual money.** `run-smc` has two modes and neither can touch a real account: paper mode
places nothing, and `--place` opens its session with `require_demo=True` and reads only `DERIV_DEMO_ACCOUNT_ID`.
There is no real-money path in this repository and none should be added on the strength of a demo result.

## Step 1 — paper first (needs no credentials, places nothing)

```bash
cd ~/Code/ClickTrader
.venv/bin/clicktrader run-smc --symbol R_100 --minutes 1 --higher-minutes 5
```

(`clicktrader` is installed inside the project's virtual environment, so it is not on your PATH: run it as
`.venv/bin/clicktrader` from the project folder, or `source .venv/bin/activate` once per terminal and then plain
`clicktrader` works.) There are **no caps by default**: it trades what it finds until you press Ctrl-C.

It pulls 1,000 one-minute bars of history so it starts with a chart rather than a blank screen, then reads the live
feed. Every two minutes it says what it sees; when the engine arms a plan it says `PAPER plan taken (nothing placed)` and
follows it with the real ticks to its stop or target. Results go to `recordings/smc-paper-trades.jsonl`.

What paper **cannot** show: slippage, the broker's Multipliers commission, and a fill at the stop that is not at the
stop. Read paper results as "what the engine would have done", never as the account's.

## Step 2 — the demo account, small and capped

Check `.env` has `DERIV_API_TOKEN`, `DERIV_APP_ID` and `DERIV_DEMO_ACCOUNT_ID`, then:

```bash
cd ~/Code/ClickTrader
.venv/bin/clicktrader run-smc --place --symbol R_100 --stake 1 --multiplier 100
```

- One position at a time, each with its stop and target attached by the broker.
- No trade cap, no time cap and no loss cap unless you pass `--max-trades`, `--max-seconds` or `--max-loss-per-trade`;
  those limits were written for the old over/under work and do not apply here by default.
- The caps stop the loop; **Ctrl-C also stops the loop but positions already open keep their stop and target on the
  broker** — close them by hand in DTrader (Positions → Close) if you want them gone.
- Results go to `recordings/smc-demo-trades.jsonl`.

## Step 3 — ask whether the evidence is enough

```bash
.venv/bin/clicktrader smc-readiness recordings/smc-demo-trades.jsonl recordings/smc-paper-trades.jsonl
```

It says, in plain words, what the logs show. It is a reading of the logs, **not a cap on the test**. It says READY only when there are at least `--min-trades`
(default 500, the number of settled trades it takes before a result can be told from luck) *placed* demo trades and a
95% interval on the mean result per unit risked wholly above zero; paper trades never count toward that, because they
carry no costs. Exit code 0 means READY, 1 means not.

## What to expect, honestly

- **A few trades prove nothing.** It takes a few hundred settled trades before a result can be told from luck, and on the
  data it holds the engine arms a handful of trades per day per instrument, so leave it running.
- **Nothing here has been validated.** The hindsight outcomes in `docs/evidence/` are tiny samples (3 wins of 4 zone trades
  on one afternoon of R_100, 0 wins of 2 on EUR/USD); the engine has been compared with only two markups, both made by an
  agent, not the owner.
- The strategy "fills" when price reaches a zone or block, and the runner then buys **at market** on that tick: expect
  slippage against the level the plan was written at.
- Gold's market closes 21:00–22:00 GMT daily; the volatility indices trade around the clock. If the broker refuses a
  multiplier for a symbol, the error is printed and nothing is placed.

## "It isn't trading" — how often to expect a trade, and the one setting that decides it

Measured on 16 hours of R_100 and 25 hours of the 1-second V100 (hindsight readings, no orders), trades armed per hour:

| slower-clock veto | R_100 | V100 (1s) |
|---|---|---|
| 5-minute **and** 15-minute (`--higher-minutes 5 15`) | 0.9 | **0.0** |
| 5-minute only (**the default**) | 0.9 | 0.6 |
| none (`--higher-minutes` with no values) | 1.8 | 1.5 |

The veto (a trade may not go against a slower clock's structure) is the decks' "align across timeframes" and is what
passes on most setups. With no veto it trades about twice as often, but about **half of those are then cancelled** as
falling knives (the return into the zone was as violent as the move that made it), and the trades taken against the
slower clock are the ones the decks say not to take. The run tells you what it passed on and why
("Passed on 14 so far: 9 against the slower clock, 3 a weaker zone, …"), shows your balance at the start, in every status
line and after each trade, and reports a broker refusal in plain words and carries on with the next plan.
