"""Run a plan-shaped strategy live on Multipliers — the product that can hold a stop and a target.

`runner.py` trades Rise/Fall: a signal, an expiry, a settlement. This trades a **`TradePlan`** — an entry,
a stop and a target — which is the shape the SMC engine emits and which a binary contract cannot carry at
all. The lifecycle is different in one way that matters:

**There is no settlement to wait for.** A Multipliers position is open until price reaches the stop, price
reaches the target, or somebody closes it. So the loop places the contract, then polls the broker's own
record of it until it is sold — and the stop and the target are the exit, not a clock.

**And the risk is the stop, not the stake.** That is the substantive difference from `runner.py` and the
reason this is its own module rather than another option on that one: a stake of 1 at multiplier 100 is a
100 position, and the most it can lose is whatever the stop distance is worth on 100 — about 1.00 for a stop
one percent away. `RiskGuard` assumes the worst case is the stake, which is true of a binary and false here,
so this loop books the *realized* loss and refuses any plan where the stop distance and the multiplier
together exceed what the session is allowed to lose. Sizing from the stake here would be sizing from the
wrong number entirely.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from .api.deriv import DerivAPIError
from .forex.model import TradePlan
from .forex.trade_strategies import TradeStrategy
from .strategies import History


def _say(line: str) -> None:
    """Print and flush — the lesson this project keeps re-learning in a new file.

    `record-deriv` gained `--progress-every` after a multi-hour capture went silent; the Rise/Fall runner's
    printer was fixed for the same reason; a throwaway probe was still invisible because of it; and the
    first live SMC run wrote nothing to its log for the same cause. A loop whose output is block-buffered
    is indistinguishable from a loop that has died, and every long-running entry point here needs its own
    copy of this because the default is per-function.
    """
    print(line, flush=True)


@dataclass
class MultiplierRun:
    """What the run did, in the terms a person reads."""

    ticks: int = 0
    plans: int = 0
    placed: int = 0
    refused: int = 0
    won: int = 0
    net: float = 0.0
    outcomes: list[float] = field(default_factory=list)

    def readout(self) -> str:
        if not self.placed:
            return f"{self.ticks} ticks, {self.plans} plan(s), nothing placed yet ({self.refused} refused)"
        return (
            f"{self.ticks} ticks, {self.plans} plan(s), {self.placed} placed ({self.refused} refused): "
            f"won {self.won} of {self.placed}, net {self.net:+.2f}"
        )


class DerivMultiplierBroker:
    """The live side: open a session, place a plan, and watch the position until the broker says it is sold."""

    def __init__(self, *, symbol: str, stake: float, multiplier: int, app_id: int | None = None) -> None:
        import websocket

        from .api.deriv.trading import get_otp_url

        self.symbol = symbol
        self.stake = stake
        self.multiplier = multiplier
        token, app, account = (
            os.environ[n] for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID")
        )
        self._ws = websocket.create_connection(
            get_otp_url(account, token, app_id or app, require_demo=True), timeout=25
        )

    def place(self, plan: TradePlan, entry: float) -> tuple[int, float, float]:
        """Place the plan with its own stop and target. Returns (contract id, price, currency)."""
        from .api.deriv.trading import get_balance, place_multiplier

        _balance, currency = get_balance(self._ws)
        bought = place_multiplier(
            self._ws, plan.direction.value == "up", symbol=self.symbol, stake=self.stake,
            multiplier=self.multiplier, stop_loss=plan.stop, take_profit=plan.target, currency=currency,
        )
        return bought.contract_id, bought.buy_price, currency

    def watch(self, contract_id: int, *, timeout: float, poll_every: float, sleep=time.sleep) -> float:
        """Poll the broker's record until the position is closed, and return its realised profit."""
        from .api.deriv.trading import get_contract_status

        waited, delay = 0.0, max(poll_every, 60.0)  # the first minute is closed to selling anyway
        while waited < timeout:
            sleep(delay)
            waited += delay
            record = get_contract_status(self._ws, contract_id)
            if record.get("is_sold"):
                return float(record.get("profit", 0.0))
        raise TimeoutError(f"contract {contract_id} was still open after {timeout:.0f}s")

    def close(self) -> None:
        self._ws.close()


def run(
    *,
    symbol: str,
    log_path: str,
    stake: float,
    multiplier: int,
    strategy: TradeStrategy,
    max_trades: int | None = None,
    max_seconds: float | None = None,
    max_loss_per_trade: float | None = None,
    ticks: Iterator | None = None,
    broker=None,
    poll_every: float = 60.0,
    hold_timeout: float = 3600.0,
    report_every: float = 300.0,
    emit: Callable[[str], None] = _say,
    now: Callable[[], float] = time.time,
) -> MultiplierRun:
    """Trade the strategy's plans on Multipliers until the trade cap, the clock or an error stops it.

    `max_loss_per_trade` refuses any plan whose stop distance is worth more than that on this exposure —
    the check `RiskGuard` cannot make, because on this product the stake is not the worst case.
    """
    from .api.deriv.ticks import stream_ticks

    run = MultiplierRun()
    feed = ticks if ticks is not None else stream_ticks(symbol)
    history: list = []
    started = now()
    last_report = started
    log = open(log_path, "a", encoding="utf-8")
    try:
        for record in feed:
            history.append(record.tick)
            run.ticks += 1
            decision = strategy.decide(History(history, len(history)))
            if report_every and now() - last_report >= report_every:
                # Narration between the trades, not only at them. A loop that speaks once an hour is a loop
                # that cannot be told from a dead one, and "it saw nothing" is as much of a result as "it
                # took a trade" — the strategy already knows which and why in `last_view`.
                last_report = now()
                emit(f"[{now() - started:.0f}s] {run.readout()}")
                seen = getattr(strategy, "last_view", None)
                if seen:
                    emit(f"  what it sees: {seen}")
            if decision is None:
                continue
            run.plans += 1
            entry = float(record.tick.price)
            exposure = stake * multiplier
            risk = abs(entry - decision.plan.stop) / entry * exposure
            if max_loss_per_trade is not None and risk > max_loss_per_trade:
                run.refused += 1
                emit(f"refused: the stop is {risk:.2f} of exposure away, over the {max_loss_per_trade:.2f} limit")
                continue
            emit(f"plan: {decision.reason[:160]}")
            contract_id, price, currency = broker.place(decision.plan, entry)
            emit(f"placed {contract_id}: {price:.2f} {currency} at risk, stop {decision.plan.stop}, "
                 f"target {decision.plan.target}")
            try:
                profit = broker.watch(contract_id, timeout=hold_timeout, poll_every=poll_every)
            except TimeoutError as exc:
                emit(f"{exc} — it will still stop itself out at {decision.plan.stop}")
                profit = 0.0
            run.placed += 1
            run.net += profit
            run.outcomes.append(profit)
            run.won += 1 if profit > 0 else 0
            log.write(json.dumps({"ts": now(), "contract_id": contract_id, "symbol": symbol,
                                  "direction": decision.plan.direction.value, "stake": stake,
                                  "multiplier": multiplier, "entry": entry, "stop": decision.plan.stop,
                                  "target": decision.plan.target, "profit": profit,
                                  "reason": decision.reason}) + "\n")
            log.flush()
            os.fsync(log.fileno())
            emit(f"closed {contract_id}: {profit:+.2f} {currency} — {run.readout()}")
            if max_trades is not None and run.placed >= max_trades:
                emit(f"reached the cap of {max_trades} trades; stopping")
                break
            if max_seconds is not None and now() - started > max_seconds:
                emit(f"reached the time cap; stopping")
                break
    except DerivAPIError as exc:
        emit(f"Deriv API error: {exc}. Stopped; whatever was logged is written.")
    finally:
        log.close()
    emit(run.readout())
    return run
