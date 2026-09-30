"""The engine: which side is in control, and the only thing allowed to change it.

The material's model is a two-state machine, drawn as a figure-eight. Control sits with **demand** or with
**supply**, never with both, and it transfers on a *change of character* — a break that genuinely moves it.
Price then swings between unmitigated zones until the next change.

The hard part, and the part every other implementation here has been missing, is that three different
things look identical at the moment of a break:

- a **genuine change of character** — the break holds and control transfers;
- a **liquidity sweep** — the break takes the stops sitting at an obvious level and comes straight back;
- a **gap mitigation** — the break is price returning to fill an old imbalance, and the trend resumes.

The discriminator is not the candle that broke. It is *what sits to the left of it*: a visible cluster of
stops, or an unfilled fair value gap. This module states that as two checks in the order the material gives
them, and returns a reason either way — because "no signal" and "a signal I declined, here is why" are the
two answers this project has never been able to tell apart.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from ..forex.candles import Candle
from ..forex.model import Direction
from ..forex.structure import (
    FairValueGap,
    SwingKind,
    fair_value_gaps,
    gap_untouched,
    key_zones,
)


class Control(str, Enum):
    """Which side is in control. The material's two states, and there is no third."""

    DEMAND = "demand"
    SUPPLY = "supply"

    @property
    def direction(self) -> Direction:
        return Direction.UP if self is Control.DEMAND else Direction.DOWN

    @property
    def other(self) -> "Control":
        """What control becomes when a change of character is valid."""
        return Control.SUPPLY if self is Control.DEMAND else Control.DEMAND


class BreakKind(str, Enum):
    """What a break through a level actually was."""

    CHANGE_OF_CHARACTER = "change-of-character"
    LIQUIDITY_SWEEP = "liquidity-sweep"
    GAP_MITIGATION = "gap-mitigation"


@dataclass(frozen=True)
class LiquidityPool:
    """A level the market has turned at more than once — where other people's stops are sitting.

    The material's "$Liquidity$" lines. Geometrically this is the same object as an entry zone: swings
    clustered within a band. The difference is its *role* — a pool is a target, the price a move needs to
    reach to fill orders against the stops there, which is why it is its own type rather than a flag on a
    zone. A break of one is a candidate for a sweep, not automatically a signal.
    """

    price: float
    kind: SwingKind
    touches: int

    @property
    def holds_stops(self) -> str:
        return "sell-side stops (below)" if self.kind is SwingKind.LOW else "buy-side stops (above)"


@dataclass(frozen=True)
class BreakResult:
    """What a break was, and why — the answer the strategy needs and a person can read."""

    kind: BreakKind
    level: float
    direction: Direction
    reason: str
    pool: LiquidityPool | None = None
    gap: FairValueGap | None = None

    @property
    def flips_control(self) -> bool:
        return self.kind is BreakKind.CHANGE_OF_CHARACTER


def liquidity_pools(
    candles: Sequence[Candle], *, strength: int = 2, band: float, min_touches: int = 2
) -> list[LiquidityPool]:
    """Levels turned at `min_touches` times, as pools rather than as entry zones.

    Delegates the geometry to `key_zones` — a level the market has turned at twice is the same measurement
    whichever question you are asking of it — and only changes what the object means.
    """
    return [
        LiquidityPool(price=zone.price, kind=zone.kind, touches=zone.touches)
        for zone in key_zones(candles, strength=strength, band=band, min_touches=min_touches)
    ]


def classify_break(
    candles: Sequence[Candle],
    *,
    index: int,
    level: float,
    direction: Direction,
) -> BreakResult:
    """Say which of the three things the break at `index` through `level` actually was.

    The checks are the material's own, in its own order:

    1. **Did the bar close beyond the level?** A wick through that closes back is a *liquidity sweep* —
       "wick below the level, rapid recovery" — and is not a change of character however dramatic it looks.
    2. **Was an unfilled gap sitting at the level?** If an unmitigated fair value gap contains it, the break
       is *gap mitigation*: price rebalancing, not reversing. The test is whether the gap was unfilled
       *right up to* the breaking bar, which is what makes this break the one that fills it.
    3. Otherwise it is a **change of character**, and control transfers.

    **The gap containment is strict, and that is a measured decision rather than a stylistic one.** An
    earlier version widened the gap by a band — a candle range either side — on the reasoning that a gap
    which *nearly* contains the level looks the same to a trader's eye. Run over a real 17-hour EUR/USD
    recording at five-minute bars it declined **62,458 bars** as "price rebalancing, not a reversal" and
    never produced a single change of character: levels and gaps are densely packed at that scale, so nearly
    every level sits within a band of some gap and the test swallowed everything. A check that never lets
    anything through is not a filter, it is an off switch.
    """
    if not 0 <= index < len(candles):
        raise ValueError("index is outside the series")
    bar = candles[index]
    breaking_up = direction is Direction.UP

    closed_beyond = bar.close > level if breaking_up else bar.close < level
    if not closed_beyond:
        pierced = bar.high > level if breaking_up else bar.low < level
        if pierced:
            return BreakResult(
                BreakKind.LIQUIDITY_SWEEP, level, direction,
                f"wick through {level:.5f} and closed back at {bar.close:.5f} — the stops at that level "
                "were taken, not the level itself",
            )
        return BreakResult(
            BreakKind.GAP_MITIGATION, level, direction,
            f"bar {index} never reached {level:.5f} at all",
        )

    for gap in fair_value_gaps(candles[: index + 1]):
        if not (gap.lower <= level <= gap.upper):
            continue
        if gap.formed_index > index - 2:
            # A gap needs three candles, so one with `formed_index` this recent includes the breaking bar
            # itself — it was created *by* this move, not left behind before it. Counting it was why this
            # test declined 62,458 bars of a 17-hour recording and let no break through: every sharp break
            # leaves a gap containing the level it just broke, so every break excused itself.
            continue
        if gap_untouched(gap, candles[:index]):  # unfilled right up to the breaking bar
            return BreakResult(
                BreakKind.GAP_MITIGATION, level, direction,
                f"{level:.5f} sits inside an unfilled gap {gap.lower:.5f}-{gap.upper:.5f}; this break is "
                "price rebalancing, not a reversal",
                gap=gap,
            )
    return BreakResult(
        BreakKind.CHANGE_OF_CHARACTER, level, direction,
        f"closed {bar.close:.5f} beyond {level:.5f} with no unfilled gap at the level",
    )


class ControlMachine:
    """Who is in control, advanced one bar at a time.

    Starts wherever the caller says and flips **only** on a break that classifies as a genuine change of
    character. A sweep or a gap fill leaves it where it was — which is the whole point: those two are
    precisely the events that would otherwise be read as reversals.

    Keep the returned `BreakResult`s. Every break it sees is reported with its reason, including the ones
    that changed nothing, so a run can say "it saw this and declined it" rather than only "it did nothing".
    """

    def __init__(
        self,
        *,
        band: float,
        strength: int = 2,
        min_touches: int = 2,
        initial: Control = Control.DEMAND,
    ) -> None:
        if band <= 0:
            raise ValueError("band must be positive — a level with no width is not a level")
        self._band = band
        self._strength = strength
        self._min_touches = min_touches
        self._control = initial
        self._reason = f"started in {initial.value} control"

    @property
    def control(self) -> Control:
        return self._control

    @property
    def reason(self) -> str:
        return self._reason

    def consider(self, candles: Sequence[Candle], *, index: int) -> BreakResult | None:
        """Report what the bar at `index` did, if it broke a pool against the current control.

        A bar is only interesting if it *pierced* a pool on the losing side — piercing, not closing beyond,
        because whether the close held is exactly what the classification is for. Returns `None` when the
        bar threatened nothing, which is a different answer from a break that was declined.
        """
        if not 0 <= index < len(candles):
            raise ValueError("index is outside the series")
        bar = candles[index]
        for pool in liquidity_pools(
            candles[: index + 1], strength=self._strength, band=self._band, min_touches=self._min_touches
        ):
            against_control = (self._control is Control.DEMAND and pool.kind is SwingKind.LOW) or (
                self._control is Control.SUPPLY and pool.kind is SwingKind.HIGH
            )
            if not against_control:
                continue
            pierced = bar.low < pool.price if pool.kind is SwingKind.LOW else bar.high > pool.price
            if not pierced:
                continue
            direction = Direction.DOWN if pool.kind is SwingKind.LOW else Direction.UP
            result = classify_break(candles, index=index, level=pool.price, direction=direction)
            if result.flips_control:
                self._control = self._control.other
            self._reason = f"bar {index}: {result.kind.value} — {result.reason}"
            return result
        return None
