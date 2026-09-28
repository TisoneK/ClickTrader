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

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

from ..strategies import History
from .candles import Candle, TimeCandleBuilder, TimedCandle
from .model import Direction, TradePlan
from .sessions import SessionLevels, SessionTracker, levels_from_sessions
from .structure import (
    FairValueGap,
    SwingKind,
    Trend,
    Zone,
    approach_speed,
    broke_structure,
    displacement,
    fair_value_gaps,
    gap_untouched,
    target_gap,
    swing_points,
    taps,
    trend_sequence,
    zone_from_origin,
)


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
"""How a registry entry is built. A trade strategy that is defined against a trading day accepts
`session_start_hour_utc`; see `build`, which passes it only where it means something."""


class EntryModel(str, Enum):
    """The three entry models the source's SOP names but does not define.

    These are **readings**, not quotes, and they live in an enum rather than in the source because the
    source only lists the names. Each is a genuinely different amount of confirmation:

    - `AGGRESSIVE` — take the first touch of the zone, at the tick that reaches it.
    - `NORMAL` — wait for a bar that traded into the zone to close back out of it.
    - `CONSERVATIVE` — additionally require that closing bar to engulf the previous bar's body, the
      confirmation candle the earlier supply-and-demand material talked about.

    They are ordered by how much they ask of the market, which is also the order in which they trade
    less often and later: if the three disagree on the same data, that is information, so all three are
    testable rather than one being picked.
    """

    AGGRESSIVE = "aggressive"
    NORMAL = "normal"
    CONSERVATIVE = "conservative"


@dataclass
class _Setup:
    """A zone whose checklist has passed and which price has not come back to yet."""

    zone: Zone
    trade_dir: Direction
    reason: str
    touched: bool = False


class SupplyDemand:
    """The supply-and-demand method, run as the eight-line checklist its own SOP states.

    Every line of the checklist is a gate, in the order the SOP lists them, and each is a measurement
    from `structure.py` rather than a judgement made inside this class:

    1. **TREND** — a 1-2-3 structure sequence agreeing with the trade's direction.
    2. **DISPLACEMENT** — a run of `min_candles` same-direction candles, each at least
       `displacement_multiple` times the median body before the run.
    3. **IMBALANCE** — a fair value gap inside that run, with no wick overlap, that price has not been
       back into.
    4. **STRUCTURE** — the run trades beyond the last opposing swing that stood before it.
    5. **PRECISION** — the zone is the candle *before* the run, drawn wick to wick.
    6. **FRESHNESS** — no candle has traded into that zone since the run ended.
    7. **MOMENTUM** — at the first touch, the approach must not be parabolic: recent candle bodies within
       `max_approach_speed` times the median body before them.
    8. **EXECUTION** — the `entry_model` decides how much confirmation the entry waits for.

    **Where this follows the SOP and where it had to choose.** The displacement count (4+), the wick-to-
    wick zone, the first-tap freshness rule, the break of structure, the no-wick-overlap imbalance and
    the falling-knife veto are the SOP's own words. These are the readings it left open, each a named
    parameter rather than a buried constant:

    - "massive candles" is `displacement_multiple` times the recent median, with `displacement_mode`
      deciding whether that applies to the run as a whole (the default) or to each candle. The SOP gives
      a count of candles but not a size, and the two readings differ enormously in practice — see
      `structure.displacement`, which records the measurement that makes "each" the wrong default.
    - the three entry models' meanings (see `EntryModel`) — the SOP names them without defining them.
    - "1-2-3 structure sequence" is read as `trend_steps` successive steps in one direction on both
      swing highs and swing lows.
    - the exit is the earlier material's: stop beyond the far side of the zone, target the next opposing
      imbalance ahead. Where there is no such imbalance there is no trade, because a method whose target
      is "the next zone" has nothing to aim at.
    - **trade management is not modelled.** The earlier material says "scale out against the biggest
      seller block" and the SOP says nothing about exits at all; a partial exit, a stop moved to
      breakeven and a runner are all absent, and a `TradePlan` cannot express them. So this is the entry
      half of the method, graded as a single stop and a single target.
    - **a setup that is touched and then abandoned stays armed.** If price enters the zone and no bar
      closes back out of it, freshness is not re-checked on the next visit, because the SOP's rule is
      about the first tap and says nothing about what voids a level afterwards. The earlier material's
      "dynamic zoning" — delete a zone that momentum destroys, redraw where the new move started — is
      the piece that would answer it, and it is not implemented either.

    One zone is armed at a time, most recent wins. A zone that is vetoed as a falling knife, or traded,
    is spent and never re-armed — a level price has already fallen through is not a fresh tap again.
    """

    def __init__(
        self,
        *,
        bar_minutes: float = 15.0,
        min_candles: int = 4,
        displacement_multiple: float = 1.5,
        displacement_mode: str = "run",
        swing_strength: int = 2,
        trend_steps: int = 3,
        entry_model: str = "normal",
        max_approach_speed: float = 3.0,
        approach_bars: int = 3,
        lookback: int = 20,
        window: int = 400,
        stake: float = 1.0,
    ) -> None:
        if bar_minutes <= 0:
            raise ValueError("bar_minutes must be positive")
        if window < lookback * 2:
            raise ValueError("window must hold at least two lookbacks of candles to measure anything")
        self._model = EntryModel(entry_model)
        self.name = (
            f"supply-demand-sop(bar={bar_minutes:g}m, displacement={min_candles}x{displacement_multiple:g}, "
            f"entry={self._model.value}, trend-steps={trend_steps})"
        )
        self._interval = bar_minutes * 60.0
        self._min_candles = min_candles
        self._displacement_multiple = displacement_multiple
        self._displacement_mode = displacement_mode
        self._swing_strength = swing_strength
        self._trend_steps = trend_steps
        self._max_approach_speed = max_approach_speed
        self._approach_bars = approach_bars
        self._lookback = lookback
        self._window = window
        self._stake = stake
        self._bars = TimeCandleBuilder(self._interval)
        self._setup: _Setup | None = None
        self._spent: set[tuple[str, float, float]] = set()

    def _spend(self, zone: Zone) -> None:
        self._spent.add((zone.direction.value, zone.lower, zone.upper))

    def decide(self, history: History) -> TradeDecision | None:
        if not len(history):
            return None
        tick = history[-1]
        closed = self._bars.feed(tick.ts, float(tick.price))
        if closed is not None:
            self._recheck()
        return self._enter(float(tick.price), closed)

    def _recheck(self) -> None:
        """Run the checklist against the bars so far and arm a zone if all of it holds.

        An already-armed setup is deliberately *not* disarmed by a later failing check, and that is not
        an oversight: once price has arrived at the level, the freshness gate ("the very first tap") is
        false by construction, so re-checking continuously would disarm exactly the setups the entry
        models are waiting to confirm. The re-check exists so a zone can be armed from the window rather
        than latched at the moment of the push; from then on the setup lives until it is spent.
        """
        candles = self._bars.last(self._window)
        if len(candles) < self._lookback + self._min_candles + self._swing_strength:
            return
        push = displacement(
            candles, min_candles=self._min_candles, size_multiple=self._displacement_multiple,
            size_mode=self._displacement_mode, lookback=self._lookback,
        )
        if push is None or push.start_index == 0:
            return
        direction = push.direction
        swings = swing_points(candles, strength=self._swing_strength)
        if trend_sequence(swings, steps=self._trend_steps) is not (
            Trend.UP if direction is Direction.UP else Trend.DOWN
        ):
            return
        prior = [s for s in swings if s.index < push.start_index]
        move = candles[push.start_index : push.end_index + 1]
        if not broke_structure(move, prior, direction=direction):
            return
        gaps = [g for g in fair_value_gaps(candles) if push.start_index <= g.formed_index <= push.end_index]
        if not any(gap_untouched(g, candles) for g in gaps):
            return
        origin = candles[push.start_index - 1]
        zone = zone_from_origin(origin, index=push.start_index - 1, direction=direction)
        if zone.size <= 0:
            return
        if taps(zone, candles, from_index=push.end_index + 1) > 0:
            return  # FRESHNESS: this is not the first tap
        if (zone.direction.value, zone.lower, zone.upper) in self._spent:
            return
        self._setup = _Setup(zone=zone, trade_dir=direction, reason=self._reason(push, zone, candles))

    def _reason(self, push, zone: Zone, candles) -> str:
        return (
            f"{self.name} {'demand' if zone.direction is Direction.UP else 'supply'}: {push.candles} candles "
            f"of displacement ({push.baseline_body:.5f} median body before it), structure broken, imbalance "
            f"left behind; zone {zone.lower:.5f}-{zone.upper:.5f} wick-to-wick on the candle before the run, "
            f"first tap"
        )

    def _enter(self, price: float, closed: TimedCandle | None) -> TradeDecision | None:
        """Apply the entry model, and the falling-knife veto at the moment price is at the level.

        The two confirmation models trigger on a *completed bar*, not on the tick price, because a bar
        that dips into the zone and closes back out of it is never at the level on the tick the decision
        is made — checking the tick price would mean never seeing the confirmation at all.
        """
        setup = self._setup
        if setup is None:
            return None
        zone = setup.zone
        if self._model is EntryModel.AGGRESSIVE:
            if not zone.contains(price):
                return None
        else:
            if closed is None or not (closed.low <= zone.upper and closed.high >= zone.lower):
                return None  # this bar never got to the level
            closed_back_out = (
                closed.close > zone.upper if setup.trade_dir is Direction.UP else closed.close < zone.lower
            )
            if not closed_back_out:
                return None
            if self._model is EntryModel.CONSERVATIVE:
                pair = self._bars.last(2)
                if len(pair) < 2 or not _engulfs(pair[0], pair[1], setup.trade_dir):
                    return None
        if not self._momentum_ok(setup):
            return None
        return self._decision(price, setup)

    def _momentum_ok(self, setup: _Setup) -> bool:
        """The falling-knife veto, decided once per setup, the first time price reaches the zone."""
        if setup.touched:
            return True
        setup.touched = True
        speed = approach_speed(self._bars.last(self._window), bars=self._approach_bars, lookback=self._lookback)
        if speed > self._max_approach_speed:
            self._spend(setup.zone)  # a parabolic crash into the level is the falling knife the SOP names
            self._setup = None
            return False
        return True

    def _decision(self, price: float, setup: _Setup) -> TradeDecision | None:
        plan = self._plan(price, setup)
        if plan is None or not plan.is_well_formed(price):
            self._spend(setup.zone)  # nothing to aim at, or no room to the stop: not a trade, not a retry
            self._setup = None
            return None
        self._spend(setup.zone)
        self._setup = None
        return TradeDecision(plan, self._stake, f"{setup.reason}; entered at {price:.5f}")

    def _plan(self, price: float, setup: _Setup) -> TradePlan | None:
        zone = setup.zone
        stop = zone.lower if setup.trade_dir is Direction.UP else zone.upper
        candles = self._bars.last(self._window)
        target = target_gap(fair_value_gaps(candles), candles, direction=setup.trade_dir, price=price)
        if target is None:
            return None
        edge = target.lower if setup.trade_dir is Direction.UP else target.upper
        return TradePlan(setup.trade_dir, stop=stop, target=edge)


def _engulfs(previous: Candle, last: Candle, direction: Direction) -> bool:
    """The confirmation candle: the last bar's body covers the previous bar's body, the other way."""
    if direction is Direction.UP:
        return not previous.bullish and last.bullish and last.open <= previous.close and last.close >= previous.open
    return previous.bullish and not last.bullish and last.open >= previous.close and last.close <= previous.open


TRADE_REGISTRY: dict[str, TradeStrategyFactory] = {
    "sneaky-pivot": SneakyPivot,
    "supply-demand": SupplyDemand,
}


def build(name: str, *, session_start_hour_utc: int | None = None) -> TradeStrategy:
    """Build a registered trade strategy, passing the session roll hour only to the ones defined against
    a trading day.

    The range method draws its lines from the previous session, so the roll hour is part of it; the
    supply-and-demand checklist is not defined against a session at all, and handing it a parameter it
    would ignore is how a strategy ends up with configuration that looks meaningful and is not.
    """
    factory = TRADE_REGISTRY[name]
    if session_start_hour_utc is not None and "session_start_hour_utc" in inspect.signature(factory).parameters:
        return factory(session_start_hour_utc=session_start_hour_utc)
    return factory()
