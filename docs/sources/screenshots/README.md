# The owner's screenshots (described, not committed)

The images show browser tabs and a demo-account balance, and the repo is public, so they are described here
instead. Originals: `~/Desktop/Screenshot 2026-09-30 151950.png`, `~/Desktop/rise and fall won.jpg`.

## `Screenshot 2026-09-30 151950.png` — the owner's live chart with a hand-drawn level
Deriv DTrader, **Volatility 100 (1s) Index**, Rise/Fall, **1-minute candles** (the "1m" badge), demo account
(balance 10,054.59). The x-axis runs about 07:00 to 12:20 GMT on 30 Sep 2026; the price axis 990 to 1030. Price
rose from ~1000 to a peak near 1022 around 09:40, fell back, and was near 1009 at 12:19. **A blue horizontal line
drawn with the platform's drawing tool sits at about 1001** (the pixel row falls between the 1000 and 1010 axis
labels), running through a cluster of lows that price returns to at least five times and that the candles do not
close below. This is the owner's own marking of a level, the reference example `docs/smc/README.md` rule 3 asks
for. Side panel: Rise/Fall, duration 2 min, stake $10, allow-equals off, **Buy, payout $18.85** — a *quote* for a $10
purchase (no trade was open in this shot): 88.5% profit, the same rate the realised trade in `rise and fall won.jpg` paid,
and not the ~95% the Pure Price Action deck shows.

## `rise and fall won.jpg` — the result of an EARLIER trade, dated 29 Sep (not the test session)
Volatility 100 (1s) Index, demo account, **29 Sep 2026, 13:21 GMT** (the day before the test session), balance
10,064.59. The green **"+8.85 USD"** bubble on the chart is the **result of a previous $10 Rise**: stake $10, profit
$8.85, so **$18.85 returned in total** (the owner's "$18.85"). The Positions panel shows no open positions, so that
trade had already settled. The **"Payout $18.85" on the Buy button is a different thing**: the platform's *quote* for
the *next* $10 purchase. The two agree: a quote of 88.5% and a realised profit of 88.5% of the stake. That is worth
stating because earlier notes found the API's proposal quote (about 95%) disagreeing with the fills (88%); on this
screen the platform's own quote and the realised result match, so 88.5% is the figure to use. A tooltip shows a bar
with open 953.92, high 953.98, low 951.56, close 952.28. Nothing here was produced by this engine or by a rule.

## `test-live.zip` — five screenshots of the owner's test session, 30 Sep 2026 21:27-21:32 GMT
Deriv DTrader, demo account. **How the owner sees the bars:** candles at the **1-minute** interval (the "1m" badge on
every shot), teal up and crimson down, with an **RSI (14, C, Y)** panel under the chart (the engine ignores it; the
decks are indicator-free), at two zooms: about 40 bars in view, and about ten hours (12:00-22:00).
1. **Gold/USD, 21:27:44 GMT** — market **closed**: Rise/Fall greyed out, "will reopen at 10:00 pm GMT" (a 21:00-22:00
   GMT daily gap; the last candle is about 20:58, price 4157.01, range about 4155-4160). Duration 5 min, stake $2.
2. **Volatility 100 Index (2-second ticks, symbol `R_100`, not the 1s index of the earlier screenshots), zoomed in** —
   tooltip for the 20:28 candle: open 634.60, high 634.88, low 633.81, close 633.84 (matches Deriv history exactly).
   Price 633.34 at 21:29:05; peak near 638 around 20:50, lower lows to about 630.5 at 21:17. **Payout $3.78 on a $2
   stake: 89.0% profit.**
3. **The same instrument zoomed out, 12:00-22:00** — a fall to about 613 near 13:00, a rise to about 640 near 16:00,
   then a range around 628-637. Price 633.04 at 21:29:34.
4. **An open test trade**: Rise, $2, 2 minutes, 1:40 left, +$0.80; entry marker on the chart; balance 10,053.74 (the
   stake is held).
5. **The same trade at 0:00:02 left: -$2.00**; it settled as a loss. **The owner states this trade was random, with
   no rules, purely to test the platform**, so it is a payout/mechanics data point and says nothing about any method.
