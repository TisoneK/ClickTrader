"""Layer 3: the live loop. Watch real ticks, ask a strategy, check `RiskGuard`, place a contract, wait
for the broker's own settlement, record the outcome. Writes the same `LedgerRow`s replay does (action
``"bet"``, ``"skip"``, or ``"blocked"``), so a live session and its replay can be diffed line for line
(DESIGN.md).

Two things are load-bearing, not incidental: every trade is checked against `RiskGuard` *before* it's
placed, and a strategy's own stake is raised to `min_stake` (a broker minimum, e.g. Deriv's $0.35) but
never silently altered otherwise — a caller that wants a different sizing rule wraps the strategy
(`MartingaleOnLoss` already does this), it doesn't get rewritten here.

A contract's win/loss and exit price are the broker's own (`wait_for_settlement`'s `proposal_open_contract`
poll), not self-graded from this loop's own tick reading — an earlier version graded settlement from the
next tick read off the public feed, which agreed with the broker in practice but was never actually
verified against it. Settling synchronously, right after buying, also means there is no more "pending
bet carried into the next tick" state to track: the whole `_PendingBet` bookkeeping the earlier version
needed is gone, not simplified — a `bet` row is now built and emitted in one place, immediately.

The *account balance* shown alongside each settled trade is likewise real: a one-off ``{"balance": 1}``
request (not a subscription — see `get_balance`'s own docstring for why) right after settlement, so
`LedgerRow.account_balance` is the broker's own number, not a self-computed tally. A failed balance
lookup is swallowed (`account_balance` comes back `None`) rather than halting trading over what is,
deliberately, a best-effort display value.
"""

from __future__ import annotations

from typing import Callable, Iterable

import websocket

from .api.deriv.connection import DerivAPIError
from .api.deriv.trading import get_balance, place_digit_contract, wait_for_settlement
from .ledger import DecisionLedger, LedgerRow
from .limits import RiskGuard
from .model import Tick, last_digit
from .recording import TickRecord
from .strategies import History, Strategy


def run(
    strategy: Strategy,
    tick_source: Iterable[TickRecord],
    trade_ws: websocket.WebSocket,
    *,
    symbol: str,
    currency: str,
    risk: RiskGuard,
    min_stake: float,
    ledger: DecisionLedger | None = None,
    on_row: Callable[[LedgerRow], None] | None = None,
    settle_timeout: float = 10.0,
) -> None:
    """Consume `tick_source` (e.g. `clicktrader.api.deriv.stream_ticks(symbol)`) until it ends, the
    caller's `KeyboardInterrupt` bubbles up, or nothing stops it — the caller decides when to stop by
    how long `tick_source` runs. `trade_ws` must already be an OTP-authenticated connection (see
    `get_otp_url`); this function only reads and writes on it, it never opens or closes it.

    A placed trade blocks this loop until `wait_for_settlement` confirms it (up to `settle_timeout`
    seconds) before the next tick is read — a real settlement wait, not a fixed delay, and typically
    close to instant for a 1-tick contract. `tick_source`'s own connection just queues incoming ticks
    while this loop is briefly not reading it, the same as any consumer that pauses a moment.

    `on_row`, if given, is called with every `LedgerRow` the instant it's produced — including "skip"
    rows, which are most of them on a selective strategy. There is no console output otherwise: a long
    run with nothing printed looks identical to a frozen one, so a caller that wants to watch this live
    should pass something here (the CLI does), not rely on a default.
    """
    ticks: list[Tick] = []

    def emit(row: LedgerRow) -> None:
        if ledger is not None:
            ledger.append(row)
        if on_row is not None:
            on_row(row)

    for record in tick_source:
        ticks.append(record.tick)
        seen = record.tick
        index = len(ticks) - 1
        history = History(ticks, len(ticks))

        if risk.halted:
            continue

        decision = strategy.decide(history)
        if decision is None:
            emit(LedgerRow(seen.ts, index, seen.digit, strategy.name, "skip", "no signal", balance=risk.session_pnl))
            continue

        stake = max(decision.stake, min_stake)
        refusal = risk.check(stake)
        if refusal is not None:
            emit(
                LedgerRow(
                    seen.ts, index, seen.digit, strategy.name, "blocked", refusal,
                    contract=str(decision.contract), stake=stake, balance=risk.session_pnl,
                )
            )
            continue

        bought = place_digit_contract(trade_ws, decision.contract, symbol=symbol, stake=stake, currency=currency)
        settlement = wait_for_settlement(trade_ws, bought.contract_id, timeout=settle_timeout)
        won = settlement.status == "won"
        risk.record(settlement.profit)
        settle_digit = last_digit(settlement.exit_spot) if settlement.exit_spot else None
        try:
            account_balance, _currency = get_balance(trade_ws)
        except (DerivAPIError, websocket.WebSocketException, KeyError):
            account_balance = None  # best-effort observability -- a failed lookup doesn't halt trading
        emit(
            LedgerRow(
                seen.ts, index, seen.digit, strategy.name, "bet", decision.reason,
                contract=str(decision.contract), stake=stake, settle_digit=settle_digit,
                won=won, pnl=settlement.profit, balance=risk.session_pnl, account_balance=account_balance,
            )
        )
