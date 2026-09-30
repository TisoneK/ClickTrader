# Pillar 3 — the operating manual (assembly)

## Top-down analysis: three timeframes, three jobs

The material routes every decision through a narrowing funnel, and each timeframe has one job:

| timeframe | goal | output |
|---|---|---|
| **Daily (macro)** | establish dominant market sentiment | mark major turning points — the key macro levels |
| **4-hour (meso)** | identify the active structural trend | confirm higher highs / lower lows and directional alignment |
| **1-hour (micro)** | pinpoint battlegrounds and execution triggers | isolate the precise order block and wait for a CHOCH confirmation |

The funnel is drawn as a filter: the daily decides *which direction and whether there is room to move*,
the 4-hour confirms structure agrees with it, and the 1-hour produces the trigger. Its stated output is one
"high-probability execution setup".

**Code status (S010):** partly implemented. The slower clock (default 60 minutes over a 15-minute trigger) acts as a **veto** — a trade against its structure is rejected as `HTF` — but the daily → 4H → 1H chain is not built: the recordings are days long, not months.

## Execution: three steps

1. **Identify the shift.** The zone fails; control changes. (Pillar 2.)
2. **Locate the origin.** Find the order block — the single candle that originated the move. Here it is
   labelled the "new bearish order block".
3. **Set the parameters:**
   - **Stop loss** — placed just above the order block's *wick*.
   - **Entry** — a **limit order at the order block**, not a market order on the break.
   - **Take profit** — at a **minimum 1:2 risk-to-reward**, targeting the **next macro level**.

Status at that point is "order pending", and the material's own phrase for it is that probability has been
maximised by *waiting* rather than by acting.

**Code status (S010):** implemented in `smc/analyst.py` and traded by `smc/strategy.py`: limit at the block edge nearest price, stop beyond the block's far wick, and the 1:2 floor is **enforced** — if no opposing level leaves it, the opportunity is rejected as `NO ROOM`. The "next macro level" is approximated by the nearest opposing level on the same chart that leaves the floor, since no daily levels exist.

## Patience as a requirement

The closing page plots setup quality rising as trade frequency falls, and says it plainly: patience is a
system requirement, overtrading breaks the architecture, and the edge is waiting for the algorithm to
*align across all timeframes* with a minimum 1:2 risk-to-reward.

Worth reading next to this project's own measurements: the code currently fires roughly once an hour on
one-minute bars, which even without a timeframes comparison is a much higher frequency than the material
describes.
