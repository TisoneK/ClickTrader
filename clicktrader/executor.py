"""Layer 3: the live loop. Watch real ticks, ask a strategy, check `RiskGuard`, place a contract, grade
it against the next tick, record the outcome — the same "decide, settle one tick later" shape
`harness.py`'s backtest already uses, just happening in real time instead of all at once. Writes the same
`LedgerRow`s replay does (action ``"bet"``, ``"skip"``, or ``"blocked"``), so a live session and its
replay can be diffed line for line (DESIGN.md).

Two things are load-bearing, not incidental: every trade is checked against `RiskGuard` *before* it's
placed, and a strategy's own stake is raised to `min_stake` (a broker minimum, e.g. Deriv's $0.35) but
never silently altered otherwise — a caller that wants a different sizing rule wraps the strategy
(`MartingaleOnLoss` already does this), it doesn't get rewritten here.

Known simplification: a contract's *win/loss* is graded from the next tick this loop itself reads off
the public market-data stream (`tick_source`), not from Deriv's own authoritative settlement message
(`proposal_open_contract`, not subscribed to here). In practice the two should agree — 1-tick duration,
same symbol — but this is self-grading, not verified against the broker's own settlement record. Worth
building `proposal_open_contract` support before trusting this for anything beyond demo learning.

The *account balance* shown alongside each settled trade, by contrast, is real: a one-off
``{"balance": 1}`` request (not a subscription — see `get_balance`'s own docstring for why) right after
grading, so `LedgerRow.account_balance` is the broker's own number, not a self-computed tally. A failed
balance lookup is swallowed (`account_balance` comes back `None`) rather than halting trading over what
is, deliberately, a best-effort display value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import websocket

from .api.deriv.connection import DerivAPIError
from .api.deriv.trading import get_balance, place_digit_contract
from .ledger import DecisionLedger, LedgerRow
from .limits import RiskGuard
from .model import Contract, Tick
from .recording import TickRecord
from .strategies import History, Strategy


@dataclass(frozen=True)
class _PendingBet:
    contract: Contract
    stake: float
    reason: str
    decision_ts: float
    decision_tick_index: int
    decision_digit: int


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
) -> None:
    """Consume `tick_source` (e.g. `clicktrader.api.deriv.stream_ticks(symbol)`) until it ends, the
    caller's `KeyboardInterrupt` bubbles up, or nothing stops it — the caller decides when to stop by
    how long `tick_source` runs. `trade_ws` must already be an OTP-authenticated connection (see
    `get_otp_url`); this function only reads and writes on it, it never opens or closes it.

    `on_row`, if given, is called with every `LedgerRow` the instant it's produced — including "skip"
    rows, which are most of them on a selective strategy. There is no console output otherwise: a long
    run with nothing printed looks identical to a frozen one, so a caller that wants to watch this live
    should pass something here (the CLI does), not rely on a default.
    """
    ticks: list[Tick] = []
    pending: _PendingBet | None = None

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

        if pending is not None:
            settle_digit = seen.digit
            pnl = pending.contract.settle(pending.stake, settle_digit)
            won = pnl > 0
            risk.record(pnl)
            try:
                account_balance, _currency = get_balance(trade_ws)
            except (DerivAPIError, websocket.WebSocketException, KeyError):
                account_balance = None  # best-effort observability -- a failed lookup doesn't halt trading
            emit(
                LedgerRow(
                    pending.decision_ts,
                    pending.decision_tick_index,
                    pending.decision_digit,
                    strategy.name,
                    "bet",
                    pending.reason,
                    contract=str(pending.contract),
                    stake=pending.stake,
                    settle_digit=settle_digit,
                    won=won,
                    pnl=pnl,
                    balance=risk.session_pnl,
                    account_balance=account_balance,
                )
            )
            pending = None

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

        place_digit_contract(trade_ws, decision.contract, symbol=symbol, stake=stake, currency=currency)
        pending = _PendingBet(decision.contract, stake, decision.reason, seen.ts, index, seen.digit)
