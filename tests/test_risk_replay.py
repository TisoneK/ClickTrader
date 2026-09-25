import pytest

from clicktrader.limits import RiskLimits
from clicktrader.model import Contract, Side
from clicktrader.risk_replay import replay_sessions, simulate_session
from clicktrader.strategies import FixedContract, LowDigitOver, MartingaleOnLoss
from clicktrader.synthetic import synthetic_ticks

LIMITS = RiskLimits(max_stake=2, max_session_loss=5, max_consecutive_losses=3)


def test_simulate_session_matches_unbounded_when_the_guard_never_trips():
    bets = [(1.0, -0.5), (1.0, 0.3), (1.0, -0.2)]
    outcome = simulate_session(bets, RiskLimits(max_stake=2, max_session_loss=100, max_consecutive_losses=99))
    assert not outcome.stopped_early
    assert outcome.guarded_bets == outcome.total_bets_available == 3
    assert outcome.guarded_final_pnl == pytest.approx(outcome.unbounded_final_pnl)
    assert outcome.guarded_max_drawdown == pytest.approx(outcome.unbounded_max_drawdown)


def test_simulate_session_stops_the_guarded_view_but_not_the_unbounded_one():
    # three straight losses trips the consecutive-loss limit; two winning bets follow in the raw sequence,
    # so the unbounded view ends up strictly better off than the guarded one stopped short of them.
    bets = [(1.0, -1.0), (1.0, -1.0), (1.0, -1.0), (1.0, +5.0), (1.0, +5.0)]
    outcome = simulate_session(bets, LIMITS)
    assert outcome.stopped_early
    assert outcome.guarded_bets == 3
    assert outcome.guarded_final_pnl == pytest.approx(-3.0)
    assert "consecutive" in outcome.halted_reason
    assert outcome.total_bets_available == 5
    assert outcome.unbounded_final_pnl == pytest.approx(7.0)  # the full sequence, guard or no guard


def test_simulate_session_never_lets_guarded_loss_exceed_the_session_cap():
    bets = [(2.0, -2.0)] * 20  # far more losses than the cap could ever absorb
    outcome = simulate_session(bets, LIMITS)
    assert outcome.guarded_final_pnl >= -LIMITS.max_session_loss - 1e-9
    assert outcome.unbounded_final_pnl == pytest.approx(-40.0)  # nothing stopped the unbounded view


def test_replay_sessions_chops_into_non_overlapping_fixed_length_windows():
    ticks = list(synthetic_ticks(1000, seed=1))
    report = replay_sessions(lambda: LowDigitOver(barrier=1, stake=0.10), ticks, LIMITS, session_ticks=100)
    assert report.n == 10  # 1000 ticks / 100 per session, exactly -- no remainder to drop here
    assert report.session_ticks == 100


def test_replay_sessions_gives_every_session_a_fresh_strategy_instance():
    # a stateful strategy's balance must not leak across session boundaries -- a ruined-out martingale
    # in session 1 must not still be ruined (stake capped to 0, no bets placed) in session 2.
    ticks = list(synthetic_ticks(6000, seed=3))
    factory = lambda: MartingaleOnLoss(  # noqa: E731
        LowDigitOver(barrier=1, stake=0.10), starting_balance=1.0, base_stake=0.10, max_fraction_of_balance=1.0
    )
    report = replay_sessions(factory, ticks, RiskLimits(max_stake=50, max_session_loss=1000, max_consecutive_losses=999), session_ticks=2000)
    assert report.n >= 2
    # every session got a fresh balance, so every session placed at least one bet -- a leaked, already-
    # ruined instance would place zero bets in every session after the first.
    assert all(s.total_bets_available > 0 for s in report.sessions)


def test_riskguard_bounds_the_worst_case_drawdown_martingales_own_doubling_produces():
    # the discipline argument, measured: an uncapped martingale's doubling has no ceiling on a losing
    # streak (DESIGN.md's own finding), and RiskGuard's job is exactly to put one there. The base contract
    # here is a plain 50/50 bet with the martingale's own internal stake cap effectively switched off
    # (a huge starting balance), so RiskGuard is the *only* thing standing between the strategy and its
    # own doubling on a real losing streak -- not the strategy's own bookkeeping.
    ticks = list(synthetic_ticks(60_000, seed=5))
    limits = RiskLimits(max_stake=10, max_session_loss=10, max_consecutive_losses=99)
    factory = lambda: MartingaleOnLoss(  # noqa: E731
        FixedContract(Contract(Side.OVER, 4)), starting_balance=1_000_000.0, base_stake=0.10, max_fraction_of_balance=1.0
    )
    report = replay_sessions(factory, ticks, limits, session_ticks=500)
    assert report.n > 10
    intervened = [s for s in report.sessions if s.stopped_early]
    assert len(intervened) > report.n / 2  # a losing streak long enough to matter is the common case here
    for outcome in report.sessions:
        assert outcome.guarded_final_pnl >= -limits.max_session_loss - 1e-9
        # never worse than the unbounded view on the same decisions -- stopping early can only help
        assert outcome.guarded_max_drawdown <= outcome.unbounded_max_drawdown + 1e-9
    # the headline, measured claim: with the guard, the worst session across the whole run is bounded
    # near the cap; without it, on the very same decisions, the worst case is catastrophically larger.
    assert report.guarded_worst_session_pnl >= -limits.max_session_loss - 1e-9
    assert report.unbounded_worst_session_pnl < 5 * report.guarded_worst_session_pnl
    assert report.unbounded_worst_drawdown > 10 * report.guarded_worst_drawdown


def test_report_shows_both_views_side_by_side():
    ticks = list(synthetic_ticks(2000, seed=1))
    report = replay_sessions(lambda: LowDigitOver(barrier=1, stake=0.10), ticks, LIMITS, session_ticks=200)
    text = report.report()
    assert "guarded" in text and "unbounded" in text
    assert "guard intervened in" in text


def test_session_ticks_must_be_at_least_two():
    with pytest.raises(ValueError):
        replay_sessions(lambda: LowDigitOver(), [], LIMITS, session_ticks=1)
