"""Pillar 3: the operating manual — top-down alignment, the order-block entry, and a 1:2 floor.

This is the assembly the other three modules feed, and it is deliberately the *last* thing built rather
than the first: it consumes a control state, a graded order block and a break classification, and there is
nothing useful it could have said before those existed.

What it does, in the material's own order:

1. **Top-down.** Two clocks run at once: a trigger timeframe where the change of character is read, and a
   slower one that has to agree before anything is armed. The material's funnel is exactly this — the
   higher timeframe gives the bias and the level, the lower one gives the order block and the trigger — and
   a trigger that contradicts the higher clock is skipped, with the reason recorded.
2. **Wait for the retrace.** A valid change of character does *not* produce a trade. It arms one: the order
   block of the leg that broke the level, with the entry at the block, the stop just beyond its wick, and a
   target at the minimum risk-to-reward. Price has to come back to the block. Nothing here chases a break,
   which is the material's own instruction and its closing slide.
3. **Say no out loud.** Every bar that produced nothing records *why* — no break, a break that was a sweep,
   a break with no aligned higher timeframe, a block that failed the three-factor check. The difference
   between "no setup" and "a setup I declined" is the whole reason this package exists.

**What is a reading rather than a quote.** The material states a *minimum* 1:2 risk-to-reward and targets
"the next macro level"; the floor is implemented and the macro-level target is not, because the daily levels
it refers to are a separate piece of work. The push threshold, the band, and the choice of clocks are all
parameters with defaults, and none of them has been measured yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..forex.candles import Candle, TimeCandleBuilder
from ..forex.model import Direction, TradePlan
from ..forex.structure import Trend, swing_points, trend_sequence
from ..forex.trade_strategies import TradeDecision
from ..strategies import History
from .components import OrderBlock, order_block
from .engine import Control, ControlMachine
from .quality import assess


@dataclass
class _Armed:
    """A valid change of character, waiting for price to come back to its block."""

    plan: TradePlan
    block: OrderBlock
    reason: str


class SmcStrategy:
    """The assembled method: arm on a validated change of character, fill on the retrace into the block."""

    def __init__(
        self,
        *,
        trigger_minutes: float = 5.0,
        higher_minutes: float = 60.0,
        band_bands: float = 1.0,
        min_pushed: float = 3.0,
        risk_reward: float = 2.0,
        strength: int = 2,
        lookback: int = 20,
        window: int = 400,
        stake: float = 1.0,
    ) -> None:
        if risk_reward < 1:
            raise ValueError("the material's floor is a minimum of 1:2; anything below 1 risks more than it targets")
        self.name = (
            f"smc(trigger={trigger_minutes:g}m, higher={higher_minutes:g}m, rr>={risk_reward:g}, "
            f"pushed>={min_pushed:g})"
        )
        self._trigger_interval = trigger_minutes * 60.0
        self._trigger = TimeCandleBuilder(self._trigger_interval)
        self._higher = TimeCandleBuilder(higher_minutes * 60.0)
        self._band_bands = band_bands
        self._min_pushed = min_pushed
        self._risk_reward = risk_reward
        self._strength = strength
        self._lookback = lookback
        self._window = window
        self._stake = stake
        self._machine: ControlMachine | None = None
        self._armed: _Armed | None = None
        self.last_view = "nothing seen yet"

    # --- the tick path --------------------------------------------------------------------------

    def decide(self, history: History) -> TradeDecision | None:
        if not len(history):
            return None
        tick = history[-1]
        price = float(tick.price)
        self._higher.feed(tick.ts, price)
        closed = self._trigger.feed(tick.ts, price)
        if closed is not None:
            self._on_trigger_bar()
        return self._fill(price)

    def _on_trigger_bar(self) -> None:
        candles = self._trigger.last(self._window)
        if len(candles) < self._lookback + self._strength * 2 + 2:
            self.last_view = f"warming up ({len(candles)} bars)"
            return
        band = self._band_bands * _typical_range(candles, self._lookback)
        if self._machine is None:
            self._machine = ControlMachine(band=band, strength=self._strength)
        result = self._machine.consider(candles, index=len(candles) - 1)
        if result is None:
            self.last_view = f"{self._machine.control.value} control; last bar threatened no level"
            return
        if not result.flips_control:
            self.last_view = f"declined: {result.reason}"
            return
        self._arm(candles, result, band, band_bands=self._band_bands)

    def _arm(self, candles, result, band: float, *, band_bands: float) -> None:
        """Turn a valid change of character into a waiting order, or say why it will not."""
        index = len(candles) - 1
        leg_is_bearish = result.direction is Direction.DOWN
        same_direction = (lambda c: not c.bullish) if leg_is_bearish else (lambda c: c.bullish)
        start = index
        while start - 1 >= 0 and same_direction(candles[start - 1]):
            start -= 1
        if start - 1 < 0:
            self.last_view = "declined: the breaking leg has no origin candle to box"
            return
        block = order_block(candles, index=start - 1)

        higher = self._higher.last(self._window)
        if len(higher) >= self._strength * 2 + 1:
            trend = trend_sequence(swing_points(higher, strength=self._strength))
            agrees = (trend is Trend.DOWN and block.direction is Direction.DOWN) or (
                trend is Trend.UP and block.direction is Direction.UP
            )
            if not agrees:
                self.last_view = (
                    f"declined: a {block.direction.value} break, but the higher timeframe reads "
                    f"{trend.value} — the funnel has to align"
                )
                return
        quality = assess(candles, block=block, band=band, min_pushed=self._min_pushed)
        if not quality.complete:
            self.last_view = f"declined: {quality.reason}"
            return

        entry = block.price_low if block.direction is Direction.DOWN else block.price_high
        stop = block.stop_level
        risk = abs(entry - stop)
        if risk <= 0:
            self.last_view = "declined: the block has no width to risk"
            return
        target = entry - risk * self._risk_reward if block.direction is Direction.DOWN else entry + risk * self._risk_reward
        plan = TradePlan(block.direction, stop=stop, target=target)
        self._armed = _Armed(
            plan=plan, block=block,
            reason=(
                f"smc: change of character with {self._machine.control.value} now in control; {quality.reason}; "
                f"limit at {entry:.5f}, stop {stop:.5f} beyond the block wick, target {target:.5f} at "
                f"{self._risk_reward:g}:1"
            ),
        )
        self.last_view = f"armed: {self._armed.reason}"

    def _fill(self, price: float) -> TradeDecision | None:
        """Fill the waiting order the moment price trades back into the block."""
        armed = self._armed
        if armed is None:
            return None
        block = armed.block
        reached = price <= block.price_high if block.direction is Direction.UP else price >= block.price_low
        if not reached:
            return None
        if not armed.plan.is_well_formed(price):
            self.last_view = f"abandoned: price reached the block at {price:.5f} with the plan no longer valid"
            self._armed = None
            return None
        self._armed = None
        return TradeDecision(armed.plan, self._stake, f"{armed.reason}; filled at {price:.5f}")


def _typical_range(candles: Sequence, lookback: int) -> float:
    """The median candle range — what sets a level's width everywhere in this package."""
    recent = candles[-lookback:]
    if not recent:
        return 0.0
    ranges = sorted(c.range for c in recent)
    return ranges[len(ranges) // 2]
