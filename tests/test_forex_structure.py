import pytest

from clicktrader.forex.candles import TimedCandle
from clicktrader.forex.model import Direction
from clicktrader.forex.structure import (
    FairValueGap,
    SwingKind,
    Trend,
    Zone,
    approach_speed,
    broke_structure,
    displacement,
    fair_value_gaps,
    gap_untouched,
    last_swing,
    swing_points,
    taps,
    target_gap,
    trend_sequence,
    zone_from_origin,
)


def bars(*specs) -> list[TimedCandle]:
    """Candles from `(open, high, low, close)` tuples, one per position, timestamps consecutive."""
    return [
        TimedCandle(open=o, high=h, low=l, close=c, opened_at=float(i))
        for i, (o, h, l, c) in enumerate(specs)
    ]


def _up(index: int, price: float) -> tuple:
    """A small bullish bar whose high is `price`."""
    return (price - 0.0010, price, price - 0.0015, price - 0.0002)


def _down(index: int, price: float) -> tuple:
    """A small bearish bar whose low is `price`."""
    return (price + 0.0010, price + 0.0015, price, price + 0.0002)


# --- swings -------------------------------------------------------------------------------------


def test_a_swing_high_is_a_bar_above_its_neighbours():
    series = bars(*[_up(i, 1.1000 + i * 0.0001) for i in range(3)], _up(3, 1.1100), *[_up(i, 1.1000) for i in range(4, 7)])
    swings = swing_points(series, strength=2)
    highs = [s for s in swings if s.kind is SwingKind.HIGH]
    assert [s.index for s in highs] == [3]
    assert highs[0].price == 1.1100


def test_a_swing_low_is_a_bar_below_its_neighbours():
    series = bars(*[_down(i, 1.1000) for i in range(3)], _down(3, 1.0900), *[_down(i, 1.1000) for i in range(4, 7)])
    lows = [s for s in swing_points(series, strength=2) if s.kind is SwingKind.LOW]
    assert [s.index for s in lows] == [3]
    assert lows[0].price == 1.0900


def test_equal_highs_are_not_a_swing():
    # two equal highs are one level the market failed to clear, not a structure point
    series = bars(*[_up(i, 1.1000) for i in range(3)], _up(3, 1.1100), _up(4, 1.1100), *[_up(i, 1.1000) for i in range(5, 8)])
    assert not any(s.kind is SwingKind.HIGH and s.price == 1.1100 for s in swing_points(series, strength=2))


def test_the_ends_can_never_be_swings():
    series = bars(*[_up(i, 1.1000 + i * 0.0010) for i in range(6)])
    assert swing_points(series, strength=2) == []
    with pytest.raises(ValueError):
        swing_points(series, strength=0)


def test_last_swing_can_be_restricted_to_those_before_an_index():
    series = bars(*[_up(i, 1.1000) for i in range(3)], _up(3, 1.1100), *[_up(i, 1.1000) for i in range(4, 7)],
                 _up(7, 1.1200), *[_up(i, 1.1000) for i in range(8, 11)])
    swings = swing_points(series, strength=2)
    assert last_swing(swings, SwingKind.HIGH).index == 7
    assert last_swing(swings, SwingKind.HIGH, before_index=7).index == 3
    assert last_swing(swings, SwingKind.LOW) is None


# --- the 1-2-3 sequence -------------------------------------------------------------------------


def _swings(highs, lows):
    out = []
    for index, (kind, price) in enumerate([(SwingKind.HIGH, h) for h in highs] + [(SwingKind.LOW, l) for l in lows]):
        out.append(__import__("clicktrader.forex.structure", fromlist=["SwingPoint"]).SwingPoint(index, price, kind))
    return sorted(out, key=lambda s: s.index)


def test_a_rising_sequence_of_highs_and_lows_is_an_uptrend():
    assert trend_sequence(_swings([1.10, 1.11, 1.12], [1.05, 1.06, 1.07])) is Trend.UP


def test_a_falling_sequence_is_a_downtrend():
    assert trend_sequence(_swings([1.12, 1.11, 1.10], [1.07, 1.06, 1.05])) is Trend.DOWN


def test_rising_highs_with_flat_lows_is_a_range_not_a_trend():
    # one leg agreeing is not a trend; this is a widening top
    assert trend_sequence(_swings([1.10, 1.11, 1.12], [1.05, 1.05, 1.05])) is Trend.RANGE


def test_too_few_swings_is_a_range():
    assert trend_sequence(_swings([1.10, 1.11], [1.05, 1.06])) is Trend.RANGE
    assert trend_sequence([]) is Trend.RANGE


def test_the_sequence_depth_is_configurable():
    swings = _swings([1.10, 1.11, 1.12], [1.05, 1.06, 1.07])
    assert trend_sequence(swings, steps=2) is Trend.UP
    assert trend_sequence(swings, steps=4) is Trend.RANGE  # not enough history at that depth


# --- breaks of structure ------------------------------------------------------------------------


def test_an_upward_push_breaks_structure_by_exceeding_the_last_swing_high():
    swings = _swings([1.1000], [])
    move = bars(_up(0, 1.1050))
    assert broke_structure(move, swings, direction=Direction.UP)
    assert not broke_structure(bars(_up(0, 1.0990)), swings, direction=Direction.UP)


def test_a_downward_push_breaks_structure_by_undercutting_the_last_swing_low():
    swings = _swings([], [1.0900])
    assert broke_structure(bars(_down(0, 1.0850)), swings, direction=Direction.DOWN)
    assert not broke_structure(bars(_down(0, 1.0950)), swings, direction=Direction.DOWN)


def test_no_prior_swing_means_nothing_to_break():
    assert not broke_structure(bars(_up(0, 1.2000)), [], direction=Direction.UP)


# --- fair value gaps ----------------------------------------------------------------------------


def test_a_bullish_imbalance_needs_the_wicks_not_to_overlap():
    series = bars(
        (1.1000, 1.1010, 1.0990, 1.1005),  # first: high 1.1010
        (1.1005, 1.1080, 1.1000, 1.1075),  # displacement
        (1.1075, 1.1090, 1.1020, 1.1085),  # third: low 1.1020, above the first high
    )
    (gap,) = fair_value_gaps(series)
    assert gap.direction is Direction.UP
    assert gap.lower == pytest.approx(1.1010)
    assert gap.upper == pytest.approx(1.1020)
    assert gap.formed_index == 1


def test_wicks_that_overlap_by_a_hair_are_not_an_imbalance():
    series = bars(
        (1.1000, 1.1010, 1.0990, 1.1005),
        (1.1005, 1.1080, 1.1000, 1.1075),
        (1.1075, 1.1090, 1.1009, 1.1085),  # low 1.1009, one pip *through* the first high
    )
    assert fair_value_gaps(series) == []


def test_a_bearish_imbalance_is_the_mirror():
    series = bars(
        (1.1000, 1.1010, 1.0990, 1.1005),
        (1.1005, 1.1010, 1.0930, 1.0935),
        (1.0935, 1.0980, 1.0920, 1.0940),  # high 1.0980, below the first low
    )
    (gap,) = fair_value_gaps(series)
    assert gap.direction is Direction.DOWN
    assert gap.lower == pytest.approx(1.0980)
    assert gap.upper == pytest.approx(1.0990)


def test_a_gap_knows_whether_price_has_been_back_into_it():
    gap = FairValueGap(Direction.UP, lower=1.1010, upper=1.1020, formed_index=1)
    untouched = bars(
        (1.1000, 1.1010, 1.0990, 1.1005),
        (1.1005, 1.1080, 1.1000, 1.1075),
        (1.1075, 1.1090, 1.1020, 1.1085),
        (1.1085, 1.1100, 1.1060, 1.1095),
    )
    assert gap_untouched(gap, untouched)
    revisited = bars(
        (1.1000, 1.1010, 1.0990, 1.1005),
        (1.1005, 1.1080, 1.1000, 1.1075),
        (1.1075, 1.1090, 1.1020, 1.1085),
        (1.1085, 1.1090, 1.1015, 1.1030),  # trades down into the gap
    )
    assert not gap_untouched(gap, revisited)


# --- displacement -------------------------------------------------------------------------------


def _flat_then_run(run_bodies, *, direction=Direction.UP, baseline=0.0002, tail=0):
    specs = [(1.0, 1.0 + baseline, 1.0 - baseline / 2, 1.0 + (baseline if direction is Direction.UP else -baseline))] * 10
    price = specs[-1][3]
    for body in run_bodies:
        if direction is Direction.UP:
            specs.append((price, price + body + 0.0001, price - 0.00005, price + body))
        else:
            specs.append((price, price + 0.00005, price - body - 0.0001, price - body))
        price = specs[-1][3]
    for _ in range(tail):
        specs.append((price, price + 0.0001, price - 0.0001, price + 0.00005))
    return bars(*specs)


def test_a_run_of_large_candles_is_displacement():
    series = _flat_then_run([0.0010] * 4)
    found = displacement(series, min_candles=4, size_multiple=1.5)
    assert found is not None
    assert found.direction is Direction.UP
    # the "run" reading takes the longest window that clears the threshold, so it can reach back over
    # the ordinary candles before the big ones — the move started there, and the zone is drawn at its
    # start (see the function's own note)
    assert found.candles >= 4
    assert found.end_index == len(series) - 1


def test_a_move_too_small_to_be_displacement_is_not_one():
    short = _flat_then_run([0.0010] * 3)
    assert displacement(short, min_candles=4, size_multiple=1.5, size_mode="each") is None
    # the same three candles, aggregated over a window that clears the count, are still not a big move
    assert displacement(short, min_candles=4, size_multiple=5.0) is None


def test_candles_that_are_not_large_enough_are_not_displacement():
    assert displacement(_flat_then_run([0.00025] * 5), min_candles=4, size_multiple=1.5) is None


def test_the_baseline_excludes_the_run_being_measured():
    # If the run were included in its own baseline, four huge candles would raise the average they are
    # judged against and the move would disqualify itself -- the wrong way round.
    series = _flat_then_run([0.0010] * 4)
    found = displacement(series, min_candles=4, size_multiple=1.5)
    assert found.baseline_body == pytest.approx(0.0002, abs=1e-9)


def test_displacement_is_found_historically_not_only_at_the_end():
    # a checklist runs after the move and after price has come back to the zone, so the push has to be
    # findable with other bars after it
    series = _flat_then_run([0.0010] * 4, tail=6)
    found = displacement(series, min_candles=4, size_multiple=1.5, size_mode="each")
    assert found is not None
    assert found.end_index == len(series) - 7


def test_a_downdraft_is_displacement_too():
    found = displacement(_flat_then_run([0.0010] * 4, direction=Direction.DOWN), min_candles=4, size_multiple=1.5)
    assert found is not None and found.direction is Direction.DOWN


def test_not_enough_history_gives_no_answer_rather_than_a_wrong_one():
    assert displacement(_flat_then_run([0.0010] * 4)[:6], min_candles=4, size_multiple=1.5) is None
    with pytest.raises(ValueError):
        displacement(_flat_then_run([0.0010] * 4), min_candles=1)
    with pytest.raises(ValueError):
        displacement(_flat_then_run([0.0010] * 4), lookback=2)


def test_last_index_bounds_what_the_search_may_see():
    series = _flat_then_run([0.0010] * 4)
    # nothing but the ordinary baseline before this index, whose own run is too short and too small
    assert displacement(series, min_candles=4, size_multiple=1.5, size_mode="each", last_index=12) is None


# --- approach speed -----------------------------------------------------------------------------


def test_a_quiet_approach_reads_slow_and_a_parabolic_one_reads_fast():
    quiet = _flat_then_run([0.0002] * 3)  # the approach itself is ordinary-sized
    assert approach_speed(quiet, bars=3, lookback=10) < 1.5
    violent = _flat_then_run([0.0020] * 3)  # the same approach, but parabolic
    assert approach_speed(violent, bars=3, lookback=10) > 5.0


def test_no_baseline_reads_as_no_objection():
    # refusing to trade because there is not enough history would be a silent extra rule
    assert approach_speed(bars(*[(1.0, 1.1, 0.9, 1.0)] * 3), bars=3, lookback=10) == 0.0


# --- zones --------------------------------------------------------------------------------------


def test_a_zone_is_the_origin_candle_wick_to_wick():
    candle = TimedCandle(open=1.1010, high=1.1020, low=1.0980, close=1.0985, opened_at=0.0)
    zone = zone_from_origin(candle, index=5, direction=Direction.UP)
    assert zone.lower == 1.0980
    assert zone.upper == 1.1020
    assert zone.origin_index == 5
    assert zone.size == pytest.approx(0.0040)


def test_taps_counts_the_first_visit_as_zero():
    series = bars(
        (1.1010, 1.1020, 1.0980, 1.0985),  # the origin candle
        (1.0985, 1.1050, 1.0985, 1.1045),  # the push, part of which is still inside the zone
        (1.1045, 1.1060, 1.1030, 1.1055),  # away from it
    )
    zone = zone_from_origin(series[0], index=0, direction=Direction.UP)
    # counting starts after the push: the bars that make the move are not a return to the level
    assert taps(zone, series, from_index=2) == 0
    returned = series + bars((1.1055, 1.1055, 1.0995, 1.1000))
    assert taps(zone, returned, from_index=2) == 1
    twice = returned + bars((1.1000, 1.1040, 1.0975, 1.1030))
    assert taps(zone, twice, from_index=2) == 2


def test_counting_from_the_origin_shows_why_the_caller_chooses_the_start():
    # the bar after a bearish origin candle opens inside the zone almost by construction, which is why
    # "the very first tap" is a question about the bars after the *move*, not after the candle
    series = bars(
        (1.1010, 1.1020, 1.0980, 1.0985),
        (1.0985, 1.1050, 1.0985, 1.1045),
    )
    zone = zone_from_origin(series[0], index=0, direction=Direction.UP)
    assert taps(zone, series) == 1  # from the origin: the push itself counts
    assert taps(zone, series, from_index=2) == 0


def test_taps_ignores_candles_before_the_zone_existed():
    series = bars(
        (1.1010, 1.1020, 1.0980, 1.0985),
        (1.0985, 1.1050, 1.0985, 1.1045),
    )
    zone = Zone(Direction.UP, lower=1.0980, upper=1.1020, origin_index=1)
    assert taps(zone, series) == 0


# --- the target gap -----------------------------------------------------------------------------


def _gap(direction, lower, upper, formed_index=2):
    return FairValueGap(direction, lower=lower, upper=upper, formed_index=formed_index)


def _never_revisited(*gaps):
    """Candles that leave every gap untouched: prices well away from all of them."""
    return bars(*[(2.0, 2.0001, 1.9999, 2.0) for _ in range(6)])


def test_the_target_is_an_opposing_gap_ahead_of_the_price():
    supplies = [_gap(Direction.DOWN, 1.1050, 1.1060, formed_index=0)]
    candles = bars((2.0, 2.0, 2.0, 2.0), (2.0, 2.0, 2.0, 2.0))
    # a long looks for a bearish imbalance above; a short for a bullish one below
    assert target_gap(supplies, candles, direction=Direction.UP, price=1.1000) is not None
    assert target_gap(supplies, candles, direction=Direction.DOWN, price=1.1000) is None
    demands = [_gap(Direction.UP, 1.0950, 1.0960, formed_index=0)]
    assert target_gap(demands, candles, direction=Direction.DOWN, price=1.1000) is not None
    assert target_gap(demands, candles, direction=Direction.UP, price=1.1000) is None


def test_a_gap_behind_the_entry_is_not_a_target():
    supplies = [_gap(Direction.DOWN, 1.0950, 1.0960, formed_index=0)]
    candles = bars((2.0, 2.0, 2.0, 2.0))
    assert target_gap(supplies, candles, direction=Direction.UP, price=1.1000) is None


def test_largest_is_the_default_and_nearest_is_available():
    # "the next major zone" is read as the biggest, because the nearest is usually the small imbalance
    # the approach itself just left -- a target worth a fraction of the risk
    gaps = [
        _gap(Direction.DOWN, 1.1020, 1.1021, formed_index=0),  # small and near
        _gap(Direction.DOWN, 1.1080, 1.1120, formed_index=0),  # large and further
    ]
    candles = bars((2.0, 2.0, 2.0, 2.0))
    assert target_gap(gaps, candles, direction=Direction.UP, price=1.1000).lower == 1.1080
    nearest = target_gap(gaps, candles, direction=Direction.UP, price=1.1000, prefer="nearest")
    assert nearest.lower == 1.1020
    with pytest.raises(ValueError):
        target_gap(gaps, candles, direction=Direction.UP, price=1.1000, prefer="biggest")


def test_a_gap_price_has_already_been_back_into_is_not_a_target():
    gaps = [_gap(Direction.DOWN, 1.1080, 1.1120, formed_index=0)]
    revisited = bars(*[(2.0, 2.0, 2.0, 2.0) for _ in range(3)])
    revisited.append(TimedCandle(open=1.1100, high=1.1110, low=1.1090, close=1.1100, opened_at=9.0))
    revisited.extend([TimedCandle(open=2.0, high=2.0, low=2.0, close=2.0, opened_at=10.0 + i) for i in range(3)])
    assert target_gap(gaps, _never_revisited(), direction=Direction.UP, price=1.1000) is not None
    assert target_gap(gaps, revisited, direction=Direction.UP, price=1.1000) is None


def test_the_two_readings_of_massive_are_both_available_and_disagree():
    # one big candle and three ordinary ones: a big *move*, but not four big candles
    uneven = _flat_then_run([0.0010, 0.0002, 0.0002, 0.0002])
    assert displacement(uneven, min_candles=4, size_multiple=1.5, size_mode="run") is not None
    assert displacement(uneven, min_candles=4, size_multiple=1.5, size_mode="each") is None
    with pytest.raises(ValueError):
        displacement(uneven, min_candles=4, size_multiple=1.5, size_mode="enormous")


def test_the_run_reading_is_the_default_because_the_each_reading_never_fires_on_real_bars():
    uneven = _flat_then_run([0.0010, 0.0002, 0.0002, 0.0002])
    assert displacement(uneven, min_candles=4, size_multiple=1.5) is not None
