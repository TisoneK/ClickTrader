"""Draw a `Reading` in the analyst's own language: swings named, levels banded, gaps boxed, every break
labelled for what it was, and every opportunity shown as the order it would have been — or the reason it was not.

Colour and word carry the verdict, so a person can disagree with a specific mark rather than with "the engine":

- `HH HL LH LL`   swing names, above highs and below lows
- blue band       a level (liquidity) while alive; it ends on the bar that closed through it
- yellow box      an open fair value gap; it stops at the bar that filled it
- `BOS`           dashed line: the trend carried on through its last extreme
- `CHOCH`         dashed green line: a true change of character (the level held as a reversal)
- `SWEEP` red     the wick took the stops and the close came back: NOT a reversal
- `GAP FILL` orange  price rebalancing an open gap: NOT a reversal
- orange box      the order block (the origin candle, wick to wick)
- pink / teal     stop zone / target zone of an opportunity the analyst would have taken, with `WIN`/`LOSS`
                  shown from hindsight only
- grey label      an opportunity it rejected, and why (`NO ROOM`, `KNIFE`, `DEAD`, `HTF`)
- top strip       who is in control: teal demand, red supply
"""

from __future__ import annotations

from ..forex.model import Direction
from .analyst import EventKind, Reading, State
from .render import Box, HLine, Label, Mark, Segment, render_chart

_BLUE = (40, 90, 200)
_GREEN = (20, 140, 90)
_RED = (200, 40, 40)
_ORANGE = (235, 120, 30)
_GREY = (110, 110, 110)
_PINK = (225, 95, 130)
_TEAL = (30, 150, 140)
_YELLOW = (235, 190, 40)
_SHORT_REASON = {State.DEAD: "DEAD", State.CANCELLED: "KNIFE"}


def _short_reason(opp) -> str:
    if opp.state is State.DECLINED:
        return "HTF" if "higher timeframe" in opp.reason else "NO ROOM" if "room" in opp.reason else "NO BLOCK"
    return _SHORT_REASON.get(opp.state, "")


def draw_reading(reading: Reading, path: str, *, bars: int = 160, width: int = 1800, height: int = 900) -> None:
    n = len(reading.candles)
    lo = max(0, n - bars)
    candles = list(reading.candles[lo:])
    m = len(candles)

    def at(i: int | None) -> int | None:
        return None if i is None else i - lo

    def visible(i: int | None) -> bool:
        return i is not None and i - lo >= 0

    lines, boxes, marks, labels, segs = [], [], [], [], []

    for ls in reading.swings:
        s = ls.swing
        if ls.known_at < n and s.index >= lo:
            high = s.kind.value == "high"
            marks.append(Mark(s.index - lo, s.price, above=high))
            labels.append(Label(s.index - lo, s.price, ls.label, _GREY, 2, "above" if high else "below"))

    most = max((b.touches for b, _, d in reading.levels if d is None), default=1)
    for band, born, died in reading.levels:
        if died is not None:
            continue  # a level that has been closed through is deleted from the chart, as the material says
        # the more often the market turned there, the more it stands out; touches are the only thing that varies
        boxes.append(Box(band.low, band.high, max(0, band.first_index - lo), None, _BLUE, 0.07 + 0.22 * band.touches / most))

    for gap, filled in reading.gaps:
        if filled is not None and filled < lo:
            continue
        boxes.append(Box(gap.lower, gap.upper, max(0, gap.formed_index - lo), None if filled is None else at(filled), _YELLOW, 0.32 if filled is None else 0.14))

    for e in reading.events:
        if e.index < lo:
            continue
        x0, x1 = max(0, e.level_from - lo), e.index - lo
        colour = {EventKind.BOS: _BLUE, EventKind.CHOCH: _GREEN, EventKind.SWEEP: _RED, EventKind.GAP_FILL: _ORANGE}[e.kind]
        segs.append(Segment(x0, e.level, x1, e.level, colour, e.kind is not EventKind.CHOCH))
        below = e.direction is Direction.DOWN
        labels.append(Label((x0 + x1) // 2, e.level, e.kind.value.replace(" ", " "), colour, 2, "below" if below else "above"))

    for o in reading.opportunities:
        if o.armed_at < lo:
            continue
        b = o.block
        end_i = o.closed_at if o.closed_at is not None else (n - 1)
        # a rejected setup's block is only worth a glance: it runs to the bar it was rejected on, no further
        box_end = (o.filled_at or o.closed_at or n - 1) if o.is_true else o.armed_at
        boxes.append(Box(b.price_low, b.price_high, max(0, b.index - lo), at(box_end), _ORANGE, 0.25 if o.is_true else 0.14))
        if o.is_true and o.target is not None:
            start = max(0, o.armed_at - lo)
            stop_lo, stop_hi = sorted((o.entry, o.stop))
            tgt_lo, tgt_hi = sorted((o.entry, o.target))
            last = at(end_i)
            boxes.append(Box(stop_lo, stop_hi, start, last, _PINK, 0.30))
            boxes.append(Box(tgt_lo, tgt_hi, start, last, _TEAL, 0.30))
            word = "SHORT" if o.direction is Direction.DOWN else "LONG"
            tag = f"{word} {o.reward_risk:.1f}R" + (f" {o.outcome.upper()}" if o.outcome else " ARMED")
            labels.append(Label(start, o.entry, tag, _GREEN if o.outcome != "loss" else _RED, 2, "above" if o.direction is Direction.UP else "below"))
        else:
            word = _short_reason(o)
            labels.append(Label(max(0, o.armed_at - lo), b.price_high if b.price_high else 0, "X " + word, _GREY, 2, "above"))

    control = [c.value if c else "" for c in reading.control[lo:]]
    lo_p = min(c.low for c in candles)
    hi_p = max(c.high for c in candles)
    for o in reading.opportunities:
        if o.is_true and o.armed_at >= lo:
            lo_p, hi_p = min(lo_p, o.stop), max(hi_p, o.stop)
    pad = (hi_p - lo_p) * 0.06
    render_chart(candles, path, lines=lines, boxes=boxes, marks=marks, labels=labels, segments=segs, control=control, price_range=(lo_p - pad, hi_p + pad), width=width, height=height)
