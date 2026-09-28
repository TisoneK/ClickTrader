"""Forex strategies that trade a plan instead of calling a direction.

`strategies.py`'s strategies answer "which way, over the next N ticks" and are graded by comparing two
prices (`harness.py`). The strategies here answer "which way, with the stop *here* and the target
*there*", which is the shape a chart method is actually written in and which cannot be graded that way
(`trade_harness.py`).

They live in their own module with their own registry rather than being mixed into `strategies.py`'s:
the two families produce different decision types, are graded by different rules, and return verdicts
that are not comparable (a hit rate against a coin flip; an expectancy in R against the mirror of the
same trades). Keeping that boundary in the module structure is clearer than an `isinstance` check buried
in the middle of a replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from ..strategies import History
from .candles import TimeCandleBuilder
from .model import Direction, TradePlan
from .sessions import SessionLevels, SessionTracker, levels_from_sessions


@dataclass(frozen=True)
class TradeDecision:
    plan: TradePlan
    stake: float
    reason: str


class TradeStrategy(Protocol):
    name: str

    def decide(self, history: History) -> TradeDecision | None:
        """Offer a trade with a stop and a target, or return None to pass."""
        ...


@dataclass
class _Armed:
    """A setup whose pattern has completed and whose trigger has not yet fired."""

    plan: TradePlan
    trigger_price: float
    expires_at: float
    reason: str


class SneakyPivot:
    """The "sneaky pivot" range method, as a mechanical reading of the blueprint it comes from.

    Four lines, all fixed before the session being traded begins:

    - **Range High / Low** — the previous session's high and low.
    - **Swing High / Low** — the highest high (and lowest low) over the sessions before that one, kept
      only when it reaches beyond the range line. Above the Range High is the sell zone, below the Range
      Low is the buy zone, and the space between them is explicitly a no-trade area.

    Then a three-candle sequence at whichever boundary price has run to, `bar_minutes` long each:

    1. the **anchor**, which reaches into a zone;
    2. the **sneaky candle**, which tests the same boundary again and closes back out of it;
    3. the **trigger** — enter on the first tick that crosses the sneaky candle's high (long) or low
       (short), which has to happen inside the next `trigger_bars` bars.

    Stop beyond the swing line, target the opposite range line.

    **Where this follows the source, and where it had to choose.** The four line definitions, the
    three-candle sequence, the crossing entry, the stop beyond the swing line and the target at the
    opposite edge are all stated by the blueprint. These are the points it left open, each resolved
    explicitly rather than left implicit:

    - "reaches into the zone" is `low <= range_low` (`high >= range_high`) measured on the bar's *wick*,
      not its close — the method is written around probes of a level, and a probe is a wick.
    - "closes back out of it" is `close > range_low`, the mechanical form of "proves intention to buy
      back up" rather than a claim about the bar's colour.
    - the anchor's direction is **not** constrained: the source's prose is about where the bar went, and
      its colour appears only in the illustration.
    - "scroll left and find the next level" does not say how far to scroll, so `swing_lookback` says it.
      It counts sessions *before the range session*, since the level has to sit outside a range that
      exists.
    - the crossing must happen within `trigger_bars` bars, because the source's engine is a 45-minute
      sequence — three consecutive bars — and a trigger that can wait all day is a different method.
    - the source's own escape hatches are deliberately **not** implemented: "if the bottom wicks test an
      area three times and hold, that is your localized floor", and "scale out against the biggest seller
      block". Both are explicitly discretionary ("don't be rigid") and neither can be written down
      without inventing the rule the source declined to state. A method has to be specified before it can
      be trusted or rejected; where the source leaves a judgement call, that judgement is absent here
      rather than invented.

    One setup is armed at a time, most recent wins — the same convention `strategies.InsideBar` uses, and
    for the same reason: a newer completed pattern supersedes an older one that has not triggered.

    Built to be tested, not believed, like every strategy on this side of the project.
    """

    def __init__(
        self,
        *,
        bar_minutes: float = 15.0,
        session_start_hour_utc: int = 0,
        swing_lookback: int = 1,
        trigger_bars: int = 1,
        stake: float = 1.0,
    ) -> None:
        if bar_minutes <= 0:
            raise ValueError("bar_minutes must be positive")
        if trigger_bars < 1:
            raise ValueError("trigger_bars must allow at least the bar immediately after the sneaky candle")
        self.name = (
            f"sneaky-pivot(bar={bar_minutes:g}m, session-start={session_start_hour_utc}h, "
            f"swing-lookback={swing_lookback}, trigger-bars={trigger_bars})"
        )
        self._interval = bar_minutes * 60.0
        self._trigger_bars = trigger_bars
        self._stake = stake
        self._bars = TimeCandleBuilder(self._interval)
        # keep = the session in progress, the range session, and the swing lookback behind it.
        self._sessions = SessionTracker(start_hour_utc=session_start_hour_utc, keep=2 + swing_lookback)
        self._swing_lookback = swing_lookback
        self._levels: SessionLevels | None = None
        self._armed: _Armed | None = None

    def decide(self, history: History) -> TradeDecision | None:
        if not len(history):
            return None
        tick = history[-1]
        price = float(tick.price)

        if self._sessions.feed(tick.ts, price):
            # A new session re-draws every line and voids anything the last one had armed: the levels a
            # pending trigger was measured against no longer exist.
            self._levels = levels_from_sessions(
                self._sessions.completed(1 + self._swing_lookback), swing_lookback=self._swing_lookback
            )
            self._armed = None

        if self._bars.feed(tick.ts, price) is not None:
            self._arm_from_last_two_bars()

        return self._take_trigger(price, tick.ts)

    def _arm_from_last_two_bars(self) -> None:
        """Check the two most recently closed bars for an anchor-then-sneaky pair at either boundary."""
        levels = self._levels
        if levels is None:
            return
        bars = self._bars.last(2)
        if len(bars) < 2:
            return
        anchor, sneaky = bars
        if sneaky.opened_at - anchor.opened_at != self._interval:
            return  # the sequence is consecutive bars; a gap means these two are not one pattern

        if levels.swing_low is not None:
            self._arm(Direction.UP, anchor.low, sneaky, below=True, levels=levels)
        if levels.swing_high is not None:
            self._arm(Direction.DOWN, anchor.high, sneaky, below=False, levels=levels)

    def _arm(
        self, direction: Direction, anchor_extreme: float, sneaky, *, below: bool, levels: SessionLevels
    ) -> None:
        """Arm a trigger for one boundary, if the two bars and the levels actually form the pattern."""
        boundary = levels.range_low if below else levels.range_high
        # The stop is the swing line and the target the opposite range line. Without a swing line on
        # this side there is no zone and no stop, so there is nothing to arm.
        stop = levels.swing_low if below else levels.swing_high
        if stop is None:
            return
        target = levels.range_high if below else levels.range_low

        reached = anchor_extreme <= boundary if below else anchor_extreme >= boundary
        tested = sneaky.low <= boundary if below else sneaky.high >= boundary
        closed_back = sneaky.close > boundary if below else sneaky.close < boundary
        if not (reached and tested and closed_back):
            return

        trigger_price = sneaky.high if below else sneaky.low
        plan = TradePlan(direction, stop=stop, target=target)
        if not plan.is_well_formed(trigger_price):
            # No room between the trigger and one of the levels — there is no trade here to arm, and
            # arming it would only produce a plan the harness has to refuse.
            return
        zone = "buy" if below else "sell"
        self._armed = _Armed(
            plan=plan,
            trigger_price=trigger_price,
            expires_at=sneaky.opened_at + self._interval * (1 + self._trigger_bars),
            reason=(
                f"sneaky pivot {zone}: {self._interval / 60:g}m anchor reached {boundary:.5f}, sneaky "
                f"candle tested it ({sneaky.low:.5f}-{sneaky.high:.5f}) and closed back at "
                f"{sneaky.close:.5f}; trigger {trigger_price:.5f}, stop {stop:.5f} (swing), "
                f"target {target:.5f} (opposite range line, range {levels.range_low:.5f}-"
                f"{levels.range_high:.5f})"
            ),
        )

    def _take_trigger(self, price: float, ts: float) -> TradeDecision | None:
        armed = self._armed
        if armed is None:
            return None
        if ts >= armed.expires_at:
            self._armed = None
            return None
        crossed = price > armed.trigger_price if armed.plan.direction is Direction.UP else price < armed.trigger_price
        if not crossed:
            return None
        self._armed = None
        return TradeDecision(armed.plan, self._stake, f"{armed.reason}; crossed at {price:.5f}")


TradeStrategyFactory = Callable[..., TradeStrategy]
"""How a registry entry is built. Every registered trade strategy accepts `session_start_hour_utc`,
since which clock a "day" runs on is a property of the market being replayed rather than of the method,
so the CLI can set it without knowing which strategy it is running."""


TRADE_REGISTRY: dict[str, TradeStrategyFactory] = {
    "sneaky-pivot": SneakyPivot,
}
