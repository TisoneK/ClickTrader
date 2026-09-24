import pytest

from clicktrader.harness import replay
from clicktrader.model import Contract, Side, Tick
from clicktrader.strategies import (
    ColdTailOverUnder,
    ColdTailReactiveOver,
    Decision,
    History,
    MartingaleOnLoss,
    ParityCounterTrend,
)
from clicktrader.synthetic import synthetic_ticks


def _tick(i: int, digit: int) -> Tick:
    return Tick(i, f"1.{digit}")


def _history(digits: list[int]) -> History:
    ticks = [_tick(i, d) for i, d in enumerate(digits)]
    return History(ticks, len(ticks))


# --- ColdTailOverUnder ---------------------------------------------------


def test_cold_tail_over_fires_when_watched_digits_are_cold():
    strategy = ColdTailOverUnder(Side.OVER, 2, window=10, stake=1.0)
    digits = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3]  # 0 and 1 never appear -> 0% each
    decision = strategy.decide(_history(digits))
    assert decision is not None
    assert decision.contract == Contract(Side.OVER, 2)


def test_cold_tail_over_does_not_fire_when_a_watched_digit_is_at_the_threshold():
    strategy = ColdTailOverUnder(Side.OVER, 2, window=10, stake=1.0)
    digits = [0, 3, 4, 5, 6, 7, 8, 9, 2, 3]  # digit 0 appears once = exactly 10%, not "under"
    assert strategy.decide(_history(digits)) is None


def test_cold_tail_under_watches_digits_above_the_barrier():
    strategy = ColdTailOverUnder(Side.UNDER, 7, window=10, stake=1.0)
    cold = [0, 1, 2, 3, 4, 5, 6, 0, 1, 2]  # 8 and 9 never appear
    hot = [0, 1, 2, 3, 4, 5, 8, 0, 1, 2]  # 8 appears once = 10%
    assert strategy.decide(_history(cold)).contract == Contract(Side.UNDER, 7)
    assert strategy.decide(_history(hot)) is None


def test_cold_tail_needs_a_full_window():
    strategy = ColdTailOverUnder(Side.OVER, 2, window=10, stake=1.0)
    assert strategy.decide(_history([2] * 9)) is None


# --- ColdTailReactiveOver -------------------------------------------------


def test_cold_tail_reactive_needs_both_the_filter_and_the_live_trigger():
    strategy = ColdTailReactiveOver(barrier=2, window=10, stake=1.0)
    cold_tail = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3]

    # filter satisfied (0, 1 cold) but last digit (3) is not in the 0..2 trigger range
    assert strategy.decide(_history(cold_tail)) is None

    # filter satisfied AND last digit is 2 (in 0..2 inclusive) -> fires
    decision = strategy.decide(_history(cold_tail[:-1] + [2]))
    assert decision is not None
    assert decision.contract == Contract(Side.OVER, 2)

    # last digit qualifies but the filter doesn't (0 is hot)
    hot_tail = [0, 3, 4, 5, 6, 7, 8, 9, 2, 1]
    assert strategy.decide(_history(hot_tail)) is None


# --- ParityCounterTrend ----------------------------------------------------


def test_parity_threshold_dominance_fires_on_the_opposite_pair():
    # 4 even digits above 10%, 1 odd digit above 10% -> even dominates
    digits = [0, 0, 2, 2, 4, 4, 6, 6, 8, 8, 1, 1, 3, 5, 7, 9] + [3, 3]  # tail forces two consecutive odds
    strategy = ParityCounterTrend(dominance="threshold", window=16, stake=1.0)
    decision = strategy.decide(_history(digits))
    assert decision is not None
    assert decision.contract == Contract(Side.EVEN)


def test_parity_threshold_does_not_fire_without_the_opposite_pair():
    digits = [0, 0, 2, 2, 4, 4, 6, 6, 8, 8, 1, 1, 3, 5, 7, 9] + [3, 2]  # last two aren't both odd
    strategy = ParityCounterTrend(dominance="threshold", window=16, stake=1.0)
    assert strategy.decide(_history(digits)) is None


def test_parity_majority_dominance_uses_combined_frequency():
    # 2 arbitrary padding digits (outside the 16-window `decide` actually reads) + a 16-digit window:
    # evens appear 10 times, odds appear 6 times -> even dominates by combined frequency, ending on
    # two odds so the trigger fires too.
    padding = [5, 5]
    window_digits = [0, 2, 4, 6, 8, 0, 2, 4, 6, 8, 1, 3, 5, 7, 9, 1]
    strategy = ParityCounterTrend(dominance="majority", window=16, stake=1.0)
    decision = strategy.decide(_history(padding + window_digits))
    assert decision is not None
    assert decision.contract == Contract(Side.EVEN)


def test_parity_rejects_an_unknown_dominance_rule():
    with pytest.raises(ValueError):
        ParityCounterTrend(dominance="vibes")


# --- MartingaleOnLoss -------------------------------------------------------


class AlwaysBetOverFour:
    """A tiny fixed strategy so Martingale's own stake logic can be tested in isolation."""

    name = "always-over-4"

    def decide(self, history: History) -> Decision:
        return Decision(Contract(Side.OVER, 4), 1.0, "always")


def test_martingale_doubles_after_a_loss_and_resets_after_a_win():
    strategy = MartingaleOnLoss(AlwaysBetOverFour(), starting_balance=1000.0, base_stake=1.0, multiplier=2.0, max_fraction_of_balance=1.0)
    # tick 0: base decision, stake 1.0
    d0 = strategy.decide(_history([9]))
    assert d0.stake == 1.0
    # tick 1 settles tick 0's bet against digit at index 1 (a loss: Over(4) loses on digit 2)
    d1 = strategy.decide(_history([9, 2]))
    assert d1.stake == 2.0
    # tick 2 settles tick 1's bet against digit at index 2 (a win: Over(4) wins on digit 9)
    d2 = strategy.decide(_history([9, 2, 9]))
    assert d2.stake == 1.0  # reset to base after the win


def test_martingale_caps_the_stake_at_a_fraction_of_balance():
    strategy = MartingaleOnLoss(
        AlwaysBetOverFour(), starting_balance=10.0, base_stake=1.0, multiplier=10.0, max_fraction_of_balance=0.05
    )
    strategy.decide(_history([9]))  # stake 1.0
    d1 = strategy.decide(_history([9, 2]))  # loss -> theoretical stake 10.0, capped at 5% of ~9 balance
    assert d1.stake == pytest.approx(strategy._balance * 0.05)
    assert d1.stake < 1.0  # far below the uncapped martingale progression


def test_martingale_stops_betting_once_balance_is_exhausted():
    strategy = MartingaleOnLoss(
        AlwaysBetOverFour(), starting_balance=1.0, base_stake=1.0, multiplier=2.0, max_fraction_of_balance=1.0
    )
    strategy.decide(_history([9]))  # places the first $1.00 bet
    # digit 2 settles that bet as a loss for Over(4): balance drops 1.0 -> 0.0, so the cap (0% of 0) is 0
    assert strategy.decide(_history([9, 2])) is None


def test_martingale_passes_through_none_when_the_base_strategy_skips():
    class NeverBets:
        name = "never"

        def decide(self, history: History):
            return None

    strategy = MartingaleOnLoss(NeverBets(), starting_balance=1000.0, base_stake=1.0)
    assert strategy.decide(_history([9, 2, 3])) is None


# --- Statistical: no edge on a uniform feed ---------------------------------


def test_cold_tail_finds_no_edge_on_a_uniform_feed():
    result = replay(ColdTailOverUnder(Side.OVER, 2, window=100, stake=0.10), list(synthetic_ticks(60_000, seed=21)))
    oos = result.out_of_sample
    assert oos.bets > 500
    assert oos.expected_hit_rate == pytest.approx(0.7)  # Over(2) wins on digits 3-9
    assert result.verdict.startswith(("No edge", "Return per stake", "Worse than the pricing"))


def test_parity_counter_trend_finds_no_edge_on_a_uniform_feed():
    result = replay(ParityCounterTrend(dominance="threshold", window=100, stake=0.10), list(synthetic_ticks(80_000, seed=22)))
    oos = result.out_of_sample
    assert oos.bets > 500
    assert oos.expected_hit_rate == pytest.approx(0.5)
    assert result.verdict.startswith(("No edge", "Return per stake", "Worse than the pricing"))
