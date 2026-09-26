"""Synthetic OHLC candles built from ticks.

`indicators.py` documents the same gap: layer 1 records ticks, not candles, and applies textbook
formulas to raw tick prices instead of grouping them first. That works for a moving average or RSI,
which are just arithmetic over a price series either way. Candlestick shape patterns (an engulfing
body, a pin bar's wick) have no tick-level analog at all — a "body" and a "wick" only exist once ticks
are grouped into an open/high/low/close bar. A candle here is `bar_size` consecutive ticks, not a
wall-clock time window (an hourly candle, say) — same math as the classic pattern, a genuinely
different (much higher-frequency, noisier) bar underneath it.
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
