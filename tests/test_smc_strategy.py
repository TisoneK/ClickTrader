"""The assembly: it arms on a validated change of character and fills on the retrace, and says why when it
declines.

The full scenario — higher-timeframe alignment, a graded block, a break that survives both invalidation
tests — is exercised end to end against real data by `forex-trade-replay --strategy smc`. What is tested
here is the plumbing that a real run cannot isolate: that nothing is emitted before there are bars to read,
and that a waiting order fills at the block with the levels the material specifies.
"""

import pytest

from clicktrader.forex.model import Direction, TradePlan
from clicktrader.forex.trade_strategies import TRADE_REGISTRY, build
from clicktrader.model import Tick
from clicktrader.smc.components import OrderBlock
from clicktrader.smc.strategy import SmcStrategy, _Armed
from clicktrader.strategies import History


def _feed(strategy, ticks):
    fired = []
    for i in range(len(ticks)):
        decision = strategy.decide(History(ticks, i + 1))
        if decision is not None:
            fired.append(decision)
    return fired


def test_it_emits_nothing_until_it_has_bars_to_read_and_says_so():
    strategy = SmcStrategy(trigger_minutes=0.05, higher_minutes=0.2)  # three-second bars
    # five ticks one second apart, so at least one bar actually closes and the strategy can look at it
    assert _feed(strategy, [Tick(float(i), "100.00", "X") for i in range(5)]) == []
    assert "warming up" in strategy.last_view


def test_a_source_order_fills_at_the_block_with_the_materials_levels():
    strategy = SmcStrategy(trigger_minutes=1.0)
    block = OrderBlock(price_low=99.0, price_high=100.0, index=0, direction=Direction.DOWN)
    strategy._armed = _Armed(
        plan=TradePlan(Direction.DOWN, stop=100.0, target=98.5), block=block, reason="test arm"
    )
    decision = strategy.decide(History([Tick(0.0, "99.50", "X")], 1))
    assert decision is not None
    assert decision.plan.stop == pytest.approx(100.0)  # just beyond the block's wick
    assert decision.plan.reward_risk(99.50) == pytest.approx(2.0)  # the floor the material states
    assert "filled at 99.50000" in decision.reason
    assert strategy._armed is None  # and it does not arm twice


def test_a_price_that_has_not_come_back_to_the_block_does_not_fill():
    strategy = SmcStrategy(trigger_minutes=1.0)
    block = OrderBlock(price_low=99.0, price_high=100.0, index=0, direction=Direction.DOWN)
    strategy._armed = _Armed(
        plan=TradePlan(Direction.DOWN, stop=100.0, target=98.5), block=block, reason="test arm"
    )
    # price is still below the block: the sell limit is above it and has not been reached
    assert strategy.decide(History([Tick(0.0, "98.00", "X")], 1)) is None
    assert strategy._armed is not None


def test_a_plan_that_goes_stale_is_abandoned_with_a_reason():
    # price returned to the block, but past the stop — filling at that price would be a trade with no risk
    # left in it, so the order is dropped rather than filled
    strategy = SmcStrategy(trigger_minutes=1.0)
    block = OrderBlock(price_low=99.0, price_high=100.0, index=0, direction=Direction.DOWN)
    strategy._armed = _Armed(
        plan=TradePlan(Direction.DOWN, stop=100.0, target=98.5), block=block, reason="test arm"
    )
    assert strategy.decide(History([Tick(0.0, "100.50", "X")], 1)) is None
    assert strategy._armed is None
    assert "no longer valid" in strategy.last_view


def test_the_registry_exposes_it_so_the_harness_can_grade_it():
    assert "smc" in TRADE_REGISTRY
    assert build("smc").name.startswith("smc(trigger=")


def test_a_risk_reward_below_the_materials_floor_is_refused():
    with pytest.raises(ValueError):
        SmcStrategy(risk_reward=0.5)


def test_describe_says_what_the_chart_reads_right_now():
    strategy = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0,))
    assert "not enough to read yet" in strategy.describe()
    ticks = [Tick(float(i * 15), f"{100 + ((i * 7) % 23) / 10:.2f}", "X") for i in range(1500)]
    strategy.warm(ticks)
    text = strategy.describe()
    assert "structure" in text and "fresh true zones:" in text and "last close" in text


def test_the_strategy_counts_what_it_passed_on_and_says_why():
    s = SmcStrategy(trigger_minutes=1.0)
    assert s.passes == {}
    s._note_pass("against the higher timeframe, which reads down")
    s._note_pass("against the higher timeframe, which reads up")
    breakdown = s._note_pass("a weaker zone: another demand zone in the same leg is lower")
    s._note_pass("no room to move: no opposing level leaves 2:1 from the zone")
    assert s.passes == {"against the slower clock": 2, "a weaker zone": 1, "no room to 1:2": 1}
    assert breakdown.startswith("2 against the slower clock")  # biggest first


def test_an_empty_chain_means_no_slower_clock_veto():
    s = SmcStrategy(trigger_minutes=1.0, higher_minutes=())
    assert s._higher == []


def test_a_filled_order_is_never_armed_again():
    from clicktrader.smc.components import OrderBlock as OB

    s = SmcStrategy(trigger_minutes=1.0)
    block = OB(price_low=99.0, price_high=100.0, index=0, direction=Direction.DOWN)
    plan = TradePlan(Direction.DOWN, stop=100.0, target=98.0)
    s._armed = _Armed(plan=plan, block=block, reason="test")
    assert s.decide(History([Tick(0.0, "99.50", "X")], 1)) is not None  # filled
    assert s._signature(plan, block) in s._taken  # so the standing-order logic will skip this zone from now on
