"""The Multipliers loop: stop-based risk, an open-ended hold, and a hard trade cap."""

import json

import pytest

from clicktrader.forex.model import Direction, TradePlan
from clicktrader.forex.trade_strategies import TradeDecision
from clicktrader.model import Tick
from clicktrader.multipliers import MultiplierRun, run
from clicktrader.recording import TickRecord


class FiresOnEveryTick:
    """A plan every tick, so the loop's own bookkeeping is what is under test."""

    name = "always"

    def __init__(self, *, stop: float, target: float, direction=Direction.UP):
        self._plan = TradePlan(direction, stop=stop, target=target)

    def decide(self, history):
        return TradeDecision(self._plan, 1.0, "test plan")


class FakeBroker:
    def __init__(self, profits):
        self.placed: list[TradePlan] = []
        self._profits = list(profits)

    def place(self, plan, entry):
        self.placed.append(plan)
        return 1000 + len(self.placed), 1.0, "USD"

    def watch(self, contract_id, *, timeout, poll_every, sleep=None):
        return self._profits.pop(0)


def _ticks(n, price=100.0):
    return [TickRecord(tick=Tick(float(i), f"{price:.5f}", "1HZ100V")) for i in range(n)]


def test_a_plan_whose_stop_risks_more_than_allowed_is_refused_not_placed(tmp_path):
    # the check RiskGuard cannot make: at multiplier 100 a stop 5% away on a 1 stake is 5.00 of exposure,
    # so the stake is not the worst case and sizing from it would be sizing from the wrong number
    broker = FakeBroker([1.0, 1.0])
    said = []
    result = run(symbol="1HZ100V", log_path=str(tmp_path / "t.jsonl"), stake=1.0, multiplier=100,
                 strategy=FiresOnEveryTick(stop=95.0, target=110.0), max_trades=1, max_loss_per_trade=2.0,
                 ticks=iter(_ticks(1)), broker=broker, emit=said.append)
    assert result.placed == 0 and result.refused == 1
    assert broker.placed == []
    assert any("over the 2.00 limit" in line for line in said)


def test_a_plan_inside_the_risk_limit_is_placed_logged_and_counted(tmp_path):
    path = tmp_path / "t.jsonl"
    broker = FakeBroker([1.25, -1.0])
    said = []
    result = run(symbol="1HZ100V", log_path=str(path), stake=1.0, multiplier=100,
                 strategy=FiresOnEveryTick(stop=99.0, target=102.0), max_trades=2, max_loss_per_trade=3.0,
                 ticks=iter(_ticks(10)), broker=broker, emit=said.append)
    assert result.placed == 2 and result.won == 1
    assert result.net == pytest.approx(0.25)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["stop"] == 99.0 and rows[0]["target"] == 102.0
    assert rows[0]["multiplier"] == 100 and rows[0]["profit"] == pytest.approx(1.25)
    assert any("reached the cap of 2 trades" in line for line in said)


def test_a_run_that_places_nothing_says_so(tmp_path):
    result = run(symbol="1HZ100V", log_path=str(tmp_path / "t.jsonl"), stake=1.0, multiplier=100,
                 strategy=FiresOnEveryTick(stop=99.0, target=102.0), max_loss_per_trade=0.5,
                 ticks=iter(_ticks(3)), broker=FakeBroker([]), emit=lambda _s: None)
    assert result.placed == 0
    assert "nothing placed yet" in result.readout()
