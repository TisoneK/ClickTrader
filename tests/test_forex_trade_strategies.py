"""The sneaky pivot strategy, driven by hand-built sessions so the pattern is exact rather than hoped for.

Bars are 3 seconds wide here and each session is one tick per second, which keeps a scenario readable
while exercising the same code a 15-minute chart would: the bar length is a parameter, not a special case.
"""

import pytest

from clicktrader.forex.model import Direction
from clicktrader.forex.trade_strategies import TRADE_REGISTRY, SneakyPivot
from clicktrader.model import Tick
from clicktrader.strategies import History

SESSION = 86_400.0
BAR_MINUTES = 0.05  # 3-second bars, three one-second ticks each


def _ticks(*sessions) -> list[Tick]:
    """One list of prices per session, one tick per second, sessions a day apart."""
    out: list[Tick] = []
    for day, prices in enumerate(sessions):
        for i, price in enumerate(prices):
            out.append(Tick(day * SESSION + i, f"{price:.5f}", "TESTFX"))
    return out


def _run(strategy: SneakyPivot, ticks: list[Tick]):
    """Feed every tick the way the harness does, returning the decisions that fired."""
    fired = []
    for i in range(len(ticks)):
        decision = strategy.decide(History(ticks, i + 1))
        if decision is not None:
            fired.append((i, decision))
    return fired


def _pivot(**kwargs) -> SneakyPivot:
    return SneakyPivot(bar_minutes=BAR_MINUTES, **kwargs)


# Buy-zone scenario. The session two days back sets the swing low; the session before it sets the range.
# Then, in the traded session: bar 1 plows into the buy zone, bar 2 tests it and closes back above it,
# and a later tick crosses bar 2's high.
_SWING_LOW_DAY = [1.0850, 1.0800, 1.0840]  # low 1.0800, below the next day's low
_RANGE_DAY = [1.0870, 1.0900, 1.0850, 1.0880]  # range 1.0850 - 1.0900
_BUY_DAY = [
    1.0870, 1.0880, 1.0875,  # bar 0: nothing in particular
    1.0870, 1.0850, 1.0855,  # bar 1: the anchor, low exactly on the range low
    1.0855, 1.0845, 1.0860,  # bar 2: the sneaky candle, wick below and close back above
    1.0858,                  # completes bar 2 and arms the trigger
    1.0865,                  # bar 3's first tick: crosses the sneaky candle's high of 1.0860
]


def test_a_buy_zone_sequence_produces_a_trade_with_the_documented_levels():
    fired = _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, _BUY_DAY))
    assert len(fired) == 1
    _, decision = fired[0]
    assert decision.plan.direction is Direction.UP
    assert decision.plan.stop == pytest.approx(1.0800)  # the swing low
    assert decision.plan.target == pytest.approx(1.0900)  # the opposite range line
    assert decision.plan.is_well_formed(1.0865)


def test_the_entry_is_at_the_tick_that_crossed_not_at_the_bar_close():
    fired = _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, _BUY_DAY))
    (index, _) = fired[0]
    assert index == len(_ticks(_SWING_LOW_DAY, _RANGE_DAY, _BUY_DAY)) - 1


def test_the_reason_names_every_level_it_used():
    _, decision = _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, _BUY_DAY))[0]
    assert "sneaky pivot buy" in decision.reason
    for level in ("1.08600", "1.08000", "1.09000", "1.08500"):
        assert level in decision.reason


def test_no_previous_session_means_no_levels_and_no_trade():
    # the first session of a recording has nothing to draw against, so it cannot be traded
    assert _run(_pivot(), _ticks(_BUY_DAY)) == []


def test_a_single_prior_session_gives_a_range_but_no_zone_to_trade():
    # with only one completed session there is no swing line, so there is no buy zone and no stop
    assert _run(_pivot(), _ticks(_RANGE_DAY, _BUY_DAY)) == []


def test_the_anchor_must_actually_reach_the_zone():
    # same shape, but the anchor never gets down to the range low
    day = [1.0870, 1.0880, 1.0875, 1.0870, 1.0860, 1.0865, 1.0865, 1.0858, 1.0870, 1.0868, 1.0875]
    assert _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, day)) == []


def test_the_sneaky_candle_must_close_back_out_of_the_zone():
    # the sneaky candle tests the low but closes *below* it, which is the zone failing rather than
    # being defended — the source's own "no defense shown, the zone is failing" case
    day = [
        1.0870, 1.0880, 1.0875,
        1.0870, 1.0850, 1.0855,  # anchor reaches the zone
        1.0855, 1.0845, 1.0840,  # sneaky candle closes below the range low
        1.0842, 1.0860,
    ]
    assert _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, day)) == []


def test_the_sneaky_candle_must_test_the_boundary_itself():
    # a bar that never gets near the zone is not a test of it, however it closes
    day = [
        1.0870, 1.0880, 1.0875,
        1.0870, 1.0850, 1.0855,
        1.0855, 1.0860, 1.0870,  # nowhere near the range low
        1.0871, 1.0880, 1.0890,
    ]
    assert _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, day)) == []


def test_the_trigger_expires_after_the_following_bar():
    # the source's engine is a 45-minute sequence, so a crossing that arrives later is a different
    # setup, not this one -- three more seconds is one more bar here
    day = _BUY_DAY[:9] + [1.0858, 1.0858, 1.0858, 1.0858, 1.0865]  # the cross comes two bars late
    assert _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, day)) == []


def test_a_wider_trigger_window_arms_the_same_setup():
    day = _BUY_DAY[:9] + [1.0858, 1.0858, 1.0858, 1.0858, 1.0865]
    fired = _run(_pivot(trigger_bars=3), _ticks(_SWING_LOW_DAY, _RANGE_DAY, day))
    assert len(fired) == 1


def test_the_two_bars_must_be_consecutive():
    # an anchor and a sneaky candle with an untouched bar between them are not one sequence; the gap
    # here is one four-tick bar, which puts the pair out of step by a bar
    day = [
        1.0870, 1.0880, 1.0875,
        1.0870, 1.0850, 1.0855,  # anchor
        1.0870, 1.0875, 1.0880, 1.0885,  # an interposed bar the pattern cannot span
        1.0855, 1.0845, 1.0860,  # would-be sneaky
        1.0858, 1.0865,
    ]
    assert _run(_pivot(), _ticks(_SWING_LOW_DAY, _RANGE_DAY, day)) == []


# Sell-zone scenario: the mirror of the above, driven by making the *high* the far side.
_SWING_HIGH_DAY = [1.0900, 1.0950, 1.0930]  # high 1.0950, above the next day's high
_SELL_DAY = [
    1.0880, 1.0875, 1.0880,
    1.0885, 1.0900, 1.0895,  # anchor reaches the range high
    1.0895, 1.0905, 1.0890,  # sneaky candle probes above and closes back below
    1.0892,                  # completes the sneaky candle, arms the trigger
    1.0885,                  # crosses the sneaky candle's low of 1.0890
]


def test_a_sell_zone_sequence_is_the_mirror_of_the_buy_zone():
    fired = _run(_pivot(), _ticks(_SWING_HIGH_DAY, _RANGE_DAY, _SELL_DAY))
    assert len(fired) == 1
    _, decision = fired[0]
    assert decision.plan.direction is Direction.DOWN
    assert decision.plan.stop == pytest.approx(1.0950)  # the swing high
    assert decision.plan.target == pytest.approx(1.0850)  # the opposite range line
    assert decision.plan.is_well_formed(1.0885)


def test_only_the_side_with_a_swing_line_is_tradeable():
    # a swing line above the range but none below: the sell zone exists, the buy zone does not
    fired = _run(_pivot(), _ticks(_SWING_HIGH_DAY, _RANGE_DAY, _BUY_DAY))
    assert fired == []
    fired = _run(_pivot(), _ticks(_SWING_HIGH_DAY, _RANGE_DAY, _SELL_DAY))
    assert len(fired) == 1


def test_a_new_session_voids_a_pending_trigger():
    # the levels an armed trigger was measured against belong to the session that armed it
    day = _BUY_DAY[:9] + [1.0858]
    ticks = _ticks(_SWING_LOW_DAY, _RANGE_DAY, day)
    ticks.append(Tick(3 * SESSION, "1.0900", "TESTFX"))  # next session opens far above the trigger
    assert _run(_pivot(), ticks) == []


def test_a_flat_market_arms_nothing():
    ticks = _ticks([1.0900] * 5, [1.0900] * 5, [1.0900] * 20)
    assert _run(_pivot(), ticks) == []


def test_the_setup_survives_the_strategy_being_fed_the_same_ticks_twice_over():
    # the harness feeds in-sample then out-of-sample from one instance, so the state has to be a pure
    # function of the ticks seen rather than of how many decisions have been made
    ticks = _ticks(_SWING_LOW_DAY, _RANGE_DAY, _BUY_DAY)
    first = _run(_pivot(), ticks)
    second = _run(_pivot(), ticks)
    assert len(first) == len(second) == 1
    assert first[0][0] == second[0][0]


def test_bad_parameters_are_refused():
    with pytest.raises(ValueError):
        SneakyPivot(bar_minutes=0)
    with pytest.raises(ValueError):
        SneakyPivot(trigger_bars=0)


def test_the_registry_exposes_it_under_its_cli_name_and_accepts_the_session_hour():
    strategy = TRADE_REGISTRY["sneaky-pivot"](session_start_hour_utc=21)
    assert isinstance(strategy, SneakyPivot)
    assert "sneaky-pivot" in strategy.name


def test_the_session_hour_decides_which_ticks_share_a_session():
    # The roll hour is not decoration: it decides where one day ends. These scenarios are placed so the
    # swing session and the range session are separate under a midnight roll and the *same* day under a
    # 06:00 roll -- which merges them, leaves no session before the range session, and so removes the
    # swing line the stop comes from. Same ticks, different answer, entirely from the roll hour.
    def timed(*groups):
        return [
            Tick(ts + i, f"{price:.5f}", "TESTFX")
            for ts, prices in groups
            for i, price in enumerate(prices)
        ]

    swing = (30_000.0, _SWING_LOW_DAY)  # 08:20 UTC
    range_ = (90_000.0, _RANGE_DAY)  # 01:00 UTC the next day
    traded = (180_000.0, _BUY_DAY)  # two days on
    ticks = timed(swing, range_, traded)

    assert _run(_pivot(session_start_hour_utc=0), ticks) != []
    assert _run(_pivot(session_start_hour_utc=6), ticks) == []
