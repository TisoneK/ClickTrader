"""The Multipliers round trip: the product that can hold a stop and a target.

Rise/Fall expires and pays; a trade plan has an entry, a stop and a target, and only this product accepts
them. The tests care about two things: the stop and target go where the platform wants them (nested in
`limit_order`, as price levels — top-level fields are rejected), and the notional guard fires before a
position is opened rather than after.
"""

import json

import pytest

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
