import pytest

from clicktrader.forex.candles import Candle, CandleBuilder, TimeCandleBuilder, TimedCandle


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


# --- wall-clock candles -------------------------------------------------------------------------


def test_timed_candle_inherits_the_shape():
    c = TimedCandle(open=1.0, high=1.5, low=0.8, close=1.2, opened_at=900.0)
    assert isinstance(c, Candle)
    assert c.bullish is True
    assert c.body == pytest.approx(0.2)
    assert c.opened_at == 900.0


def test_interval_must_be_positive():
    with pytest.raises(ValueError):
        TimeCandleBuilder(0)


def test_a_candle_closes_only_when_a_tick_from_a_later_interval_arrives():
    builder = TimeCandleBuilder(900)  # 15 minutes
    assert builder.feed(0.0, 1.10) is None
    assert builder.feed(500.0, 1.12) is None
    assert builder.feed(899.0, 1.11) is None
    closed = builder.feed(900.0, 1.13)
    assert closed is not None
    assert closed.opened_at == 0.0
    assert (closed.open, closed.high, closed.low, closed.close) == (1.10, 1.12, 1.10, 1.11)


def test_candles_are_aligned_to_the_epoch_not_to_the_first_tick():
    # a tick arriving mid-interval belongs to the interval the clock says, not to a fresh candle --
    # otherwise two runs over the same recording would disagree depending on when they started
    builder = TimeCandleBuilder(900)
    builder.feed(1800.0, 1.10)
    assert builder.bucket_of(1800.0) == 2
    assert builder.bucket_of(2699.0) == 2
    assert builder.bucket_of(2700.0) == 3
    assert builder.feed(2700.0, 1.11).opened_at == 1800.0


def test_intervals_with_no_ticks_are_skipped_not_invented():
    # a market closure has to look like a gap; emitting zero-range candles for it would fake flat prices
    builder = TimeCandleBuilder(900)
    builder.feed(0.0, 1.10)
    closed = builder.feed(900 * 40, 1.20)
    assert closed is not None and closed.opened_at == 0.0
    assert len(builder.last(100)) == 1  # 39 empty intervals produced nothing


def test_wall_clock_bars_and_tick_count_bars_are_not_the_same_bar():
    # the same six ticks, grouped both ways: the point of having both builders is that they disagree,
    # and the wall-clock bar is the one that means what a chart means
    ticks = [(t, p) for t, p in zip((0.0, 1.0, 2.0, 3.0, 4.0, 5.0), (1.0, 1.1, 1.2, 1.3, 1.4, 1.5))]
    by_count = CandleBuilder(3)
    for _ts, price in ticks:
        by_count.feed(price)
    by_time = TimeCandleBuilder(2.5)
    for ts, price in ticks:
        by_time.feed(ts, price)
    assert [c.close for c in by_count.last(2)] == [1.2, 1.5]  # intervals of 3 ticks
    # the wall-clock bar covers [0,2.5) and [2.5,5); the interval holding only the last tick is still
    # open, since a candle only closes when a later one is traded in
    assert [c.close for c in by_time.last(2)] == [1.2, 1.4]
    assert [c.opened_at for c in by_time.last(2)] == [0.0, 2.5]
    assert not hasattr(by_count.last(1)[0], "opened_at")


def test_out_of_order_ticks_raise():
    builder = TimeCandleBuilder(900)
    builder.feed(900.0, 1.10)
    with pytest.raises(ValueError):
        builder.feed(0.0, 1.11)


def test_last_with_zero_or_negative_count_returns_empty_for_timed_candles():
    builder = TimeCandleBuilder(900)
    builder.feed(0.0, 1.0)
    builder.feed(900.0, 1.0)
    assert builder.last(0) == []
    assert builder.last(-1) == []
