"""Market structure: swings, breaks, imbalance and displacement — the vocabulary a checklist written
against a chart is actually in.

Nothing here decides anything. These are the measurements a discretionary method reads off a chart:
where the swing points are, whether a push broke structure, whether three candles left an untraded gap
behind them, whether a run of candles is large enough to be called displacement. Each is a pure function
of the bars it is given, and every threshold is an argument rather than a constant buried in the body —
so a definition can be varied and measured instead of assumed, and two people reading a checklist the
same way can still disagree about "massive" without that disagreement being invisible in the code.

`swing_points` deliberately takes plain `Candle`s, so these work on wall-clock bars from
`TimeCandleBuilder` and on tick-count bars from `CandleBuilder` alike.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .candles import Candle
from .model import Direction


class SwingKind(str, Enum):
    HIGH = "high"
    LOW = "low"


class Trend(str, Enum):
    UP = "up"
    DOWN = "down"
    RANGE = "range"


@dataclass(frozen=True)
class SwingPoint:
    """A fractal pivot: a bar whose high (or low) stands above (or below) its neighbours'."""

    index: int
    price: float
    kind: SwingKind

    def __str__(self) -> str:
        return f"{self.kind.value}@[{self.index}]={self.price:.5f}"


@dataclass(frozen=True)
class FairValueGap:
    """An untraded range between two candles that a displacement bar in between left behind.

    The definition is the strict one — *no* wick overlap, which is what makes it an imbalance rather
    than a gap: for a bullish gap, the third candle's low sits entirely above the first candle's high,
    so the range between them was only ever traversed in one direction, in one move.
    """

    direction: Direction
    lower: float
    upper: float
    formed_index: int

    @property
    def size(self) -> float:
        return self.upper - self.lower

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper


@dataclass(frozen=True)
class Displacement:
    """A run of same-direction candles large enough to be read as an aggressive, not a drifting, move."""

    direction: Direction
    start_index: int
    end_index: int
    baseline_body: float

    @property
    def candles(self) -> int:
        return self.end_index - self.start_index + 1


def swing_points(candles: Sequence[Candle], *, strength: int = 2) -> list[SwingPoint]:
    """Every fractal pivot in `candles`: a bar whose high is strictly above the `strength` bars on each
    side, and separately whose low is strictly below them.

    Strictly, so a flat top is not a structure point — two equal highs are one level the market failed
    to clear, not a swing. A bar that is both a high and a low (an outside bar spanning its neighbours)
    yields both, which is what it is. The first and last `strength` bars can never qualify, so the list
    lags the tape by that much; that is inherent to looking at either side, not a shortcut.
    """
    if strength < 1:
        raise ValueError("strength must be at least 1")
    out: list[SwingPoint] = []
    for i in range(strength, len(candles) - strength):
        window = candles[i - strength : i + strength + 1]
        bar = candles[i]
        if all(bar.high > c.high for c in window if c is not bar):
            out.append(SwingPoint(index=i, price=bar.high, kind=SwingKind.HIGH))
        if all(bar.low < c.low for c in window if c is not bar):
            out.append(SwingPoint(index=i, price=bar.low, kind=SwingKind.LOW))
    return out


def last_swing(swings: Sequence[SwingPoint], kind: SwingKind, *, before_index: int | None = None) -> SwingPoint | None:
    """The most recent swing of `kind`, optionally one formed strictly before `before_index`."""
    for swing in reversed(swings):
        if swing.kind is kind and (before_index is None or swing.index < before_index):
            return swing
    return None


def trend_sequence(swings: Sequence[SwingPoint], *, steps: int = 3) -> Trend:
    """The 1-2-3 reading: up when the last `steps` swing highs each exceed the one before *and* the same
    holds for the swing lows; down when both are descending; otherwise `RANGE`.

    Both legs have to agree, which is the point of the sequence: one rising series of highs with flat
    or falling lows is a range with a widening top, not a trend. Fewer than `steps` of either means
    `RANGE` too — "not established" and "no trend" are the same answer for a checklist that only trades
    with the trend, and a method that wants to treat them differently can count the swings itself.
    """
    if steps < 1:
        raise ValueError("steps must be at least 1")
    highs = [s for s in swings if s.kind is SwingKind.HIGH][-steps:]
    lows = [s for s in swings if s.kind is SwingKind.LOW][-steps:]
    if len(highs) < steps or len(lows) < steps:
        return Trend.RANGE
    rising = all(b.price > a.price for a, b in zip(highs, highs[1:])) and all(
        b.price > a.price for a, b in zip(lows, lows[1:])
    )
    falling = all(b.price < a.price for a, b in zip(highs, highs[1:])) and all(
        b.price < a.price for a, b in zip(lows, lows[1:])
    )
    if rising:
        return Trend.UP
    if falling:
        return Trend.DOWN
    return Trend.RANGE


def broke_structure(
    move: Sequence[Candle], prior_swings: Sequence[SwingPoint], *, direction: Direction
) -> bool:
    """Did the candles in `move` trade beyond the last opposing swing that stood before it?

    An upward push breaks structure by exceeding the most recent swing *high*; a downward one by
    undercutting the most recent swing low. `prior_swings` is the caller's responsibility to have
    filtered to those formed before the move started — passing later swings in would let the move
    "break" a level it created itself.
    """
    if direction is Direction.UP:
        level = last_swing(prior_swings, SwingKind.HIGH)
        return level is not None and any(c.high > level.price for c in move)
    level = last_swing(prior_swings, SwingKind.LOW)
    return level is not None and any(c.low < level.price for c in move)


def fair_value_gaps(
    candles: Sequence[Candle], *, from_index: int = 1, to_index: int | None = None
) -> list[FairValueGap]:
    """Every three-candle imbalance in the range, oldest first.

    The middle candle is the displacement that created it; the gap is between the candles either side of
    that one, which is why a gap always spans exactly three: two of them to define the untraded range
    and one to have crossed it.
    """
    out: list[FairValueGap] = []
    last = len(candles) - 1 if to_index is None else to_index
    for i in range(max(1, from_index), min(last, len(candles) - 1)):
        first, third = candles[i - 1], candles[i + 1]
        if third.low > first.high:
            out.append(FairValueGap(Direction.UP, lower=first.high, upper=third.low, formed_index=i))
        elif third.high < first.low:
            out.append(FairValueGap(Direction.DOWN, lower=third.high, upper=first.low, formed_index=i))
    return out


def gap_untouched(gap: FairValueGap, candles: Sequence[Candle], *, from_index: int | None = None) -> bool:
    """Has price come back into this gap since it formed? Untouched is what makes an imbalance usable —
    a gap already revisited is a level the market has been to, not one it has left behind."""
    start = gap.formed_index + 2 if from_index is None else from_index
    for candle in candles[start:]:
        if candle.low <= gap.upper and candle.high >= gap.lower:
            return False
    return True


def target_gap(
    gaps: Sequence[FairValueGap], candles: Sequence[Candle], *, direction: Direction, price: float,
    prefer: str = "largest",
) -> FairValueGap | None:
    """An imbalance *ahead* of `price`, untouched, on the side the trade is heading for — the measurable
    form of "take profit at the next major zone on the opposite side".

    Ahead means the whole gap sits beyond `price` in the trade's direction, so a target already partly
    behind the entry is not a target. Opposing means the gap was left by a move *against* the trade,
    which is what a supply zone is to a long: an untraded range above, created by sellers.

    `prefer` is the reading of "major", and it matters more than it sounds. `"largest"` (the default)
    takes the biggest untouched gap ahead, which is the source's own wording — "the biggest seller
    block", "the next major zone". `"nearest"` takes the closest, which is the more literal reading of
    "next" and is a trap: the move into a zone usually leaves a small imbalance just ahead of the entry,
    so the nearest gap is often a trivial one created by the approach itself, giving a target a fraction
    of the risk. That is a property of the rule, not of the market, and it would be measured as if it
    were the method's — which is why it is a named parameter with the source's wording as the default.

    Returns None when there is none, which a caller should treat as "no target" rather than inventing
    one: a method whose exits are defined by the next zone has no trade where there is no zone.
    """
    if prefer not in ("largest", "nearest"):
        raise ValueError("prefer must be 'largest' or 'nearest'")
    candidates = [g for g in gaps if gap_untouched(g, candles)]
    if direction is Direction.UP:
        candidates = [g for g in candidates if g.direction is Direction.DOWN and g.lower > price]
    else:
        candidates = [g for g in candidates if g.direction is Direction.UP and g.upper < price]
    if not candidates:
        return None
    if prefer == "largest":
        return max(candidates, key=lambda g: g.size)
    if direction is Direction.UP:
        return min(candidates, key=lambda g: g.lower)
    return max(candidates, key=lambda g: g.upper)


def displacement(
    candles: Sequence[Candle],
    *,
    min_candles: int = 4,
    size_multiple: float = 1.5,
    lookback: int = 20,
    size_mode: str = "run",
    last_index: int | None = None,
) -> Displacement | None:
    """The most recent run of at least `min_candles` consecutive same-direction candles whose bodies are
    each at least `size_multiple` times the median body of the `lookback` candles before the run.

    The baseline is measured *before* the run and excluding it, which matters: including the run would
    let four huge candles raise the very average they are being compared against, and the bigger the move
    the harder it would be to qualify — the wrong way round.

    `size_mode` is the reading of "massive", and it decides whether a method fires at all:

    - `"run"` (the default) requires the run as a whole to have displaced that much — the bodies summed,
      against the same multiple of an ordinary run of the same length.
    - `"each"` requires *every* candle in the run to be large on its own. It is the stricter reading and
      it is offered, but it is not the default because it does not fire at all on real bars: over 72
      real 15-minute EUR/USD bars the longest same-direction stretch was four candles and none had four
      large bodies in a row (`0.00079, 0.00032, 0.00013, 0.00054` against a 0.000185 median). Four
      consecutive *uniformly* large candles is a much rarer shape than one big candle among small ones,
      so a checklist saying "4+ massive candles" most likely means the move, not each bar. A default
      that never fires would report "no setups" for a reason that is about this reading and not about
      the method, which is the failure mode worth avoiding.

    With the aggregate reading the longest qualifying window wins, which on real data means the run can
    extend back through ordinary same-coloured candles before the large ones. That is deliberate rather
    than sloppy: the SOP draws the zone on "the preceding opposite-coloured candle", so the run has to
    start where the move actually started, not at its biggest candle. It does mean the run and the zone
    both depend on the reading, which is one more reason both are parameters.

    Windows are searched within the longest same-direction stretch ending at each bar, longest first,
    rather than taking that stretch as the run. Two small candles of the same colour in front of four
    large ones are a run of four, not a run of six that fails — treating the stretch as the unit is how
    a real displacement gets missed because of what happened before it.

    `None` means no run qualified, including when there is not enough history to compute a baseline at
    all. That is a "not yet", not a "no": a checklist that gates on displacement should wait.
    """
    if min_candles < 2:
        raise ValueError("min_candles must be at least 2 — a single large candle is not a run")
    if lookback < 5:
        raise ValueError("lookback must be at least 5 candles to give the median anything to stand on")
    last = len(candles) - 1 if last_index is None else last_index
    if last >= len(candles):
        raise ValueError("last_index is past the end of the series")

    for end in range(last, min_candles - 1, -1):
        bullish = candles[end].bullish
        stretch_start = end
        while stretch_start - 1 >= 0 and candles[stretch_start - 1].bullish == bullish:
            stretch_start -= 1
        longest = min(end - stretch_start + 1, lookback)
        for length in range(longest, min_candles - 1, -1):
            start = end - length + 1
            baseline_slice = candles[max(0, start - lookback) : start]
            if len(baseline_slice) < 5:
                continue
            bodies = sorted(c.body for c in baseline_slice)
            baseline = bodies[len(bodies) // 2]
            if baseline <= 0:
                continue
            run = candles[start : end + 1]
            if size_mode == "each":
                big = all(c.body >= size_multiple * baseline for c in run)
            elif size_mode == "run":
                big = sum(c.body for c in run) >= size_multiple * len(run) * baseline
            else:
                raise ValueError("size_mode must be 'each' or 'run'")
            if big:
                return Displacement(
                    direction=Direction.UP if bullish else Direction.DOWN,
                    start_index=start,
                    end_index=end,
                    baseline_body=baseline,
                )
    return None


def approach_speed(candles: Sequence[Candle], *, bars: int, lookback: int) -> float:
    """How fast the last `bars` candles have moved, relative to the median body over `lookback` before
    them — the measurable form of "is this a parabolic crash into the level".

    Returns 0.0 when there is not enough history to say, which a caller gating on a falling knife should
    treat as "no objection" rather than "no approach": refusing to trade for want of a baseline would be
    a silent extra rule.
    """
    if bars < 1:
        raise ValueError("bars must be at least 1")
    recent = candles[-bars:]
    baseline_slice = candles[max(0, len(candles) - bars - lookback) : len(candles) - bars]
    if len(baseline_slice) < 5:
        return 0.0
    bodies = sorted(c.body for c in baseline_slice)
    baseline = bodies[len(bodies) // 2]
    if baseline <= 0:
        return 0.0
    return (sum(c.body for c in recent) / len(recent)) / baseline


def zone_invalidated(zone: Zone, candles: Sequence[Candle], *, from_index: int | None = None) -> bool:
    """Has a candle *closed* beyond the zone's far boundary?

    "If a candle closes outside the boundary, the institutional volume is exhausted — delete the zone
    from your chart immediately." A close, not a wick: a wick through the level is the market probing it,
    which is what the zone is for; a close through it means the orders that made the level are gone.

    The far boundary is the zone's *outer* edge — its low for demand, its high for supply. Price leaving
    a demand zone upward through its upper edge is just the trade working.
    """
    start = zone.origin_index + 1 if from_index is None else from_index
    if zone.direction is Direction.UP:
        return any(c.close < zone.lower for c in candles[start:])
    return any(c.close > zone.upper for c in candles[start:])


def structure_target(
    swings: Sequence[SwingPoint], *, direction: Direction, price: float
) -> float | None:
    """The recent extreme price action is heading back to — the take-profit the worked example draws.

    For a long that is the *most recent* swing high above the entry; for a short the most recent swing
    low below it. "Most recent" rather than "highest", and the difference is not cosmetic: taking the
    highest swing in the window picks up whatever peak the recording happens to contain hundreds of bars
    back, which on the test chart turned a sensible target into a 21R one that price would essentially
    never reach — trades that never resolve instead of trades that win or lose. The deck's own example
    draws the level at the top of the leg the zone came from, which after a pullback of lower highs *is*
    the most recent high above the entry.

    It is a level the market has already turned at, not a projection and not a gap: an earlier version of
    this project aimed at the nearest untouched imbalance, which is a rule nothing states.

    `None` when there is no swing beyond the entry, which a caller should read as "no target" rather
    than inventing one.
    """
    if direction is Direction.UP:
        above = [s.price for s in swings if s.kind is SwingKind.HIGH and s.price > price]
        return above[-1] if above else None
    below = [s.price for s in swings if s.kind is SwingKind.LOW and s.price < price]
    return below[-1] if below else None


@dataclass(frozen=True)
class KeyZone:
    """A horizontal level the market has already turned at more than once.

    "Key Zone (Ceiling)" and "Key Zone (Floor)" in the source's own diagram, defined there as a level
    with *past rejections* — which is what separates a zone from a swing point: one turn is a pivot, and
    the second turn at the same price is the market remembering it.
    """

    price: float
    touches: int
    kind: SwingKind

    @property
    def is_ceiling(self) -> bool:
        return self.kind is SwingKind.HIGH

    def within(self, price: float, tolerance: float) -> bool:
        """Is `price` close enough to count as being at this level? `tolerance` is a fraction."""
        return abs(price - self.price) <= tolerance * self.price


def key_zones(
    candles: Sequence[Candle], *, strength: int = 2, tolerance: float = 0.002, min_touches: int = 2
) -> list[KeyZone]:
    """Levels built by clustering swing points that sit within `tolerance` of each other.

    Relative rather than absolute distance, so one rule works on a 1.13 forex pair and a 4,100 gold
    quote without being re-tuned. Clustering is greedy over sorted prices, which is enough for levels a
    human would circle with a line and is stable between bars — an over-engineered clusterer would move
    the level slightly every bar and make the strategy's decisions flicker.
    """
    if min_touches < 2:
        raise ValueError("min_touches must be at least 2 — a single swing is a pivot, not a key zone")
    by_kind: dict[SwingKind, list[SwingPoint]] = {SwingKind.HIGH: [], SwingKind.LOW: []}
    for swing in swing_points(candles, strength=strength):
        by_kind[swing.kind].append(swing)

    zones: list[KeyZone] = []
    for kind, swings in by_kind.items():
        cluster: list[SwingPoint] = []
        for swing in sorted(swings, key=lambda s: s.price):
            if cluster and not (abs(swing.price - cluster[-1].price) <= tolerance * cluster[-1].price * 4):
                if len(cluster) >= min_touches:
                    zones.append(KeyZone(sum(s.price for s in cluster) / len(cluster), len(cluster), kind))
                cluster = []
            cluster.append(swing)
        if len(cluster) >= min_touches:
            zones.append(KeyZone(sum(s.price for s in cluster) / len(cluster), len(cluster), kind))
    return sorted(zones, key=lambda z: z.price)


def is_momentum_candle(
    candle: Candle, *, baseline_body: float, size_multiple: float = 1.5, body_ratio: float = 0.6
) -> bool:
    """A large body with negligible wicks — the source's "clear directional power".

    Both conditions, because neither alone is the thing being described: a big candle full of wicks is a
    fight rather than a move, and a tiny candle with no wicks is nothing at all. The source's own
    contrast is a doji ("indecision — do not execute") against an oversized body, so the test is size
    *relative to recent candles* and shape *relative to its own range*.
    """
    if candle.range <= 0 or baseline_body <= 0:
        return False
    return candle.body >= size_multiple * baseline_body and (candle.body / candle.range) >= body_ratio


@dataclass(frozen=True)
class Zone:
    """A supply or demand zone, drawn wick to wick on one candle.

    `lower`/`upper` are that candle's low and high — the whole candle, wicks included, which is what
    "strictly wick-to-wick" pins down. `origin_index` is the candle it was drawn on, so a caller can ask
    how many times price has been back since.
    """

    direction: Direction
    lower: float
    upper: float
    origin_index: int

    @property
    def size(self) -> float:
        return self.upper - self.lower

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper


def zone_from_origin(candle: Candle, *, index: int, direction: Direction) -> Zone:
    """Draw the zone wick-to-wick on one candle."""
    return Zone(direction=direction, lower=candle.low, upper=candle.high, origin_index=index)


def taps(zone: Zone, candles: Sequence[Candle], *, from_index: int | None = None) -> int:
    """How many candles have traded into the zone since it formed — 0 is the "very first tap".

    Counted in candles rather than ticks deliberately: a zone price sits in for a whole bar is still one
    visit, and counting ticks would make freshness depend on how busy the feed happened to be.

    `from_index` is the caller's to set, and for a zone drawn at the origin of a move it should be the
    bar *after the move*: the candles that make up the push are not a return to the level, and the bar
    that closes the origin candle usually still overlaps it.
    """
    start = zone.origin_index + 1 if from_index is None else from_index
    return sum(1 for c in candles[start:] if c.low <= zone.upper and c.high >= zone.lower)
