"""Synthetic OHLC candles built from ticks, two ways: by tick count, and by wall clock.

`indicators.py` documents the same gap: layer 1 records ticks, not candles, and applies textbook
formulas to raw tick prices instead of grouping them first. That works for a moving average or RSI,
which are just arithmetic over a price series either way. Candlestick shape patterns (an engulfing
body, a pin bar's wick) have no tick-level analog at all — a "body" and a "wick" only exist once ticks
are grouped into an open/high/low/close bar.

`CandleBuilder` groups by tick *count* — "a candle here is `bar_size` consecutive ticks, not a wall-clock
time window (an hourly candle, say)" — which is the right bar for a shape pattern applied to a feed whose
tick rate is roughly constant, and the only bar this project had until a strategy arrived that is written
against a chart. `TimeCandleBuilder` groups by the *clock*, for exactly that case: a method that says
"the 15-minute candle that tested yesterday's low" means the interval a chart draws, and a tick-count bar
is not that bar however similar the arithmetic looks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


class CandleBuilder:
    """Groups ticks into `bar_size`-tick candles incrementally, one `feed()` call per tick in order —
    the same assumption the zone-edge strategies already make about `decide()` being called once per
    tick with a monotonically growing `History` (`strategies.py`'s `_ZoneEdgeStrategy`). Incremental
    rather than rebuilding from the full tick history each call keeps a strategy's per-tick cost
    constant instead of growing with how much history has accumulated.
    """

    def __init__(self, bar_size: int) -> None:
        if bar_size < 1:
            raise ValueError("bar_size must be at least 1")
        self._bar_size = bar_size
        self._buffer: list[float] = []
        self._completed: list[Candle] = []

    def feed(self, price: float) -> bool:
        """Add the next tick's price. Returns True the instant this completes a new candle."""
        self._buffer.append(price)
        if len(self._buffer) < self._bar_size:
            return False
        chunk, self._buffer = self._buffer, []
        self._completed.append(Candle(open=chunk[0], high=max(chunk), low=min(chunk), close=chunk[-1]))
        return True

    def last(self, count: int) -> list[Candle]:
        """The most recently completed candles, oldest first, at most `count` of them."""
        return self._completed[-count:] if count > 0 else []


@dataclass(frozen=True)
class TimedCandle(Candle):
    """A `Candle` that also knows which clock interval it covers."""

    opened_at: float
    """Start of the interval, epoch seconds: the candle covers `[opened_at, opened_at + interval)`."""


class TimeCandleBuilder:
    """Groups ticks into fixed wall-clock candles, `interval_seconds` each, aligned to the epoch.

    Only ticks decide when a candle closes — the candle for one interval completes when the first tick of
    a later interval arrives. Nothing is ever clocked in on its own, so a thin or halted feed leaves the
    current candle open rather than producing candles nothing traded in, and intervals that received no
    ticks at all are skipped instead of being emitted as zero-range candles: a market closure has to look
    like a gap, not like a stretch of perfectly flat prices.

    Ticks must arrive in time order. One that arrives before the candle it would belong to has already
    been seen is a genuine contradiction (two prices for the same instant, in the wrong order), so it
    raises rather than quietly dropping or back-filling — the same reason `stats` refuses to report on a
    sample too small to mean anything instead of printing a number anyway.
    """

    def __init__(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._interval = float(interval_seconds)
        self._bucket: int | None = None
        self._buffer: list[float] = []
        self._completed: list[TimedCandle] = []

    def bucket_of(self, ts: float) -> int:
        """Which candle `ts` belongs to — integer index since the epoch."""
        return int(ts // self._interval)

    def feed(self, ts: float, price: float) -> TimedCandle | None:
        """Add one tick. Returns the candle this tick just completed, if it completed one."""
        bucket = self.bucket_of(ts)
        if self._bucket is None:
            self._bucket = bucket
            self._buffer = [price]
            return None
        if bucket < self._bucket:
            raise ValueError(
                f"tick at ts={ts} belongs to an earlier candle (bucket {bucket} < {self._bucket}) — "
                "a feed has to arrive in time order for a wall-clock bar to mean anything"
            )
        if bucket == self._bucket:
            self._buffer.append(price)
            return None
        closed = TimedCandle(
            open=self._buffer[0], high=max(self._buffer), low=min(self._buffer), close=self._buffer[-1],
            opened_at=self._bucket * self._interval,
        )
        self._completed.append(closed)
        self._bucket = bucket
        self._buffer = [price]
        return closed

    def last(self, count: int) -> list[TimedCandle]:
        """The most recently completed candles, oldest first, at most `count` of them."""
        return self._completed[-count:] if count > 0 else []
