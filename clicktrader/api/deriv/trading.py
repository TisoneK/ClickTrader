"""Layer 3 (gated): price and buy one digit contract via Deriv's OTP-authenticated WebSocket.

Nothing here bypasses DESIGN.md's gates on its own. `get_otp_url` refuses a `/ws/real` URL by default —
a strategy earns its way to live money by a human changing `require_demo`, not by this code drifting
there quietly. Nothing here consults `RiskGuard` either; that check belongs to the caller, once per
trade, before this module is ever called — keeping the boundary between "may we trade" (limits.py) and
"how do we place one" (this file) explicit rather than tangled together.

Field names and the proposal-then-buy flow are from Deriv's own docs (developers.deriv.com/llms/
proposal.md, buy.md, authentication.md), fetched directly 2026-09-24 after the commonly-documented
ws.derivws.com/v3 endpoint turned out to be retired — see connection.py for that whole story.

Verified live 2026-09-24 on the demo account: a real DIGITOVER(1) contract, $0.35 stake (Deriv's
documented minimum for this contract is $0.35 — the strategy's $0.10 backtest default in strategies.py
is fine for replay but too low to actually place; a live-trading caller needs to raise it). Contract
14296246299, buy_price 0.35, payout 0.41, balance stepped from 10000.00 to 9999.65 exactly as expected.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import websocket

from ...model import Contract, Side
from .connection import DerivAPIError

OTP_URL_TEMPLATE = "https://api.derivws.com/trading/v1/options/accounts/{account_id}/otp"

_CONTRACT_TYPE = {Side.OVER: "DIGITOVER", Side.UNDER: "DIGITUNDER"}


class DemoGateError(Exception):
    """`get_otp_url` was asked for a demo URL but the account behind `account_id` returned a real one."""


def get_otp_url(account_id: str, token: str, app_id: int, *, require_demo: bool = True, timeout: float = 10.0) -> str:
    """`POST .../accounts/{account_id}/otp` → the one-time private WebSocket URL to trade on.

    `require_demo=True` (the default) raises `DemoGateError` rather than silently trading real money if
    `account_id` turns out to name a real account — a deliberate default, not a convenience toggle.
    """
    request = urllib.request.Request(
        OTP_URL_TEMPLATE.format(account_id=account_id),
        headers={"Authorization": f"Bearer {token}", "Deriv-App-ID": str(app_id)},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DerivAPIError(f"OTP request failed ({exc.code}): {detail}") from exc
    url = body["data"]["url"]
    if require_demo and "/ws/demo" not in url:
        raise DemoGateError(f"OTP URL is not a demo account URL: {url!r} — refusing to proceed")
    return url


@dataclass(frozen=True)
class BuyResult:
    contract_id: int
    transaction_id: int
    buy_price: float
    payout: float
    balance_after: float
    purchase_time: float


def place_digit_contract(
    ws: websocket.WebSocket,
    contract: Contract,
    *,
    symbol: str,
    stake: float,
    currency: str,
    duration: int = 1,
    duration_unit: str = "t",
) -> BuyResult:
    """Price then buy one digit contract on an already OTP-authenticated connection.

    Two round trips, matching Deriv's documented flow exactly: a `proposal` for the live ask price, then
    a `buy` naming that exact proposal's id and price. There is no single combined call for this.
    """
    ws.send(
        json.dumps(
            {
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": _CONTRACT_TYPE[contract.side],
                "currency": currency,
                "underlying_symbol": symbol,
                "duration": duration,
                "duration_unit": duration_unit,
                "barrier": str(contract.barrier),
            }
        )
    )
    priced = _recv_or_raise(ws)["proposal"]
    ws.send(json.dumps({"buy": priced["id"], "price": priced["ask_price"]}))
    bought = _recv_or_raise(ws)["buy"]
    return BuyResult(
        contract_id=bought["contract_id"],
        transaction_id=bought["transaction_id"],
        buy_price=bought["buy_price"],
        payout=bought["payout"],
        balance_after=bought["balance_after"],
        purchase_time=float(bought["purchase_time"]),
    )


def _recv_or_raise(ws: websocket.WebSocket) -> dict[str, Any]:
    message = json.loads(ws.recv())
    if "error" in message:
        raise DerivAPIError(message["error"].get("message", str(message["error"])))
    return message
