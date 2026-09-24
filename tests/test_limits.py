import pytest

from clicktrader.limits import RiskGuard, RiskLimits

LIMITS = RiskLimits(max_stake=2, max_session_loss=10, max_consecutive_losses=3)


def test_limits_must_all_be_set():
    with pytest.raises(ValueError):
        RiskLimits(max_stake=0, max_session_loss=10, max_consecutive_losses=3)
    with pytest.raises(ValueError):
        RiskLimits(max_stake=20, max_session_loss=10, max_consecutive_losses=3)


def test_stake_cap():
    g = RiskGuard(LIMITS)
    assert g.check(2) is None
    assert "max stake" in g.check(2.01)
    assert g.check(0) is not None


def test_consecutive_losses_trip_and_latch():
    g = RiskGuard(LIMITS)
    for _ in range(3):
        g.record(-1)
    assert g.halted and "consecutive" in g.halted_reason
    g.record(+5)  # a win after the trip does not un-trip it
    assert g.halted and g.check(1).startswith("halted")


def test_session_cap_is_checked_before_the_trade():
    g = RiskGuard(LIMITS)
    for pnl in (-2, +0.1, -2, +0.1, -2, +0.1, -2):  # streak never reaches 3
        g.record(pnl)
    assert not g.halted and g.session_pnl == pytest.approx(-7.7)
    assert g.check(2) is None
    g.record(-2)
    assert "over the cap" in g.check(1)  # 9.7 lost; losing 1 more would breach 10


def test_session_cap_trips():
    g = RiskGuard(RiskLimits(max_stake=5, max_session_loss=10, max_consecutive_losses=99))
    g.record(-5)
    g.record(-5)
    assert g.halted and "session loss" in g.halted_reason


def test_only_a_named_human_rearms():
    g = RiskGuard(LIMITS)
    g.kill("operator saw something odd")
    assert g.halted
    with pytest.raises(ValueError):
        g.rearm("  ")
    g.rearm("Tisone")
    assert not g.halted and g.rearmed_by == ["Tisone"]


def test_rearm_does_not_forgive_the_session_loss():
    g = RiskGuard(RiskLimits(max_stake=5, max_session_loss=10, max_consecutive_losses=99))
    g.record(-5)
    g.record(-5)
    g.rearm("Tisone")
    assert g.check(1) is not None
