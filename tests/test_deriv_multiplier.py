"""The Multipliers round trip: the product that can hold a stop and a target.

Rise/Fall expires and pays; a trade plan has an entry, a stop and a target, and only this product accepts
them. The tests care about two things: the stop and target go where the platform wants them (nested in
`limit_order`, as price levels — top-level fields are rejected), and the notional guard fires before a
position is opened rather than after.
"""

import json

import pytest
import websocket

from clicktrader.api.deriv.trading import (
    MAX_MULTIPLIER_NOTIONAL,
    MULTIPLIER_LIMIT_MULTIPLE,
    DerivAPIError,
    place_multiplier,
)


class FakeSocket:
    def __init__(self, *replies):
        self.sent: list[dict] = []
        self._replies = list(replies)

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        return json.dumps(self._replies.pop(0))

    def close(self):
        pass


def _buy(contract_id=11, buy_price=1.0):
    return {"buy": {"contract_id": contract_id, "transaction_id": 5, "buy_price": buy_price,
                    "payout": 0.0, "balance_after": 500.0, "purchase_time": 1_700_000_000}}


def test_the_stop_and_target_go_in_as_money_converted_from_the_price_levels():
    # the levels a plan is written in are prices; what the platform takes is money, capped at 50x the stake
    ws = FakeSocket({"proposal": {"spot": 1000.0}}, {"proposal": {"id": "p1", "ask_price": 1.0}}, _buy())
    place_multiplier(ws, True, symbol="1HZ100V", stake=1.0, multiplier=100,
                     stop_loss=990.0, take_profit=1020.0, currency="USD")
    proposal = ws.sent[1]
    assert proposal["contract_type"] == "MULTUP"
    assert proposal["multiplier"] == 100
    # 100 of exposure, a stop 1% away is 1.00 of currency, a target 2% away is 2.00
    assert proposal["limit_order"] == {"stop_loss": 1.0, "take_profit": 2.0}
    assert "stop_loss" not in proposal and "take_profit" not in proposal  # rejected at the top level
    assert proposal["basis"] == "stake"


def test_a_fall_is_a_multdown():
    ws = FakeSocket({"proposal": {"spot": 1000.0}}, {"proposal": {"id": "p2", "ask_price": 1.0}}, _buy())
    place_multiplier(ws, False, symbol="1HZ100V", stake=1.0, multiplier=50,
                     stop_loss=1030.0, take_profit=1000.0, currency="USD")
    assert ws.sent[0]["contract_type"] == "MULTDOWN"


def test_it_buys_the_exact_proposal_it_was_quoted():
    ws = FakeSocket({"proposal": {"spot": 1000.0}}, {"proposal": {"id": "abc", "ask_price": 2.34}},
                    _buy(buy_price=2.34))
    place_multiplier(ws, True, symbol="1HZ100V", stake=2.0, multiplier=100,
                     stop_loss=990.0, take_profit=1010.0, currency="USD")
    assert ws.sent[2] == {"buy": "abc", "price": 2.34}


def test_exposure_over_the_accounts_cap_is_refused_before_anything_is_sent():
    # 10 at multiplier 100 is 1,000 of exposure, which the account refused live with
    # LimitOrderAmountTooHigh — so the guard fires here rather than after a socket round trip
    ws = FakeSocket()
    with pytest.raises(DerivAPIError) as caught:
        place_multiplier(ws, True, symbol="1HZ100V", stake=10.0, multiplier=100,
                         stop_loss=1015.0, take_profit=1046.0, currency="USD")
    assert "exposure" in str(caught.value)
    assert ws.sent == []  # nothing left the machine


def test_the_cap_is_the_accounts_own_number():
    assert MAX_MULTIPLIER_NOTIONAL == 500.0


def test_a_broker_error_is_raised_rather_than_read_as_a_buy():
    ws = FakeSocket({"error": {"code": "LimitOrderAmountTooHigh", "message": "Enter an amount <= 500.00."}})
    with pytest.raises(DerivAPIError):
        place_multiplier(ws, True, symbol="1HZ100V", stake=1.0, multiplier=100,
                         stop_loss=1015.0, take_profit=1046.0, currency="USD")


def test_a_stop_further_away_than_the_account_allows_is_refused_with_the_reason():
    # a stop 60% away on 100 of exposure is 60.00 of currency, over the 50x-stake limit
    ws = FakeSocket({"proposal": {"spot": 1000.0}})
    with pytest.raises(DerivAPIError) as caught:
        place_multiplier(ws, True, symbol="1HZ100V", stake=1.0, multiplier=100,
                         stop_loss=400.0, take_profit=1010.0, currency="USD")
    assert "limit this account enforces" in str(caught.value)
    assert MULTIPLIER_LIMIT_MULTIPLE == 50.0


# --- the session socket can drop mid-run: reads reconnect, a place never re-buys ---


class DeadSocket:
    """Every use raises — what a dropped websocket looks like from the outside."""

    def __init__(self):
        self.closed = False

    def send(self, payload):
        raise websocket.WebSocketConnectionClosedException("dropped")

    def recv(self):
        raise websocket.WebSocketConnectionClosedException("dropped")

    def close(self):
        self.closed = True


class DiesOnPlaceSocket(FakeSocket):
    """Answers reads, but dies the moment a proposal (the buy) is attempted — a drop after the
    buy was sent but before its reply is indistinguishable from this from the caller's side."""

    def send(self, payload):
        if json.loads(payload).get("proposal"):
            raise websocket.WebSocketConnectionClosedException("dropped mid-place")
        super().send(payload)


def _broker_with_replayable_sessions(monkeypatch, sockets):
    """A broker whose OTP URL and websocket come from `sockets`; returns (broker, otp_call_count list)."""
    from clicktrader.multipliers import DerivMultiplierBroker

    otp_calls = []

    def fake_otp_url(account_id, token, app_id, *, require_demo=True, timeout=10.0):
        otp_calls.append((account_id, app_id))
        assert require_demo is True  # the demo gate must hold on every reconnect, not just the first
        return f"wss://gateway/ws/demo?session={len(otp_calls)}"

    def fake_create_connection(url, timeout=None):
        assert "/ws/demo" in url  # a reconnect must never land on a real-account URL
        return queue.pop(0)

    for name, value in (("DERIV_API_TOKEN", "t"), ("DERIV_APP_ID", "1089"), ("DERIV_DEMO_ACCOUNT_ID", "VRTC1")):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("clicktrader.api.deriv.trading.get_otp_url", fake_otp_url)
    monkeypatch.setattr(websocket, "create_connection", fake_create_connection)
    queue = list(sockets)  # hand the sockets out in order without consuming the caller's list
    return DerivMultiplierBroker(symbol="R_100", stake=1.0, multiplier=100), otp_calls


def test_watch_polls_through_a_dropped_socket_on_a_fresh_otp_session(monkeypatch):
    # seen live: a socket drop mid-run killed the loop while a position was open; the poll must
    # reconnect (a fresh one-time URL) and keep watching the same contract
    sockets = [DeadSocket(), FakeSocket({"proposal_open_contract": {"is_sold": True, "profit": 2.5}})]
    broker, otp_calls = _broker_with_replayable_sessions(monkeypatch, sockets)

    profit = broker.watch(11, timeout=3600.0, poll_every=60.0, sleep=lambda _s: None)

    assert profit == 2.5
    assert len(otp_calls) == 2  # a fresh one-time URL per session, not a replay of the spent one
    assert sockets[0].closed


def test_balance_reconnects_when_the_session_socket_dropped(monkeypatch):
    sockets = [DeadSocket(), FakeSocket({"balance": {"balance": 100053.74, "currency": "USD"}})]
    broker, otp_calls = _broker_with_replayable_sessions(monkeypatch, sockets)

    assert broker.balance() == (100053.74, "USD")
    assert len(otp_calls) == 2


def test_place_does_not_rebuy_after_a_transport_failure(monkeypatch):
    # a buy whose response was lost cannot be told from a buy that never landed; re-placing on the
    # fresh session risks a second position, so place raises and only refreshes the session
    from clicktrader.forex.model import Direction, TradePlan

    sockets = [DiesOnPlaceSocket({"balance": {"balance": 500.0, "currency": "USD"}}), FakeSocket()]
    broker, otp_calls = _broker_with_replayable_sessions(monkeypatch, sockets)
    plan = TradePlan(direction=Direction.UP, stop=990.0, target=1020.0)

    with pytest.raises(websocket.WebSocketException):
        broker.place(plan, 1000.0)

    assert len(otp_calls) == 2  # the session was refreshed for later calls
    assert sockets[1].sent == []  # the fresh session was never asked to buy again


def test_run_creates_a_missing_log_directory(tmp_path):
    # a fresh clone has no recordings/ and it is not in git: the log must not be what kills the run
    from clicktrader.model import Tick
    from clicktrader.multipliers import run as run_multipliers
    from clicktrader.recording import TickRecord

    class NoStrategy:
        last_view = ""

        def decide(self, history):
            return None

    class QuietBroker:
        def balance(self):
            return (100.0, "USD")

    feed = [TickRecord(tick=Tick(ts=1.0, price="100.0", symbol="R_100"))] * 3
    log_path = tmp_path / "recordings" / "nested" / "smc-demo-trades.jsonl"

    run_multipliers(symbol="R_100", log_path=str(log_path), stake=1.0, multiplier=100,
                    strategy=NoStrategy(), ticks=feed, broker=QuietBroker(), emit=lambda _line: None)

    assert log_path.exists()
