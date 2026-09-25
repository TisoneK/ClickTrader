import pytest

from clicktrader.forex.model import Direction, Signal


def test_up_wins_only_on_a_strictly_higher_exit():
    signal = Signal(Direction.UP, horizon_ticks=5)
    assert signal.wins(entry_price=1.1000, exit_price=1.1001)
    assert not signal.wins(entry_price=1.1000, exit_price=1.1000)  # a tie loses, same as no "allow equals"
    assert not signal.wins(entry_price=1.1000, exit_price=1.0999)


def test_down_wins_only_on_a_strictly_lower_exit():
    signal = Signal(Direction.DOWN, horizon_ticks=5)
    assert signal.wins(entry_price=1.1000, exit_price=1.0999)
    assert not signal.wins(entry_price=1.1000, exit_price=1.1000)
    assert not signal.wins(entry_price=1.1000, exit_price=1.1001)


def test_horizon_must_be_positive():
    with pytest.raises(ValueError):
        Signal(Direction.UP, horizon_ticks=0)


def test_str():
    assert str(Signal(Direction.UP, 10)) == "up over 10"
