"""Layer 2 extended: does RiskGuard actually bound drawdown, measured rather than asserted.

Chops a recording into fixed-length "sessions" and, for each one, runs a strategy exactly once to
get its real sequence of (stake, pnl) outcomes. That identical sequence is then replayed twice: once
through a fresh `RiskGuard` (stopping the moment it would refuse a trade or trip), once with no guard
at all. Both numbers come from the same decisions on the same ticks, so the only thing that can differ
between them is what the guard itself changed — not sampling noise from two separate simulated runs.

A stateful strategy (`MartingaleOnLoss`'s escalating stake) gets a fresh instance every session: a real
session-loss cap resets at the start of a session too, not carrying yesterday's balance in with it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Callable

from .limits import RiskGuard, RiskLimits
from .model import Tick
from .strategies import History, Strategy


@dataclass(frozen=True)
class SessionOutcome:
    total_bets_available: int
    """How many bets the strategy made across the whole session if nothing ever stopped it."""
    guarded_bets: int
    guarded_final_pnl: float
    guarded_max_drawdown: float
    stopped_early: bool
    halted_reason: str | None
    unbounded_final_pnl: float
    unbounded_max_drawdown: float


def _bets_for_session(strategy: Strategy, ticks: Sequence[Tick]) -> list[tuple[float, float]]:
    """(stake, pnl) for every bet across one session, in order — no RiskGuard involved yet, matching
    `harness._run_segment`'s own decide/settle mechanics exactly."""
    bets: list[tuple[float, float]] = []
    for i in range(len(ticks) - 1):
        decision = strategy.decide(History(ticks, i + 1))
        if decision is None:
            continue
        pnl = decision.contract.settle(decision.stake, ticks[i + 1].digit)
        bets.append((decision.stake, pnl))
    return bets


def _max_drawdown(pnls: Sequence[float]) -> float:
    balance = peak = drawdown = 0.0
    for pnl in pnls:
        balance += pnl
        peak = max(peak, balance)
        drawdown = max(drawdown, peak - balance)
    return drawdown


def simulate_session(bets: Sequence[tuple[float, float]], limits: RiskLimits) -> SessionOutcome:
    """Replay one session's (stake, pnl) sequence through a *fresh* RiskGuard, and separately measure
    what the identical sequence does with no guard at all."""
    guard = RiskGuard(limits)
    guarded_pnls: list[float] = []
    for stake, pnl in bets:
        if guard.check(stake) is not None:
            break
        guard.record(pnl)
        guarded_pnls.append(pnl)
    all_pnls = [pnl for _, pnl in bets]
    return SessionOutcome(
        total_bets_available=len(bets),
        guarded_bets=len(guarded_pnls),
        guarded_final_pnl=sum(guarded_pnls),
        guarded_max_drawdown=_max_drawdown(guarded_pnls),
        stopped_early=len(guarded_pnls) < len(bets),
        halted_reason=guard.halted_reason,
        unbounded_final_pnl=sum(all_pnls),
        unbounded_max_drawdown=_max_drawdown(all_pnls),
    )


@dataclass
class RiskReplayReport:
    strategy: str
    limits: RiskLimits
    session_ticks: int
    sessions: list[SessionOutcome] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.sessions)

    @property
    def fraction_halted(self) -> float:
        return sum(s.stopped_early for s in self.sessions) / self.n if self.n else 0.0

    @property
    def guarded_worst_drawdown(self) -> float:
        return max((s.guarded_max_drawdown for s in self.sessions), default=0.0)

    @property
    def unbounded_worst_drawdown(self) -> float:
        return max((s.unbounded_max_drawdown for s in self.sessions), default=0.0)

    @property
    def guarded_worst_session_pnl(self) -> float:
        return min((s.guarded_final_pnl for s in self.sessions), default=0.0)

    @property
    def unbounded_worst_session_pnl(self) -> float:
        return min((s.unbounded_final_pnl for s in self.sessions), default=0.0)

    @property
    def guarded_mean_pnl(self) -> float:
        return sum(s.guarded_final_pnl for s in self.sessions) / self.n if self.n else 0.0

    @property
    def unbounded_mean_pnl(self) -> float:
        return sum(s.unbounded_final_pnl for s in self.sessions) / self.n if self.n else 0.0

    def report(self) -> str:
        lines = [
            f"strategy: {self.strategy}",
            f"limits: max_stake={self.limits.max_stake}, max_session_loss={self.limits.max_session_loss}, "
            f"max_consecutive_losses={self.limits.max_consecutive_losses}",
            f"{self.n} sessions of {self.session_ticks} ticks each",
            "",
            f"guard intervened in {self.fraction_halted:.1%} of sessions",
            "",
            "                             guarded      unbounded",
            f"worst single-session P/L   {self.guarded_worst_session_pnl:>10.2f}   {self.unbounded_worst_session_pnl:>10.2f}",
            f"worst drawdown seen        {self.guarded_worst_drawdown:>10.2f}   {self.unbounded_worst_drawdown:>10.2f}",
            f"mean session P/L           {self.guarded_mean_pnl:>10.2f}   {self.unbounded_mean_pnl:>10.2f}",
        ]
        return "\n".join(lines)


def replay_sessions(
    strategy_factory: Callable[[], Strategy],
    ticks: Sequence[Tick],
    limits: RiskLimits,
    *,
    session_ticks: int,
) -> RiskReplayReport:
    """Chop `ticks` into non-overlapping `session_ticks`-long windows, each run with a fresh strategy
    instance, and measure how a fresh `RiskGuard` bounds each session's drawdown against the same
    session run unbounded."""
    if session_ticks < 2:
        raise ValueError("a session needs at least 2 ticks to place and settle one bet")
    report = RiskReplayReport(strategy_factory().name, limits, session_ticks)
    for start in range(0, len(ticks) - session_ticks + 1, session_ticks):
        window = ticks[start : start + session_ticks]
        bets = _bets_for_session(strategy_factory(), window)
        report.sessions.append(simulate_session(bets, limits))
    return report
