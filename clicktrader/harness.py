"""Layer 2: replay a strategy over recorded ticks, and be hostile to the result.

- A contract decided on tick ``i`` settles on tick ``i + 1`` (one-tick digit contracts).
- The recording is split chronologically. The verdict is drawn from the out-of-sample half only; the
  in-sample half is shown, labelled, and never trusted.
- A random control runs over the same ticks, so the report always shows what knowing nothing earns.
- Fewer than ``MIN_BETS_REPORT`` out-of-sample bets and there is no verdict at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .ledger import DecisionLedger, LedgerRow
from .model import HOUSE_EDGE, Tick
from .stats import MIN_BETS_REPORT, mean_interval, wilson_interval
from .strategies import History, RandomControl, Strategy


@dataclass
class SegmentResult:
    label: str
    ticks: int
    bets: int = 0
    wins: int = 0
    staked: float = 0.0
    pnl: float = 0.0
    expected_wins: float = 0.0
    """Sum of p(win) over the contracts actually taken — what uniform digits would give."""
    max_drawdown: float = 0.0
    longest_losing_streak: int = 0
    returns: list[float] = field(default_factory=list, repr=False)
    """P/L per unit staked, one per bet."""

    @property
    def hit_rate(self) -> float:
        return self.wins / self.bets if self.bets else 0.0

    @property
    def expected_hit_rate(self) -> float:
        return self.expected_wins / self.bets if self.bets else 0.0

    @property
    def hit_rate_interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.bets)

    @property
    def return_per_stake(self) -> tuple[float, float, float]:
        """(mean, low, high) P/L per unit staked. The pricing says the mean is -0.05."""
        return mean_interval(self.returns)


@dataclass
class ReplayResult:
    strategy: str
    in_sample: SegmentResult
    out_of_sample: SegmentResult
    control: SegmentResult
    """The random control over the same out-of-sample ticks."""

    @property
    def verdict(self) -> str:
        oos = self.out_of_sample
        if oos.bets < MIN_BETS_REPORT:
            return (
                f"NO VERDICT — {oos.bets} out-of-sample bets; at least {MIN_BETS_REPORT} are needed. "
                "Record more ticks rather than read anything into this."
            )
        mean, low, high = oos.return_per_stake
        if low > 0:
            return (
                "POSITIVE out-of-sample return with its whole interval above zero. That contradicts the "
                "pricing; before believing it, re-record on a fresh day and run again."
            )
        if low <= -HOUSE_EDGE <= high:
            return (
                f"No edge: return per stake {mean:+.3f} is indistinguishable from the pricing's "
                f"{-HOUSE_EDGE:+.3f}."
            )
        if high < -HOUSE_EDGE:
            return f"Worse than the pricing: {mean:+.3f} per stake, interval entirely below {-HOUSE_EDGE:+.3f}."
        return (
            f"Return per stake {mean:+.3f} sits between the pricing and zero but its interval includes "
            "zero — not evidence of an edge. More data would tighten it."
        )

    def report(self) -> str:
        lines = [f"strategy: {self.strategy}", ""]
        for seg in (self.in_sample, self.out_of_sample, self.control):
            lo, hi = seg.hit_rate_interval
            mean, rlo, rhi = seg.return_per_stake
            lines += [
                f"[{seg.label}] {seg.ticks} ticks, {seg.bets} bets",
                f"  hit rate   {seg.hit_rate:.3f}  (95% CI {lo:.3f}–{hi:.3f}; uniform digits give {seg.expected_hit_rate:.3f})",
                f"  P/L        {seg.pnl:+.2f} on {seg.staked:.2f} staked",
                f"  per stake  {mean:+.4f}  (95% CI {rlo:+.4f} to {rhi:+.4f}; pricing gives {-HOUSE_EDGE:+.4f})",
                f"  drawdown   {seg.max_drawdown:.2f}   longest losing streak {seg.longest_losing_streak}",
            ]
        lines += ["", f"verdict (out-of-sample only): {self.verdict}"]
        return "\n".join(lines)


def _run_segment(
    strategy: Strategy,
    ticks: Sequence[Tick],
    start: int,
    stop: int,
    label: str,
    ledger: DecisionLedger | None,
    log_skips: bool,
) -> SegmentResult:
    seg = SegmentResult(label=label, ticks=stop - start)
    balance = peak = 0.0
    streak = 0
    # The last tick of the segment has no settling tick inside it, so decisions stop one short.
    for i in range(start, stop - 1):
        history = History(ticks, i + 1)
        decision = strategy.decide(history)
        seen = ticks[i]
        if decision is None:
            if ledger is not None and log_skips:
                ledger.append(LedgerRow(seen.ts, i, seen.digit, strategy.name, "skip", "no signal", balance=balance))
            continue
        settle = ticks[i + 1].digit
        pnl = decision.contract.settle(decision.stake, settle)
        won = pnl > 0
        seg.bets += 1
        seg.wins += won
        seg.staked += decision.stake
        seg.pnl += pnl
        seg.expected_wins += decision.contract.win_probability
        seg.returns.append(pnl / decision.stake)
        balance += pnl
        peak = max(peak, balance)
        seg.max_drawdown = max(seg.max_drawdown, peak - balance)
        streak = 0 if won else streak + 1
        seg.longest_losing_streak = max(seg.longest_losing_streak, streak)
        if ledger is not None:
            ledger.append(
                LedgerRow(
                    seen.ts, i, seen.digit, strategy.name, "bet", decision.reason,
                    contract=str(decision.contract), stake=decision.stake,
                    settle_digit=settle, won=won, pnl=pnl, balance=balance,
                )
            )
    return seg


def replay(
    strategy: Strategy,
    ticks: Sequence[Tick],
    *,
    split: float = 0.5,
    control: Strategy | None = None,
    ledger: DecisionLedger | None = None,
    log_skips: bool = False,
) -> ReplayResult:
    """Replay ``strategy`` over ``ticks``: the first ``split`` fraction is in-sample, the rest is the
    out-of-sample half the verdict is drawn from. The control defaults to a seeded random strategy that
    bets as often as ``strategy`` did out-of-sample, so the two are compared on equal footing."""
    if not 0 < split < 1:
        raise ValueError("split must be strictly between 0 and 1 — an out-of-sample half is not optional")
    cut = int(len(ticks) * split)
    ins = _run_segment(strategy, ticks, 0, cut, "in-sample", ledger, log_skips)
    oos = _run_segment(strategy, ticks, cut, len(ticks), "out-of-sample", ledger, log_skips)
    if control is None:
        opportunities = max(1, len(ticks) - cut - 1)
        control = RandomControl(seed=12345, bet_probability=min(1.0, oos.bets / opportunities) or 1.0)
    ctl = _run_segment(control, ticks, cut, len(ticks), f"control: {control.name}", None, False)
    return ReplayResult(strategy.name, ins, oos, ctl)
