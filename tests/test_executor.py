import json

import pytest

from clicktrader.executor import run
from clicktrader.ledger import DecisionLedger
from clicktrader.limits import RiskGuard, RiskLimits
from clicktrader.model import Contract, Side, Tick
from clicktrader.recording import TickRecord
from clicktrader.strategies import Decision


def _record(i: int, digit: int) -> TickRecord:
    return TickRecord(tick=Tick(i, f"1.{digit}"))


class FakeTradeWS:
    """Answers any proposal/buy pair generically -- executor.py never reads BuyResult's fields, so the
    exact numbers here don't matter, only that a well-formed response comes back."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self._n = 0

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self) -> str:
        self._n += 1
        last = self.sent[-1]
        if "proposal" in last:
            return json.dumps({"proposal": {"id": f"prop-{self._n}", "ask_price": last["amount"]}})
        return json.dumps(
            {"buy": {"contract_id": self._n, "transaction_id": self._n, "buy_price": last["price"], "payout": last["price"] * 1.5, "balance_after": 999.0, "purchase_time": 1}}
        )


class AlwaysBetOver4:
    name = "always-over-4"

    def decide(self, history) -> Decision:
        return Decision(Contract(Side.OVER, 4), 0.10, "always")


class NeverBets:
    name = "never"

    def decide(self, history):
        return None


def _risk(**overrides) -> RiskGuard:
    defaults = dict(max_stake=10.0, max_session_loss=100.0, max_consecutive_losses=10)
    defaults.update(overrides)
    return RiskGuard(RiskLimits(**defaults))


def test_places_a_contract_and_settles_it_next_tick():
    ws = FakeTradeWS()
    risk = _risk()
    ledger = DecisionLedger()
    ticks = [_record(0, 9), _record(1, 2)]  # decide on digit 9, settle against digit 2 -> Over(4) loses

    run(AlwaysBetOver4(), ticks, ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10, ledger=ledger)

    # AlwaysBetOver4 fires unconditionally, so the second tick both settles the first bet AND places a
    # new one (still pending, unsettled, since there's no third tick) -- two trades placed in total.
    assert len(ws.sent) == 4
    assert ws.sent[0]["contract_type"] == "DIGITOVER"
    assert ws.sent[0]["amount"] == 0.10

    bets = [r for r in ledger.rows if r.action == "bet"]
    assert len(bets) == 1  # only the first trade had a following tick to settle against
    assert bets[0].won is False
    assert bets[0].settle_digit == 2
    assert bets[0].digit_seen == 9
    assert risk.trades == 1
    assert risk.session_pnl == pytest.approx(-0.10)


def test_min_stake_overrides_a_strategy_stake_that_is_too_low():
    ws = FakeTradeWS()
    risk = _risk()
    ticks = [_record(0, 9), _record(1, 9)]  # Over(4) wins on 9

    run(AlwaysBetOver4(), ticks, ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.35)

    assert ws.sent[0]["amount"] == 0.35  # raised from the strategy's own 0.10
    assert risk.session_pnl > 0  # won, and graded using the raised stake


def test_risk_guard_blocks_an_oversized_stake_without_placing_anything():
    ws = FakeTradeWS()
    risk = _risk(max_stake=0.05)  # below min_stake, so the decision gets blocked
    ledger = DecisionLedger()
    ticks = [_record(0, 9)]

    run(AlwaysBetOver4(), ticks, ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10, ledger=ledger)

    assert ws.sent == []
    blocked = [r for r in ledger.rows if r.action == "blocked"]
    assert len(blocked) == 1
    assert "exceeds max stake" in blocked[0].reason


def test_halted_guard_stops_new_trades_but_nothing_crashes():
    ws = FakeTradeWS()
    risk = _risk()
    risk.kill("manual test halt")
    ticks = [_record(0, 9), _record(1, 9), _record(2, 9)]

    run(AlwaysBetOver4(), ticks, ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10)

    assert ws.sent == []
    assert risk.trades == 0


def test_a_losing_streak_trips_the_kill_switch_mid_run():
    ws = FakeTradeWS()
    risk = _risk(max_consecutive_losses=2)
    ledger = DecisionLedger()
    # digits: decide@9(loss vs 2), decide@2(loss vs 1) trips the switch, decide@1 must be skipped
    ticks = [_record(0, 9), _record(1, 2), _record(2, 1), _record(3, 9)]

    run(AlwaysBetOver4(), ticks, ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10, ledger=ledger)

    assert risk.halted
    assert risk.trades == 2  # the third tick's decision was never placed once halted
    assert len([r for r in ledger.rows if r.action == "bet"]) == 2


def test_skip_is_logged_when_the_strategy_passes():
    ledger = DecisionLedger()
    ticks = [_record(0, 5), _record(1, 5)]

    run(NeverBets(), ticks, FakeTradeWS(), symbol="1HZ10V", currency="USD", risk=_risk(), min_stake=0.10, ledger=ledger)

    assert all(r.action == "skip" for r in ledger.rows)
    assert len(ledger.rows) == 2
