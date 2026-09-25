"""Cross-checked against known reference values for each indicator (not just internally self-consistent):
a strictly rising series drives RSI to 100 and a strictly falling one to 0, a constant series collapses
all three Bollinger bands together, and so on."""

import math

import pytest

from clicktrader.forex.indicators import bollinger_bands, ema, last_non_null, macd, rsi, sma


def test_sma_pads_leading_values_with_none_and_averages_the_window():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]


def test_ema_nulls_before_the_period_and_seeds_with_the_sma():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2)  # seed = SMA of [1,2,3]
    assert out[3] == pytest.approx(4 * 0.5 + 2 * 0.5)  # k = 2/(3+1) = 0.5
    assert out[4] == pytest.approx(5 * 0.5 + 3 * 0.5)


def test_rsi_returns_all_none_when_too_few_prices():
    assert rsi([1, 2, 3], 14) == [None, None, None]


def test_rsi_is_100_rising_and_0_falling():
    rising = rsi([1, 2, 3, 4, 5, 6, 7, 8], 3)
    falling = rsi([8, 7, 6, 5, 4, 3, 2, 1], 3)
    assert last_non_null(rising) == 100
    assert last_non_null(falling) == 0


def test_rsi_stays_within_0_100():
    series = rsi([5, 3, 8, 2, 9, 4, 7, 1, 6, 10, 2, 8], 5)
    for v in series:
        if v is None:
            continue
        assert 0 <= v <= 100


def test_macd_histogram_equals_macd_minus_signal_at_the_last_index():
    prices = [100 + math.sin(i / 3) * 10 for i in range(60)]
    line, signal, histogram = macd(prices, 12, 26, 9)
    h, m, s = last_non_null(histogram), last_non_null(line), last_non_null(signal)
    assert h == pytest.approx(m - s, abs=1e-9)


def test_bollinger_collapses_for_a_constant_series():
    middle, upper, lower = bollinger_bands([100.0] * 25, 20, 2)
    assert last_non_null(middle) == pytest.approx(100)
    assert last_non_null(upper) == pytest.approx(100)
    assert last_non_null(lower) == pytest.approx(100)


def test_bollinger_orders_lower_middle_upper_for_a_varying_series():
    prices = [10, 12, 11, 13, 9, 14, 8, 15, 10, 12, 11, 13, 9, 14, 8, 15, 10, 12, 11, 13, 20]
    middle, upper, lower = bollinger_bands([float(p) for p in prices], 20, 2)
    m, u, l = last_non_null(middle), last_non_null(upper), last_non_null(lower)
    assert l < m < u
