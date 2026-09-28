import pytest

from clicktrader.forex.sessions import (
    SECONDS_PER_DAY,
    SessionExtremes,
    SessionTracker,
    levels_from_sessions,
)


def test_ticks_in_the_same_day_stay_in_the_same_session():
    tracker = SessionTracker()
    assert tracker.feed(0.0, 1.10) is False
    assert tracker.feed(3600.0, 1.12) is False
    assert tracker.feed(SECONDS_PER_DAY - 1, 1.09) is False
    assert tracker.completed(5) == []


def test_the_first_tick_of_a_new_day_closes_the_previous_session():
    tracker = SessionTracker()
    tracker.feed(0.0, 1.10)
    tracker.feed(3600.0, 1.12)
    tracker.feed(7200.0, 1.09)
    assert tracker.feed(SECONDS_PER_DAY, 1.11) is True
    (previous,) = tracker.completed(5)
    assert previous.opened_at == 0.0
    assert previous.high == 1.12
    assert previous.low == 1.09


def test_a_gap_between_sessions_is_a_gap_not_an_invented_day():
    # a weekend, a halted feed, a recorder that was simply off: the days with no ticks never exist
    tracker = SessionTracker()
    tracker.feed(0.0, 1.10)
    tracker.feed(3 * SECONDS_PER_DAY, 1.20)
    assert len(tracker.completed(10)) == 1


def test_the_session_boundary_hour_is_configurable():
    tracker = SessionTracker(start_hour_utc=21)  # 21:00 UTC, a common FX roll hour
    tracker.feed(0.0, 1.10)  # still the previous day under a 21:00 roll
    assert tracker.feed(21 * 3600.0, 1.11) is True
    # the day a 00:00-UTC tick belongs to under a 21:00 roll began at 21:00 the previous evening
    assert tracker.completed(1)[0].opened_at == 21 * 3600.0 - SECONDS_PER_DAY
    assert tracker.session_opened_at == 21 * 3600.0


def test_session_boundary_hour_must_be_a_real_hour():
    with pytest.raises(ValueError):
        SessionTracker(start_hour_utc=24)


def test_tracker_keeps_only_the_requested_number_of_sessions():
    tracker = SessionTracker(keep=2)
    for day in range(4):
        tracker.feed(day * SECONDS_PER_DAY, 1.10 + day)
    assert len(tracker.completed(10)) == 2


def test_out_of_order_ticks_raise_rather_than_corrupt_the_day():
    tracker = SessionTracker()
    tracker.feed(SECONDS_PER_DAY, 1.10)
    with pytest.raises(ValueError):
        tracker.feed(0.0, 1.11)


def test_a_flat_session_reports_a_zero_range():
    tracker = SessionTracker()
    tracker.feed(0.0, 1.10)
    tracker.feed(SECONDS_PER_DAY, 1.10)
    (previous,) = tracker.completed(1)
    assert previous.high == previous.low == 1.10


def _session(opened_at, high, low):
    return SessionExtremes(opened_at=opened_at, high=high, low=low)


def test_no_previous_session_means_no_levels_at_all():
    # the first day of a recording has nothing to draw against; inventing a range from the current
    # session's own ticks would be a lookahead, since the lines have to exist before trading starts
    assert levels_from_sessions([], swing_lookback=1) is None


def test_range_lines_come_from_the_previous_session():
    levels = levels_from_sessions([_session(0.0, 1.20, 1.05)], swing_lookback=1)
    assert levels is not None
    assert levels.range_high == 1.20
    assert levels.range_low == 1.05


def test_one_previous_session_is_not_enough_for_a_swing_line():
    levels = levels_from_sessions([_session(0.0, 1.20, 1.05)], swing_lookback=1)
    assert levels is not None
    assert levels.swing_high is None and levels.swing_low is None
    assert levels.sell_zone is None and levels.buy_zone is None


def test_swing_lines_are_taken_from_the_sessions_before_the_range_session():
    # swing_high/low are read from the session *before* the range session, and only kept when they
    # really do reach beyond the range — that is what "scroll left for the next level" means
    levels = levels_from_sessions(
        [_session(0.0, 1.30, 1.00), _session(SECONDS_PER_DAY, 1.20, 1.05)], swing_lookback=1
    )
    assert levels is not None
    assert levels.range_high == 1.20 and levels.range_low == 1.05
    assert levels.swing_high == 1.30
    assert levels.swing_low == 1.00
    assert levels.sell_zone == (1.20, 1.30)
    assert levels.buy_zone == (1.00, 1.05)


def test_a_swing_line_inside_the_range_is_not_a_zone():
    # the earlier session sat entirely inside the range session: there is no outer boundary on either
    # side, so there is no zone to trade from and no stop to place
    levels = levels_from_sessions(
        [_session(0.0, 1.19, 1.06), _session(SECONDS_PER_DAY, 1.20, 1.05)], swing_lookback=1
    )
    assert levels is not None
    assert levels.swing_high is None and levels.swing_low is None


def test_swing_lookback_widens_the_window():
    sessions = [
        _session(0.0, 1.50, 1.00),
        _session(SECONDS_PER_DAY, 1.25, 1.10),
        _session(2 * SECONDS_PER_DAY, 1.20, 1.05),
    ]
    assert levels_from_sessions(sessions, swing_lookback=1).swing_high == 1.25
    assert levels_from_sessions(sessions, swing_lookback=2).swing_high == 1.50


def test_zero_lookback_disables_the_swing_lines():
    levels = levels_from_sessions(
        [_session(0.0, 1.30, 1.00), _session(SECONDS_PER_DAY, 1.20, 1.05)], swing_lookback=0
    )
    assert levels.swing_high is None and levels.swing_low is None


def test_negative_lookback_is_refused():
    with pytest.raises(ValueError):
        levels_from_sessions([_session(0.0, 1.20, 1.05)], swing_lookback=-1)
