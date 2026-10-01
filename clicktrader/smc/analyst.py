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
    "a supply/demand ZONE is the last opposite-coloured candle before a run of 3+ same-coloured candles whose bodies are at least 1.5x the median body before them (the decks' \"3+ large\"; the SOP says 4+), boxed wick to wick; valid only with a fair value gap in the run and a break of the last major swing; fresh until first tapped; dead on a close through its far edge",
    "structure is read from MAJOR swings: a leg smaller than the median leg among the recent swings is noise and its two ends are dropped (comparison, not a constant)",
    "a wick through a stacked level that closes back inside it on the same bar is a SWEEP of that level, whatever swing control is watching; several closes beyond it are a break or an undercut, not a sweep",
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
    event: Event | None
    gap: FairValueGap | None
    pushed: float
    reward_risk: float | None
    state: State = State.ARMED
    reason: str = ""
    filled_at: int | None = None
    closed_at: int | None = None
    outcome: str | None = None
    """HINDSIGHT — "win", "loss" or "open" once filled. Nothing decides on this; it is for the picture."""
    source: str = "choch"
    """"choch" (the block left by a change of character) or "zone" (a fresh true supply/demand zone)."""
    impulse_from: int | None = None
    """First bar of the impulse that made the zone/block; the falling-knife test compares the return with it."""

    @property
    def is_true(self) -> bool:
        return self.state in (State.ARMED, State.FILLED)


@dataclass
class Zone:
    """A supply or demand zone in the sense the decks and S01 use: the ORIGIN of an aggressive move.

    Not a stack of swing points. It is the last opposite-coloured candle before a displacement — a run of
    same-coloured candles far larger than the chart's own — boxed wick to wick. The decks make it valid only when
    the run left an imbalance (a fair value gap) and broke structure; it is tradeable only while **fresh** (price has
    not come back to it yet) and is deleted when a bar closes through its far edge.
    """

    direction: Direction
    """UP = demand (the run went up from it), DOWN = supply."""
    low: float
    high: float
    origin_index: int
    start: int
    end: int
    """The displacement run, `start..end` (grows while the run continues)."""
    born: int
    """The bar on which the run first qualified — when a person could first have drawn it."""
    has_gap: bool = False
    has_bos: bool = False
    aggressive: bool = True
    """The run was far larger than the chart's own candles. A run that breaks structure with ordinary-sized candles
    is the decks' "invalid: fails the aggression rule"."""
    pushed: float = 0.0
    """How far price travelled from the zone since, in typical candle ranges. Reported, never gated."""
    status: str = "fresh"
    """fresh -> used (price has come back once) -> dead (a bar closed through the far edge)."""
    tapped_at: int | None = None
    died_at: int | None = None
    knife: bool = False
    """The bar that first tapped it was itself as large as the impulse: the violent return the decks say to skip."""
    leg_anchor: int | None = None
    """The major swing (of the opposite kind) that began the move this zone formed in; zones sharing it are one leg."""
    weaker: bool = False
    """Another true zone of the same kind in the same leg is lower (demand) / higher (supply): "lowest = strongest"."""
    stacked: bool = False
    """A level that had been closed through the other way sits under it: resistance turned support (or the reverse)
    — the decks' "flip zone" / level stack, their strongest confirmation."""
    fib: str = ""
    """"" or e.g. "61.8-78.6": the zone lies in the deep discount (premium) of the leg before it, the decks' Fibonacci
    confluence. Reported as a flag; it never changes the stake."""

    @property
    def valid(self) -> bool:
        """Passed all three of the decks' rules when it formed: aggression, imbalance, break of structure."""
        return self.aggressive and self.has_gap and self.has_bos

    @property
    def verdict(self) -> str:
        """TRUE (valid and still standing), FALSE (failed a rule at birth), or BROKEN (was valid, then closed through)."""
        if not self.valid:
            return "FALSE"
        return "BROKEN" if self.status == "dead" else "TRUE"

    @property
    def kind(self) -> str:
        return "DEMAND" if self.direction is Direction.UP else "SUPPLY"

    @property
    def why_not(self) -> str:
        missing = [n for n, ok in (("not aggressive", self.aggressive), ("no imbalance", self.has_gap), ("no break of structure", self.has_bos)) if not ok]
        return ", ".join(missing)


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
    zones: list[Zone] = field(default_factory=list)
    major: set[int] = field(default_factory=set)
    """Bars whose swing was ever part of the structure the analyst read; the rest are drawn as bare dots."""

    def summary(self) -> str:
        opp = self.opportunities
        zt = [z for z in self.zones if z.verdict == 'TRUE']
        zf = [z for z in self.zones if z.verdict == 'FALSE']
        zb = [z for z in self.zones if z.verdict == 'BROKEN']
        true = [o for o in opp if o.is_true]
        declined = [o for o in opp if not o.is_true]
        by = lambda k: sum(1 for e in self.events if e.kind is k)  # noqa: E731
        won = sum(1 for o in true if o.outcome == "win")
        lost = sum(1 for o in true if o.outcome == "loss")
        return (
            f"{len(self.candles)} bars, {len(self.swings)} swings; events: {by(EventKind.BOS)} BOS, "
            f"{by(EventKind.CHOCH)} CHOCH, {by(EventKind.SWEEP)} sweep, {by(EventKind.GAP_FILL)} gap fill; "
            f"zones: {len(zt)} true ({sum(1 for z in zt if z.status == 'fresh')} fresh, {sum(1 for z in zt if z.status == 'used')} used), "
            f"{len(zf)} false, {len(zb)} broken; "
            f"opportunities: {len(true)} true ({won} won, {lost} lost in hindsight), {len(declined)} rejected"
        )


RULES_VERSION = "2026-10-01.1"
"""Bump this whenever a rule that changes which trades are taken changes. It is part of every log row's rules fingerprint, so a test's
evidence is only ever one set of rules."""


def _median(values: Sequence[float]) -> float:
    v = sorted(values)
    return v[len(v) // 2] if v else 0.0


def _body(c: Candle) -> float:
    return abs(c.close - c.open)


def _run_ending_at(candles: Sequence[Candle], t: int, *, min_candles: int, lookback: int, size_multiple: float = 1.5) -> tuple[int, int] | None:
    """The longest run of same-coloured candles ending exactly at bar `t` whose bodies, taken together, are at least
    `size_multiple` times what the same number of ordinary candles (the median body of the `lookback` bars before the
    run) would add up to — "far larger than this chart's own". Returns (start, end) or None. Checks only runs ending at
    `t`, so it is cheap enough to ask on every bar."""
    bullish = candles[t].close > candles[t].open
    if candles[t].close == candles[t].open:
        return None
    stretch = t
    while stretch - 1 >= 0 and (candles[stretch - 1].close > candles[stretch - 1].open) == bullish and candles[stretch - 1].close != candles[stretch - 1].open:
        stretch -= 1
    for length in range(min(t - stretch + 1, lookback), min_candles - 1, -1):
        start = t - length + 1
        base = candles[max(0, start - lookback) : start]
        if len(base) < 5:
            continue
        median = _median([_body(c) for c in base])
        if median <= 0:
            continue
        if sum(_body(c) for c in candles[start : t + 1]) >= size_multiple * length * median:
            return start, t
    return None


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


def major_swings(known: Sequence[SwingPoint], *, recent: int = 80) -> list[SwingPoint]:
    """The swings a person treats as structure at the scale they are looking at, out of every fractal pivot.

    On a one-minute chart almost every pause is a two-bar fractal, and a five-minute wiggle inside a rally is not
    "the low the trend has to hold" — the floor the whole leg started from is. The eye drops the wiggles by size
    *relative to the chart in view*: here, a leg smaller than the median leg among the recent swings is noise, and
    both its ends are removed (the standard zig-zag simplification), repeatedly, so what remains alternates high and
    low and every leg is at least median-sized. Nothing is a price or a percentage: "small" means "smaller than most
    of what is on this chart". Uses only swings already known, so it is as causal as they are."""
    pts = list(known[-recent:])
    zz: list[SwingPoint] = []
    for sp in pts:  # alternate kinds: two highs in a row are one swing, the higher
        if zz and zz[-1].kind is sp.kind:
            if (sp.kind is SwingKind.HIGH and sp.price > zz[-1].price) or (sp.kind is SwingKind.LOW and sp.price < zz[-1].price):
                zz[-1] = sp
        else:
            zz.append(sp)
    if len(zz) < 6:
        return zz
    thr = _median([abs(zz[i].price - zz[i - 1].price) for i in range(1, len(zz))])
    while len(zz) >= 6:
        legs = [abs(zz[i].price - zz[i - 1].price) for i in range(1, len(zz))]
        small = min(range(len(legs)), key=legs.__getitem__)
        if legs[small] >= thr or small == len(legs) - 1 or small == 0:
            break  # the ends of the chart are kept: the newest leg is the one being decided and the oldest has no other side
        del zz[small : small + 2]
    return zz


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


def read_structure_now(known: Sequence[SwingPoint], last_close: float) -> Structure:
    """`read_structure`, but a close that has already gone through the level the trend has to hold counts at once.

    Swing-based structure only changes after a new pivot is confirmed, which on a slower chart is hours: a 15-minute chart
    that has just rallied 20 points through its last lower high still "reads down" until the rally's own high is confirmed.
    A person sees the break immediately. Here a DOWN structure whose last major high has been closed above, or an UP
    structure whose last major low has been closed below, is a RANGE (changed, not yet confirmed as the opposite)."""
    base = read_structure(known)
    if base is Structure.DOWN:
        highs = [s for s in known if s.kind is SwingKind.HIGH]
        if highs and last_close > highs[-1].price:
            return Structure.RANGE
    elif base is Structure.UP:
        lows = [s for s in known if s.kind is SwingKind.LOW]
        if lows and last_close < lows[-1].price:
            return Structure.RANGE
    return base


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


def _as_clocks(higher) -> list[Sequence[Candle]]:
    """One slower clock, or a chain of them (daily -> 4H -> 1H), as a list of candle sequences."""
    if not higher:
        return []
    return [higher] if isinstance(higher[0], Candle) else [h for h in higher if h]


class _ClockView:
    """The slower clocks as they stood when bar `t` closed — only their bars that had already CLOSED by then.

    The veto asks "what does the slower chart say?"; reading history with the whole slower series would let a bar at
    08:00 see the slower chart as it looked at 12:00. Truncating by time keeps the reading causal."""

    def __init__(self, trigger: Sequence[Candle], clocks: list[Sequence[Candle]]) -> None:
        self._clocks = clocks
        self._timed = bool(trigger) and hasattr(trigger[0], "opened_at") and all(c and hasattr(c[0], "opened_at") for c in clocks)
        self._trigger_step = self._step(trigger)
        self._steps = [self._step(c) for c in clocks]
        self._ends = [[b.opened_at + st for b in c] for c, st in zip(clocks, self._steps)] if self._timed else []
        self._trigger = trigger

    @staticmethod
    def _step(series: Sequence[Candle]) -> float:
        diffs = sorted(b.opened_at - a.opened_at for a, b in zip(series, series[1:]) if hasattr(a, "opened_at"))
        return diffs[len(diffs) // 2] if diffs else 0.0

    def at(self, t: int) -> list[Sequence[Candle]]:
        if not self._timed:
            return self._clocks  # untimed candles carry no clock: nothing to truncate by
        until = self._trigger[t].opened_at + self._trigger_step
        out = []
        for series, ends in zip(self._clocks, self._ends):
            lo, hi = 0, len(ends)
            while lo < hi:  # bisect: how many slower bars had closed by `until`
                mid = (lo + hi) // 2
                if ends[mid] <= until:
                    lo = mid + 1
                else:
                    hi = mid
            out.append(series[:lo])
        return out


def _veto(clocks, short: bool, strength: int) -> str:
    """Why a trade is against the slower clocks, or "" — every clock in the chain gets a say."""
    for htf in clocks:
        if len(htf) >= strength * 2 + 2:
            reading = read_structure_now(major_swings(swing_points(htf, strength=strength)), htf[-1].close)
            if (reading is Structure.UP and short) or (reading is Structure.DOWN and not short):
                return f"against the higher timeframe, which reads {reading.value}"
    return ""


def _agrees(clocks, short: bool, strength: int) -> bool:
    """Every slower clock with enough bars has already turned the trade's way (it reads the trade's direction, not merely 'not against')."""
    want = Structure.DOWN if short else Structure.UP
    seen = False
    for htf in clocks:
        if len(htf) >= strength * 2 + 2:
            seen = True
            if read_structure_now(major_swings(swing_points(htf, strength=strength)), htf[-1].close) is not want:
                return False
    return seen


def read_chart(
    candles: Sequence[Candle],
    *,
    higher: Sequence[Candle] | Sequence[Sequence[Candle]] | None = None,
    strength: int = 2,
    lookback: int = 20,
    risk_reward: float = 2.0,
    zone_min_candles: int = 2,
    stale_bars: int | None = None,
    counter_trend: bool = False,
    stop_buffer: float = 0.0,
    strict_choch: bool = False,
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
    all_clocks = _as_clocks(higher)
    view = _ClockView(candles, all_clocks)

    gaps_all = fair_value_gaps(candles)
    major_ever: set[int] = set()
    consumed: set[tuple[int, str]] = set()
    swept: set[tuple[int, str]] = set()  # one SWEEP per level until it is finally broken: a person says it once
    control: Control | None = None
    armed: list[Opportunity] = []
    level_life: dict[tuple[str, int], list] = {}
    zone_by_start: dict[int, Zone] = {}
    zone_opps: dict[int, Opportunity] = {}

    for t in range(n):
        bar = candles[t]
        window = candles[max(0, t - lookback) : t]
        body_med = _median([_body(c) for c in window]) or 1e-12
        minor = [s for s in all_swings if s.index + strength <= t]
        known = major_swings(minor)
        major_ever.update(s.index for s in known)
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
                same = [k for k, rec in level_life.items() if k[0] == p.kind.value and rec[0].low <= p.high and p.low <= rec[0].high]
                alive = next((k for k in same if level_life[k][2] is None), None)
                if alive is not None:
                    level_life[alive][0], level_life[alive][2] = p, died
                elif any(p.last_index <= level_life[k][2] for k in same):
                    continue  # the swings of a level already deleted, found again: it stays deleted
                else:
                    # the market has turned at this price again AFTER the old level was closed through: a new level
                    level_life[(p.kind.value, len(level_life))] = [p, t, died]
            reading.levels = [(rec[0], rec[1], rec[2]) for rec in level_life.values()]

            # A wick under (over) a stacked level that closes back is the stops being taken, whichever swing the
            # control machinery happens to be watching: "wick below the level, rapid recovery". The level held.
            for rec in level_life.values():
                p0 = rec[0]
                if rec[2] is not None or p0.touches < 2 or t <= p0.last_index + 1:
                    continue
                prev = candles[t - 1]
                low_side = p0.kind is SwingKind.LOW
                pierced = bar.low < p0.low and bar.close >= p0.low and prev.low >= p0.low if low_side else bar.high > p0.high and bar.close <= p0.high and prev.high <= p0.high
                if pierced and not any(e.index == t and e.kind is EventKind.SWEEP for e in reading.events):
                    reading.events.append(Event(
                        t, EventKind.SWEEP, Verdict.FALSE, p0.low if low_side else p0.high, p0.first_index,
                        Direction.DOWN if low_side else Direction.UP,
                        f"wick through a level the market had turned at {p0.touches} times and closed back: the stops were taken, the level held",
                        _body(bar) / body_med,
                    ))

        # -- supply / demand zones: the ORIGIN of an aggressive move, not a stack of swings
        if t >= lookback:
            run = _run_ending_at(candles, t, min_candles=zone_min_candles, lookback=lookback)
            aggressive = run is not None
            if run is None:
                run = _run_ending_at(candles, t, min_candles=zone_min_candles, lookback=lookback, size_multiple=0.0)
            if run is not None:
                st, en = run
                up = candles[t].close > candles[t].open
                o = st - 1
                while o >= 0 and (candles[o].close == candles[o].open or ((candles[o].close > candles[o].open) == up)):
                    o -= 1
                if o >= 0:
                    want = Direction.UP if up else Direction.DOWN
                    has_gap = any(g.direction is want and st <= g.formed_index <= en - 1 for g in fair_value_gaps(candles[: en + 1], from_index=st))
                    prior = major_swings([sw for sw in all_swings if sw.index + strength <= st])
                    ref = [sw for sw in prior if sw.kind is (SwingKind.HIGH if up else SwingKind.LOW)][-1:]
                    has_bos = bool(ref) and any((c.high > ref[0].price) if up else (c.low < ref[0].price) for c in candles[st : en + 1])
                    z = zone_by_start.get(st) or zone_by_start.get(("origin", o))  # one zone per origin candle, however many runs grew from it
                    # An aggressive run is always a candidate. An ordinary-sized one only when it still breaks structure —
                    # the decks' "invalid: fails the aggression rule" — otherwise it is just noise and is not a zone at all.
                    if z is None and (aggressive or has_bos):
                        origin = candles[o]
                        z = Zone(Direction.UP if up else Direction.DOWN, origin.low, origin.high, o, st, en, t, aggressive=aggressive)
                        zone_by_start[st] = z
                        zone_by_start[("origin", o)] = z
                        reading.zones.append(z)
                    if z is not None:
                        z.end = max(z.end, en)
                        z.has_gap, z.has_bos = z.has_gap or has_gap, z.has_bos or has_bos
                        z.aggressive = z.aggressive or aggressive  # once the growing run is far larger than ordinary, it stays so
        rng = _median([c.range for c in candles[max(0, t - lookback) : t + 1]]) or 1e-12
        for z in reading.zones:
            if z.status == "dead" or t <= z.end:
                continue
            demand = z.direction is Direction.UP
            z.pushed = ((max(c.high for c in candles[z.origin_index : t + 1]) - z.high) if demand else (z.low - min(c.low for c in candles[z.origin_index : t + 1]))) / rng
            if (bar.close < z.low) if demand else (bar.close > z.high):
                z.status, z.died_at = "dead", t
            elif z.status == "fresh" and bar.low <= z.high and bar.high >= z.low:
                z.status, z.tapped_at = "used", t
                impulse = _median([_body(c) for c in candles[z.start : z.end + 1]]) or 1e-12
                z.knife = _body(bar) >= impulse and ((bar.close < bar.open) if demand else (bar.close > bar.open))

        # -- once a zone's run has ended: which leg it belongs to, whether it is a flip zone, where it sits on the Fibonacci
        for z in reading.zones:
            if t != z.end + 1:
                continue
            demand = z.direction is Direction.UP
            prior = major_swings([sw for sw in all_swings if sw.index + strength <= z.start])
            top_kind, bottom_kind = (SwingKind.HIGH, SwingKind.LOW) if demand else (SwingKind.LOW, SwingKind.HIGH)
            anchors = [sw for sw in prior if sw.kind is top_kind]
            z.leg_anchor = anchors[-1].index if anchors else -1
            # flip zone: a level closed through the OTHER way before this zone formed sits under it
            for band, _born, died in reading.levels:
                if died is not None and died <= z.start and band.kind is (SwingKind.HIGH if demand else SwingKind.LOW) and band.low <= z.high and z.low <= band.high:
                    z.stacked = True
            # Fibonacci: the zone inside the 61.8-78.6 retracement of the leg before it (the decks' "deep discount")
            if anchors:
                far = [sw for sw in prior if sw.kind is bottom_kind and sw.index < anchors[-1].index][-1:]
                if far:
                    lo_f, hi_f = fib_zone(anchors[-1].price, far[0].price, demand=demand) if demand else fib_zone(far[0].price, anchors[-1].price, demand=False)
                    if z.low <= hi_f and lo_f <= z.high:
                        z.fib = "61.8-78.6"
        _mark_weaker(reading.zones)

        # -- a fresh true zone is itself an opportunity — judged EVERY bar until it is tapped or dies, not once at birth.
        # A person leaves a limit order at a fresh zone and re-judges it as the trend and the slower clocks change: a zone
        # that could not be traded when it formed (against the trend, no room yet, a weaker neighbour) can become tradeable
        # an hour later, and an order that stops qualifying is withdrawn.
        for z in reading.zones:
            if not z.valid or z.status != "fresh" or t <= z.end:
                continue
            standing = zone_opps.get(id(z))
            now_opp = _zone_opportunity(candles, t, z, known, view.at(t), strength, risk_reward, control, structure, counter_trend, stop_buffer)
            if standing is not None:
                if standing.state is State.ARMED and now_opp.state is State.DECLINED:
                    standing.state, standing.closed_at = State.CANCELLED, t
                    standing.reason = f"withdrawn: {now_opp.reason}"
                    if standing in armed:
                        armed.remove(standing)
                continue
            if now_opp.state is State.ARMED:
                reading.opportunities.append(now_opp)
                zone_opps[id(z)] = now_opp
                armed.append(now_opp)
            elif t == z.end + 1:
                reading.opportunities.append(now_opp)  # the decision at birth is recorded once, so the picture can say why

        # -- opportunities waiting for a retrace: dead zone, first tap, falling knife
        for opp in list(armed):
            blk = opp.block
            short = opp.direction is Direction.DOWN
            if stale_bars is not None and t - opp.armed_at >= stale_bars:
                opp.state, opp.closed_at = State.CANCELLED, t
                opp.reason = f"stale: the order stood {t - opp.armed_at} bars without price coming back to it — the chart has moved on"
                armed.remove(opp)
                continue
            dead = bar.close > blk.price_high if short else bar.close < blk.price_low
            if dead:
                opp.state, opp.closed_at, opp.reason = State.DEAD, t, "closed through the zone's far edge before the tap — dead zone, deleted"
                armed.remove(opp)
                continue
            reached = bar.high >= opp.entry if short else bar.low <= opp.entry
            if reached and t > opp.armed_at:
                impulse = candles[(opp.impulse_from if opp.impulse_from is not None else opp.event.level_from) : opp.armed_at + 1]
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
        # The material's last invalidator: a visible stop cluster to the left. If the level being broken sits INSIDE a
        # stacked level and the close has not left that stack, the stops under it were taken — the level held.
        cluster = next((rec[0] for rec in level_life.values() if rec[2] is None and rec[0].touches >= 2
                        and rec[0].kind is (SwingKind.LOW if ups else SwingKind.HIGH) and rec[0].low <= against.price <= rec[0].high), None)
        if cluster is not None and ((bar.close >= cluster.low) if ups else (bar.close <= cluster.high)):
            if key not in swept:
                swept.add(key)
                reading.events.append(Event(
                    t, EventKind.SWEEP, Verdict.FALSE, against.price, against.index, brk,
                    f"the level sits inside a stack the market had turned at {cluster.touches} times and the close did not leave it: the stops were taken, not a reversal",
                    strength_x,
                ))
            reading.control.append(control)
            continue

        consumed.add(key)
        event = Event(t, EventKind.CHOCH, Verdict.TRUE, against.price, against.index, brk, result.reason, strength_x)
        reading.events.append(event)
        control = control.other
        reading.control.append(control)

        # -- the opportunity this change of character leaves behind
        opp = _opportunity(candles, t, event, known, view.at(t), strength, risk_reward, stop_buffer, strict_choch)
        reading.opportunities.append(opp)
        if opp.state is State.ARMED:
            armed.append(opp)

    reading.major = major_ever
    for opp in reading.opportunities:
        if opp.state is State.FILLED and opp.outcome is None:
            opp.outcome = "open"
    while len(reading.control) < n:
        reading.control.append(control)
    return reading


def _opportunity(
    candles: Sequence[Candle], t: int, event: Event, known: Sequence[SwingPoint],
    clocks, strength: int, risk_reward: float, stop_buffer: float = 0.0, strict_choch: bool = False,
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
    band = _median([c.range for c in candles[max(0, t - 20) : t + 1]]) or 1e-12
    stop = (blk.price_high + stop_buffer * band) if short else (blk.price_low - stop_buffer * band)  # just outside the far edge, not on it
    risk = abs(stop - entry)
    if risk <= 0:
        return _declined(t, event, "the block has no width to risk", blk=blk)

    pushed = pushed_distance(candles[: t + 1], block=blk, band=band)
    gaps = [g for g in fair_value_gaps(candles[: t + 1]) if origin_index <= g.formed_index <= t - 1]
    gap = next((g for g in gaps if gap_untouched(g, candles[: t + 1])), None)

    # the slower clock(s) must not contradict the trade
    why_not = _veto(clocks, short, strength)
    if not why_not and strict_choch and clocks and not _agrees(clocks, short, strength):
        why_not = "the slower chart has not turned yet: one fast chart changing direction is not enough to trade against the bigger move"

    # next level with room: nearest opposing swing beyond the entry that leaves at least the floor
    want = [s for s in known if (s.kind is SwingKind.LOW if short else s.kind is SwingKind.HIGH)]
    cands = sorted({s.price for s in want if (s.price < entry if short else s.price > entry)}, reverse=short)
    target = next((p for p in cands if abs(entry - p) >= risk * risk_reward), None)
    rr = abs(entry - target) / risk if target is not None else None
    if not why_not and target is None:
        why_not = f"no room to move: no opposing level leaves {risk_reward:g}:1 from the block"
    opp = Opportunity(t, event.direction, blk, entry, stop, target, event, gap, pushed, rr, impulse_from=event.level_from)
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


def _mark_weaker(zones: Sequence[Zone]) -> None:
    """"Lowest = strongest": among the true zones of one kind formed in one leg, only the lowest demand (highest supply)
    keeps the deepest liquidity; every other one is marked `weaker` and is not traded."""
    groups: dict[tuple[str, int], list[Zone]] = {}
    for z in zones:
        if z.verdict == "TRUE" and z.leg_anchor is not None:
            groups.setdefault((z.kind, z.leg_anchor), []).append(z)
    for (kind, _anchor), members in groups.items():
        best = min(members, key=lambda q: q.low) if kind == "DEMAND" else max(members, key=lambda q: q.high)
        for q in members:
            q.weaker = q is not best


def fib_zone(top: float, bottom: float, *, demand: bool) -> tuple[float, float]:
    """The 61.8%-78.6% retracement band of the leg from `bottom` to `top`: for demand it is measured down from the
    top, for supply up from the bottom. The decks' "deep discount" / premium where a zone has the most confluence."""
    span = abs(top - bottom)
    a, b = (top - 0.618 * span, top - 0.786 * span) if demand else (bottom + 0.618 * span, bottom + 0.786 * span)
    return (min(a, b), max(a, b))


def _zone_opportunity(
    candles: Sequence[Candle], t: int, z: Zone, known: Sequence[SwingPoint], clocks, strength: int, risk_reward: float,
    control: Control | None, structure: Structure, counter_trend: bool = False, stop_buffer: float = 0.0,
) -> Opportunity:
    """The trade a fresh, true zone offers, or the reason it is not taken.

    The decks' rules, in their order: trade only with the trend ("if in an uptrend, only look for demand zones"),
    take the lowest demand / highest supply of a leg, never against the slower clock, limit at the zone's near edge,
    stop just outside its far edge, target the nearest opposing level that leaves the 1:2 floor. Fibonacci and a flip
    zone are reported on the opportunity as conviction; they never change the stake."""
    short = z.direction is Direction.DOWN
    blk = OrderBlock(z.low, z.high, z.origin_index, z.direction)
    entry = z.low if short else z.high
    band = _median([c.range for c in candles[max(0, t - 20) : t + 1]]) or 1e-12
    stop = (z.high + stop_buffer * band) if short else (z.low - stop_buffer * band)  # just outside the far edge, not on it
    risk = abs(stop - entry)
    with_trend = (control is Control.DEMAND and not short) or (control is Control.SUPPLY and short) if control is not None else (
        (structure is Structure.UP and not short) or (structure is Structure.DOWN and short)
    )
    why_not = ""
    # Against the trend, but at a zone the decks call their strongest (Fibonacci 61.8-78.6 or a flip zone): where a run is
    # sold or bought after it has gone far. A person takes that trade (the supply above a long rally); the decks' "only with
    # the trend" rule refuses it. Optional, because it is a judgement the decks do not make; the slower-clock veto does not
    # apply to it, since it is counter-trend by definition.
    counter = counter_trend and not with_trend and bool(z.fib or z.stacked)
    if not with_trend and not counter:
        up = control is Control.DEMAND or (control is None and structure is Structure.UP)
        down = control is Control.SUPPLY or (control is None and structure is Structure.DOWN)
        state = "an up-trend (the decks only look for demand)" if up else "a down-trend (the decks only look for supply)" if down else "no established trend yet"
        why_not = f"against the trend: it is {state}, and this is a {z.kind.lower()} zone"
    elif z.weaker:
        why_not = f"a weaker zone: another {z.kind.lower()} zone in the same leg is {'lower' if not short else 'higher'} and holds the deeper liquidity"
    elif risk <= 0:
        why_not = "the zone has no width to risk"
    if not why_not and not counter:
        why_not = _veto(clocks, short, strength)
    want = [sw for sw in known if (sw.kind is SwingKind.LOW if short else sw.kind is SwingKind.HIGH)]
    cands = sorted({sw.price for sw in want if (sw.price < entry if short else sw.price > entry)}, reverse=short)
    target = next((q for q in cands if risk > 0 and abs(entry - q) >= risk * risk_reward), None)
    rr = abs(entry - target) / risk if (target is not None and risk > 0) else None
    if not why_not and target is None:
        why_not = f"no room to move: no opposing level leaves {risk_reward:g}:1 from the zone"
    opp = Opportunity(t, z.direction, blk, entry, stop, target, None, None, z.pushed, rr, source="zone", impulse_from=z.start)
    if why_not:
        opp.state, opp.reason = State.DECLINED, why_not
    else:
        extras = ", ".join(x for x in (("counter-trend at a " + ("premium" if short else "discount") + " zone" if counter else ""),
                                       ("flip zone" if z.stacked else ""), (f"Fibonacci {z.fib}" if z.fib else "")) if x)
        opp.reason = (
            f"fresh {z.kind.lower()} zone {z.low:.5f}-{z.high:.5f}; limit {entry:.5f}, stop {stop:.5f}, target {target:.5f} "
            f"({rr:.1f}:1)" + (f"; conviction: {extras}" if extras else "")
        )
    return opp
