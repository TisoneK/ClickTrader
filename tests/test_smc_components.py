"""The order block as an object, and the three-factor scorecard over it."""

import pytest

from clicktrader.forex.candles import TimedCandle
from clicktrader.forex.model import Direction
from clicktrader.smc.components import order_block
from clicktrader.smc.quality import assess, pushed_distance


def _bars(*specs):
    return [TimedCandle(open=o, high=h, low=l, close=c, opened_at=float(i)) for i, (o, h, l, c) in enumerate(specs)]


# A prior swing high at 101.6 (index 2, two bars clear on each side), a down candle at index 5 to box, then
# a displacement out of it that leaves a rising gap and breaks that swing high at index 7.
_SERIES = [
    (100.2, 100.4, 100.0, 100.2),
    (100.2, 100.8, 100.1, 100.6),
    (100.6, 101.6, 100.5, 101.2),  # the prior swing high the move will break
    (101.2, 101.4, 100.6, 100.8),
    (100.8, 100.9, 100.2, 100.4),
    (100.4, 100.6, 99.4, 99.5),    # the order block
    (99.5, 101.0, 99.4, 100.9),    # displacement out of it; leaves a gap
    (100.9, 103.0, 100.8, 102.9),  # breaks 101.6
    (102.9, 104.0, 102.8, 103.8),  # the extreme, 3.4 bands from the block
]
_BLOCK_INDEX = 5


def _block():
    return order_block(_bars(*_SERIES), index=_BLOCK_INDEX)


def test_an_order_block_is_one_candle_boxed_wick_to_wick():
    block = _block()
    assert (block.price_low, block.price_high) == (99.4, 100.6)
    assert block.index == _BLOCK_INDEX
    assert block.direction is Direction.UP  # taken from the move that followed, not the candle's colour
    assert block.size == pytest.approx(1.2)


def test_the_stop_goes_beyond_the_wick_on_the_losing_side():
    # the entry goes at the block, so this level is the whole risk of the trade
    assert _block().stop_level == pytest.approx(99.4)


def test_the_direction_comes_from_the_move_not_the_candle():
    # same series with the block's colour flipped: the move still went up, so the block still points up
    flipped = list(_SERIES)
    o, h, l, c = flipped[_BLOCK_INDEX]
    flipped[_BLOCK_INDEX] = (l, h, l, o)
    assert order_block(_bars(*flipped), index=_BLOCK_INDEX).direction is Direction.UP


def test_the_block_records_the_gap_the_move_left():
    block = _block()
    assert block.gap is not None
    assert block.gap.direction is Direction.UP


def test_the_last_candle_cannot_be_an_order_block():
    with pytest.raises(ValueError):
        order_block(_bars(*_SERIES), index=len(_SERIES) - 1)


# --- the scorecard -------------------------------------------------------------------------------


def test_pushed_distance_is_measured_in_bands():
    bars = _bars(*_SERIES)
    block = order_block(bars, index=_BLOCK_INDEX)
    # the extreme is 104.0 and the block's top is 100.6, so 3.4 points; the unit is the typical candle
    assert pushed_distance(bars, block=block, band=1.0) == pytest.approx(3.4)
    assert pushed_distance(bars, block=block, band=1.7) == pytest.approx(2.0)  # same move, wider candles


def test_a_distance_needs_a_unit():
    bars = _bars(*_SERIES)
    with pytest.raises(ValueError):
        pushed_distance(bars, block=order_block(bars, index=_BLOCK_INDEX), band=0.0)


def test_the_scorecard_answers_all_three_questions():
    bars = _bars(*_SERIES)
    quality = assess(bars, block=order_block(bars, index=_BLOCK_INDEX), band=1.0, min_pushed=3.0)
    assert quality.complete
    assert "inefficiency: yes" in quality.reason
    assert "structure: yes" in quality.reason
    assert "3.4 bands" in quality.reason


def test_the_scorecard_names_the_factor_that_failed():
    # a move that went nowhere near far enough is not a valid zone however clean everything else is
    bars = _bars(*_SERIES)
    quality = assess(bars, block=order_block(bars, index=_BLOCK_INDEX), band=1.0, min_pushed=10.0)
    assert not quality.complete
    assert "needs 10.0" in quality.reason


def test_no_break_of_structure_is_reported_as_no():
    # the same block with no prior swing to break: the displacement goes up, but nothing was shattered
    bars = _bars(*_SERIES[5:])
    quality = assess(bars, block=order_block(bars, index=0), band=1.0, min_pushed=3.0)
    assert not quality.structure_broken
    assert "structure: NO" in quality.reason
