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
    """Answers proposal -> buy -> proposal_open_contract (already settled) -> balance, generically.

    `outcomes` is one (status, profit, exit_spot) tuple per trade this fake will ever price, consumed in
    order as each new proposal locks in that trade's eventual settlement -- so a test can script exactly
    what each successive trade does (win, lose, ...) without needing a second tick for anything, since
    settlement is synchronous now.
    """

    def __init__(self, outcomes: list[tuple[str, float, str]] | None = None) -> None:
        self.sent: list[dict] = []
        self._outcomes = iter(outcomes if outcomes is not None else [("won", 0.0625, "1.9")] * 1000)
        self._current: tuple[str, float, str] | None = None
        self._n = 0

    def send(self, payload: str) -> None:
        msg = json.loads(payload)
        self.sent.append(msg)
        if "proposal" in msg and "contract_type" in msg:
            self._current = next(self._outcomes)

    def recv(self) -> str:
        self._n += 1
        last = self.sent[-1]
        if "proposal_open_contract" in last:
            status, profit, exit_spot = self._current
            return json.dumps(
                {"proposal_open_contract": {"contract_id": last["contract_id"], "status": status, "profit": str(profit), "exit_spot": exit_spot, "sell_price": None}}
            )
        if "balance" in last:
            return json.dumps({"balance": {"balance": 999.0, "currency": "USD", "loginid": "X"}})
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


def test_places_a_contract_and_settles_it_from_the_brokers_own_response():
    ws = FakeTradeWS(outcomes=[("lost", -0.10, "1.2")])
    risk = _risk()
    ledger = DecisionLedger()

    run(AlwaysBetOver4(), [_record(0, 9)], ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10, ledger=ledger)

    assert "proposal" in ws.sent[0] and ws.sent[0]["contract_type"] == "DIGITOVER"
    assert "buy" in ws.sent[1]
    assert "proposal_open_contract" in ws.sent[2]
    assert "balance" in ws.sent[3]

    bets = [r for r in ledger.rows if r.action == "bet"]
    assert len(bets) == 1
    assert bets[0].won is False
    assert bets[0].pnl == pytest.approx(-0.10)
    assert bets[0].settle_digit == 2  # from the broker's own exit_spot "1.2", not our own tick reading
    assert bets[0].account_balance == 999.0
    assert bets[0].digit_seen == 9
    assert risk.trades == 1
    assert risk.session_pnl == pytest.approx(-0.10)


def test_a_winning_trade_is_recorded_as_such():
    ws = FakeTradeWS(outcomes=[("won", 0.0656, "1.9")])
    ledger = DecisionLedger()

    run(AlwaysBetOver4(), [_record(0, 5)], ws, symbol="1HZ10V", currency="USD", risk=_risk(), min_stake=0.10, ledger=ledger)

    bet = next(r for r in ledger.rows if r.action == "bet")
    assert bet.won is True
    assert bet.pnl == pytest.approx(0.0656)
    assert bet.settle_digit == 9


def test_min_stake_overrides_a_strategy_stake_that_is_too_low():
    ws = FakeTradeWS(outcomes=[("won", 0.315, "1.9")])
    risk = _risk()

    run(AlwaysBetOver4(), [_record(0, 9)], ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.35)

    assert ws.sent[0]["amount"] == 0.35  # raised from the strategy's own 0.10


def test_risk_guard_blocks_an_oversized_stake_without_placing_anything():
    ws = FakeTradeWS()
    risk = _risk(max_stake=0.05)  # below min_stake, so the decision gets blocked
    ledger = DecisionLedger()

    run(AlwaysBetOver4(), [_record(0, 9)], ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10, ledger=ledger)

    assert ws.sent == []
    blocked = [r for r in ledger.rows if r.action == "blocked"]
    assert len(blocked) == 1
    assert "exceeds max stake" in blocked[0].reason


def test_halted_guard_stops_new_trades_but_nothing_crashes():
    ws = FakeTradeWS()
    risk = _risk()
    risk.kill("manual test halt")

    run(AlwaysBetOver4(), [_record(0, 9), _record(1, 9), _record(2, 9)], ws, symbol="1HZ10V", currency="USD", risk=risk, min_stake=0.10)

    assert ws.sent == []
    assert risk.trades == 0


def test_a_losing_streak_trips_the_kill_switch_mid_run():
    ws = FakeTradeWS(outcomes=[("lost", -0.10, "1.2"), ("lost", -0.10, "1.1"), ("won", 0.0656, "1.9")])
    risk = _risk(max_consecutive_losses=2)
    ledger = DecisionLedger()
    ticks = [_record(0, 9), _record(1, 9), _record(2, 9)]

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


def test_a_caught_balance_lookup_failure_leaves_it_none_and_keeps_trading():
    from clicktrader.api.deriv.connection import DerivAPIError

    class FlakyBalanceWS(FakeTradeWS):
        def recv(self) -> str:
            if "balance" in self.sent[-1]:
                raise DerivAPIError("session expired")
            return super().recv()

    ws = FlakyBalanceWS(outcomes=[("lost", -0.10, "1.2")])
    ledger = DecisionLedger()

    run(AlwaysBetOver4(), [_record(0, 9)], ws, symbol="1HZ10V", currency="USD", risk=_risk(), min_stake=0.10, ledger=ledger)

    bets = [r for r in ledger.rows if r.action == "bet"]
    assert len(bets) == 1
    assert bets[0].account_balance is None  # lookup failed, but the trade itself still settled correctly
    assert bets[0].won is False


def test_an_uncaught_balance_lookup_error_propagates():
    class FlakyBalanceWS(FakeTradeWS):
        def recv(self) -> str:
            if "balance" in self.sent[-1]:
                raise ConnectionError("connection dropped")
            return super().recv()

    ws = FlakyBalanceWS(outcomes=[("lost", -0.10, "1.2")])

    with pytest.raises(ConnectionError):
        # a raw ConnectionError isn't one of executor.py's caught balance-lookup exceptions on purpose --
        # only DerivAPIError/WebSocketException/KeyError are treated as "the lookup failed, keep going".
        run(AlwaysBetOver4(), [_record(0, 9)], ws, symbol="1HZ10V", currency="USD", risk=_risk(), min_stake=0.10)


def test_settlement_timeout_propagates(monkeypatch):
    from clicktrader.api.deriv import trading

    monkeypatch.setattr(trading.time, "sleep", lambda _seconds: None)

    class NeverSettlesWS(FakeTradeWS):
        def recv(self) -> str:
            last = self.sent[-1]
            if "proposal_open_contract" in last:
                return json.dumps({"proposal_open_contract": {"contract_id": last["contract_id"], "status": "open"}})
            return super().recv()

    with pytest.raises(TimeoutError):
        run(
            AlwaysBetOver4(), [_record(0, 9)], NeverSettlesWS(), symbol="1HZ10V", currency="USD",
            risk=_risk(), min_stake=0.10, settle_timeout=0.05,
        )


def test_on_row_fires_for_every_row_even_without_a_ledger():
    seen_rows = []

    run(
        AlwaysBetOver4(), [_record(0, 9)], FakeTradeWS(outcomes=[("won", 0.0656, "1.9")]), symbol="1HZ10V",
        currency="USD", risk=_risk(), min_stake=0.10, on_row=seen_rows.append,
    )

    assert [r.action for r in seen_rows] == ["bet"]
