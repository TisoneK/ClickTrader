import pytest

from clicktrader.forex.model import Direction
from clicktrader.forex.strategies import MovingAverageCrossover, RandomDirection
from clicktrader.model import Tick
from clicktrader.strategies import History


def _history(prices: list[float]) -> History:
    ticks = [Tick(i, str(p)) for i, p in enumerate(prices)]
    return History(ticks, len(ticks))


def test_short_window_must_be_smaller_than_long_window():
    with pytest.raises(ValueError):
        MovingAverageCrossover(short_window=10, long_window=10)


def test_no_signal_without_enough_history():
    strategy = MovingAverageCrossover(short_window=2, long_window=4)
    assert strategy.decide(_history([1.0, 1.0, 1.0, 1.0])) is None  # needs long+1 = 5


def test_no_signal_on_a_flat_series():
    strategy = MovingAverageCrossover(short_window=2, long_window=4)
    assert strategy.decide(_history([1.0] * 6)) is None


def test_detects_a_crossing_up():
    strategy = MovingAverageCrossover(short_window=2, long_window=4, horizon_ticks=7, stake=2.0)
    decision = strategy.decide(_history([1.0, 1.0, 1.0, 1.0, 1.0, 3.0]))
    assert decision is not None
    assert decision.signal.direction is Direction.UP
    assert decision.signal.horizon_ticks == 7
    assert decision.stake == 2.0


def test_detects_a_crossing_down():
    strategy = MovingAverageCrossover(short_window=2, long_window=4)
    decision = strategy.decide(_history([1.0, 1.0, 1.0, 1.0, 1.0, -1.0]))
    assert decision is not None
    assert decision.signal.direction is Direction.DOWN


def test_does_not_fire_again_while_merely_staying_on_one_side():
    # after the initial cross up, staying above the long MA without a fresh cross should not re-fire
    strategy = MovingAverageCrossover(short_window=2, long_window=4)
    prices = [1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 3.1, 3.2]
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(4, len(prices))]
    fired = [d is not None for d in decisions]
    # index 4 (only 5 prices, all flat): no signal yet; index 5: the cross itself fires; then it settles
    # above the long MA without crossing again, so indices 6-7 correctly stay quiet.
    assert fired == [False, True, False, False]


def test_random_direction_is_deterministic_per_seed():
    a = RandomDirection(seed=1, bet_probability=1.0)
    b = RandomDirection(seed=1, bet_probability=1.0)
    history = _history([1.0, 1.0])
    assert a.decide(history).signal.direction == b.decide(history).signal.direction


def test_random_direction_can_pass():
    strategy = RandomDirection(seed=1, bet_probability=0.0)
    assert strategy.decide(_history([1.0])) is None
