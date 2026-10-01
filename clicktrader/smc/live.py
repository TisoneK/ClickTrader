"""Running the SMC engine on the live feed: paper mode (the default) and demo-account placement.

**Paper mode places nothing.** It reads the same live ticks, asks the same strategy, and "takes" each plan as a virtual
position that the real ticks then resolve against its stop and target. That gives a forward, out-of-sample record
with no account involved, and is the right first step for any live test. What it cannot show: slippage, the broker's
commission on Multipliers, and a fill at the stop that is not at the stop. Those only appear when orders are placed,
so paper results must never be read as the account's.

**Placing is demo-only by construction.** `multipliers.DerivMultiplierBroker` opens its session with
`require_demo=True` and reads only `DERIV_DEMO_ACCOUNT_ID`; there is no real-money path here and none is added.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ..forex.model import Direction
from ..forex.trade_strategies import TradeStrategy
from ..multipliers import MultiplierRun, StatusPrinter, _say, _tell
from ..strategies import History


@dataclass
class _Paper:
    direction: Direction
    entry: float
    stop: float
    target: float
    opened: float
    reason: str


class SmokeTest:
    """A pipeline test, not a strategy: place ONE small trade at once, whatever the chart says, so everything after the
    decision (placing, polling the position, closing, logging, the page) can be watched in minutes instead of hours.

    It wraps the real strategy and keeps feeding it, so the page still shows the live chart; the real strategy's own
    decisions are ignored. The stop and target are sized in money (stop 0.2 and target 0.3 of the stake), small enough to
    resolve within a few minutes and large enough for the broker's 0.10 minimum. Its trade is logged to its own file, so it
    can never count as evidence."""

    name = "smoke-test"

    def __init__(self, inner, *, side: str, stake: float, multiplier: int) -> None:
        self._inner, self._side, self._stake, self._multiplier = inner, side, stake, multiplier
        self.fired = False

    def __getattr__(self, name):  # warm(), reading, last_view, describe()...: the page and the warm-up see the real strategy
        return getattr(self._inner, name)

    def decide(self, history):
        from ..forex.trade_strategies import TradeDecision
        from ..forex.model import TradePlan

        self._inner.decide(history)
        if self.fired or not len(history):
            return None
        self.fired = True
        price = float(history[-1].price)
        # money = distance / price * stake * multiplier, so a stop worth 0.2 of the stake is 0.2 / multiplier of the price away
        stop_d, target_d = 0.2 / self._multiplier * price, 0.3 / self._multiplier * price
        up = self._side == "buy"
        plan = TradePlan(Direction.UP if up else Direction.DOWN, stop=price - stop_d if up else price + stop_d,
                         target=price + target_d if up else price - target_d)
        return TradeDecision(plan, self._stake, f"smoke test: a forced {self._side} to check the whole path - not a signal")


def warm_from_history(strategy, symbol: str, *, minutes: float, bars: int, decimals: int = 2, emit: Callable[[str], None] = _say) -> int:
    """Give the strategy the chart a person would already have on screen: recent candles from Deriv, fed as ticks.

    Without this a live run is blind for the first hours (the reading needs dozens of bars and the higher clocks need
    more). Four ticks per bar: real prices, invented times inside each bar, which is fine for building bars."""
    from ..api.deriv.history import fetch_candles, ticks_from_candles

    granularity = int(minutes * 60)
    candles = fetch_candles(symbol, granularity=granularity, count=bars)
    candles = [c for c in candles if int(c["epoch"]) % granularity == 0]  # the candle still forming carries the time of its last tick, not its open
    ticks = [r.tick for r in ticks_from_candles(candles, symbol=symbol, granularity=granularity, decimals=decimals)]
    fed = strategy.warm(ticks)
    emit(f"warmed with {len(candles)} {minutes:g}-minute bars of {symbol} ({fed} ticks) — the engine starts with a chart, not a blank screen")
    return fed


def paper_run(
    *,
    symbol: str,
    log_path: str,
    stake: float,
    multiplier: int,
    strategy: TradeStrategy,
    ticks: Iterator,
    max_trades: int | None = None,
    max_seconds: float | None = None,
    max_loss_per_trade: float | None = None,
    report_every: float = 300.0,
    on_state: Callable[[dict | None], None] | None = None,
    emit: Callable[[str], None] = _say,
    now: Callable[[], float] = time.time,
) -> MultiplierRun:
    """Trade the strategy's plans on paper against the live ticks. One virtual position at a time, like the live loop.

    Exits are at the stop or target LEVEL (no slippage) and a loss is capped at the stake, which is what a
    Multiplier's stop-out does. No commission is modelled. The log rows say `"mode": "paper"`."""
    run = MultiplierRun()
    history: list = []
    open_pos: _Paper | None = None
    started = last_report = now()
    exposure = stake * multiplier
    # a fresh clone has no recordings/ (it is not in git) — the log must not be the thing that kills a run
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    printer = StatusPrinter(emit, heartbeat=max(report_every * 5, 300.0), now=now)
    emit("connecting to the live feed; the first tick should arrive within a few seconds...")
    try:
        for record in ticks:
            tick = record.tick
            price = float(tick.price)
            history.append(tick)
            run.ticks += 1
            if run.ticks == 1:
                emit(f"live feed connected: first tick {price}. Status every {report_every:g}s, and a line whenever it plans or closes a trade.")
            decision = strategy.decide(History(history, len(history)))
            if report_every and now() - last_report >= report_every:
                last_report = now()
                printer.show(price, run.readout(), getattr(strategy, "last_view", None))
            if open_pos is not None:
                long = open_pos.direction is Direction.UP
                unrealised = max(-stake, exposure * (price - open_pos.entry) / open_pos.entry * (1 if long else -1))
                run.open = f"practice position open {unrealised:+.2f}"
                _tell(on_state, {"contract_id": "paper", "side": "buy" if long else "sell", "entry": open_pos.entry, "stop": open_pos.stop,
                                 "target": open_pos.target, "price": price, "opened": open_pos.opened, "profit": unrealised})
                hit_stop = price <= open_pos.stop if long else price >= open_pos.stop
                hit_target = price >= open_pos.target if long else price <= open_pos.target
                if hit_stop or hit_target:
                    exit_price = open_pos.stop if hit_stop else open_pos.target
                    move = (exit_price - open_pos.entry) / open_pos.entry * (1 if long else -1)
                    profit = max(-stake, exposure * move)
                    run.placed += 1
                    run.net += profit
                    run.outcomes.append(profit)
                    run.won += 1 if profit > 0 else 0
                    log.write(json.dumps({
                        "mode": "paper", "ts": now(), "contract_id": f"paper-{run.placed}", "symbol": symbol,
                        "direction": open_pos.direction.value, "stake": stake, "multiplier": multiplier,
                        "entry": open_pos.entry, "stop": open_pos.stop, "target": open_pos.target, "profit": profit,
                        "reason": open_pos.reason, "rules": strategy.config_id() if hasattr(strategy, "config_id") else None,
                    }) + "\n")
                    log.flush()
                    os.fsync(log.fileno())
                    emit(f"paper trade closed at the {'stop' if hit_stop else 'target'}: {profit:+.2f} — {run.readout()}")
                    open_pos = None
                    run.open = ""
                    _tell(on_state, None)
                    if max_trades is not None and run.placed >= max_trades:
                        emit(f"reached the cap of {max_trades} paper trades; stopping")
                        break
                continue
            if decision is None:
                if max_seconds is not None and now() - started > max_seconds:
                    emit("reached the time cap; stopping")
                    break
                continue
            run.plans += 1
            risk = abs(price - decision.plan.stop) / price * exposure
            if max_loss_per_trade is not None and risk > max_loss_per_trade:
                run.refused += 1
                emit(f"refused: the stop is {risk:.2f} of exposure away, over the {max_loss_per_trade:.2f} limit")
                continue
            open_pos = _Paper(decision.plan.direction, price, decision.plan.stop, decision.plan.target, now(), decision.reason)
            emit(f"PAPER plan taken (nothing placed): {decision.reason[:170]}")
    finally:
        log.close()
    emit(run.readout())
    return run
