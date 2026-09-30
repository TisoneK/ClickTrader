# Evidence: what the engine saw, as pictures

These PNGs are **the engine's own output**, so they are safe to keep in the repo (unlike the owner's screenshots
or the course decks). Each has a `.txt` beside it holding the exact console output of the command that made it,
so a picture is never separated from what the engine said about it. Regenerate any of them with the command below;
the readings are causal and deterministic, so the same data gives the same picture.

| picture | data | command |
|---|---|---|
| `v100-1m-owner-level-1001.png` | Volatility 100 (1s), 1-minute bars, 2026-09-30 07:00–12:20 UTC (the window of the owner's screenshot), fetched with `history-deriv --symbol 1HZ100V --granularity 60` | `clicktrader smc-chart v100_1m.jsonl out.png --minutes 1 --from "2026-09-30 07:00" --to "2026-09-30 12:20" --mark 1001 --higher-minutes 5` |
| `v100-zoom.{1m,5m,15m}.png` | the same window at three zoom levels | `... --minutes 1 5 15` |
| `eurusd-15m.png` | `recordings/forex/live-eurusd-20260928.jsonl` (241,125 lines, sha256 `bc2b4133…`) | `clicktrader smc-chart recordings/forex/live-eurusd-20260928.jsonl out.png --minutes 15 --bars 150` |
| `gold-15m.png` | 288 fifteen-minute gold candles, 2026-09-25 → 09-30, `history-deriv --symbol frxXAUUSD` | `... --minutes 15 --bars 130` |

**The first comparison with a markup — mine, not the owner's** (`markup/v100-20260930-0700-1220.*`). Written from the owner's screenshot *before* the engine's output was looked at, in the JSON format the owner can fill in (`clicktrader smc-compare markup.json recording.jsonl`). Result after the fixes it prompted: **5 of 7 marks agree.** What it found, in order:

1. **Wrong swing scale (fixed).** I marked a bearish change of character at 10:22 (the close through the floor the whole leg started from, ~1011). The engine called one at 10:12 — a break of a five-minute wiggle inside the rally (1019.85). It treated every two-bar fractal as structure. Structure now uses *major* swings: a leg smaller than the median leg in view is noise. The engine's CHOCH is now at 10:22, level 1011.60.
2. **Level identity (fixed).** 58 bands stacked at one level because every swing joining a cluster made a new one; a level is now one object that grows.
3. **Pool sweeps (added).** A wick through a stacked level that closes back inside on the same bar is now a SWEEP of that level whichever swing control is watching.
4. **Disagreements left standing.** (a) My 'sweep at 11:24' was really an undercut — price closed below the support for four bars before recovering — so the engine not calling it a sweep is right by the material's own rule, and my mark was loose. (b) My long from the support was rejected as `HTF`: the 5-minute structure read down. That is a real difference of method (I bought a held support against the slower clock; the material's funnel does not). (c) In the chop I marked no-trade the engine armed one trade. (d) The engine calls 12–14 changes of character in the window where I marked one: I marked only the decisive one, so this shows the engine labels at finer scale than I do, not that it is wrong. (e) My 'flip zone' at ~1010.8 (a floor that broke and then capped bounces) was found as bands but they were deleted when price closed through them; the level-stack / flip-zone concept is not implemented.

**The earlier one-line comparison** (`v100-1m-owner-level-1001.*`, the owner's hand-drawn line): the owner drew a horizontal
line at about 1001 through a cluster of lows on the live chart (`docs/sources/screenshots/`). The engine's level
there is the band 1000.84–1001.10 (5 touches), which contains the line; 58 swing points sit within one typical
candle range of it, 42 of them lows. So it found the level **where the owner drew it, but as a thinner band than the
owner's line suggests**. One level, one instrument, one afternoon: a first data point, not a validation.

**Zoom and drag.** Zoom is the bar size (`--minutes`), drag is the time window (`--from`/`--to`, UTC), and the time
axis is on the picture so it can be placed on the clock. The reading is always of the whole recording, so dragging
never changes what is seen in a window. At 12:20 the structure by zoom is `1m range, 5m down, 15m up`; that
table, not one chart, is how the engine tells the zoom levels apart today. It does **not** yet re-read a level
at a finer zoom or carry a level across zooms (the material's daily → 4H → 1H chain).

**What is not here:** the owner's screenshots and the course decks (public repo; the screenshots also show browser
tabs and an account balance). They are described page by page in `docs/sources/`.

## The owner's test-live screenshots (`r100-1m-test-live.*`, `r100-zoomed-out.*`, `gold-1m-market-closing.*`, `markup/r100-*`)
Deriv history for the same instrument and windows matches the screens exactly (R_100 20:28 candle identical to the
tooltip; gold's last price within 0.07). The engine's picture of the owner's zoomed-in view has the same shape as the
screenshot (20:51 peak, fall, lower low at 21:17, bounce). My markup of that view (`markup/r100-20260930-2010-2132.*`):
**3 of 4 marks agree, plus 1 with the level right and a different label.**
- **Resistance 637.85:** found (engine band 637.47-637.98, 7 touches). **Support 630.4-631.4:** found *after a fix*
  (below). **No-trade 21:18-21:32:** the engine armed nothing.
- **The bearish break I marked at 634.2 (20:54):** the engine has it at the same price (a BOS at 20:55, level 634.20)
  but names it BOS, because it had already called a CHOCH down at 20:44 (break of 635.08). The engine's story is
  CHOCH 20:44 -> a sweep of the equal highs at 20:51 -> BOS 20:55; mine was one CHOCH. By the material's own logic the
  engine's reading is arguably the better one (the 20:51 spike above 637.8 that closed back is a textbook sweep), but
  a person who marks one CHOCH would not see it that way; only the owner's marks can say which they would call.
- **A real engine defect, found and fixed:** the support was *found and then dropped*. Low-side pools at 630.46-630.87
  (6 touches) and 631.54-631.77 (10 touches) existed, but an older level at that price had been closed through, and
  the rule "a deleted level stays deleted" kept the market turning there again from ever becoming a new level. A level
  that has been closed through and then gets fresh swings afterwards is now a new level.
- **Over-labelling is still the main gap:** 47 BOS, 47 CHOCH and 126 sweeps over the 999 one-minute bars read. Sweep
  lines are now capped at 14 bars of reach so they no longer span the picture.
- **Also seen:** gold's daily 21:00-22:00 GMT closure (the feed and the bars stop at ~20:58), and the owner's RSI panel,
  which nothing here uses.

## True zones and false zones (added after the owner asked whether the engine "just marks")
The blue bands in these pictures are **levels**, stacks of swing points. **Zones** are separate, and are the decks' and
S01's object: the origin of an aggressive move. In the owner's zoomed-in V100 view (`r100-1m-test-live.png`) the engine
finds a **SUPPLY FRESH** zone at 636.39-637.51 (the last up candle before the drop from the 20:51 peak; it left a gap,
broke structure, and price never came back to it) and a **SUPPLY USED KNIFE** zone at 633.48-634.39 (price came back to
it violently at 21:18). It finds **no demand zone** under the 21:17 low, correctly by the decks' rules: the bounce
from there did not break structure, so it fails the break-of-structure rule. Over the 999 one-minute bars read there
are 4 true zones standing, 31 broken and 60 false. `smc-compare` now reports zones as well as levels. The zone
detector has not yet been compared with the owner's own marks of zones, which is the test that matters.
