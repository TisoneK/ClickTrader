import io
import json
import urllib.error

import pytest

from clicktrader.api.deriv import trading
from clicktrader.model import Contract, Side


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class FakeWS:
    def __init__(self, messages: list[dict]) -> None:
        self._messages = iter(messages)
        self.sent: list[str] = []

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str:
        return json.dumps(next(self._messages))


def test_get_otp_url_returns_a_demo_url(monkeypatch):
    def fake_urlopen(request, timeout=None):
        assert request.get_header("Authorization") == "Bearer tok123"
        assert request.get_header("Deriv-app-id") == "42"
        assert request.full_url == "https://api.derivws.com/trading/v1/options/accounts/acct-1/otp"
        return FakeHTTPResponse({"data": {"url": "wss://api.derivws.com/trading/v1/options/ws/demo?otp=abc"}})

    monkeypatch.setattr(trading.urllib.request, "urlopen", fake_urlopen)
    url = trading.get_otp_url("acct-1", "tok123", 42)
    assert url == "wss://api.derivws.com/trading/v1/options/ws/demo?otp=abc"


def test_get_otp_url_refuses_a_real_account_by_default(monkeypatch):
    monkeypatch.setattr(
        trading.urllib.request,
        "urlopen",
        lambda request, timeout=None: FakeHTTPResponse({"data": {"url": "wss://api.derivws.com/trading/v1/options/ws/real?otp=abc"}}),
    )
    with pytest.raises(trading.DemoGateError):
        trading.get_otp_url("acct-1", "tok123", 42)


def test_get_otp_url_allows_real_only_when_explicitly_told(monkeypatch):
    monkeypatch.setattr(
        trading.urllib.request,
        "urlopen",
        lambda request, timeout=None: FakeHTTPResponse({"data": {"url": "wss://api.derivws.com/trading/v1/options/ws/real?otp=abc"}}),
    )
    url = trading.get_otp_url("acct-1", "tok123", 42, require_demo=False)
    assert "/ws/real" in url


def test_get_otp_url_wraps_http_errors(monkeypatch):
    def raise_http_error(request, timeout=None):
        raise urllib.error.HTTPError(
            url=request.full_url, code=401, msg="Unauthorized", hdrs=None, fp=io.BytesIO(b"Invalid application")
        )

    monkeypatch.setattr(trading.urllib.request, "urlopen", raise_http_error)
    with pytest.raises(trading.DerivAPIError, match="401"):
        trading.get_otp_url("acct-1", "tok123", 42)


def test_place_digit_contract_prices_then_buys():
    ws = FakeWS(
        [
            {"msg_type": "proposal", "proposal": {"id": "prop-1", "ask_price": 10.5}},
            {
                "msg_type": "buy",
                "buy": {
                    "contract_id": 999,
                    "transaction_id": 888,
                    "buy_price": 10.5,
                    "payout": 19.72,
                    "balance_after": 9989.5,
                    "purchase_time": 1700000000,
                },
            },
        ]
    )
    result = trading.place_digit_contract(ws, Contract(Side.OVER, 1), symbol="1HZ10V", stake=10, currency="USD")
    assert result.contract_id == 999
    assert result.transaction_id == 888
    assert result.buy_price == 10.5
    assert result.payout == 19.72

    sent_proposal = json.loads(ws.sent[0])
    assert sent_proposal["contract_type"] == "DIGITOVER"
    assert sent_proposal["barrier"] == "1"
    assert sent_proposal["basis"] == "stake"
    assert sent_proposal["amount"] == 10
    assert sent_proposal["underlying_symbol"] == "1HZ10V"
    assert json.loads(ws.sent[1]) == {"buy": "prop-1", "price": 10.5}


def test_get_balance_sends_a_one_off_non_subscribed_request():
    ws = FakeWS([{"msg_type": "balance", "balance": {"balance": 9999.65, "currency": "USD", "loginid": "DOT91205289"}}])
    balance, currency = trading.get_balance(ws)
    assert balance == 9999.65
    assert currency == "USD"
    sent = json.loads(ws.sent[0])
    assert sent == {"balance": 1}  # no "subscribe" key -- a one-off request, not a live subscription


def test_get_balance_raises_on_error():
    ws = FakeWS([{"error": {"code": "Unauthorized", "message": "session expired"}}])
    with pytest.raises(trading.DerivAPIError, match="session expired"):
        trading.get_balance(ws)


def test_place_digit_contract_uses_digitunder_for_under_side():
    ws = FakeWS(
        [
            {"proposal": {"id": "prop-2", "ask_price": 5.0}},
            {"buy": {"contract_id": 1, "transaction_id": 2, "buy_price": 5.0, "payout": 9.5, "balance_after": 100.0, "purchase_time": 1}},
        ]
    )
    trading.place_digit_contract(ws, Contract(Side.UNDER, 5), symbol="1HZ10V", stake=5, currency="USD")
    assert json.loads(ws.sent[0])["contract_type"] == "DIGITUNDER"


def test_place_digit_contract_raises_on_proposal_error():
    ws = FakeWS([{"error": {"code": "InputValidationFailed", "message": "bad barrier"}}])
    with pytest.raises(trading.DerivAPIError, match="bad barrier"):
        trading.place_digit_contract(ws, Contract(Side.OVER, 1), symbol="1HZ10V", stake=10, currency="USD")


def test_place_digit_contract_raises_on_buy_error():
    ws = FakeWS(
        [
            {"proposal": {"id": "prop-1", "ask_price": 10.5}},
            {"error": {"code": "InsufficientBalance", "message": "not enough funds"}},
        ]
    )
    with pytest.raises(trading.DerivAPIError, match="not enough funds"):
        trading.place_digit_contract(ws, Contract(Side.OVER, 1), symbol="1HZ10V", stake=10, currency="USD")
