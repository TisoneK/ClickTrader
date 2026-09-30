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
