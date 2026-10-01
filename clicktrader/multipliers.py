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
import re
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
        refused = f", {self.refused} refused" if self.refused else ""
        if not self.placed:
            return f"no trades yet{refused}"
        return f"{self.placed} trade(s): won {self.won}, net {self.net:+.2f}{refused}"


def tidy(text: str) -> str:
    """Prices as a person writes them: 616.09000 -> 616.09 (a 5-decimal price keeps its 5 decimals)."""
    return re.sub(r"(\d+\.\d\d)0{3,}(?!\d)", r"\1", text)


class StatusPrinter:
    """Quiet status: say something when the chart's story changed, and otherwise only a short heartbeat.

    The old readout repeated the same two lines every minute for hours; the person watching could not
    tell a change from a repeat. Now a full block appears only when what the engine sees differs from what it
    last said, and an unchanged view gets one short line every `heartbeat` seconds so a dead loop still shows."""

    def __init__(self, emit, heartbeat: float, now) -> None:
        self.emit, self.heartbeat, self.now = emit, heartbeat, now
        self._seen: str | None = None
        self._last = None

    def show(self, price, readout: str, seen: str | None, extra: str = "") -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(self.now()))
        view = tidy(seen) if seen else None
        tail = f" · {extra}" if extra else ""
        if view != self._seen:
            self._seen, self._last = view, self.now()
            self.emit(f"{stamp}  price {price}  ·  {readout}{tail}")
            if view:
                self.emit(f"          {view}")
        elif self._last is None or self.now() - self._last >= self.heartbeat:
            self._last = self.now()
            self.emit(f"{stamp}  price {price}  ·  {readout}{tail}  (view unchanged)")


def _connection_errors() -> tuple[type[Exception], ...]:
    """The exception types that mean 'the socket failed; reconnecting may fix it' — the same class of
    transient failure `stream_ticks` retries through. A `DerivAPIError` is deliberately absent: the API
    is up and has said something is wrong, and a fresh session cannot fix a request that is wrong on
    its face."""
    import websocket

    return (websocket.WebSocketException, TimeoutError, ConnectionError)


class DerivMultiplierBroker:
    """The live side: open a session, place a plan, and watch the position until the broker says it is sold.

    The OTP session is one websocket, and it can drop like any other — seen live, a mid-session drop
    killed a demo run. So reads (`balance`, and every `watch` poll while a position is open) reconnect
    through a fresh OTP URL and carry on: the position and its stop and target live at the broker, not
    in this socket. A `place` is deliberately different — see its docstring.
    """

    def __init__(self, *, symbol: str, stake: float, multiplier: int, app_id: int | None = None) -> None:
        self.symbol = symbol
        self.stake = stake
        self.multiplier = multiplier
        self._token, app, self._account = (
            os.environ[n] for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID")
        )
        self._app_id = app_id if app_id is not None else app
        self._ws = self._connect()

    def _connect(self, *, retries: int = 5, backoff: float = 2.0, sleep=time.sleep):
        """A fresh OTP-authenticated websocket, retrying transient connection failures like `stream_ticks`.

        A reconnect needs a *new* one-time URL — the old one is spent — so every attempt re-asks the OTP
        endpoint, which is why the credentials are kept on the instance.
        """
        import websocket

        from .api.deriv.trading import get_otp_url

        attempt = 0
        while True:
            try:
                url = get_otp_url(self._account, self._token, self._app_id, require_demo=True)
                return websocket.create_connection(url, timeout=25)
            except _connection_errors():
                attempt += 1
                if attempt >= retries:
                    raise
                sleep(backoff)

    def _reconnect(self, *, sleep=time.sleep) -> None:
        """Drop the current socket and open a fresh session (transient failures retried)."""
        try:
            self._ws.close()
        except Exception:
            pass  # a socket that is already gone has nothing left to close
        self._ws = self._connect(sleep=sleep)

    def balance(self) -> tuple[float, str]:
        """(balance, currency) of the demo account right now; reconnects once if the socket dropped."""
        from .api.deriv.trading import get_balance

        try:
            return get_balance(self._ws)
        except _connection_errors():
            self._reconnect()
            return get_balance(self._ws)

    def place(self, plan: TradePlan, entry: float) -> tuple[int, float, float]:
        """Place the plan with its own stop and target. Returns (contract id, price, currency).

        Transport failures here are **not** retried with a re-buy: a buy whose response was lost cannot
        be told from a buy that never landed, and re-placing on a fresh socket risks opening a second
        position. The session is refreshed for later calls and the failure surfaces — a position that
        did land still carries its stop and target at the broker.
        """
        from .api.deriv.trading import place_multiplier

        _balance, currency = self.balance()  # also proves the session is alive before we buy
        try:
            bought = place_multiplier(
                self._ws, plan.direction.value == "up", symbol=self.symbol, stake=self.stake,
                multiplier=self.multiplier, stop_loss=plan.stop, take_profit=plan.target, currency=currency,
            )
        except _connection_errors():
            self._reconnect()
            raise
        return bought.contract_id, bought.buy_price, currency

    def watch(self, contract_id: int, *, timeout: float, poll_every: float, sleep=time.sleep) -> float:
        """Poll the broker's record until the position is closed, and return its realised profit.

        A socket drop between polls must not end the run while a position is open: reconnect (a fresh
        OTP session) and keep polling the same contract — the broker still holds the stop and target
        through every reconnect.
        """
        from .api.deriv.trading import get_contract_status

        waited, delay = 0.0, max(poll_every, 60.0)  # the first minute is closed to selling anyway
        while waited < timeout:
            sleep(delay)
            waited += delay
            try:
                record = get_contract_status(self._ws, contract_id)
            except _connection_errors():
                self._reconnect(sleep=sleep)
                continue
            if record.get("is_sold"):
                return float(record.get("profit", 0.0))
        raise TimeoutError(f"contract {contract_id} was still open after {timeout:.0f}s")

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass  # a socket that already died has nothing left to close


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
    # a fresh clone has no recordings/ (it is not in git) — the log must not be the thing that kills a run
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    printer = StatusPrinter(emit, heartbeat=max(report_every * 5, 300.0), now=now)
    def money() -> str:
        """The account's balance, when the broker can say — a live run must always show it."""
        try:
            bal, cur = broker.balance()
            return f"balance {bal:,.2f} {cur}"
        except Exception:  # a broker that cannot say, or a hiccup: never let the readout take the run down
            return ""

    if broker is not None and hasattr(broker, "balance"):
        emit(f"demo account {money() or 'balance unavailable'}")
    emit("connecting to the live feed; the first tick should arrive within a few seconds...")
    try:
        for record in feed:
            history.append(record.tick)
            run.ticks += 1
            if run.ticks == 1:
                emit(f"live feed connected: first tick {record.tick.price}. Status every {report_every:g}s, and a line whenever it plans, places or closes a trade.")
            decision = strategy.decide(History(history, len(history)))
            if report_every and now() - last_report >= report_every:
                # Narration between the trades, not only at them. A loop that speaks once an hour is a loop
                # that cannot be told from a dead one, and "it saw nothing" is as much of a result as "it
                # took a trade" — the strategy already knows which and why in `last_view`.
                last_report = now()
                printer.show(record.tick.price, run.readout(), getattr(strategy, "last_view", None),
                             money() if hasattr(broker, "balance") else "")
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
            try:
                contract_id, price, currency = broker.place(decision.plan, entry)
            except DerivAPIError as exc:
                # One refused order must not end the run, and it must be said plainly what the broker objected to.
                run.refused += 1
                emit(f"BROKER REFUSED this plan: {exc} — carrying on with the next one")
                continue
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
            emit(f"closed {contract_id}: {profit:+.2f} {currency} — {run.readout()}"
                 + (f" — {money()}" if hasattr(broker, "balance") else ""))
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
