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
from ..multipliers import MultiplierRun, _say
from ..strategies import History


@dataclass
class _Paper:
    direction: Direction
    entry: float
    stop: float
    target: float
    opened: float
    reason: str


def warm_from_history(strategy, symbol: str, *, minutes: float, bars: int, decimals: int = 2, emit: Callable[[str], None] = _say) -> int:
    """Give the strategy the chart a person would already have on screen: recent candles from Deriv, fed as ticks.

    Without this a live run is blind for the first hours (the reading needs dozens of bars and the higher clocks need
    more). Four ticks per bar: real prices, invented times inside each bar, which is fine for building bars."""
    from ..api.deriv.history import fetch_candles, ticks_from_candles

    granularity = int(minutes * 60)
    candles = fetch_candles(symbol, granularity=granularity, count=bars)
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
    log = open(log_path, "a", encoding="utf-8")
    try:
        for record in ticks:
            tick = record.tick
            price = float(tick.price)
            history.append(tick)
            run.ticks += 1
            decision = strategy.decide(History(history, len(history)))
            if report_every and now() - last_report >= report_every:
                last_report = now()
                emit(f"[{now() - started:.0f}s] {run.readout()}")
                seen = getattr(strategy, "last_view", None)
                if seen:
                    emit(f"  what it sees: {seen}")
            if open_pos is not None:
                long = open_pos.direction is Direction.UP
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
                        "reason": open_pos.reason,
                    }) + "\n")
                    log.flush()
                    os.fsync(log.fileno())
                    emit(f"paper trade closed at the {'stop' if hit_stop else 'target'}: {profit:+.2f} — {run.readout()}")
                    open_pos = None
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
