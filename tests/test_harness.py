import pytest

from clicktrader.harness import replay
from clicktrader.ledger import DecisionLedger, read_ledger
from clicktrader.model import Contract, Side, Tick
from clicktrader.strategies import FixedContract, History, LowDigitOver, RandomControl, StreakReversal
from clicktrader.synthetic import synthetic_ticks


def test_history_cannot_see_the_future():
    ticks = [Tick(i, f"1.0{i}") for i in range(5)]
    h = History(ticks, 3)
    assert len(h) == 3 and h[-1].price == "1.02"
    assert [t.price for t in h[:]] == ["1.00", "1.01", "1.02"]
    with pytest.raises(IndexError):
        h[3]


class Peeker:
    """Tries to cheat by reading the settling tick — the harness must make that impossible."""
    name = "peeker"

    def decide(self, history):
        try:
            history[len(history)]
        except IndexError:
            return None
        return pytest.fail("strategy read a tick from the future")


def test_harness_gives_strategies_no_lookahead():
    replay(Peeker(), list(synthetic_ticks(100)))


def test_contract_settles_on_the_next_tick():
    ticks = [Tick(0, "1.00"), Tick(1, "1.09"), Tick(2, "1.00"), Tick(3, "1.00")]
    ledger = DecisionLedger()
    replay(FixedContract(Contract(Side.OVER, 4)), ticks, split=0.5, ledger=ledger)
    first = ledger.rows[0]
    assert (first.digit_seen, first.settle_digit, first.won) == (0, 9, True)


def test_split_is_mandatory():
    with pytest.raises(ValueError):
        replay(RandomControl(), list(synthetic_ticks(10)), split=1.0)


def test_small_sample_gets_no_verdict():
    result = replay(FixedContract(Contract(Side.OVER, 4)), list(synthetic_ticks(400)))
    assert result.verdict.startswith("NO VERDICT")


def test_streak_reversal_finds_no_edge_on_a_uniform_feed():
    result = replay(StreakReversal(run=3), list(synthetic_ticks(60_000, seed=7)))
    oos = result.out_of_sample
    assert oos.bets > 1000
    assert oos.expected_hit_rate == pytest.approx(0.5)
    lo, hi = oos.hit_rate_interval
    assert lo < 0.5 < hi
    assert result.verdict.startswith(("No edge", "Return per stake"))


def test_fixed_contract_converges_to_the_pricing():
    result = replay(FixedContract(Contract(Side.OVER, 4)), list(synthetic_ticks(40_000, seed=3)))
    mean, lo, hi = result.out_of_sample.return_per_stake
    assert lo < -0.05 < hi


def test_control_bets_about_as_often_as_the_strategy():
    result = replay(StreakReversal(run=3), list(synthetic_ticks(20_000, seed=1)))
    assert result.control.bets == pytest.approx(result.out_of_sample.bets, rel=0.15)


def test_low_digit_over_fires_only_on_digits_0_and_1():
    strategy = LowDigitOver(barrier=1, stake=0.10)
    ticks = [Tick(0, "1.00"), Tick(1, "1.01"), Tick(2, "1.02"), Tick(3, "1.09")]
    decisions = [strategy.decide(History(ticks, end)) for end in range(1, len(ticks) + 1)]
    assert [d is not None for d in decisions] == [True, True, False, False]
    assert decisions[0].contract == Contract(Side.OVER, 1)
    assert decisions[0].stake == 0.10


def test_low_digit_over_finds_no_edge_on_a_uniform_feed():
    result = replay(LowDigitOver(barrier=1, stake=0.10), list(synthetic_ticks(60_000, seed=11)))
    oos = result.out_of_sample
    assert oos.bets > 1000
    assert oos.expected_hit_rate == pytest.approx(0.8)  # Over(1) wins on digits 2-9
    lo, hi = oos.hit_rate_interval
    assert lo < 0.8 < hi
    assert result.verdict.startswith(("No edge", "Return per stake", "Worse than the pricing"))


def test_ledger_rows_account_for_every_bet(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ticks = list(synthetic_ticks(2000, seed=2))
    with DecisionLedger(path) as ledger:
        result = replay(StreakReversal(run=2), ticks, ledger=ledger, log_skips=True)
    rows = list(read_ledger(path))
    bets = [r for r in rows if r.action == "bet"]
    assert len(bets) == result.in_sample.bets + result.out_of_sample.bets
    assert len(rows) == len(ticks) - 2  # one decision per tick that has a settling tick in its segment
    assert sum(r.pnl for r in bets) == pytest.approx(result.in_sample.pnl + result.out_of_sample.pnl)
    assert all(r.reason for r in rows)
