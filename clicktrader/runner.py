"""Layer 3 for the Rise/Fall method: run it live, and learn from the record while it runs.

The digit-contract side has `executor.py` — place trades behind a guard, one at a time, with a ledger.
This is the same shape for the contract the price-action method actually trades, plus the part that
makes a live run worth more than an expensive replay: it **learns on the side**.

What "learning" means here, and what it deliberately does not:

- **Variants run in the shadow.** Alongside the live settings, a small grid of alternative ones (a
  tighter or looser level tolerance, a stricter momentum test, three touches rather than two) reads the
  same live ticks, takes the same decisions in *theory*, and is scored on what price actually did. Their
  leaderboard is printed as the run goes on, so the loop comes back with "this setting is ahead, on this
  many trades" instead of a hunch. No money is placed on a variant, so a lucky streak in the shadows
  cannot cost anything and cannot contaminate the live record.
- **The live rules do not change mid-run.** This is the one thing that would make the whole exercise
  worthless: a system that rewrites its own rules while it is also deciding what counts as a win can
  never tell whether a change helped or whether it got lucky, and telling those two apart is the entire
  reason this project exists. A variant that leads in the shadows is a *candidate* — it earns its way
  into the live settings by being tested on the record first, through the replay, where the
  out-of-sample split already lives. DESIGN.md has said "no model in the decision loop, and learning
  lives in replay" since the first session; this is what that looks like when the loop is real.

Every settled live trade goes to the trade log, so the run accumulates the count that decides the
method. Nothing here decides that on its own.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterator, Sequence

from .api.deriv import DEFAULT_APP_ID, DerivAPIError
from .api.deriv.ticks import stream_ticks
from .api.deriv.trading import get_balance, get_otp_url, place_rise_fall, wait_for_settlement
from .forex.model import Direction, Signal
from .forex.strategies import PurePriceAction
from .limits import RiskGuard, RiskLimits
from .model import Tick
from .strategies import History
from .trade_log import RiseFallTrade, TradeLog, tally


def _say(line: str) -> None:
    """Print and flush. A long run's output goes to a file or a pipe, where Python block-buffers — and a
    loop that is working but silent is indistinguishable from one that has died. This project already
    learned that once on `record-deriv` (`--progress-every` exists for the same reason) and the lesson is
    the same here: a multi-hour process has to report as it goes."""
    print(line, flush=True)


@dataclass
class ShadowVariant:
    """A set of settings scored on live price without ever being traded."""

    name: str
    strategy: PurePriceAction
    bets: int = 0
    wins: int = 0
    pending: list[tuple[float, float, Direction, float]] = field(default_factory=list)
    """(entry ts, entry price, direction, settle-at ts) — decisions waiting for the clock to reach them."""

    @property
    def rate(self) -> float:
        return self.wins / self.bets if self.bets else 0.0

    def feed(self, tick: Tick, history: History) -> None:
        decision = self.strategy.decide(history)
        if decision is None or decision.signal.horizon_seconds is None:
            return
        self.pending.append(
            (tick.ts, float(tick.price), decision.signal.direction,
             tick.ts + decision.signal.horizon_seconds)
        )

    def resolve(self, now: Tick) -> None:
        price = float(now.price)
        still_waiting = []
        for entry_ts, entry_price, direction, settle_at in self.pending:
            if now.ts < settle_at:
                still_waiting.append((entry_ts, entry_price, direction, settle_at))
                continue
            self.bets += 1
            self.wins += 1 if Signal(direction).wins(entry_price, price) else 0
        self.pending = still_waiting


def shadow_grid(*, tolerance: float, body_ratio: float, size_multiple: float, expiry: float) -> list[ShadowVariant]:
    """The alternatives the loop scores for free — a step either side of each live setting.

    Deliberately small and coarse: this is a leaderboard of *directions to look in*, not a search. A wide
    grid read live would be fitting noise in public, and the project's multiple-comparisons work already
    showed how easily a batch of variants produces a leader that means nothing.
    """
    variants = [
        ("looser levels", dict(level_tolerance=tolerance * 2)),
        ("tighter levels", dict(level_tolerance=tolerance / 2)),
        ("three touches", dict(min_touches=3)),
        ("stricter candle", dict(body_ratio=min(0.9, body_ratio + 0.2))),
        ("bigger candle", dict(size_multiple=size_multiple * 1.5)),
        ("longer expiry", dict(expiry_seconds=expiry * 2)),
    ]
    return [ShadowVariant(name, PurePriceAction(**settings)) for name, settings in variants]


@dataclass
class RunSummary:
    ticks: int = 0
    signals: int = 0
    placed: int = 0
    refused: int = 0
    won: int = 0
    net: float = 0.0

    def readout(self) -> str:
        if not self.placed:
            return (
                f"{self.ticks} ticks, {self.signals} signal(s), nothing placed yet — the method takes about "
                "one trade an hour at these settings, so this is normal"
            )
        return (
            f"{self.ticks} ticks, {self.signals} signal(s), {self.placed} placed ({self.refused} refused by "
            f"the limits): won {self.won} of {self.placed}, net {self.net:+.2f}"
        )


def shadow_leaderboard(variants: Sequence[ShadowVariant], *, live: tuple[int, int] | None = None) -> str:
    """The shadow results, worst-to-best, with the live settings alongside for scale."""
    lines = ["what the shadows say so far (no money on any of these):"]
    for variant in sorted(variants, key=lambda v: v.rate):
        lines.append(f"  {variant.name:<16} won {variant.wins:>4} of {variant.bets:>4}  ({variant.rate:.1%})")
    if live is not None:
        wins, bets = live
        rate = wins / bets if bets else 0.0
        lines.append(f"  {'-- live settings':<16} won {wins:>4} of {bets:>4}  ({rate:.1%})")
    return "\n".join(lines)


def run(
    *,
    symbol: str,
    log_path: str,
    stake: float,
    duration: int = 2,
    duration_unit: str = "m",
    app_id: int = DEFAULT_APP_ID,
    limits: RiskLimits | None = None,
    max_trades: int | None = None,
    max_ticks: int | None = None,
    paper: bool = False,
    report_every: float = 900.0,
    expiry_seconds: float = 120.0,
    strategy_factory: Callable[[], PurePriceAction] = PurePriceAction,
    guard_factory: Callable[[], RiskGuard] | None = None,
    otp_url: str | None = None,
    ticks: Iterator | None = None,
    now: Callable[[], float] = time.time,
    emit: Callable[[str], None] = _say,
) -> RunSummary:
    """Run the method against the live feed, placing one contract per signal until a limit or a stop.

    Everything that touches the outside world is injectable — the tick stream, the OTP url, the clock and
    the printer — so the loop can be exercised end to end without a network or a broker. `ticks` yields
    `TickRecord`s, the same shape `stream_ticks` produces, so what the tests drive is what the feed sends.
    """
    strategy = strategy_factory()
    shadows = shadow_grid(
        tolerance=0.002, body_ratio=0.6, size_multiple=1.5, expiry=expiry_seconds
    )
    summary = RunSummary()
    history: list[Tick] = []
    feed = ticks if ticks is not None else stream_ticks(symbol, app_id=app_id)
    guard = (guard_factory or (lambda: RiskGuard(limits)))() if guard_factory or limits else RiskGuard(
        RiskLimits(max_stake=stake, max_session_loss=stake * 10, max_consecutive_losses=5)
    )
    trade_ws = None
    last_report = now()
    trade_log = TradeLog(log_path)

    try:
        if not paper:
            import websocket  # local: only needed when actually trading

            token, app, account = (
                os.environ[n] for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID")
            )
            trade_ws = websocket.create_connection(otp_url or get_otp_url(account, token, app, require_demo=True))
            balance, currency = get_balance(trade_ws)
            emit(f"trading {symbol} on the demo account, balance {balance:.2f} {currency}, stake {stake}")
        else:
            currency = "USD"
            emit(f"PAPER MODE — watching {symbol} and scoring the signals, placing nothing")

        for record in feed:
            tick = record.tick
            history.append(tick)
            summary.ticks += 1

            decision = strategy.decide(History(history, len(history)))
            for variant in shadows:
                variant.feed(tick, History(history, len(history)))
                variant.resolve(tick)

            if decision is not None and decision.signal.horizon_seconds is not None:
                summary.signals += 1
                refusal = guard.check(stake)
                if refusal is not None:
                    summary.refused += 1
                    emit(f"signal refused by the limits: {refusal}")
                    if guard.halted:
                        # The guard *latches*: once tripped it refuses everything until a named human
                        # rearms it. Carrying on here would leave a loop that is watching, printing and
                        # inert — looking like it is working while placing nothing, which is the worst of
                        # the available behaviours. Stop, and say why.
                        emit(f"STOPPING: {guard.halted_reason}. A person has to decide whether to start again.")
                        break
                else:
                    summary = _take(
                        summary, decision, tick, trade_ws, trade_log, guard, currency, symbol, stake,
                        duration, duration_unit, paper=paper, emit=emit,
                    )
                    if max_trades is not None and summary.placed >= max_trades:
                        emit(f"reached --max-trades {max_trades}; stopping")
                        break
            if max_ticks is not None and summary.ticks >= max_ticks:
                emit(f"reached --max-ticks {max_ticks}; stopping")
                break
            if now() - last_report >= report_every:
                last_report = now()
                emit(summary.readout())
                emit(shadow_leaderboard(shadows, live=(summary.won, summary.placed)))
                settled = tally(log_path)
                if settled.trades:
                    emit(settled.report())
    finally:
        trade_log.close()
        if trade_ws is not None:
            trade_ws.close()

    emit(summary.readout())
    emit(shadow_leaderboard(shadows, live=(summary.won, summary.placed)))
    return summary


def _take(
    summary: RunSummary, decision, tick: Tick, trade_ws, trade_log: TradeLog, guard: RiskGuard,
    currency: str, symbol: str, stake: float, duration: int, duration_unit: str, *, paper: bool,
    emit: Callable[[str], None],
) -> RunSummary:
    """Place one contract (or, in paper mode, just record that the signal happened) and book the result."""
    rise = decision.signal.direction is Direction.UP
    if paper:
        emit(f"SIGNAL (paper): {rise and 'Rise' or 'Fall'} {symbol} — {decision.reason}")
        return summary
    bought = place_rise_fall(
        trade_ws, rise, symbol=symbol, stake=stake, currency=currency,
        duration=duration, duration_unit=duration_unit,
    )
    settled = wait_for_settlement(trade_ws, bought.contract_id, timeout=float(duration) * 60.0 + 120.0)
    guard.record(settled.profit)
    summary.placed += 1
    summary.won += 1 if settled.status == "won" else 0
    summary.net += settled.profit
    trade_log.write(
        RiseFallTrade(
            settled_at=time.time(), symbol=symbol, direction="up" if rise else "down", stake=stake,
            buy_price=bought.buy_price, payout=bought.payout, status=settled.status,
            profit=settled.profit, contract_id=bought.contract_id, duration=duration,
            duration_unit=duration_unit, exit_spot=settled.exit_spot, currency=currency,
            reason=decision.reason,
        )
    )
    emit(
        f"trade {summary.placed}: {rise and 'Rise' or 'Fall'} at {bought.buy_price:.2f} paying "
        f"{bought.payout:.2f} -> {settled.status} {settled.profit:+.2f} — {decision.reason}"
    )
    return summary
