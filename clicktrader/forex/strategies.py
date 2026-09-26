"""Forex strategies: given the prices seen so far, call a direction over some horizon, or pass.

Reuses `clicktrader.strategies.History` directly rather than a forex-specific subclass — it's already
just a read-only windowed view of `Tick`s, generic over price and digit alike.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Protocol

from ..strategies import History
from .candles import CandleBuilder
from .indicators import bollinger_bands, ema, last_non_null, macd, rsi
from .model import Direction, Signal


@dataclass(frozen=True)
class SignalDecision:
    signal: Signal
    stake: float
    reason: str


class ForexStrategy(Protocol):
    name: str

    def decide(self, history: History) -> SignalDecision | None:
        """Call a direction over the signal's own horizon, or return None to pass."""
        ...


class RandomDirection:
    """The control every forex report should run alongside: picks a direction at random, knows
    nothing. Anything a strategy "achieves" that this also achieves is noise — the same role
    `strategies.RandomControl` plays on the digit-contract side."""

    def __init__(self, *, horizon_ticks: int = 10, stake: float = 1.0, seed: int = 0, bet_probability: float = 1.0) -> None:
        self.name = f"random-direction(seed={seed})"
        self._rng = random.Random(seed)
        self._horizon = horizon_ticks
        self._stake = stake
        self._bet_probability = bet_probability

    def decide(self, history: History) -> SignalDecision | None:
        if self._rng.random() >= self._bet_probability:
            return None
        direction = self._rng.choice((Direction.UP, Direction.DOWN))
        return SignalDecision(Signal(direction, self._horizon), self._stake, "random pick")


class MovingAverageCrossover:
    """The textbook baseline forex strategy: track a short-window and a long-window average price, and
    call a direction the instant the short average crosses the long one — not for as long as it merely
    stays on one side of it, which would count one crossing as many separate decisions.

    Included to be tested, not believed — whether this has any real directional accuracy is a genuinely
    open empirical question on this side of the project, unlike the digit contracts' provable -5%
    (DESIGN.md). The natural null it's compared against is `RandomDirection`, i.e. a coin flip.
    """

    def __init__(self, *, short_window: int = 10, long_window: int = 30, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.name = f"ma-crossover(short={short_window}, long={long_window}, horizon={horizon_ticks})"
        self._short = short_window
        self._long = long_window
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if len(history) < self._long + 1:
            return None
        prices = history.last_prices(self._long + 1)
        now, prev = prices[1:], prices[:-1]  # "prev" is the same window, one tick earlier
        now_short, now_long = _mean(now[-self._short :]), _mean(now)
        prev_short, prev_long = _mean(prev[-self._short :]), _mean(prev)
        if prev_short <= prev_long and now_short > now_long:
            direction = Direction.UP
        elif prev_short >= prev_long and now_short < now_long:
            direction = Direction.DOWN
        else:
            return None
        return SignalDecision(
            Signal(direction, self._horizon), self._stake,
            f"MA({self._short})={now_short:.5f} crossed MA({self._long})={now_long:.5f} {direction.value}",
        )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


class _ZoneEdgeStrategy:
    """Shared "fire only when the zone changes" bookkeeping for the four indicator strategies below.
    Each of RSI/MACD/Bollinger/EMA-trend computes a zone ("long"/"short"/"neutral") fresh every tick;
    a real signal only happens the instant that zone changes, not on every tick it merely holds —
    otherwise a single extended oversold reading would count as hundreds of separate decisions."""

    def __init__(self) -> None:
        self._last_zone: str | None = None

    def _fire(self, zone: str) -> bool:
        fired = zone != self._last_zone and zone != "neutral"
        self._last_zone = zone
        return fired


class RSIMeanReversion(_ZoneEdgeStrategy):
    """The classic RSI claim: below 30 is "oversold" (predicts UP, mean-reversion), above 70 is
    "overbought" (predicts DOWN). Recomputes RSI over a bounded recent window each tick rather than
    incrementally over the strategy's whole lifetime — an approximation, since Wilder's smoothing
    converges geometrically rather than needing the exact full history; `window` should be several
    times `period` for that convergence to have actually happened by the time a value is read.

    Included to be tested, not believed — see `MovingAverageCrossover`'s docstring for why forex
    direction has no algebraic answer the way digit contracts do.
    """

    def __init__(self, *, period: int = 14, window: int = 100, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        super().__init__()
        self.name = f"rsi-mean-reversion(period={period}, horizon={horizon_ticks})"
        self._period = period
        self._window = window
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if len(history) < self._period + 1:
            return None
        value = last_non_null(rsi(history.last_prices(self._window), self._period))
        if value is None:
            return None
        zone = "long" if value < 30 else "short" if value > 70 else "neutral"
        if not self._fire(zone):
            return None
        direction = Direction.UP if zone == "long" else Direction.DOWN
        return SignalDecision(Signal(direction, self._horizon), self._stake, f"RSI({self._period})={value:.2f} entered {zone}")


class MACDMomentum(_ZoneEdgeStrategy):
    """The classic MACD claim: the MACD line above its signal line with a positive histogram is
    "bullish momentum" (predicts UP); below with a negative histogram is "bearish" (predicts DOWN).
    Same recompute-over-a-bounded-window approximation as `RSIMeanReversion`, for the same reason."""

    def __init__(
        self, *, fast: int = 12, slow: int = 26, signal_period: int = 9, window: int = 150, horizon_ticks: int = 10, stake: float = 1.0
    ) -> None:
        super().__init__()
        self.name = f"macd-momentum(fast={fast}, slow={slow}, signal={signal_period}, horizon={horizon_ticks})"
        self._fast, self._slow, self._signal_period = fast, slow, signal_period
        self._window = window
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if len(history) < self._slow + self._signal_period + 1:
            return None
        line, signal_line, histogram = macd(history.last_prices(self._window), self._fast, self._slow, self._signal_period)
        m, s, h = last_non_null(line), last_non_null(signal_line), last_non_null(histogram)
        if m is None or s is None or h is None:
            return None
        zone = "long" if (h > 0 and m > s) else "short" if (h < 0 and m < s) else "neutral"
        if not self._fire(zone):
            return None
        direction = Direction.UP if zone == "long" else Direction.DOWN
        return SignalDecision(Signal(direction, self._horizon), self._stake, f"MACD histogram={h:+.6f}, line {'above' if zone == 'long' else 'below'} signal")


class BollingerMeanReversion(_ZoneEdgeStrategy):
    """The classic Bollinger Bands claim: price below the lower band is "oversold" (predicts UP,
    mean-reversion), above the upper band is "overbought" (predicts DOWN)."""

    def __init__(self, *, period: int = 20, std_dev_mult: float = 2.0, window: int = 100, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        super().__init__()
        self.name = f"bollinger-mean-reversion(period={period}, horizon={horizon_ticks})"
        self._period, self._std_dev_mult = period, std_dev_mult
        self._window = window
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if len(history) < self._period:
            return None
        prices = history.last_prices(self._window)
        _middle, upper, lower = bollinger_bands(prices, self._period, self._std_dev_mult)
        u, l = last_non_null(upper), last_non_null(lower)
        if u is None or l is None:
            return None
        price = prices[-1]
        zone = "long" if price < l else "short" if price > u else "neutral"
        if not self._fire(zone):
            return None
        direction = Direction.UP if zone == "long" else Direction.DOWN
        return SignalDecision(Signal(direction, self._horizon), self._stake, f"price {price:.5f} {'below lower' if zone == 'long' else 'above upper'} band")


class EMATrendFollowing(_ZoneEdgeStrategy):
    """A broader claim than `MovingAverageCrossover`: predicts UP whenever the fast EMA is above the
    slow one at all (not only at the instant of crossing), DOWN whenever it's below — "which side" only
    changes at a crossing anyway, so in practice this fires at the same moments, differing from
    `MovingAverageCrossover` in the indicator itself (EMA weights recent prices more than SMA does) and
    the default periods (12/26, conventionally paired with MACD, rather than 10/30)."""

    def __init__(self, *, fast: int = 12, slow: int = 26, window: int = 100, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        super().__init__()
        self.name = f"ema-trend(fast={fast}, slow={slow}, horizon={horizon_ticks})"
        self._fast, self._slow = fast, slow
        self._window = window
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if len(history) < self._slow:
            return None
        prices = history.last_prices(self._window)
        fast_ema = last_non_null(ema(prices, self._fast))
        slow_ema = last_non_null(ema(prices, self._slow))
        if fast_ema is None or slow_ema is None or fast_ema == slow_ema:
            return None
        zone = "long" if fast_ema > slow_ema else "short"
        if not self._fire(zone):
            return None
        direction = Direction.UP if zone == "long" else Direction.DOWN
        return SignalDecision(
            Signal(direction, self._horizon), self._stake,
            f"EMA({self._fast})={fast_ema:.5f} {'above' if zone == 'long' else 'below'} EMA({self._slow})={slow_ema:.5f}",
        )


class EngulfingBar:
    """The Engulfing Bar reversal claim from candlestick price-action trading: a candle whose body
    fully covers the prior candle's body, in the opposite direction, read as that side's buyers or
    sellers having overwhelmed the prior candle entirely — call the reversal the instant a bar
    completes that shape.

    Candle-shape patterns have no tick-level analog the way a moving average does; see `candles.py`'s
    docstring for the synthetic-bar gap this and `PinBar` share. Rule per the standard engulfing-candle
    definition used across candlestick price-action trading, not any one book's specific wording.
    """

    def __init__(self, *, bar_size: int = 10, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        self.name = f"engulfing-bar(bar_size={bar_size}, horizon={horizon_ticks})"
        self._builder = CandleBuilder(bar_size)
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if not self._builder.feed(history.last_prices(1)[0]):
            return None
        candles = self._builder.last(2)
        if len(candles) < 2:
            return None
        prev, last = candles
        if prev.bullish and not last.bullish and last.open >= prev.close and last.close <= prev.open:
            direction = Direction.DOWN
        elif not prev.bullish and last.bullish and last.open <= prev.close and last.close >= prev.open:
            direction = Direction.UP
        else:
            return None
        return SignalDecision(
            Signal(direction, self._horizon), self._stake,
            f"engulfing {direction.value}: candle {last.open:.5f}->{last.close:.5f} engulfs prior body {prev.open:.5f}->{prev.close:.5f}",
        )


class PinBar(_ZoneEdgeStrategy):
    """The Pin Bar rejection claim (a "Hammer" when it calls up, a "Shooting Star" when it calls
    down): a candle whose wick makes up most of its range on one side and almost none on the other,
    read as price probing beyond a level and being rejected back — call the direction opposite the
    long wick the instant a bar completes that shape.

    Uses `_ZoneEdgeStrategy` for the same reason RSI/MACD/Bollinger/EMA-trend do: a bar can hold the
    same shape (e.g. two hammers in a row) without that being two independent decisions. Wick and body
    are measured as a fraction of the candle's own range rather than an absolute price move, so the
    shape test is scale-free — the same ratios apply regardless of instrument or of how a real, wider
    time-based candle compares to this project's synthetic tick-count bar (see `candles.py`). Rule per
    the standard pin-bar / hammer / shooting-star definition used across candlestick price-action
    trading, not any one book's specific wording.
    """

    def __init__(
        self, *, bar_size: int = 10, wick_ratio: float = 0.66, opposite_wick_ratio: float = 0.25,
        horizon_ticks: int = 10, stake: float = 1.0,
    ) -> None:
        super().__init__()
        self.name = f"pin-bar(bar_size={bar_size}, horizon={horizon_ticks})"
        self._builder = CandleBuilder(bar_size)
        self._wick_ratio = wick_ratio
        self._opposite_wick_ratio = opposite_wick_ratio
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if not self._builder.feed(history.last_prices(1)[0]):
            return None
        candle = self._builder.last(1)[0]
        if candle.range <= 0:
            zone = "neutral"
        else:
            lower, upper = candle.lower_wick / candle.range, candle.upper_wick / candle.range
            if lower >= self._wick_ratio and upper <= self._opposite_wick_ratio:
                zone = "long"
            elif upper >= self._wick_ratio and lower <= self._opposite_wick_ratio:
                zone = "short"
            else:
                zone = "neutral"
        if not self._fire(zone):
            return None
        direction = Direction.UP if zone == "long" else Direction.DOWN
        shape = "hammer" if zone == "long" else "shooting star"
        return SignalDecision(
            Signal(direction, self._horizon), self._stake,
            f"{shape}: lower wick {candle.lower_wick / candle.range:.2f} / upper wick {candle.upper_wick / candle.range:.2f} of range {candle.range:.5f}",
        )


class InsideBar:
    """The Inside Bar breakout claim: a candle whose entire high/low range sits inside the prior
    candle's range (the "mother bar") reads as a pause, not a reversal by itself — the call only comes
    once price actually breaks back out of that range.

    A genuinely different shape from `EngulfingBar`/`PinBar`: those call a direction the instant their
    pattern completes; this one is two stages — spot the pause, then watch every subsequent tick (not
    just the next bar boundary) for the first one to cross the watched range, and call that direction.
    Forming a fresh inside bar replaces whichever range was being watched, since a new pause supersedes
    an old, still-unbroken one; a candle that merely touches (rather than strictly clears) the mother
    bar's edge is not inside and leaves the current watch alone. Rule per the standard inside-bar /
    mother-bar breakout definition used across candlestick price-action trading, not any one book's
    specific wording.
    """

    def __init__(self, *, bar_size: int = 10, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        self.name = f"inside-bar(bar_size={bar_size}, horizon={horizon_ticks})"
        self._builder = CandleBuilder(bar_size)
        self._horizon = horizon_ticks
        self._stake = stake
        self._watch_low: float | None = None
        self._watch_high: float | None = None

    def decide(self, history: History) -> SignalDecision | None:
        price = history.last_prices(1)[0]
        decision: SignalDecision | None = None
        if self._watch_low is not None and self._watch_high is not None:
            if price > self._watch_high:
                decision = SignalDecision(
                    Signal(Direction.UP, self._horizon), self._stake,
                    f"inside-bar breakout up through {self._watch_high:.5f}",
                )
            elif price < self._watch_low:
                decision = SignalDecision(
                    Signal(Direction.DOWN, self._horizon), self._stake,
                    f"inside-bar breakout down through {self._watch_low:.5f}",
                )
            if decision is not None:
                self._watch_low = self._watch_high = None
        if self._builder.feed(price):
            candles = self._builder.last(2)
            if len(candles) == 2:
                mother, inside = candles
                if inside.high < mother.high and inside.low > mother.low:
                    self._watch_low, self._watch_high = inside.low, inside.high
        return decision


REGISTRY: dict[str, Callable[[], ForexStrategy]] = {
    "random-direction": lambda: RandomDirection(),
    "ma-crossover": lambda: MovingAverageCrossover(),
    "rsi-mean-reversion": lambda: RSIMeanReversion(),
    "macd-momentum": lambda: MACDMomentum(),
    "bollinger-mean-reversion": lambda: BollingerMeanReversion(),
    "ema-trend": lambda: EMATrendFollowing(),
    "engulfing-bar": lambda: EngulfingBar(),
    "pin-bar": lambda: PinBar(),
    "inside-bar": lambda: InsideBar(),
}
