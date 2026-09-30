"""The analyst: read a chart the way a person does, one bar at a time, and say what it sees.

Everything else in this package answers a narrow question (is this a pool? is this break a sweep?). The analyst
puts them in the order a trader's eye takes them and keeps the *whole reading*, so it can be drawn, argued with
and compared with a person's markup:

1. **Swings** — the pivots the eye circles — each named against the one before it (HH, HL, LH, LL).
2. **Structure** — up, down or range, from those names.
3. **Levels** — bands where swings stacked up (liquidity), alive until a close goes through them.
4. **Gaps** — imbalances (fair value gaps), filled or still open.
5. **Breaks** — a close through the level that matters: a BOS when it carries the trend on, a CHOCH when it goes
   against it; and the two impostors that look identical at that moment — a *sweep* (the wick took the stops and
   the close came back) and a *gap fill* (price rebalancing an open imbalance).
6. **Opportunities** — a true CHOCH leaves an order block; the analyst arms a limit order there, says where the
   stop and the target are, and then watches the order live or die: dead zone, falling knife, no room to move,
   against the higher timeframe, filled and won, filled and lost.

**Causality is the contract.** At bar `t` the analyst knows only bars `0..t`. A swing at bar `i` is not known
until `strength` bars later, and is not used before. The hindsight fields (`outcome`) are filled in after the
fact and exist only so the picture can show what happened; nothing decides on them.

**No number here was invented.** Where the material gives a rule it is implemented as stated (the strict gap, the
single origin candle, a close beyond the far edge kills a zone, minimum 1:2 to the next level, first tap only,
cancel on a violent approach). Where it uses a comparative word, the comparison is against the chart's own window
(`docs/smc/README.md`, rule 2). Where it leaves a judgement to the eye, the field is reported and never gated.
The few choices that are this project's own are listed in `READINGS` and printed with every reading.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from ..forex.candles import Candle
from ..forex.model import Direction
from ..forex.structure import (
    FairValueGap,
    SwingKind,
    SwingPoint,
    Trend,
    fair_value_gaps,
    gap_untouched,
    swing_points,
)
from .components import OrderBlock, order_block
from .engine import BreakKind, Control, LiquidityPool, classify_break, liquidity_pools
from .quality import pushed_distance

READINGS = (
    "a swing is a fractal pivot: the extreme of `strength` bars on each side (the convention every SMC reference uses)",
    "structure is UP when the last two swing highs and the last two swing lows both rise, DOWN when both fall, else RANGE; it only SEEDS control",
    "control is demand or supply and flips only on a true CHOCH; breaks are read against control, not against the structure label",
    "a level band is the lowest wick to the lowest body bottom of the swings that stacked there, merged when bands overlap",
    "a level is alive until a bar CLOSES through its far edge; it is then a dead zone and is deleted",
    "the CHOCH level is the most recent swing on the side the trend needs to hold (the last HL in an up-trend)",
    "the target is the nearest opposing level that leaves at least the stated 1:2; if none does, there is no room",
    "a return is a falling knife when the bar that first reaches the zone is itself as large as the impulse's median body",
)


class Structure(str, Enum):
    UP = "up"
    DOWN = "down"
    RANGE = "range"


class EventKind(str, Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"
    SWEEP = "SWEEP"
    GAP_FILL = "GAP FILL"


class Verdict(str, Enum):
    TRUE = "true"
    FALSE = "false"
    CONTINUATION = "continuation"


class State(str, Enum):
    ARMED = "armed"
    FILLED = "filled"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    DEAD = "dead"


@dataclass(frozen=True)
class LabeledSwing:
    swing: SwingPoint
    label: str
    """HH, HL, LH, LL — or H / L for the first of its kind, which has nothing to be compared with yet."""
    known_at: int
    """The bar on which a person could first have circled it."""


@dataclass(frozen=True)
class Event:
    index: int
    kind: EventKind
    verdict: Verdict
    level: float
    level_from: int
    """The bar the level came from — where the line is drawn from."""
    direction: Direction
    reason: str
    strength: float = 0.0
    """The breaking bar's body as a multiple of the window's median body. Reported, never gated."""


@dataclass
class Opportunity:
    """A limit order the analyst would place, and everything that happened to it."""

    armed_at: int
    direction: Direction
    block: OrderBlock
    entry: float
    stop: float
    target: float | None
    event: Event
    gap: FairValueGap | None
    pushed: float
    reward_risk: float | None
    state: State = State.ARMED
    reason: str = ""
    filled_at: int | None = None
    closed_at: int | None = None
    outcome: str | None = None
    """HINDSIGHT — "win", "loss" or "open" once filled. Nothing decides on this; it is for the picture."""

    @property
    def is_true(self) -> bool:
        return self.state in (State.ARMED, State.FILLED)


@dataclass
class Reading:
    candles: Sequence[Candle]
    swings: list[LabeledSwing] = field(default_factory=list)
    structure: list[Structure] = field(default_factory=list)
    """The structure as it read at each bar."""
    control: list[Control | None] = field(default_factory=list)
    levels: list[tuple[LiquidityPool, int, int | None]] = field(default_factory=list)
    """(band, first bar it existed, bar it died on or None if still alive)."""
    gaps: list[tuple[FairValueGap, int | None]] = field(default_factory=list)
    """(gap, bar that filled it or None)."""
    events: list[Event] = field(default_factory=list)
    opportunities: list[Opportunity] = field(default_factory=list)

    def summary(self) -> str:
        opp = self.opportunities
        true = [o for o in opp if o.is_true]
        declined = [o for o in opp if not o.is_true]
        by = lambda k: sum(1 for e in self.events if e.kind is k)  # noqa: E731
        won = sum(1 for o in true if o.outcome == "win")
        lost = sum(1 for o in true if o.outcome == "loss")
        return (
            f"{len(self.candles)} bars, {len(self.swings)} swings; events: {by(EventKind.BOS)} BOS, "
            f"{by(EventKind.CHOCH)} CHOCH, {by(EventKind.SWEEP)} sweep, {by(EventKind.GAP_FILL)} gap fill; "
            f"opportunities: {len(true)} true ({won} won, {lost} lost in hindsight), {len(declined)} rejected"
        )


def _median(values: Sequence[float]) -> float:
    v = sorted(values)
    return v[len(v) // 2] if v else 0.0


def _body(c: Candle) -> float:
    return abs(c.close - c.open)


def label_swings(swings: Sequence[SwingPoint], strength: int) -> list[LabeledSwing]:
    """Name every swing against the previous swing of its own kind."""
    last: dict[SwingKind, SwingPoint] = {}
    out: list[LabeledSwing] = []
    for s in swings:
        prev = last.get(s.kind)
        if prev is None:
            label = "H" if s.kind is SwingKind.HIGH else "L"
        elif s.kind is SwingKind.HIGH:
            label = "HH" if s.price > prev.price else "LH"
        else:
            label = "HL" if s.price > prev.price else "LL"
        out.append(LabeledSwing(s, label, s.index + strength))
        last[s.kind] = s
    return out


def read_structure(known: Sequence[SwingPoint]) -> Structure:
    highs = [s for s in known if s.kind is SwingKind.HIGH][-2:]
    lows = [s for s in known if s.kind is SwingKind.LOW][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return Structure.RANGE
    if highs[1].price > highs[0].price and lows[1].price > lows[0].price:
        return Structure.UP
    if highs[1].price < highs[0].price and lows[1].price < lows[0].price:
        return Structure.DOWN
    return Structure.RANGE


def _merge_bands(pools: list[LiquidityPool]) -> list[LiquidityPool]:
    """Bands of the same kind that overlap are one level to the eye — circle it once."""
    merged: list[LiquidityPool] = []
    for kind in (SwingKind.LOW, SwingKind.HIGH):
        same = sorted((p for p in pools if p.kind is kind), key=lambda p: p.low)
        cur: LiquidityPool | None = None
        for p in same:
            if cur is not None and p.low <= cur.high:
                cur = LiquidityPool(
                    price=(cur.price * cur.touches + p.price * p.touches) / (cur.touches + p.touches),
                    kind=kind, touches=cur.touches + p.touches, low=min(cur.low, p.low), high=max(cur.high, p.high),
                    first_index=min(cur.first_index, p.first_index), last_index=max(cur.last_index, p.last_index),
                )
            else:
                if cur is not None:
                    merged.append(cur)
                cur = p
        if cur is not None:
            merged.append(cur)
    return merged


def read_chart(
    candles: Sequence[Candle],
    *,
    higher: Sequence[Candle] | None = None,
    strength: int = 2,
    lookback: int = 20,
    risk_reward: float = 2.0,
) -> Reading:
    """Read `candles` bar by bar. `higher` is the slower clock's candles, used only to confirm direction."""
    n = len(candles)
    reading = Reading(candles)
    if n < lookback + strength * 2 + 2:
        reading.structure = [Structure.RANGE] * n
        reading.control = [None] * n
        return reading

    all_swings = swing_points(candles, strength=strength)
    reading.swings = label_swings(all_swings, strength)
    higher_swings = swing_points(higher, strength=strength) if higher else []

    gaps_all = fair_value_gaps(candles)
    consumed: set[tuple[int, str]] = set()
    swept: set[tuple[int, str]] = set()  # one SWEEP per level until it is finally broken: a person says it once
    control: Control | None = None
    armed: list[Opportunity] = []
    level_life: dict[tuple[str, int], list] = {}

    for t in range(n):
        bar = candles[t]
        window = candles[max(0, t - lookback) : t]
        body_med = _median([_body(c) for c in window]) or 1e-12
        known = [s for s in all_swings if s.index + strength <= t]
        structure = read_structure(known)
        reading.structure.append(structure)

        # -- gaps: known one bar after the third candle forms; filled when price trades back into them
        for g in gaps_all:
            if g.formed_index + 1 == t:
                reading.gaps.append((g, None))
        for k, (g, filled) in enumerate(reading.gaps):
            if filled is None and t >= g.formed_index + 2 and bar.low <= g.upper and bar.high >= g.lower:
                reading.gaps[k] = (g, t)

        # -- levels: bands of stacked swings, alive until a close goes through the far edge
        if t >= lookback:
            band = _median([c.range for c in candles[t - lookback : t + 1]])
            live = _merge_bands(liquidity_pools(candles[: t + 1], strength=strength, band=band, min_touches=2))
            for p in live:
                died = None
                for u in range(p.last_index + 1, t + 1):
                    if (candles[u].close < p.low) if p.kind is SwingKind.LOW else (candles[u].close > p.high):
                        died = u
                        break
                # A level is one object that GROWS as the market turns at it again — not a new level each time a
                # swing joins the cluster. Match by kind and overlap with one already being tracked; only when
                # nothing matches is this a newly found level.
                match = next((k for k, rec in level_life.items() if k[0] == p.kind.value
                              and rec[0].low <= p.high and p.low <= rec[0].high), None)
                if match is not None:
                    if level_life[match][2] is None:  # a level already deleted stays deleted, however often its swings are re-found
                        level_life[match][0] = p
                        level_life[match][2] = died
                else:
                    level_life[(p.kind.value, len(level_life))] = [p, t, died]
            reading.levels = [(rec[0], rec[1], rec[2]) for rec in level_life.values()]

        # -- opportunities waiting for a retrace: dead zone, first tap, falling knife
        for opp in list(armed):
            blk = opp.block
            short = opp.direction is Direction.DOWN
            dead = bar.close > blk.price_high if short else bar.close < blk.price_low
            if dead:
                opp.state, opp.closed_at, opp.reason = State.DEAD, t, "closed through the zone's far edge before the tap — dead zone, deleted"
                armed.remove(opp)
                continue
            reached = bar.high >= opp.entry if short else bar.low <= opp.entry
            if reached and t > opp.armed_at:
                impulse = candles[opp.event.level_from : opp.armed_at + 1]
                impulse_med = _median([_body(c) for c in impulse]) or 1e-12
                if _body(bar) >= impulse_med and (bar.close < bar.open if not short else bar.close > bar.open):
                    opp.state, opp.closed_at = State.CANCELLED, t
                    opp.reason = "falling knife: the bar that reached the zone is as large as the impulse's own median body — cancel the order"
                else:
                    opp.state, opp.filled_at = State.FILLED, t
                armed.remove(opp)
        for opp in reading.opportunities:
            if opp.state is State.FILLED and opp.closed_at is None and opp.filled_at is not None and t >= opp.filled_at:
                short = opp.direction is Direction.DOWN
                hit_stop = bar.high >= opp.stop if short else bar.low <= opp.stop
                hit_tgt = opp.target is not None and (bar.low <= opp.target if short else bar.high >= opp.target)
                if hit_stop or hit_tgt:
                    opp.closed_at = t
                    opp.outcome = "loss" if hit_stop else "win"  # both in one bar: the stop, conservatively

        if t < lookback:
            reading.control.append(control)
            continue
        if control is None:
            # Control starts with the first clear structure and from then on moves ONLY on a true change of
            # character (the material's two-state machine). Swing names keep being drawn, but they no longer
            # switch the break logic off in a range — which is when most of the breaks happen.
            if structure is Structure.RANGE:
                reading.control.append(control)
                continue
            control = Control.DEMAND if structure is Structure.UP else Control.SUPPLY
        ups = control is Control.DEMAND
        highs = [s for s in known if s.kind is SwingKind.HIGH]
        lows = [s for s in known if s.kind is SwingKind.LOW]
        if not highs or not lows:
            reading.control.append(control)
            continue
        prev_close = candles[t - 1].close
        strength_x = _body(bar) / body_med

        # BOS: the trend's own extreme taken out (continuation)
        with_level = highs[-1] if ups else lows[-1]
        with_key = (with_level.index, "with")
        if with_key not in consumed:
            crossed = bar.high > with_level.price >= prev_close if ups else bar.low < with_level.price <= prev_close
            if crossed:
                closed_beyond = bar.close > with_level.price if ups else bar.close < with_level.price
                if closed_beyond:
                    consumed.add(with_key)  # only a close uses the level up; a sweep leaves it to be broken later
                    reading.events.append(Event(t, EventKind.BOS, Verdict.CONTINUATION, with_level.price, with_level.index,
                                                Direction.UP if ups else Direction.DOWN, "closed beyond the trend's last extreme", strength_x))
                elif with_key not in swept:
                    swept.add(with_key)
                    reading.events.append(Event(t, EventKind.SWEEP, Verdict.FALSE, with_level.price, with_level.index,
                                                Direction.UP if ups else Direction.DOWN,
                                                "wick through the last extreme and closed back: the stops there were taken, not the level", strength_x))

        # CHOCH: the level the trend has to hold gives way (reversal)
        against = lows[-1] if ups else highs[-1]
        key = (against.index, "against")
        if key in consumed:
            reading.control.append(control)
            continue
        crossed = bar.low < against.price <= prev_close if ups else bar.high > against.price >= prev_close
        if not crossed:
            reading.control.append(control)
            continue
        brk = Direction.DOWN if ups else Direction.UP
        result = classify_break(candles, index=t, level=against.price, direction=brk)
        if result.kind is BreakKind.LIQUIDITY_SWEEP:
            if key not in swept:
                swept.add(key)
                reading.events.append(Event(t, EventKind.SWEEP, Verdict.FALSE, against.price, against.index, brk, result.reason, strength_x))
            reading.control.append(control)
            continue
        if result.kind is BreakKind.GAP_MITIGATION:
            reading.events.append(Event(t, EventKind.GAP_FILL, Verdict.FALSE, against.price, against.index, brk, result.reason, strength_x))
            reading.control.append(control)
            continue
        if result.kind is not BreakKind.CHANGE_OF_CHARACTER:
            reading.control.append(control)
            continue

        consumed.add(key)
        event = Event(t, EventKind.CHOCH, Verdict.TRUE, against.price, against.index, brk, result.reason, strength_x)
        reading.events.append(event)
        control = control.other
        reading.control.append(control)

        # -- the opportunity this change of character leaves behind
        opp = _opportunity(candles, t, event, known, higher, higher_swings, strength, risk_reward)
        reading.opportunities.append(opp)
        if opp.state is State.ARMED:
            armed.append(opp)

    for opp in reading.opportunities:
        if opp.state is State.FILLED and opp.outcome is None:
            opp.outcome = "open"
    while len(reading.control) < n:
        reading.control.append(control)
    return reading


def _opportunity(
    candles: Sequence[Candle], t: int, event: Event, known: Sequence[SwingPoint],
    higher: Sequence[Candle] | None, higher_swings: Sequence[SwingPoint], strength: int, risk_reward: float,
) -> Opportunity:
    short = event.direction is Direction.DOWN
    same = (lambda c: c.close < c.open) if short else (lambda c: c.close > c.open)
    start = t
    while start - 1 >= 0 and same(candles[start - 1]):
        start -= 1
    origin_index = start - 1
    # the origin is the last candle of the OPPOSITE colour before the leg (all three S&D decks say so)
    while origin_index >= 0 and (candles[origin_index].close == candles[origin_index].open or same(candles[origin_index])):
        origin_index -= 1
    if origin_index < 0:
        return _declined(t, event, "the breaking leg has no origin candle to box")
    blk = order_block(candles, index=origin_index, gap_search=max(3, t - origin_index))
    blk = OrderBlock(blk.price_low, blk.price_high, origin_index, event.direction, blk.gap)
    entry = blk.price_low if short else blk.price_high
    stop = blk.price_high if short else blk.price_low
    risk = abs(stop - entry)
    if risk <= 0:
        return _declined(t, event, "the block has no width to risk", blk=blk)

    band = _median([c.range for c in candles[max(0, t - 20) : t + 1]]) or 1e-12
    pushed = pushed_distance(candles[: t + 1], block=blk, band=band)
    gaps = [g for g in fair_value_gaps(candles[: t + 1]) if origin_index <= g.formed_index <= t - 1]
    gap = next((g for g in gaps if gap_untouched(g, candles[: t + 1])), None)

    # higher timeframe must not contradict the trade
    why_not = ""
    if higher and len(higher) >= strength * 2 + 2:
        htf = read_structure(higher_swings)
        if (htf is Structure.UP and short) or (htf is Structure.DOWN and not short):
            why_not = f"against the higher timeframe, which reads {htf.value}"

    # next level with room: nearest opposing swing beyond the entry that leaves at least the floor
    want = [s for s in known if (s.kind is SwingKind.LOW if short else s.kind is SwingKind.HIGH)]
    cands = sorted({s.price for s in want if (s.price < entry if short else s.price > entry)}, reverse=short)
    target = next((p for p in cands if abs(entry - p) >= risk * risk_reward), None)
    rr = abs(entry - target) / risk if target is not None else None
    if not why_not and target is None:
        why_not = f"no room to move: no opposing level leaves {risk_reward:g}:1 from the block"
    opp = Opportunity(t, event.direction, blk, entry, stop, target, event, gap, pushed, rr)
    if why_not:
        opp.state, opp.reason = State.DECLINED, why_not
    else:
        opp.reason = (
            f"CHOCH then a block at {blk.price_low:.5f}-{blk.price_high:.5f}; limit {entry:.5f}, stop {stop:.5f}, "
            f"target {target:.5f} ({rr:.1f}:1); gap {'yes' if gap else 'no'}; pushed {pushed:.1f} bands"
        )
    return opp


def _declined(t: int, event: Event, reason: str, blk: OrderBlock | None = None) -> Opportunity:
    blk = blk or OrderBlock(0.0, 0.0, t, event.direction)
    opp = Opportunity(t, event.direction, blk, blk.price_low, blk.price_high, None, event, None, 0.0, None)
    opp.state, opp.reason = State.DECLINED, reason
    return opp
