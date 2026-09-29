"""The live loop and its shadows, driven through injected ticks and a fake strategy.

The loop's job is bookkeeping: one trade per signal, limits respected, results logged, variants scored
without being traded. All of that is testable without a broker, which is why the tick stream, the clock
and the printer are all injectable.
"""

import pytest

from clicktrader.forex.model import Direction, Signal
from clicktrader.forex.strategies import SignalDecision
from clicktrader.limits import RiskLimits
from clicktrader.model import Tick
from clicktrader.recording import TickRecord
from clicktrader.runner import RunSummary, ShadowVariant, run, shadow_grid
from clicktrader.trade_log import read_trades


class AlwaysRises:
    """Signals on every tick, so the loop's own behaviour is what is under test."""

    def __init__(self, direction=Direction.UP, seconds=2.0):
        self.name = "always"
        self._direction, self._seconds = direction, seconds

    def decide(self, history):
        return SignalDecision(Signal(self._direction, horizon_seconds=self._seconds), 1.0, "always")


def _ticks(n, *, start=1.0, step=0.0):
    """TickRecords, exactly what `stream_ticks` yields — the loop consumes the real feed's shape."""
    return [
        TickRecord(tick=Tick(float(i), f"{start + i * step:.5f}", "1HZ25V")) for i in range(n)
    ]


def test_paper_mode_runs_the_loop_and_places_nothing(tmp_path):
    said = []
    summary = run(
        symbol="1HZ25V", log_path=str(tmp_path / "t.jsonl"), stake=1.0, paper=True,
        ticks=iter(_ticks(5)), strategy_factory=AlwaysRises, emit=said.append,
        report_every=1e9, max_ticks=5,
    )
    assert summary.ticks == 5
    assert summary.signals >= 4
    assert summary.placed == 0
    assert any("PAPER MODE" in line for line in said)
    assert any("SIGNAL (paper)" in line for line in said)
    assert list(read_trades(tmp_path / "t.jsonl")) == []


def test_it_stops_when_asked_to():
    said = []
    summary = run(
        symbol="1HZ25V", log_path="/tmp/unused.jsonl", stake=1.0, paper=True,
        ticks=iter(_ticks(1000)), strategy_factory=AlwaysRises, emit=said.append,
        report_every=1e9, max_ticks=10,
    )
    assert summary.ticks == 10
    assert any("reached --max-ticks 10" in line for line in said)


def test_the_limits_can_refuse_a_signal_without_stopping_the_run():
    # a stake cap below the stake refuses every signal, and the run keeps watching rather than dying
    said = []
    summary = run(
        symbol="1HZ25V", log_path="/tmp/unused.jsonl", stake=1.0, paper=True,
        ticks=iter(_ticks(6)), strategy_factory=AlwaysRises, emit=said.append, report_every=1e9,
        limits=RiskLimits(max_stake=0.5, max_session_loss=10.0, max_consecutive_losses=5),
    )
    assert summary.signals >= 1 and summary.placed == 0
    assert summary.refused == summary.signals
    assert any("refused by the limits" in line for line in said)


def test_a_tripped_guard_stops_the_run_instead_of_going_quiet():
    # The guard latches when it trips. A loop that keeps running past that point watches, prints and
    # places nothing -- the worst of the available behaviours, because it looks like it is working.
    from clicktrader.limits import RiskGuard, RiskLimits

    class TripsImmediately(RiskGuard):
        def __init__(self):
            super().__init__(RiskLimits(max_stake=1.0, max_session_loss=1.0, max_consecutive_losses=1))
            self._trip("1 consecutive loss (limit 1)")

    said = []
    summary = run(
        symbol="1HZ25V", log_path="/tmp/unused.jsonl", stake=1.0, paper=True,
        ticks=iter(_ticks(50)), strategy_factory=AlwaysRises, emit=said.append, report_every=1e9,
        guard_factory=TripsImmediately,
    )
    assert summary.placed == 0
    assert any("STOPPING" in line for line in said)
    assert any("A person has to decide" in line for line in said)
    assert summary.ticks < 50  # it stopped rather than grinding through the stream


def test_the_readout_says_nothing_is_placed_yet_and_that_that_is_normal():
    assert "nothing placed yet" in RunSummary(ticks=500, signals=0).readout()
    assert "normal" in RunSummary(ticks=500, signals=0).readout()
    assert "won 3 of 8" in RunSummary(ticks=999, signals=9, placed=8, won=3, net=-1.5).readout()


# --- the shadows --------------------------------------------------------------------------------


def test_a_shadow_scores_a_decision_against_the_price_that_actually_arrived():
    variant = ShadowVariant("v", AlwaysRises(Direction.UP, seconds=2.0))
    ticks = [Tick(0.0, "1.00000"), Tick(1.0, "1.00000"), Tick(2.0, "1.00500")]
    variant.feed(ticks[0], type("H", (), {"__len__": lambda self: 1})())
    assert variant.bets == 0  # nothing settles before the clock reaches it
    variant.resolve(ticks[1])
    assert variant.bets == 0
    variant.resolve(ticks[2])
    assert (variant.bets, variant.wins, variant.rate) == (1, 1, 1.0)


def test_a_shadow_loses_when_the_market_went_the_other_way():
    variant = ShadowVariant("v", AlwaysRises(Direction.UP, seconds=1.0))
    ticks = [Tick(0.0, "1.00000"), Tick(1.0, "0.99000")]
    variant.feed(ticks[0], type("H", (), {"__len__": lambda self: 1})())
    variant.resolve(ticks[1])
    assert (variant.bets, variant.wins) == (1, 0)


def test_shadows_are_scored_but_never_traded():
    said = []
    run(
        symbol="1HZ25V", log_path="/tmp/unused.jsonl", stake=1.0, paper=True,
        ticks=iter(_ticks(20, step=0.001)), strategy_factory=AlwaysRises, emit=said.append,
        report_every=1e9,
    )
    assert any("what the shadows say so far" in line for line in said)
    assert any("no money on any of these" in line for line in said)
    assert any("-- live settings" in line for line in said)


def test_the_grid_is_small_and_coarse_on_purpose():
    # a wide grid read live would be fitting noise in public; these are directions to look in, not a search
    grid = shadow_grid(tolerance=0.002, body_ratio=0.6, size_multiple=1.5, expiry=120)
    assert len(grid) <= 6
    names = [v.name for v in grid]
    assert "looser levels" in names and "tighter levels" in names and "three touches" in names
    assert all(isinstance(v, ShadowVariant) and v.bets == 0 for v in grid)
