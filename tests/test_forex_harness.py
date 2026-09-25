import pytest

from clicktrader.forex.harness import replay
from clicktrader.forex.model import Direction, Signal
from clicktrader.forex.strategies import MovingAverageCrossover, RandomDirection, SignalDecision
from clicktrader.forex.synthetic import synthetic_price_ticks
from clicktrader.model import Tick
from clicktrader.strategies import History


class AlwaysUpOverThree:
    """Fixed-signal strategy so the harness's own settlement mechanics can be tested in isolation,
    the forex equivalent of test_harness.py's FixedContract-based checks."""

    name = "always-up-3"

    def decide(self, history: History) -> SignalDecision:
        return SignalDecision(Signal(Direction.UP, horizon_ticks=3), 1.0, "always")


class Peeker:
    """Tries to read past the end of history -- the harness must make that impossible."""

    name = "peeker"

    def decide(self, history: History):
        try:
            history[len(history)]
        except IndexError:
            return None
        return pytest.fail("strategy read a tick from the future")


def test_harness_gives_strategies_no_lookahead():
    ticks = list(synthetic_price_ticks(100))
    replay(Peeker(), ticks)


def test_settles_against_the_signals_own_horizon_not_the_next_tick():
    ticks = [Tick(i, f"{1.0 + i * 0.1:.2f}") for i in range(10)]  # strictly increasing
    result = replay(AlwaysUpOverThree(), ticks, split=0.5)
    # every decision that has 3 ticks of runway left should win, on a strictly increasing series
    assert result.out_of_sample.bets > 0
    assert result.out_of_sample.hit_rate == pytest.approx(1.0)


def test_skips_decisions_without_enough_future_data_in_the_segment():
    ticks = [Tick(i, "1.0") for i in range(5)]  # flat; horizon=3 leaves only 2 gradeable decisions in 5
    result = replay(AlwaysUpOverThree(), ticks, split=0.999)
    # whichever segment gets the tail end, no bet should be counted past ticks - horizon
    assert result.in_sample.bets <= 2 or result.out_of_sample.bets <= 2


def test_split_is_mandatory():
    with pytest.raises(ValueError):
        replay(RandomDirection(), list(synthetic_price_ticks(10)), split=1.0)


def test_small_sample_gets_no_verdict():
    result = replay(AlwaysUpOverThree(), list(synthetic_price_ticks(400)))
    assert result.verdict.startswith("NO VERDICT")


def test_ma_crossover_finds_no_directional_edge_on_a_driftless_random_walk():
    ticks = list(synthetic_price_ticks(60_000, seed=3, drift=0.0))
    result = replay(MovingAverageCrossover(short_window=5, long_window=20, horizon_ticks=10), ticks)
    oos = result.out_of_sample
    assert oos.bets > 500
    lo, hi = oos.hit_rate_interval
    assert lo < 0.5 < hi
    assert result.verdict.startswith("No directional edge")


def test_random_direction_is_close_to_a_coin_flip_by_construction():
    ticks = list(synthetic_price_ticks(20_000, seed=4))
    result = replay(RandomDirection(seed=9, horizon_ticks=5), ticks)
    assert result.out_of_sample.hit_rate == pytest.approx(0.5, abs=0.05)


def test_the_harness_can_detect_a_real_signal_when_one_obviously_exists():
    # positive control: a strong, obvious upward drift should make "always predict up" clearly win --
    # sanity-checking the mechanism itself, not a claim about real markets.
    ticks = list(synthetic_price_ticks(20_000, seed=5, drift=0.001, step_std=0.00005))
    result = replay(AlwaysUpOverThree(), ticks)
    lo, _hi = result.out_of_sample.hit_rate_interval
    assert lo > 0.9
    assert result.verdict.startswith("POSITIVE")


def test_report_includes_the_verdict_and_all_three_segments():
    ticks = list(synthetic_price_ticks(2000, seed=1))
    report = replay(RandomDirection(seed=1), ticks).report()
    assert "in-sample" in report and "out-of-sample" in report and "control:" in report
    assert "verdict" in report


def test_verdict_uses_the_measured_control_baseline_not_a_fixed_50_percent():
    # coarse rounding creates real, non-degenerate ties (not aliased with the horizon), the same
    # mechanism that dragged a real EUR/USD recording's random control down to ~43% instead of 50%.
    raw = list(synthetic_price_ticks(20_000, seed=11, step_std=0.0003))
    coarse = [Tick(t.ts, f"{round(float(t.price), 3):.3f}", t.symbol) for t in raw]

    result = replay(RandomDirection(seed=1, horizon_ticks=5), coarse, control=RandomDirection(seed=99, horizon_ticks=5))

    baseline = result.control.hit_rate
    assert baseline < 0.48  # meaningfully depressed below a naive 50% by real ties
    # the strategy under test is itself just a differently-seeded coin flip -- genuinely no-skill --
    # so it should read as "no edge" relative to the depressed baseline, not get falsely flagged as
    # "worse than a coin flip" the way the old fixed-0.5 comparison would have.
    assert result.verdict.startswith("No directional edge")
    assert not result.verdict.startswith("Worse than")
