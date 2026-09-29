"""The Rise/Fall round trip, exercised against a fake socket.

The point of this contract is that its payout is *quoted* rather than scaled to the probability, so the
tests care most about the two things that make it usable: the request asks for CALL/PUT with a time
expiry, and the broker's own payout comes back on the result instead of being assumed.
"""

import json

import pytest

from clicktrader.api.deriv.trading import place_rise_fall


class FakeSocket:
    """Records what was sent and replays canned replies, so no network is involved."""

    def __init__(self, *replies):
        self.sent: list[dict] = []
        self._replies = list(replies)
        self.closed = False

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        return json.dumps(self._replies.pop(0))

    def close(self):
        self.closed = True


def _buy_reply(contract_id=7, buy_price=1.0, payout=1.9535):
    return {
        "buy": {
            "contract_id": contract_id,
            "transaction_id": 99,
            "buy_price": buy_price,
            "payout": payout,
            "balance_after": 500.0,
            "purchase_time": 1_700_000_000,
        }
    }


def test_a_rise_is_a_call_and_a_fall_is_a_put_with_a_time_expiry():
    ws = FakeSocket({"proposal": {"id": "p1", "ask_price": 1.0}}, _buy_reply())
    place_rise_fall(ws, True, symbol="1HZ25V", stake=1.0, currency="USD", duration=2, duration_unit="m")
    proposal = ws.sent[0]
    assert proposal["contract_type"] == "CALL"
    assert proposal["duration"] == 2 and proposal["duration_unit"] == "m"
    assert proposal["underlying_symbol"] == "1HZ25V"
    assert proposal["basis"] == "stake" and proposal["amount"] == 1.0
    assert "barrier" not in proposal  # a Rise/Fall has no barrier; that is why its payout is flat

    downside = FakeSocket({"proposal": {"id": "p2", "ask_price": 1.0}}, _buy_reply())
    place_rise_fall(downside, False, symbol="1HZ25V", stake=1.0, currency="USD")
    assert downside.sent[0]["contract_type"] == "PUT"


def test_it_buys_the_exact_proposal_it_was_quoted():
    ws = FakeSocket({"proposal": {"id": "abc", "ask_price": 4.21}}, _buy_reply(buy_price=4.21))
    place_rise_fall(ws, True, symbol="1HZ25V", stake=4.0, currency="USD")
    assert ws.sent[1] == {"buy": "abc", "price": 4.21}


def test_the_brokers_quoted_payout_comes_back_on_the_result():
    # not assumed from a formula the way a digit contract's is: the flat ROI is the whole reason this
    # contract can be won on, so it has to be read rather than derived
    ws = FakeSocket({"proposal": {"id": "p1", "ask_price": 1.0}}, _buy_reply(payout=1.9535))
    bought = place_rise_fall(ws, True, symbol="1HZ25V", stake=1.0, currency="USD")
    assert bought.payout == pytest.approx(1.9535)
    assert bought.contract_id == 7
    assert bought.balance_after == 500.0
    assert (bought.payout - bought.buy_price) / bought.buy_price == pytest.approx(0.9535)


def test_an_error_from_the_broker_is_raised_rather_than_read_as_a_buy():
    from clicktrader.api.deriv.trading import DerivAPIError

    ws = FakeSocket({"error": {"code": "ContractBuyValidationError", "message": "Number of ticks must be between 1 and 10."}})
    with pytest.raises(DerivAPIError):
        place_rise_fall(ws, True, symbol="1HZ25V", stake=1.0, currency="USD", duration=120, duration_unit="t")
