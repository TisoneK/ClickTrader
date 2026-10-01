"""The chart the way the trader leaves it on the screen: a few areas that matter, the plan, and a sentence.

`draw.draw_reading` shows everything the engine knows, each mark open to argument. A person does not draw that. He
draws the few bands and zones that matter for where price is NOW, the order he is waiting to take (entry, stop,
target as two boxes), the path he expects as one arrow, and says in a line what he is doing and why. This is that view
of the same reading — nothing here is a second analysis:

- wide pale-blue bands   the strongest levels still alive near price, running off to the right (at most two each side)
- red / green boxes      a TRUE, FRESH supply / demand zone near price (at most two each side; a weaker one is left out)
- two boxes + an arrow   an order the engine is waiting with: green = where it pays, red = where it is wrong; the
                         arrow is the expected path (to the zone, then to the target)
- header                 what price is doing, and either what it is waiting for or why there is nothing to do
- right-hand axis        the prices of every edge drawn, so it can be checked against a chart on another screen
"""

from __future__ import annotations

from ..forex.model import Direction
from .analyst import Reading, State
from .draw import _tick_labels
from .render import AxisLabel, Arrow, Box, Label, Segment, render_chart

_DEMAND = (20, 160, 105)
_SUPPLY = (215, 60, 90)
_LEVEL = (40, 90, 200)
_REWARD = (30, 150, 140)
_RISK = (225, 95, 130)
_INK = (30, 30, 30)
_WHY = {
    "higher timeframe": "THE SLOWER CHART DISAGREES",
    "against the trend": "THE ZONE IS AGAINST THE TREND",
    "room": "NO ROOM TO THE NEXT LEVEL",
    "weaker zone": "A BETTER ZONE SITS ELSEWHERE IN THE SAME MOVE",
    "knife": "PRICE CAME BACK TOO VIOLENTLY",
    "dead": "PRICE CLOSED THROUGH THE ZONE",
}


def _why_nothing(reading: Reading, n: int) -> str:
    """The most recent reason an order was refused or taken away, in words; else that no fresh zone is in reach."""
    for o in reversed(reading.opportunities):
        if o.state in (State.DECLINED, State.CANCELLED, State.DEAD) and n - 1 - (o.closed_at or o.armed_at) <= 30:
            for key, words in _WHY.items():
                if key in o.reason:
                    return words
    return "NO FRESH ZONE IN REACH WITH ROOM TO A TARGET"


def trader_view(reading: Reading, *, bars: int = 120) -> dict:
    """Choose what a person would draw. Pure data, so it can be checked without a picture."""
    n = len(reading.candles)
    lo = max(0, n - bars)
    candles = list(reading.candles[lo:n])
    price = candles[-1].close
    base_lo, base_hi = min(c.low for c in candles), max(c.high for c in candles)
    reach = (base_hi - base_lo) * 3.0  # anything that would squash the candles into a strip is left off

    def fits(*prices: float) -> bool:
        return max(base_hi, *prices) - min(base_lo, *prices) <= reach

    standing = [o for o in reading.opportunities if o.state is State.ARMED and o.target is not None]
    standing.sort(key=lambda o: abs(o.entry - price))
    orders = [o for o in standing if fits(o.stop, o.target, o.entry)][:2]

    zones = [z for z in reading.zones if z.valid and z.status == "fresh" and z.died_at is None and not z.weaker]
    supply = sorted((z for z in zones if z.direction is Direction.DOWN and z.high > price), key=lambda z: z.low)[:2]
    demand = sorted((z for z in zones if z.direction is Direction.UP and z.low < price), key=lambda z: -z.high)[:2]
    zones = [z for z in (*supply, *demand) if fits(z.low, z.high)]

    alive = [(b, born) for b, born, died in reading.levels if died is None and born < n]
    above = sorted((x for x in alive if x[0].low > price), key=lambda x: x[0].low)[:2]
    below = sorted((x for x in alive if x[0].high < price), key=lambda x: -x[0].high)[:2]
    levels = [x for x in (*above, *below) if fits(x[0].low, x[0].high)]
    return {"lo": lo, "candles": candles, "price": price, "orders": orders, "zones": zones, "levels": levels}


def sentences(reading: Reading, view: dict | None = None, fmt=None, decimals: int | None = None) -> list[str]:
    """The three header sentences: what price is doing, what the engine waits for (or that there is nothing to do), and why."""
    view = view or trader_view(reading)
    price = view["price"]
    if fmt is None:
        if decimals is None:
            decimals = 5 if price < 20 else 2
        fmt = lambda p: f"{p:.{decimals}f}"  # noqa: E731
    n = len(reading.candles)
    structure = reading.structure[-1].value.upper() if reading.structure else "?"
    control = reading.control[-1] if reading.control else None
    who = {"demand": "BUYERS IN CONTROL", "supply": "SELLERS IN CONTROL"}.get(control.value if control else "", "NO ONE IN CONTROL YET")
    lines = [f"PRICE {fmt(price)}   TREND {structure}   {who}"]
    if view["orders"]:
        o = view["orders"][0]
        zone = "ZONE " if o.source == "zone" else "BLOCK "
        lines.append(f"WAITING: {'BUY' if o.direction is Direction.UP else 'SELL'} AT {fmt(min(o.block.price_low, o.block.price_high))}-"
                     f"{fmt(max(o.block.price_low, o.block.price_high))}   STOP {fmt(o.stop)}   TARGET {fmt(o.target)}   {o.reward_risk:.1f} TO 1")
        why = "A FRESH TRUE ZONE" if o.source == "zone" else "THE BLOCK THAT LEFT WHEN THE TREND CHANGED CHARACTER"
        more = f"   (+{len(view['orders']) - 1} MORE WAITING)" if len(view["orders"]) > 1 else ""
        lines.append(f"WHY: {why} - ROOM TO THE NEXT LEVEL{more}")
    else:
        lines.append("NOTHING TO DO NOW")
        lines.append(f"WHY: {_why_nothing(reading, n)}")
    return lines


def draw_trader_view(reading: Reading, path: str, *, bars: int = 120, decimals: int | None = None, width: int = 1800, height: int = 900) -> list[str]:
    """Write the picture and return the header sentences (so a console can say the same thing in words)."""
    view = trader_view(reading, bars=bars)
    lo, candles, price = view["lo"], view["candles"], view["price"]
    n, m = len(reading.candles), len(candles)
    if decimals is None:
        decimals = 5 if price < 20 else 2  # a currency pair quotes five decimals; an index, a metal or a synthetic two
    fmt = lambda p: f"{p:.{decimals}f}"  # noqa: E731
    boxes, labels, segs, arrows, axis = [], [], [], [], []

    for band, born in view["levels"]:
        boxes.append(Box(band.low, band.high, max(0, band.first_index - lo), None, _LEVEL, 0.16))
        axis.append(AxisLabel((band.low + band.high) / 2, f"LEVEL {fmt(band.low)}-{fmt(band.high)}", _LEVEL))
    for z in view["zones"]:
        colour = _DEMAND if z.direction is Direction.UP else _SUPPLY
        boxes.append(Box(z.low, z.high, max(0, z.origin_index - lo), None, colour, 0.30))
        labels.append(Label(max(0, z.origin_index - lo), z.high if z.direction is Direction.DOWN else z.low, z.kind, colour, 2,
                            "above" if z.direction is Direction.DOWN else "below"))
        axis.append(AxisLabel((z.low + z.high) / 2, f"{z.kind} {fmt(z.low)}-{fmt(z.high)}", colour))

    future = max(10, m // 5)  # empty room on the right: the plan lives in the future
    for o in view["orders"]:
        start = max(0, o.armed_at - lo)
        boxes.append(Box(*sorted((o.entry, o.stop)), start, None, _RISK, 0.28))
        boxes.append(Box(*sorted((o.entry, o.target)), start, None, _REWARD, 0.28))
        long = o.direction is Direction.UP
        word = "BUY" if long else "SELL"
        labels.append(Label(start, o.entry, f"{word} {o.reward_risk:.1f} TO 1", _REWARD, 2, "above" if long else "below"))
        step = max(3, future // 3)
        segs.append(Segment(m - 1, price, m - 1 + step, o.entry, _INK, True))  # price goes to the zone ...
        arrows.append(Arrow(m - 1 + step, o.entry, m - 1 + 2 * step, o.target, _INK))  # ... and from there to the target
        axis += [AxisLabel(o.entry, f"ENTRY {fmt(o.entry)}", _INK), AxisLabel(o.stop, f"STOP {fmt(o.stop)}", _RISK),
                 AxisLabel(o.target, f"TARGET {fmt(o.target)}", _REWARD)]

    lines = sentences(reading, view, fmt)

    pad = (max(c.high for c in candles) - min(c.low for c in candles)) * 0.06
    lo_p = min([c.low for c in candles] + [z.low for z in view["zones"]] + [o.stop for o in view["orders"]] + [o.target for o in view["orders"]])
    hi_p = max([c.high for c in candles] + [z.high for z in view["zones"]] + [o.stop for o in view["orders"]] + [o.target for o in view["orders"]])
    render_chart(candles, path, boxes=boxes, labels=labels, segments=segs, arrows=arrows, axis=axis,
                 header=[(lines[0], _INK), (lines[1], _REWARD if view["orders"] else (110, 110, 110)), (lines[2], (90, 90, 90))],
                 price_range=(lo_p - pad, hi_p + pad), xticks=_tick_labels(candles, lo), future=future, right_margin=190,
                 width=width, height=height)
    return lines
