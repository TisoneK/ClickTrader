"""The supply-and-demand checklist, driven bar by bar so each of the eight gates can be shown working.

A scenario is built from named blocks — an earlier excursion, a decline, a quiet stretch, three rising
legs, an origin candle, a displacement run — so a test can break exactly one of the SOP's conditions and
show that gate is what stops it.
"""

import pytest

from clicktrader.forex.model import Direction
from clicktrader.forex.trade_strategies import EntryModel, SupplyDemand, build
from clicktrader.model import Tick
from clicktrader.strategies import History

BAR_MINUTES = 1.0  # four one-second ticks per bar: enough for a wick and a body, short enough to read
TICKS_PER_BAR = int(BAR_MINUTES * 60)
SMALL = 0.0002


def _bar(open_, high, low, close):
    return (open_, high, low, close)


def _series(*bars) -> list[Tick]:
    """One tick per second; each bar's prices are spread across its seconds."""
    ticks: list[Tick] = []
    for index, prices in enumerate(bars):
        base = index * TICKS_PER_BAR
        for offset in range(TICKS_PER_BAR):
            price = prices[min(offset, len(prices) - 1)]
            ticks.append(Tick(base + offset, f"{price:.5f}", "TESTFX"))
    return ticks


def _build(*, run_body=0.0030, run_candles=4, trend_legs=3, spike=True, decline=True):
    """A chart where the whole checklist holds, built from named blocks so one can be broken at a time.

    The shape, and why each part is there:

    - an earlier excursion high up leaves a *bearish* imbalance near the top that nothing has come back
      to. Without an untouched imbalance ahead there is no target, and a method whose exit is "the next
      zone on the opposite side" has no trade where there is none;
    - a decline and a quiet stretch give the median candle body something to stand on;
    - three rising legs with shallow pullbacks give the 1-2-3 sequence, the swing points the break of
      structure is measured against, and the bearish gaps the run later trades straight through;
    - the last pullback's final candle is the origin candle the zone is drawn on, wick to wick;
    - the run is the displacement: four candles, each far larger than the median body before them.

    Returns `(bars, zone_low, zone_high)` with the run as the last block, so a test can append whatever
    approach it wants to test.
    """
    bars: list = []

    def bar(o, h, l, c):
        bars.append(_bar(o, h, l, c))
        return c

    def leg(n, body, bullish):
        price = bars[-1][3]
        for _ in range(n):
            if bullish:
                price = bar(price, price + body + 0.00005, price - 0.00003, price + body)
            else:
                price = bar(price, price + 0.00003, price - body - 0.00005, price - body)
        return price

    bar(1.11500, 1.11560, 1.11480, 1.11540)
    if spike:
        leg(3, 0.0025, True)
    if decline:
        leg(3, 0.0020, False)
        leg(6, 0.0025, False)
    for i in range(14):
        price = bars[-1][3]
        if i % 2:
            bar(price, price + SMALL, price - SMALL / 2, price + SMALL)
        else:
            bar(price, price + SMALL / 2, price - SMALL, price - SMALL)
    for _ in range(trend_legs):
        leg(3, 0.0006, True)
        leg(3, 0.0004, False)
    origin = bars[-1][3]
    bar(origin, origin + 0.0003, origin - 0.0005, origin - 0.0004)
    zone_low, zone_high = bars[-1][2], bars[-1][1]
    leg(run_candles, run_body, True)
    return bars, zone_low, zone_high


def _approach(bars, *, bars_down=12, body=0.0010):
    """Walk price back down towards the zone without yet deciding what it does there."""
    price = bars[-1][3]
    for _ in range(bars_down):
        price -= body
        bars.append(_bar(price + body, price + body + 0.00005, price - 0.00005, price))
    return bars


def _continue(bars):
    """One more bar, so the bar before it actually *completes*.

    A candle closes when a later one is traded in, so a bar appended at the end of a series is still
    forming and a trigger that waits for a completed bar would never see it. Every real recording has
    bars after the one that matters; a fixture has to say so explicitly.
    """
    price = bars[-1][3]
    bars.append(_bar(price, price + 0.0001, price - 0.00005, price + 0.00005))
    return bars


def _return_to_zone(bars, zone_low, zone_high):
    """Price comes back to the zone and a bar closes back out of it: the `normal` trigger."""
    _approach(bars)
    price = bars[-1][3]
    bars.append(_bar(price, price + 0.0002, (zone_low + zone_high) / 2, zone_high + 0.0001))
    return _continue(bars)


def _touch_only(bars, zone_low, zone_high):
    """Price reaches the zone and stays inside it: enough for `aggressive`, not for the others."""
    _approach(bars)
    price = bars[-1][3]
    bars.append(_bar(price, price + 0.0001, zone_low + 0.0002, (zone_low + zone_high) / 2))
    return _continue(bars)


def _feed(strategy, ticks):
    fired = []
    for i in range(len(ticks)):
        decision = strategy.decide(History(ticks, i + 1))
        if decision is not None:
            fired.append((i, decision))
    return fired


def _sop(**kwargs) -> SupplyDemand:
    kwargs.setdefault("bar_minutes", BAR_MINUTES)
    kwargs.setdefault("swing_strength", 1)  # the fixture's legs are three bars long; see the builder
    return SupplyDemand(**kwargs)


# --- the checklist passing ----------------------------------------------------------------------


def test_a_full_checklist_produces_a_trade_with_the_documented_levels():
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    fired = _feed(_sop(entry_model="normal"), _series(*bars))
    assert len(fired) == 1
    _, decision = fired[0]
    assert decision.plan.direction is Direction.UP
    assert decision.plan.stop == pytest.approx(zone_low)  # beyond the far side of the demand zone
    assert decision.plan.target > decision.plan.stop
    assert "displacement" in decision.reason and "first tap" in decision.reason


def test_the_zone_is_the_origin_candle_wick_to_wick():
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    _, decision = _feed(_sop(entry_model="normal"), _series(*bars))[0]
    assert decision.plan.stop == pytest.approx(zone_low)
    assert f"{zone_high:.5f}" in decision.reason and f"{zone_low:.5f}" in decision.reason


def test_the_reason_reads_like_the_checklist_it_passed():
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    _, decision = _feed(_sop(entry_model="normal"), _series(*bars))[0]
    for fragment in ("demand", "displacement", "structure broken", "imbalance", "wick-to-wick", "first tap"):
        assert fragment in decision.reason


def test_the_target_is_the_largest_untouched_imbalance_ahead():
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    _, decision = _feed(_sop(entry_model="normal"), _series(*bars))[0]
    # the biggest bearish imbalance left near the top of the earlier excursion, which nothing has been
    # back to. "Largest", not "nearest": the approach into a zone leaves its own small imbalance just
    # ahead of the entry, and aiming at that one gives a target worth a fraction of the risk
    assert decision.plan.target == pytest.approx(1.11893, abs=1e-4)
    assert decision.plan.reward_risk(decision.plan.stop + 0.0009) > 2.0


# --- each gate blocking -------------------------------------------------------------------------


def test_without_displacement_there_is_no_setup():
    # ordinary-sized candles in a qualifying count: the "massive" part of the line fails
    bars, zone_low, zone_high = _build(run_body=0.0004)
    _return_to_zone(bars, zone_low, zone_high)
    assert _feed(_sop(entry_model="normal"), _series(*bars)) == []


def test_the_displacement_count_is_the_sop_four_and_is_configurable():
    bars, zone_low, zone_high = _build(run_candles=3)
    _return_to_zone(bars, zone_low, zone_high)
    ticks = _series(*bars)
    assert _feed(_sop(entry_model="normal"), ticks) == []
    # the earlier deck said 3+ where the SOP says 4+, which is exactly the sort of difference that
    # should be a parameter rather than a silent choice
    assert len(_feed(_sop(entry_model="normal", min_candles=3), ticks)) == 1


def test_a_parabolic_crash_into_the_zone_is_vetoed():
    bars, zone_low, zone_high = _build()
    _approach(bars, body=0.0035)  # the whole return happens in huge candles
    price = bars[-1][3]
    bars.append(_bar(price, price + 0.0002, (zone_low + zone_high) / 2, zone_high + 0.0001))
    _continue(bars)
    ticks = _series(*bars)
    assert _feed(_sop(entry_model="normal"), ticks) == []
    # and the same chart with the veto loosened does trade, so the veto is what stopped it
    assert len(_feed(_sop(entry_model="normal", max_approach_speed=50.0), ticks)) == 1


def test_a_second_visit_is_not_a_fresh_zone():
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    price = bars[-1][3]
    for _ in range(4):  # wander away again
        price += 0.0010
        bars.append(_bar(price - 0.0010, price, price - 0.0011, price))
    _return_to_zone(bars, zone_low, zone_high)  # and come back a second time
    assert len(_feed(_sop(entry_model="normal"), _series(*bars))) == 1  # the first tap is the trade


# --- the three entry models ---------------------------------------------------------------------


def test_aggressive_enters_on_the_touch_itself():
    bars, zone_low, zone_high = _build()
    _touch_only(bars, zone_low, zone_high)
    assert len(_feed(_sop(entry_model="aggressive"), _series(*bars))) == 1


def test_normal_waits_for_a_bar_to_close_back_out_of_the_zone():
    inside, low, high = _build()
    _touch_only(inside, low, high)
    assert _feed(_sop(entry_model="normal"), _series(*inside)) == []
    out, low, high = _build()
    _return_to_zone(out, low, high)
    assert len(_feed(_sop(entry_model="normal"), _series(*out))) == 1


def test_conservative_wants_the_engulfing_confirmation_too():
    bars, zone_low, zone_high = _build()
    _approach(bars)
    price = bars[-1][3]
    # dips in and closes back out, but the bar is small and does not engulf the one before it
    bars.append(_bar(price, price + 0.00005, (zone_low + zone_high) / 2, zone_high + 0.00002))
    _continue(bars)
    ticks = _series(*bars)
    assert len(_feed(_sop(entry_model="normal"), ticks)) == 1
    assert _feed(_sop(entry_model="conservative"), ticks) == []


def test_the_entry_models_are_ordered_by_how_much_they_wait_for():
    assert [m.value for m in EntryModel] == ["aggressive", "normal", "conservative"]
    with pytest.raises(ValueError):
        SupplyDemand(entry_model="yolo")


# --- plumbing -----------------------------------------------------------------------------------


def test_bad_parameters_are_refused():
    with pytest.raises(ValueError):
        SupplyDemand(bar_minutes=0)
    with pytest.raises(ValueError):
        SupplyDemand(window=10, lookback=20)


def test_a_flat_market_arms_nothing():
    flat = _bar(1.10000, 1.10000, 1.10000, 1.10000)
    assert _feed(_sop(), _series(*([flat] * 60))) == []


def test_the_setup_is_a_pure_function_of_the_ticks_it_has_seen():
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    ticks = _series(*bars)
    first = _feed(_sop(entry_model="normal"), ticks)
    second = _feed(_sop(entry_model="normal"), ticks)
    assert len(first) == len(second) == 1 and first[0][0] == second[0][0]


def test_a_spent_zone_is_not_traded_twice():
    # after the trade, price returning to the same level is not a fresh setup
    bars, zone_low, zone_high = _build()
    _return_to_zone(bars, zone_low, zone_high)
    price = bars[-1][3]
    for _ in range(4):
        price += 0.0010
        bars.append(_bar(price - 0.0010, price, price - 0.0011, price))
    _return_to_zone(bars, zone_low, zone_high)
    assert len(_feed(_sop(entry_model="normal"), _series(*bars))) == 1


def test_the_registry_exposes_it_and_build_passes_no_session_hour_to_a_method_without_one():
    assert isinstance(build("supply-demand"), SupplyDemand)
    # the range method draws on a trading day and takes the roll hour; this checklist has no session
    # concept at all, so build must not hand it a parameter it would silently ignore
    assert build("sneaky-pivot", session_start_hour_utc=21).name.startswith("sneaky-pivot(bar=15m, session-start=21h")
    assert build("supply-demand", session_start_hour_utc=21).name == SupplyDemand().name
