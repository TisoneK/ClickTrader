"""Pillar 3: the operating manual — top-down alignment, the order-block entry, and a 1:2 floor.

**Perception now lives in `analyst.py`.** This class no longer has its own idea of what a level, a break or a block
is: on every closed trigger bar it asks `read_chart` what the chart says — the same reading `smc-chart` draws — and
trades only an opportunity that reading calls true and has just armed. What stays here is the tick path: holding the
order, filling it on the retrace, and dropping it when the zone dies. The constants this class used to own
(`band_bands`, `min_pushed`, `alignment_steps`) are gone; see `analyst.READINGS` for the few choices that remain.

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

**Nothing here gates on a number nobody stated.** The material states a *minimum* 1:2 risk-to-reward — that
is implemented as a floor — and it describes three qualities of a valid zone without giving a threshold for
any of them. So pushed distance is **measured and reported, and by default not gated at all**: an earlier
version required three bands, a number invented here, and that single invented threshold was the entire
difference between an engine that never fired in 42 days and one that fires. Gating a method on a made-up
constant does not make it more faithful, it makes the constant the strategy.

The clocks default to the ratio the material itself draws — a 1-hour view above a 15-minute trigger — rather
than the 5m/60m first chosen here. The alignment reading defaults to two structural steps rather than three,
because three was strict enough that on real EUR/USD the higher timeframe read "range" at every one of 1,797
crossings, which is not a filter but an off switch. Both are still parameters, and both are still unmeasured.

The macro-level target the material names is not implemented — it needs the daily key levels, which are their
own piece of work.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..forex.candles import Candle, TimeCandleBuilder
from ..forex.model import Direction, TradePlan
from ..forex.trade_strategies import TradeDecision
from ..strategies import History
from .components import OrderBlock
from .analyst import read_chart


@dataclass
class _Armed:
    """A valid change of character, waiting for price to come back to its block."""

    plan: TradePlan
    block: OrderBlock
    reason: str


class SmcStrategy:
    """The assembled method: arm on an opportunity the analyst calls true, fill on the retrace into the block."""

    def __init__(
        self,
        *,
        trigger_minutes: float = 15.0,
        higher_minutes: float | tuple[float, ...] = 60.0,
        risk_reward: float = 2.0,
        strength: int = 2,
        lookback: int = 20,
        window: int = 400,
        stake: float = 1.0,
    ) -> None:
        if risk_reward < 1:
            raise ValueError("the material's floor is a minimum of 1:2; anything below 1 risks more than it targets")
        chain = tuple(higher_minutes) if isinstance(higher_minutes, (tuple, list)) else (higher_minutes,)
        self.name = f"smc(trigger={trigger_minutes:g}m, higher={'/'.join(f'{m:g}' for m in chain)}m, rr>={risk_reward:g})"
        self._trigger = TimeCandleBuilder(trigger_minutes * 60.0)
        self._higher = [TimeCandleBuilder(m * 60.0) for m in chain]
        self._risk_reward = risk_reward
        self._strength = strength
        self._lookback = lookback
        self._window = window
        self._stake = stake
        self._armed: _Armed | None = None
        self.last_view = "nothing seen yet"

    # --- the tick path --------------------------------------------------------------------------

    def decide(self, history: History) -> TradeDecision | None:
        if not len(history):
            return None
        tick = history[-1]
        price = float(tick.price)
        for builder in self._higher:
            builder.feed(tick.ts, price)
        closed = self._trigger.feed(tick.ts, price)
        if closed is not None:
            self._on_trigger_bar(closed)
        return self._fill(price)

    def warm(self, ticks) -> int:
        """Feed historical ticks into the bar builders WITHOUT reading the chart or placing anything.

        A live run starts with no bars, and the reading needs hours of them: this is how it starts with the
        chart a person would already have on screen. Nothing armed before the last warm-up tick can exist, so
        the first live bar is read as a fresh one. Returns how many ticks were fed."""
        fed = 0
        for tick in ticks:
            price = float(tick.price)
            for builder in self._higher:
                builder.feed(tick.ts, price)
            self._trigger.feed(tick.ts, price)
            fed += 1
        self._armed = None
        self.last_view = f"warmed with {fed} historical tick(s)"
        return fed

    def _on_trigger_bar(self, closed: Candle) -> None:
        candles = self._trigger.last(self._window)
        if len(candles) < self._lookback + self._strength * 2 + 2:
            self.last_view = f"warming up ({len(candles)} bars)"
            return
        armed = self._armed
        if armed is not None:
            dead = closed.close > armed.block.price_high if armed.block.direction is Direction.DOWN else closed.close < armed.block.price_low
            if dead:
                self._armed = None
                self.last_view = "dropped: the bar closed through the block's far edge — dead zone"
        reading = read_chart(
            candles, higher=[b.last(self._window) for b in self._higher] or None, strength=self._strength,
            lookback=self._lookback, risk_reward=self._risk_reward,
        )
        last = len(candles) - 1
        fresh = [o for o in reading.opportunities if o.armed_at == last]
        if not fresh:
            latest = reading.events[-1] if reading.events else None
            what = f"{reading.structure[-1].value} structure" + (f"; last event {latest.kind.value} {latest.verdict.value} at bar {latest.index}" if latest else "")
            self.last_view = what if self._armed is None else f"waiting for the retrace; {what}"
            return
        opp = fresh[0]
        if not opp.is_true or opp.target is None:
            self.last_view = f"declined: {opp.reason}"
            return
        plan = TradePlan(opp.direction, stop=opp.stop, target=opp.target)
        self._armed = _Armed(plan=plan, block=opp.block, reason=f"smc: {opp.reason}")
        self.last_view = f"armed: {opp.reason}"

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
