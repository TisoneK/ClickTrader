"""The price-action method's own triggers — the tests that were missing when they broke.

`PurePriceAction` shipped with no tests of its two setups, so when the level tolerance changed meaning
from a fraction of price to a multiple of the candle range, two things broke silently: every swing within
100% of price clustered into one meaningless level, and the breakout test became unreachable so no retest
setup could ever fire. Nothing failed; the setups just stopped existing. These tests exist so that class of
change fails loudly instead.
"""

import pytest

from clicktrader.forex.candles import TimedCandle
from clicktrader.forex.model import Direction
from clicktrader.forex.strategies import PurePriceAction, _typical_range
from clicktrader.forex.structure import KeyZone, SwingKind


def _bar(o, h, l, c, ts):
    return TimedCandle(open=o, high=h, low=l, close=c, opened_at=ts)


def _seed_bars(strategy, *, n, price=100.0, rng=1.0, step=60.0):
    """Fill the strategy's bar builder with `n` ordinary bars of roughly `rng` range."""
    for i in range(n):
        strategy._bars.feed(float(i * step), price)
        strategy._bars.feed(float(i * step), price + rng)
        strategy._bars.feed(float(i * step), price - rng / 2)
        strategy._bars.feed(float(i * step), price + rng / 2)


def test_the_typical_range_is_the_median_candle_range():
    candles = [_bar(1.0, 1.0 + r, 1.0, 1.0, float(i)) for i, r in enumerate((1.0, 1.0, 1.0, 50.0))]
    assert _typical_range(candles, 4) == pytest.approx(1.0)  # the outlier does not set the width


def test_swings_further_apart_than_a_candle_are_not_one_level():
    # the bug this guards: with the tolerance read as a fraction of price, a band of 1.0 x price swallowed
    # every swing on the chart into a single level, so the method was trading one meaningless zone a side
    from clicktrader.forex.structure import key_zones

    swings = [10.0, 20.0, 30.0, 40.0]  # far apart relative to a 1.0 candle
    candles = []
    for i, price in enumerate(swings):
        peak = price
        candles.append(_bar(peak - 0.4, peak, peak - 0.6, peak - 0.3, float(i * 2)))
        candles.append(_bar(peak - 0.3, peak - 0.1, peak - 0.9, peak - 0.5, float(i * 2 + 1)))
    band = 1.0  # one candle range: only genuinely coincident swings should cluster
    faces = key_zones(candles, strength=1, min_touches=2, band=band)
    assert faces == []  # no two of these are within one candle of each other
    assert key_zones(candles, strength=1, min_touches=2, band=20.0) != []  # a wide band does cluster them


def test_a_close_barely_past_a_level_is_not_a_breakout():
    strategy = PurePriceAction(bar_minutes=1, level_tolerance=1.0, lookback=5)
    _seed_bars(strategy, n=5, price=100.0, rng=1.0)
    zone = KeyZone(price=100.0, touches=2, kind=SwingKind.HIGH)
    strategy._note_breaks(_bar(100.4, 100.6, 100.2, 100.5, 400.0), [zone])
    assert strategy._broken == {}  # half a candle past the level is not a break


def test_a_close_well_past_a_level_is_a_breakout():
    strategy = PurePriceAction(bar_minutes=1, level_tolerance=1.0, lookback=5)
    _seed_bars(strategy, n=5, price=100.0, rng=1.0)
    zone = KeyZone(price=100.0, touches=2, kind=SwingKind.HIGH)
    strategy._note_breaks(_bar(100.5, 103.0, 100.4, 102.5, 400.0), [zone])
    assert strategy._broken == {100.0: Direction.UP}
    strategy._note_breaks(_bar(99.5, 99.6, 97.0, 97.5, 460.0), [zone])
    assert strategy._broken == {100.0: Direction.DOWN}
