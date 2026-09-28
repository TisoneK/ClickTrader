import pytest

from clicktrader.forex.model import Direction, TradePlan
from clicktrader.forex.synthetic import synthetic_price_ticks
from clicktrader.forex.trade_harness import (
    TradeReplayResult,
    TradeSegmentResult,
    mirrored_plan,
    replay_trades,
    resolve,
)
from clicktrader.forex.trade_strategies import TradeDecision
from clicktrader.model import Tick
from clicktrader.strategies import History


class FiresOnce:
    """Fires one fixed plan at one chosen tick, so the grading mechanics can be tested in isolation."""

    def __init__(self, at: int, plan: TradePlan, name: str = "fires-once") -> None:
        self.name = name
        self._at = at
        self._plan = plan

    def decide(self, history: History) -> TradeDecision | None:
        if len(history) - 1 != self._at:
            return None
        return TradeDecision(self._plan, 1.0, "test")


class FixedGeometry:
    """Fires a plan at fixed distances from whatever the current price is — no signal at all, which is
    exactly what makes it the right vehicle for calibrating the harness against a driftless walk."""

    def __init__(
        self, *, direction: Direction = Direction.UP, risk: float, reward: float, every: int = 1
    ) -> None:
        self.name = f"fixed-geometry({direction.value}, {risk}, {reward})"
        self._direction, self._risk, self._reward, self._every = direction, risk, reward, every
        self._seen = 0

    def decide(self, history: History) -> TradeDecision | None:
        self._seen += 1
        if self._seen % self._every:
            return None
        entry = float(history[-1].price)
        if self._direction is Direction.UP:
            plan = TradePlan(Direction.UP, stop=entry - self._risk, target=entry + self._reward)
        else:
            plan = TradePlan(Direction.DOWN, stop=entry + self._risk, target=entry - self._reward)
        return TradeDecision(plan, 1.0, "fixed geometry")


class Peeker:
    """Tries to read past the end of history -- the harness must make that impossible."""

    name = "peeker"

    def decide(self, history: History):
        try:
            history[len(history)]
        except IndexError:
            return None
        return pytest.fail("strategy read a tick from the future")


def _ticks(prices, *, start_ts: float = 0.0) -> list[Tick]:
    return [Tick(start_ts + i, f"{p:.5f}") for i, p in enumerate(prices)]


# --- resolve() ----------------------------------------------------------------------------------


def test_a_target_reached_first_pays_the_reward_risk_multiple():
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00200)  # risk 10 pips, reward 20
    ticks = _ticks([1.00000, 1.00050, 1.00100, 1.00250])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) == pytest.approx(2.0)


def test_a_stop_reached_first_costs_exactly_one_R():
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00200)
    ticks = _ticks([1.00000, 0.99950, 0.99850, 1.00300])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) == -1.0


def test_a_touch_of_the_level_counts_as_reaching_it():
    # the plan is read off levels a chart draws; a price that reaches the line has reached it
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00200)
    ticks = _ticks([1.00000, 1.00200])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) == pytest.approx(2.0)


def test_short_plans_are_mirrored_the_same_way():
    plan = TradePlan(Direction.DOWN, stop=1.00100, target=0.99800)
    ticks = _ticks([1.00000, 0.99990, 0.99790])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) == pytest.approx(2.0)
    stopped = _ticks([1.00000, 1.00150])
    assert resolve(plan, entry=1.00000, ticks=stopped, first=1, stop=len(stopped)) == -1.0


def test_a_trade_that_reaches_neither_level_is_unresolved_not_marked_to_market():
    # the source method has no time exit, so inventing one here would be inventing a different method
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00200)
    ticks = _ticks([1.00000, 1.00010, 1.00020, 1.00030])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) is None


def test_a_zero_risk_plan_is_refused_rather_than_dividing_by_it():
    plan = TradePlan(Direction.UP, stop=1.00000, target=1.00200)
    ticks = _ticks([1.00000, 1.00200])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) is None


def test_the_lookahead_wall_is_the_level_not_the_integer_index():
    # a level already behind the entry is not reachable "later" just because more ticks arrive
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00200)
    ticks = _ticks([1.00300, 1.00000, 1.00050])
    assert resolve(plan, entry=1.00000, ticks=ticks, first=1, stop=len(ticks)) is None


# --- TradePlan geometry -------------------------------------------------------------------------


def test_well_formed_requires_the_levels_on_the_correct_sides():
    up = TradePlan(Direction.UP, stop=0.99900, target=1.00200)
    assert up.is_well_formed(1.00000)
    assert not up.is_well_formed(0.99800)  # entry already through the "stop"
    assert not up.is_well_formed(1.00300)  # entry already past the "target"
    down = TradePlan(Direction.DOWN, stop=1.00100, target=0.99800)
    assert down.is_well_formed(1.00000)
    assert not down.is_well_formed(1.00200)


def test_reward_risk_is_reported_from_the_entry():
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00300)
    assert plan.risk(1.00000) == pytest.approx(0.00100)
    assert plan.reward(1.00000) == pytest.approx(0.00300)
    assert plan.reward_risk(1.00000) == pytest.approx(3.0)


def test_a_plan_that_risks_more_than_it_targets_is_allowed_and_reported_honestly():
    # 1:0.5 is a real shape for a mean-reversion method; the harness's job is to price it, not forbid it
    plan = TradePlan(Direction.UP, stop=0.99800, target=1.00100)
    assert plan.reward_risk(1.00000) == pytest.approx(0.5)


# --- the mirror control -------------------------------------------------------------------------


def test_the_mirror_flips_direction_and_keeps_both_distances():
    plan = TradePlan(Direction.UP, stop=0.99900, target=1.00300)
    mirror = mirrored_plan(plan, 1.00000)
    assert mirror.direction is Direction.DOWN
    assert mirror.risk(1.00000) == pytest.approx(plan.risk(1.00000))
    assert mirror.reward(1.00000) == pytest.approx(plan.reward(1.00000))
    # and it is a genuinely different trade, not the original's complement: its levels are elsewhere
    assert mirror.stop == pytest.approx(1.00100)
    assert mirror.target == pytest.approx(0.99700)


def test_a_mirror_is_always_well_formed_when_the_original_is():
    for plan in (TradePlan(Direction.UP, stop=0.9, target=1.1), TradePlan(Direction.DOWN, stop=1.1, target=0.9)):
        assert mirrored_plan(plan, 1.0).is_well_formed(1.0)


# --- the replay ---------------------------------------------------------------------------------


def test_harness_gives_strategies_no_lookahead():
    replay_trades(Peeker(), list(synthetic_price_ticks(100)))


def test_split_is_mandatory():
    with pytest.raises(ValueError):
        replay_trades(FixedGeometry(risk=0.0002, reward=0.0004), list(synthetic_price_ticks(100)), split=1.0)


def test_the_control_trades_the_same_moments_as_the_strategy():
    ticks = list(synthetic_price_ticks(5_000, seed=1))
    result = replay_trades(FixedGeometry(risk=0.0002, reward=0.0004, every=7), ticks)
    assert result.out_of_sample.trades == result.control.trades
    assert result.control.label.startswith("control: mirror of")


def test_the_paired_edge_is_recorded_per_trade_not_as_two_totals():
    ticks = list(synthetic_price_ticks(2_000, seed=1))
    result = replay_trades(FixedGeometry(risk=0.0002, reward=0.0004, every=20), ticks)
    oos = result.out_of_sample
    assert len(oos.paired_r_differences) <= oos.resolved
    assert result.control.paired_r_differences == []  # the pair's information lives on one side only


def test_malformed_plans_are_counted_not_silently_graded():
    ticks = _ticks([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    # a "long" whose stop sits above the entry is not a trade at all
    result = replay_trades(FiresOnce(2, TradePlan(Direction.UP, stop=1.5, target=2.0)), ticks, split=0.5)
    assert result.in_sample.malformed == 1
    assert result.in_sample.trades == 0


def test_unresolved_trades_are_counted_and_excluded_from_the_sample():
    ticks = _ticks([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    plan = TradePlan(Direction.UP, stop=0.9, target=1.1)
    result = replay_trades(FiresOnce(1, plan), ticks, split=0.5)
    assert result.in_sample.trades == 1
    assert result.in_sample.unresolved == 1
    assert result.in_sample.resolved == 0
    assert result.in_sample.r_multiples == []
    assert result.in_sample.paired_r_differences == []


def test_a_fixed_geometry_has_no_edge_over_its_mirror_on_a_driftless_walk():
    # The central null of the module: entering a stop/target trade at an arbitrary moment is worth
    # nothing against taking the opposite side of the same trade. Asserted on the *paired* difference,
    # which is what the verdict reads (see the barrier-jump test below for why the absolute numbers are
    # not the test) -- and averaged over several realizations, because a single driftless walk still has
    # a *realized* trend, and a method aligned with it legitimately scores above its own mirror. The
    # claim being tested is about the process, so it has to be measured over more than one sample.
    means = []
    for seed in range(6):
        ticks = list(synthetic_price_ticks(20_000, seed=seed, decimals=8))
        result = replay_trades(FixedGeometry(risk=0.0002, reward=0.0004, every=100), ticks)
        assert result.out_of_sample.resolved > 90
        means.append(result.out_of_sample.paired_interval[0])
    assert sum(means) / len(means) == pytest.approx(0.0, abs=0.15)


def test_a_tick_grid_coarse_enough_to_jump_a_level_biases_both_sides_alike():
    # The property that makes the paired test necessary rather than tidy. With a barrier smaller than a
    # typical tick step, a 2:1 trade wins about half the time instead of a third and shows a large
    # positive expectancy in *both* directions -- so the absolute number is an artifact of the grid.
    # The paired comparison stays correct: it must not report that as an edge.
    ticks = list(synthetic_price_ticks(20_000, seed=3))  # 5 decimals, step_std 5e-5: barriers 2e-5/4e-5
    result = replay_trades(FixedGeometry(risk=0.00002, reward=0.00004), ticks)
    assert result.out_of_sample.expectancy > 0.2
    assert result.control.expectancy > 0.2  # the mirror is biased the same way, not less
    assert not result.verdict.startswith("POSITIVE")


def test_the_harness_can_detect_a_real_edge_when_one_obviously_exists():
    # positive control: with a strong upward drift, a plan that only ever goes long must show a clearly
    # positive edge over its mirror -- confirming the instrument can register a real signal, not only a
    # null. Driven through the verdict, so it exercises the paired statistic the way a real run does.
    ticks = list(synthetic_price_ticks(20_000, seed=5, drift=0.001, step_std=0.00005))
    result = replay_trades(FixedGeometry(risk=0.0002, reward=0.0004), ticks)
    assert result.out_of_sample.expectancy > 1.0
    assert result.verdict.startswith("POSITIVE")


def test_a_wrong_way_round_plan_reads_worse_than_its_own_mirror():
    # the mirror control's other half: on a rising market the short plan is the losing side and the
    # mirror (long) is the winning one, so this must not read as "no edge"
    ticks = list(synthetic_price_ticks(20_000, seed=5, drift=0.001, step_std=0.00005))
    result = replay_trades(FixedGeometry(direction=Direction.DOWN, risk=0.0002, reward=0.0004), ticks)
    assert result.verdict.startswith("Worse than its own mirror")


def test_report_names_every_segment_and_the_counts():
    ticks = list(synthetic_price_ticks(2_000, seed=1))
    report = replay_trades(FixedGeometry(risk=0.0002, reward=0.0004, every=50), ticks).report()
    assert "in-sample" in report and "out-of-sample" in report and "control:" in report
    assert "expectancy" in report and "win rate" in report and "verdict" in report
    assert "resolved" in report and "paired edge" in report


# --- verdict thresholds, driven directly rather than waiting on a real recording ------------------


def _seg(label, r_multiples=(), paired=()):
    seg = TradeSegmentResult(label=label, ticks=1)
    seg.trades = len(r_multiples)
    seg.wins = sum(1 for r in r_multiples if r > 0)
    seg.losses = sum(1 for r in r_multiples if r <= 0)
    seg.r_multiples = list(r_multiples)
    seg.paired_r_differences = list(paired)
    return seg


def _result(oos):
    return TradeReplayResult("test", _seg("in-sample"), oos, _seg("control"))


def test_too_few_paired_trades_gets_no_verdict():
    result = _result(_seg("out-of-sample", [1.0] * 10, paired=[0.2] * 10))
    assert result.verdict.startswith("NO VERDICT")
    assert "500" in result.verdict


def test_a_consistently_positive_paired_edge_is_reported_as_positive():
    result = _result(_seg("out-of-sample", [1.0] * 600, paired=[0.4] * 600))
    assert result.verdict.startswith("POSITIVE edge over its own mirror")


def test_a_consistently_negative_paired_edge_reads_as_worse_than_the_mirror():
    result = _result(_seg("out-of-sample", [-1.0] * 600, paired=[-0.4] * 600))
    assert result.verdict.startswith("Worse than its own mirror")


def test_a_paired_edge_straddling_zero_reads_as_no_edge():
    result = _result(_seg("out-of-sample", [1.0] * 600, paired=[1.0, -1.0] * 300))
    assert result.verdict.startswith("No edge over its own mirror")


def test_expectancy_is_the_mean_over_resolved_trades_only():
    seg = _seg("x", [1.0, -1.0, 2.0])
    assert seg.resolved == 3
    assert seg.expectancy == pytest.approx(2.0 / 3)
