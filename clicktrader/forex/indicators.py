"""Standard technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands) — the ordinary textbook
formulas, operating on raw prices (a `list[float]` of closes) rather than OHLC candles, since layer 1
here only records ticks, not candles.

That's a real difference, not a formality: these indicators are normally computed on candles at some
chosen timeframe (e.g. hourly), and this project applies the identical formulas directly to 1-second
tick prices instead. Same math, a genuinely different (much higher-frequency, noisier) question — see
`strategies.py`'s docstrings for each strategy built on these.
"""

from __future__ import annotations


def sma(prices: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(prices)):
        if i < period - 1:
            out.append(None)
            continue
        out.append(sum(prices[i - period + 1 : i + 1]) / period)
    return out


def ema(prices: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    k = 2 / (period + 1)
    prev: float | None = None
    for i in range(len(prices)):
        if i < period - 1:
            out.append(None)
            continue
        if prev is None:
            prev = sum(prices[i - period + 1 : i + 1]) / period  # seed with the SMA
        else:
            prev = prices[i] * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(prices: list[float], period: int = 14) -> list[float | None]:
    if len(prices) < period + 1:
        return [None] * len(prices)

    out: list[float | None] = [None] * len(prices)
    avg_gain = avg_loss = 0.0
    for i in range(1, period + 1):
        change = prices[i] - prices[i - 1]
        if change >= 0:
            avg_gain += change
        else:
            avg_loss -= change
    avg_gain /= period
    avg_loss /= period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)

    for i in range(period + 1, len(prices)):
        change = prices[i] - prices[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def macd(
    prices: list[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """(macd_line, signal_line, histogram) — the signal line is an EMA of the MACD line itself, seeded
    only once the MACD line has enough non-null values of its own to seed an EMA."""
    fast_ema = ema(prices, fast_period)
    slow_ema = ema(prices, slow_period)
    macd_line: list[float | None] = [
        None if f is None or s is None else f - s for f, s in zip(fast_ema, slow_ema)
    ]

    start = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line: list[float | None] = [None] * len(prices)
    if start is not None and len(prices) - start >= signal_period:
        macd_values = [v for v in macd_line[start:] if v is not None]
        signal_trimmed = ema(macd_values, signal_period)
        for offset, value in enumerate(signal_trimmed):
            signal_line[start + offset] = value

    histogram: list[float | None] = [
        None if m is None or s is None else m - s for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, histogram


def bollinger_bands(
    prices: list[float], period: int = 20, std_dev_mult: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """(middle, upper, lower) — middle is the SMA; upper/lower are ± `std_dev_mult` population
    standard deviations (divide by `period`, not `period - 1` — matches Proxigrid exactly)."""
    middle = sma(prices, period)
    upper: list[float | None] = []
    lower: list[float | None] = []
    for i in range(len(prices)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
            continue
        mean = middle[i]
        assert mean is not None
        window = prices[i - period + 1 : i + 1]
        variance = sum((p - mean) ** 2 for p in window) / period
        std = variance**0.5
        upper.append(mean + std_dev_mult * std)
        lower.append(mean - std_dev_mult * std)
    return middle, upper, lower


def last_non_null(series: list[float | None]) -> float | None:
    for value in reversed(series):
        if value is not None:
            return value
    return None
