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
import time
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


@dataclass(frozen=True)
class SettlementResult:
    contract_id: int
    status: str
    """``"won"`` or ``"lost"`` — `wait_for_settlement` only ever returns once one of those is reached."""
    profit: float
    exit_spot: str | None
    """The broker's own exit price, kept as a string like `model.Tick.price` — a trailing zero is a
    real digit. `None` if the broker didn't report one (shouldn't happen for a plain digit contract,
    but nothing here assumes it can't)."""
    sell_price: float | None


def get_contract_status(ws: websocket.WebSocket, contract_id: int) -> dict[str, Any]:
    """A one-off (non-subscribed) ``proposal_open_contract`` lookup for one contract's current state.
    Same reasoning as `get_balance`: a plain request-response, not `subscribe: 1`, to avoid interleaving
    unsolicited pushes with another call's own send-then-immediately-recv assumption."""
    ws.send(json.dumps({"proposal_open_contract": 1, "contract_id": contract_id}))
    return _recv_or_raise(ws)["proposal_open_contract"]


def wait_for_settlement(
    ws: websocket.WebSocket, contract_id: int, *, timeout: float = 10.0, poll_interval: float = 0.3
) -> SettlementResult:
    """Poll `get_contract_status` until the broker itself reports this contract ``"won"`` or ``"lost"``,
    rather than assuming an outcome from a tick read off a separate connection. This is *the* fix for
    what was previously a self-graded, unverified settlement (see `executor.py`'s git history).

    A 1-tick contract on a ~1-second-cadence symbol should settle within a poll or two; taking the full
    `timeout` means something is actually wrong (a stalled connection, an unexpected contract type),
    not just slow — this raises `TimeoutError` rather than waiting forever or guessing.
    """
    deadline = time.monotonic() + timeout
    while True:
        contract = get_contract_status(ws, contract_id)
        status = contract.get("status")
        if status in ("won", "lost"):
            sell_price = contract.get("sell_price")
            return SettlementResult(
                contract_id=contract_id,
                status=status,
                profit=float(contract["profit"]),
                exit_spot=contract.get("exit_spot"),
                sell_price=float(sell_price) if sell_price is not None else None,
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(f"contract {contract_id} did not settle within {timeout:.0f}s (status={status!r})")
        time.sleep(poll_interval)


def get_balance(ws: websocket.WebSocket) -> tuple[float, str]:
    """A one-off ``{"balance": 1}`` request (no ``subscribe``) — the broker's own current balance and
    currency, right now. Deliberately not a subscription: `balance`'s docs show ``subscribe: 1`` pushing
    unsolicited updates on the same connection, which would arrive interleaved with `place_digit_contract`'s
    own send-then-immediately-recv calls and break its assumption that the next message received is
    always the response to what it just sent. A plain one-off request avoids that risk entirely, at the
    cost of one extra round trip whenever the caller wants a fresh number (`executor.py` calls this once
    per settled trade, not once per tick)."""
    ws.send(json.dumps({"balance": 1}))
    balance = _recv_or_raise(ws)["balance"]
    return balance["balance"], balance["currency"]


def _recv_or_raise(ws: websocket.WebSocket) -> dict[str, Any]:
    message = json.loads(ws.recv())
    if "error" in message:
        raise DerivAPIError(message["error"].get("message", str(message["error"])))
    return message
