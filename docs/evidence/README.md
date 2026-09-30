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

**The one comparison with a person's markup that exists** (`v100-1m-owner-level-1001.*`): the owner drew a horizontal
line at about 1001 through a cluster of lows on the live chart (`docs/sources/screenshots/`). The engine's level
there is the band 1000.84–1001.10 (5 touches), which contains the line; 58 swing points sit within one typical
candle range of it, 42 of them lows. So it found the level **where the owner drew it, but as a thinner band than the
owner's line suggests**. One level, one instrument, one afternoon: a first data point, not a validation.

**Zoom and drag.** Zoom is the bar size (`--minutes`), drag is the time window (`--from`/`--to`, UTC), and the time
axis is on the picture so it can be placed on the clock. The reading is always of the whole recording, so dragging
never changes what is seen in a window. At 12:20 the structure by zoom was `1m down, 5m down, 15m range`; that
table, not one chart, is how the engine tells the zoom levels apart today. It does **not** yet re-read a level
at a finer zoom or carry a level across zooms (the material's daily → 4H → 1H chain).

**What is not here:** the owner's screenshots and the course decks (public repo; the screenshots also show browser
tabs and an account balance). They are described page by page in `docs/sources/`.
