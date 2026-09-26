import pytest

from clicktrader.forex.candles import Candle, CandleBuilder


def test_candle_shape_properties():
    c = Candle(open=1.0, high=1.5, low=0.8, close=1.2)
    assert c.bullish is True
    assert c.body == pytest.approx(0.2)
    assert c.range == pytest.approx(0.7)
    assert c.upper_wick == pytest.approx(0.3)
    assert c.lower_wick == pytest.approx(0.2)


def test_candle_bearish_when_close_below_open():
    assert Candle(open=1.2, high=1.3, low=1.0, close=1.0).bullish is False


def test_builder_rejects_non_positive_bar_size():
    with pytest.raises(ValueError):
        CandleBuilder(0)


def test_builder_only_signals_true_when_a_bar_completes():
    builder = CandleBuilder(3)
    assert builder.feed(1.0) is False
    assert builder.feed(1.1) is False
    assert builder.feed(1.2) is True  # third tick completes the first candle


def test_builder_groups_ticks_into_ohlc():
    builder = CandleBuilder(3)
    for price in (1.0, 1.5, 0.9):
        builder.feed(price)
    candle = builder.last(1)[0]
    assert candle.open == 1.0
    assert candle.high == 1.5
    assert candle.low == 0.9
    assert candle.close == 0.9


def test_builder_keeps_completed_candles_across_multiple_bars():
    builder = CandleBuilder(2)
    for price in (1.0, 1.1, 1.2, 1.3, 1.4, 1.0):
        builder.feed(price)
    candles = builder.last(3)
    assert len(candles) == 3
    assert [c.close for c in candles] == [1.1, 1.3, 1.0]


def test_last_with_fewer_completed_candles_than_requested():
    builder = CandleBuilder(2)
    builder.feed(1.0)
    builder.feed(1.1)
    assert len(builder.last(5)) == 1


def test_last_with_zero_or_negative_count_returns_empty():
    builder = CandleBuilder(1)
    builder.feed(1.0)
    assert builder.last(0) == []
    assert builder.last(-1) == []
