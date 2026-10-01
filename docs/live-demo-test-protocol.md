# Live demo test - rules decided BEFORE the results (draft, 1 Oct 2026)

Why this file exists: deciding what counts as success after seeing the numbers is how a bad system gets talked into. Everything
marked **OWNER TO CONFIRM** is a proposal from the engineer, not a decision; nothing here has been confirmed by the owner yet.
Commit the confirmed version before more demo trades are counted, and do not edit it afterwards except by a dated amendment.

## What is being tested (frozen)

One strategy: the zone-based SMC engine (`run-smc`), on R_100, 1-minute bars with the 5- and 15-minute slower charts.
`RULES_VERSION` in `clicktrader/smc/analyst.py` plus every setting form a short fingerprint written into each trade row
(`"rules"`). The evidence counts only rows made under the fingerprint of the most recent trade. Any change to a rule that changes
which trades are taken (including a flag such as `--counter-trend`, `--stop-buffer`, `--strict-trend-change`) changes the
fingerprint and so **restarts the count**. A bug fix that leaves the trades unchanged does not bump the version. The first demo
trade (a -0.20 stop-out, 29 Sep) and the second (-0.30) were made under earlier rules and do not count.

## What counts

- **Demo-account trades only**, with real fills and commission. Paper ("practice") trades never count; the page keeps them
  collapsed and labelled.
- **Independent setups, not trades.** Same-direction trades within an hour of each other are one idea tested more than once
  and count once (`smc/readiness.py: independent_setups`). The target is **500 independent setups**.
- Result per setup in units of risk (R: profit divided by the money at the stop), averaged inside a setup; the 95% interval of the
  mean uses `clicktrader/stats.mean_interval`.
- Smoke-test trades (`--smoke-test`) are logged elsewhere and never count.

## Settings (OWNER TO CONFIRM)

| Setting | Proposed | Note |
|---|---|---|
| Stake / multiplier | 1.00 at x100 (unchanged) | The broker refuses a stop worth under 0.10, so zones narrower than about 0.6 points are skipped. A larger stake or x200 would trade them but is a rules change |
| Daily loss cap | 3.00 USD (3 x stake) per UTC day, `--daily-loss-cap 3` | Stops the run for the day; restart next day |
| Trade frequency cap | none beyond one position at a time | Honest counting (independent setups) replaces a cap |

## Verdict after 500 independent setups (OWNER TO CONFIRM)

Using the 95% interval of the mean result per unit of risk, after costs:

- **Lower bound above 0 and mean at least +0.10R** -> the demo evidence clears the project's bar. The next step is only the
  small live platform test below, not real size.
- **Interval includes 0** -> keep testing, same rules, up to 1000 independent setups.
- **Upper bound below 0, or still no edge at 1000 setups (mean under +0.05R)** -> drop this strategy.

Stated requirement beside the ratio: a plan of R:1 breaks even above 100/(1+R) percent wins before costs; the page shows this next
to every plan. The strategy is judged on the win rate it actually reaches, not on how good the ratio looks.

## Before any real money (separate from the 500)

Demo fills are often kinder than live ones. Before real money, run a small live test whose only purpose is the platform: compare
fill prices with what the screen showed, and confirm a **withdrawal actually works**. This repository has no real-money path and
trades only the Deriv demo account; whether a given broker is regulated, and how it treats withdrawals, is not something this
code can verify and should be checked by the owner independently.

## What the reviewers got right and wrong (kept so the reasoning is not lost)

- Plan rules vs the "stop grab" wording: right in substance. A poke past a plan's stop touches the broker's stop even if it "came
  straight back". The page now says so when a sweep level is beyond the plan's stop.
- "Results do not look like the plan": wrong on the data. In units of risk every logged win realised its planned ratio and every
  loss was exactly -1R; they look tiny because each stop is worth 7 to 28 cents.
- Practice runs flattering the scoreboard: right. They are collapsed by default and never counted.
- Correlated trades inflating the count: right; fixed by counting independent setups.
- "Trend change too easy to trigger": a strict rule exists (`--strict-trend-change`) but in hindsight it removes 27 of 28 such trades
  and those were not worse, so it is off by default and the evidence is the arbiter.
