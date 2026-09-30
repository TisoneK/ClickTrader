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

**Code status:** **everything the code does runs on a single timeframe** — one-minute bars for the
price-action method, fifteen-minute bars for others. There is no higher-timeframe bias and no alignment
step. Since the material's whole funnel is that alignment, this is the second structural gap after the
missing control state.

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

**Code status:** the limit-entry and the stop relative to the origin are implemented for one of the
methods. The **1:2 minimum** is not enforced anywhere — the exits in the code aim at various targets
(a swing, an imbalance, a structure extreme) chosen to make the trade well-formed, not against a
risk-to-reward floor. The "next macro level" target needs the daily levels, which do not exist yet.

## Patience as a requirement

The closing page plots setup quality rising as trade frequency falls, and says it plainly: patience is a
system requirement, overtrading breaks the architecture, and the edge is waiting for the algorithm to
*align across all timeframes* with a minimum 1:2 risk-to-reward.

Worth reading next to this project's own measurements: the code currently fires roughly once an hour on
one-minute bars, which even without a timeframes comparison is a much higher frequency than the material
describes.
