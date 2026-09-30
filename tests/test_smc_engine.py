"""The engine's three-way classification, which is the whole point of the module.

A break can be a genuine change of character, a liquidity sweep, or a gap being filled — and the material's
claim is that the last two are *not* reversals. So each case gets a fixture that is identical except for the
one thing that distinguishes it, which is what makes the tests evidence rather than decoration.
"""

import pytest

from clicktrader.forex.candles import TimedCandle
from clicktrader.forex.model import Direction
from clicktrader.forex.structure import SwingKind
from clicktrader.smc.engine import (
    BreakKind,
    Control,
    ControlMachine,
    classify_break,
    liquidity_pools,
)


def _bars(*specs):
    return [TimedCandle(open=o, high=h, low=l, close=c, opened_at=float(i)) for i, (o, h, l, c) in enumerate(specs)]


# Two swing lows at exactly 100.0, a level the market has turned at twice — the material's "$ liquidity $".
_TWO_LOWS = [
    (101.5, 102.0, 101.0, 101.6),
    (101.6, 101.8, 100.0, 100.8),
    (100.8, 102.0, 100.6, 101.8),
    (101.8, 102.0, 100.0, 100.6),
    (100.6, 101.6, 100.4, 101.4),
]
_BAND = 0.5


def test_a_level_needs_more_than_one_turn_to_be_a_pool():
    once = _bars(*_TWO_LOWS[:3])
    assert liquidity_pools(once, strength=1, band=_BAND, min_touches=2) == []
    twice = _bars(*_TWO_LOWS)
    (pool,) = liquidity_pools(twice, strength=1, band=_BAND, min_touches=2)
    assert pool.price == pytest.approx(100.0)
    assert pool.kind is SwingKind.LOW
    assert pool.touches == 2
    assert "stops" in pool.holds_stops


def test_a_break_that_closes_through_with_no_gap_at_the_level_is_a_change_of_character():
    candles = _bars(*_TWO_LOWS, (100.5, 100.7, 97.6, 98.2))
    result = classify_break(candles, index=5, level=100.0, direction=Direction.DOWN)
    assert result.kind is BreakKind.CHANGE_OF_CHARACTER
    assert result.flips_control
    assert "no unfilled gap" in result.reason


def test_a_wick_through_that_closes_back_is_a_liquidity_sweep_not_a_reversal():
    # the same fixture, changed only in where the breaking bar closed
    candles = _bars(*_TWO_LOWS, (100.5, 100.7, 97.6, 100.5))
    result = classify_break(candles, index=5, level=100.0, direction=Direction.DOWN)
    assert result.kind is BreakKind.LIQUIDITY_SWEEP
    assert not result.flips_control
    assert "stops at that level were taken" in result.reason


def test_a_close_through_an_older_unfilled_gap_is_mitigation_not_a_reversal():
    # the material's picture: a *bullish* gap left behind by an earlier rally, sitting below price, with the
    # swing low inside it — and price falling back into the gap later. The gap has to predate the break.
    candles = _bars(
        (99.0, 99.5, 98.8, 99.4),      # candle 1 of the gap: high 99.5
        (99.4, 101.0, 99.3, 100.9),    # the rally that leaves it
        (100.9, 101.5, 99.8, 101.2),   # candle 3: low 99.8 -> gap 99.5-99.8
        (101.2, 101.6, 100.4, 100.6),  # stays above the gap, so it stays unfilled
        (100.6, 100.8, 99.4, 99.55),   # the break: falls through the level inside the gap
    )
    result = classify_break(candles, index=4, level=99.65, direction=Direction.DOWN)
    assert result.kind is BreakKind.GAP_MITIGATION
    assert not result.flips_control
    assert result.gap is not None
    assert "rebalancing" in result.reason


def test_a_gap_created_by_the_breaking_move_does_not_excuse_the_break():
    # the bug this guards, found by running the whole stack over a real recording: a gap needs three candles,
    # so one whose middle candle is the breaking bar was left by this move rather than before it. Counting it
    # meant every sharp break excused itself as "rebalancing" and no change of character could ever form.
    candles = _bars(
        (101.0, 101.5, 100.9, 101.2),
        (101.2, 101.3, 99.5, 99.6),    # the middle candle of a gap that contains 100.0...
        (99.6, 99.0, 98.4, 98.6),      # ...and its third candle, which is also the break
    )
    result = classify_break(candles, index=2, level=100.0, direction=Direction.DOWN)
    assert result.kind is BreakKind.CHANGE_OF_CHARACTER


def test_a_gap_that_was_already_filled_does_not_excuse_the_break():
    # the same shape, but price came back into the gap on a *later* bar and filled it, so this break is not
    # the mitigation. (Getting this fixture right took the test failing first: the candle that completes a
    # gap is part of the gap's own definition, not a later visit to it.)
    candles = _bars(
        (101.0, 101.5, 100.9, 101.2),  # candle 1 of the gap: low 100.9
        (101.2, 101.3, 99.5, 99.6),    # candle 2, the displacement
        (99.6, 99.9, 98.9, 99.0),      # candle 3 of the gap: high 99.9 -> gap 99.9-100.9
        (99.0, 100.5, 98.8, 100.2),    # a later bar trades back up into it, filling it
        (100.2, 100.3, 97.6, 98.2),    # now a clean close below the level
    )
    result = classify_break(candles, index=4, level=100.0, direction=Direction.DOWN)
    assert result.kind is BreakKind.CHANGE_OF_CHARACTER


def test_a_bar_that_never_reached_the_level_is_reported_as_neither():
    candles = _bars(*_TWO_LOWS, (101.0, 101.5, 100.8, 101.2))
    result = classify_break(candles, index=5, level=100.0, direction=Direction.DOWN)
    assert result.kind is BreakKind.NO_BREAK
    assert not result.flips_control
    assert "never reached" in result.reason


# --- the machine ---------------------------------------------------------------------------------


def test_control_transfers_on_a_genuine_change_of_character():
    machine = ControlMachine(band=_BAND, strength=1, initial=Control.DEMAND)
    candles = _bars(*_TWO_LOWS, (100.5, 100.7, 97.6, 98.2))
    result = machine.consider(candles, index=5)
    assert result is not None and result.flips_control
    assert machine.control is Control.SUPPLY
    assert "change-of-character" in machine.reason


def test_control_survives_a_sweep():
    # the event that would otherwise be read as a reversal, and is the reason this module exists
    machine = ControlMachine(band=_BAND, strength=1, initial=Control.DEMAND)
    candles = _bars(*_TWO_LOWS, (100.5, 100.7, 97.6, 100.5))
    result = machine.consider(candles, index=5)
    assert result is not None and result.kind is BreakKind.LIQUIDITY_SWEEP
    assert machine.control is Control.DEMAND  # unchanged


def test_a_bar_that_threatens_nothing_reports_nothing():
    machine = ControlMachine(band=_BAND, strength=1, initial=Control.DEMAND)
    candles = _bars(*_TWO_LOWS, (101.0, 101.5, 100.8, 101.2))
    assert machine.consider(candles, index=5) is None
    assert machine.control is Control.DEMAND


def test_a_pool_above_is_ignored_while_demand_is_in_control():
    # only the losing side's pools can take control away, which is what keeps the machine two-state
    machine = ControlMachine(band=_BAND, strength=1, initial=Control.DEMAND)
    candles = _bars(
        (99.0, 99.2, 98.5, 98.8),
        (98.8, 100.0, 98.6, 99.2),
        (99.2, 98.9, 98.4, 98.6),
        (98.6, 100.0, 98.5, 99.4),
        (99.4, 99.6, 98.8, 99.0),
    )
    assert machine.control is Control.DEMAND
    assert machine.consider(candles, index=4) is None  # a high-side pool, not the losing side


def test_a_level_with_no_width_is_refused():
    with pytest.raises(ValueError):
        ControlMachine(band=0.0)
    with pytest.raises(ValueError):
        ControlMachine(band=_BAND).consider(_bars(*_TWO_LOWS), index=99)


def test_sitting_below_a_level_is_not_breaking_it_again():
    # the bug that hid behind 62,566 declines on a real recording: `bar.low < level` is true of every bar
    # below the level forever, so one eleven-touch pool registered a "break" on every subsequent bar. A
    # crossing is a moment; being below is a state, and only the moment can be a signal.
    machine = ControlMachine(band=_BAND, strength=1, initial=Control.DEMAND)
    candles = _bars(
        *_TWO_LOWS,
        (100.5, 100.7, 97.6, 98.2),   # crosses 100 downward — this one is a break
        (98.2, 98.4, 97.0, 97.2),     # already below; nothing was crossed
        (97.2, 97.5, 96.4, 96.8),     # still below
    )
    first = machine.consider(candles, index=5)
    assert first is not None and first.kind is BreakKind.CHANGE_OF_CHARACTER
    assert machine.consider(candles, index=6) is None
    assert machine.consider(candles, index=7) is None


def test_a_bar_that_closes_back_above_before_the_next_one_is_still_a_crossing():
    # the crossing is what counts, so a bar that pierces on the way down and closes above the level is
    # classified as a sweep rather than ignored
    machine = ControlMachine(band=_BAND, strength=1, initial=Control.DEMAND)
    candles = _bars(*_TWO_LOWS, (100.5, 100.7, 97.6, 100.5))
    result = machine.consider(candles, index=5)
    assert result is not None and result.kind is BreakKind.LIQUIDITY_SWEEP


def test_a_level_is_a_band_around_the_candles_that_formed_it_not_a_line_at_their_mean():
    (pool,) = liquidity_pools(_bars(*_TWO_LOWS), strength=1, band=_BAND, min_touches=2)
    # from the lowest wick (100.0) up to the LOWEST member body bottom (100.6): the grey "Demand" box of S01,
    # whose top edge sits at the lowest body bottom in all three panels — it covers the wicks, not the bodies
    assert pool.low == pytest.approx(100.0)
    assert pool.high == pytest.approx(100.6)
    assert pool.far_edge == pytest.approx(100.0)  # the edge a break of a floor has to get through


def test_a_ceiling_is_the_mirror_image():
    mirrored = _bars(*[(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in _TWO_LOWS])
    (pool,) = liquidity_pools(mirrored, strength=1, band=_BAND, min_touches=2)
    assert pool.kind is SwingKind.HIGH
    assert pool.high == pytest.approx(100.0)
    assert pool.low == pytest.approx(99.4)
    assert pool.far_edge == pytest.approx(pool.high)  # a ceiling is broken through its top


def test_reaching_into_the_band_is_not_a_break_but_leaving_it_is():
    # demand in control; the floor band is 100.0-100.6. A bar that dips to 100.3 has entered the band and
    # has not left it, so it threatens nothing; the next bar, through 100.0, is a crossing of the far edge.
    candles = _bars(*_TWO_LOWS, (100.9, 101.0, 100.3, 100.9))
    machine = ControlMachine(band=_BAND, strength=1)
    assert machine.consider(candles, index=5) is None
    candles = _bars(*_TWO_LOWS, (100.9, 101.0, 100.3, 100.9), (100.9, 100.9, 97.6, 98.2))
    result = machine.consider(candles, index=6)
    assert result is not None and result.flips_control
    assert result.level == pytest.approx(100.0)
