import pytest

from clicktrader.forex.model import Direction
from clicktrader.forex.strategies import (
    REGISTRY,
    BollingerMeanReversion,
    EMATrendFollowing,
    EngulfingBar,
    MACDMomentum,
    MovingAverageCrossover,
    PinBar,
    RandomDirection,
    RSIMeanReversion,
)
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


# --- RSIMeanReversion -------------------------------------------------------


def test_rsi_fires_up_once_on_a_falling_series_then_holds_quiet():
    strategy = RSIMeanReversion(period=5, window=50)
    prices = [100.0 - i for i in range(40)]  # strictly falling -> RSI pinned near 0 once past warmup
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d is not None for d in decisions]
    assert fired.count(True) == 1  # one transition into "long", then it just holds
    first = next(d for d in decisions if d is not None)
    assert first.signal.direction is Direction.UP


def test_rsi_fires_down_on_a_rising_series():
    strategy = RSIMeanReversion(period=5, window=50)
    prices = [1.0 + i for i in range(40)]  # strictly rising -> RSI pinned near 100
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    first = next(d for d in decisions if d is not None)
    assert first.signal.direction is Direction.DOWN


def test_rsi_no_signal_without_enough_history():
    strategy = RSIMeanReversion(period=14)
    assert strategy.decide(_history([1.0] * 10)) is None


# --- MACDMomentum ------------------------------------------------------------


def test_macd_fires_on_a_clear_trend():
    strategy = MACDMomentum(fast=3, slow=6, signal_period=3, window=60)
    prices = [1.0 + i * 0.01 for i in range(50)]  # a clean, steady uptrend
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d for d in decisions if d is not None]
    assert fired  # at least one bullish signal on a clean uptrend
    assert fired[0].signal.direction is Direction.UP


def test_macd_no_signal_without_enough_history():
    strategy = MACDMomentum()
    assert strategy.decide(_history([1.0] * 10)) is None


# --- BollingerMeanReversion --------------------------------------------------


def test_bollinger_fires_up_when_price_drops_below_the_lower_band():
    strategy = BollingerMeanReversion(period=10, window=30)
    prices = [1.0] * 15 + [0.5]  # a flat run then a sharp one-tick drop
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    assert decisions[-1] is not None
    assert decisions[-1].signal.direction is Direction.UP


def test_bollinger_no_signal_inside_the_bands():
    strategy = BollingerMeanReversion(period=10, window=30)
    assert strategy.decide(_history([1.0] * 15)) is None  # flat series, no variance, price == middle


# --- EMATrendFollowing -------------------------------------------------------


def test_ema_trend_fires_on_the_first_valid_side_then_holds_quiet():
    strategy = EMATrendFollowing(fast=3, slow=6, window=30)
    prices = [1.0 + i * 0.1 for i in range(20)]  # steadily rising -> fast EMA stays above slow EMA
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d is not None for d in decisions]
    assert fired.count(True) == 1  # fires once (first valid side), then holds without re-firing
    first = next(d for d in decisions if d is not None)
    assert first.signal.direction is Direction.UP


def test_ema_trend_no_signal_without_enough_history():
    strategy = EMATrendFollowing(fast=3, slow=6)
    assert strategy.decide(_history([1.0] * 4)) is None


# --- EngulfingBar -------------------------------------------------------


def test_engulfing_bar_detects_bullish_engulfing():
    strategy = EngulfingBar(bar_size=3, horizon_ticks=5, stake=2.0)
    prices = [10.0, 9.0, 8.0, 7.0, 11.0, 12.0]  # bearish candle then a larger bullish one engulfing it
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d for d in decisions if d is not None]
    assert len(fired) == 1
    assert fired[0].signal.direction is Direction.UP
    assert fired[0].signal.horizon_ticks == 5
    assert fired[0].stake == 2.0


def test_engulfing_bar_detects_bearish_engulfing():
    strategy = EngulfingBar(bar_size=3)
    prices = [8.0, 9.0, 10.0, 11.0, 7.0, 6.0]  # bullish candle then a larger bearish one engulfing it
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d for d in decisions if d is not None]
    assert len(fired) == 1
    assert fired[0].signal.direction is Direction.DOWN


def test_engulfing_bar_no_signal_without_two_completed_candles():
    strategy = EngulfingBar(bar_size=3)
    assert strategy.decide(_history([1.0, 1.1])) is None  # not even one full candle yet


def test_engulfing_bar_no_signal_when_there_is_no_body_to_engulf():
    strategy = EngulfingBar(bar_size=3)
    prices = [1.0] * 6  # flat: every candle is a doji, nothing counts as bullish or bearish
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    assert all(d is None for d in decisions)


# --- PinBar ---------------------------------------------------------------


def test_pin_bar_fires_up_on_a_hammer():
    strategy = PinBar(bar_size=3, horizon_ticks=6, stake=1.5)
    prices = [10.0, 7.0, 9.8]  # long lower wick, closes near the top -> hammer
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d for d in decisions if d is not None]
    assert len(fired) == 1
    assert fired[0].signal.direction is Direction.UP
    assert fired[0].signal.horizon_ticks == 6
    assert fired[0].stake == 1.5


def test_pin_bar_fires_down_on_a_shooting_star():
    strategy = PinBar(bar_size=3)
    prices = [10.0, 13.0, 10.2]  # long upper wick, closes near the bottom -> shooting star
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d for d in decisions if d is not None]
    assert len(fired) == 1
    assert fired[0].signal.direction is Direction.DOWN


def test_pin_bar_no_signal_on_a_balanced_candle():
    strategy = PinBar(bar_size=3)
    assert strategy.decide(_history([10.0, 11.0, 10.5])) is None


def test_pin_bar_no_signal_without_a_completed_candle():
    strategy = PinBar(bar_size=3)
    assert strategy.decide(_history([1.0, 1.1])) is None


def test_pin_bar_does_not_refire_on_consecutive_matching_shapes():
    strategy = PinBar(bar_size=3)
    prices = [10.0, 7.0, 9.8, 10.0, 7.0, 9.8]  # two hammers back to back
    decisions = [strategy.decide(_history(prices[: i + 1])) for i in range(len(prices))]
    fired = [d is not None for d in decisions]
    assert fired.count(True) == 1


def test_forex_registry_has_all_eight_strategies():
    assert set(REGISTRY) == {
        "random-direction", "ma-crossover", "rsi-mean-reversion", "macd-momentum",
        "bollinger-mean-reversion", "ema-trend", "engulfing-bar", "pin-bar",
    }
