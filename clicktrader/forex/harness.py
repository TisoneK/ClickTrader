"""Layer 2 for forex: replay a strategy over recorded ticks, checking each signal's own horizon ahead
rather than the very next tick (`clicktrader.harness.replay`'s fixed one-tick settlement doesn't fit a
signal that's about price N ticks from now).

Deliberately reports hit rate only, not P/L — there is no verified payout number to turn a win into a
dollar amount yet (see `forex/model.py`'s docstring: real Rise/Fall pricing needs Deriv's live quoted
terms at entry, which nothing here records). Reporting a fabricated payout would be worse than not
reporting one at all (DESIGN.md: honesty of the numbers above all). The verdict is drawn against a coin
flip (0.5), the natural null for short-horizon direction on a reasonably efficient market — an empirical
assumption, not a proof, which is exactly why it's measured against a random control rather than asserted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..model import Tick
from ..stats import MIN_BETS_REPORT, wilson_interval
from ..strategies import History
from .strategies import ForexStrategy, RandomDirection


@dataclass
class ForexSegmentResult:
    label: str
    ticks: int
    bets: int = 0
    wins: int = 0
    z: float = 1.96

    @property
    def hit_rate(self) -> float:
        return self.wins / self.bets if self.bets else 0.0

    @property
    def hit_rate_interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.bets, z=self.z)


@dataclass
class ForexReplayResult:
    strategy: str
    in_sample: ForexSegmentResult
    out_of_sample: ForexSegmentResult
    control: ForexSegmentResult

    @property
    def verdict(self) -> str:
        """Compared against the random control's *own measured rate*, not a fixed 50% — a literal coin
        flip only averages exactly 50% when every comparison has a winner. Real tick data doesn't: an
        exact tie (price unchanged over the horizon) is a loss for either direction, so even a strategy
        with zero real skill lands below 50% by an amount that depends on how often ties actually happen
        (confirmed against a real recording: 14.8% ties dragging the empirical baseline down to ~43%,
        not 50%). The control measures that baseline directly instead of assuming it."""
        oos = self.out_of_sample
        if oos.bets < MIN_BETS_REPORT:
            return (
                f"NO VERDICT — {oos.bets} out-of-sample bets; at least {MIN_BETS_REPORT} are needed. "
                "Record more ticks rather than read anything into this."
            )
        baseline = self.control.hit_rate
        lo, hi = oos.hit_rate_interval
        if lo > baseline:
            return (
                f"POSITIVE directional accuracy: interval {lo:.3f}-{hi:.3f} entirely above the random "
                f"control's {baseline:.3f} (not a fixed 50% — see this property's own docstring for why). "
                "Unlike digit contracts there is no algebra ruling this out, but it is still a surprising "
                "result — re-record on a fresh period and confirm before trusting it."
            )
        if hi < baseline:
            return f"Worse than the random control: interval {lo:.3f}-{hi:.3f}, entirely below its {baseline:.3f}."
        return f"No directional edge: hit rate {oos.hit_rate:.3f}, interval {lo:.3f}-{hi:.3f} includes the control's {baseline:.3f}."

    def report(self) -> str:
        lines = [f"strategy: {self.strategy}", ""]
        for seg in (self.in_sample, self.out_of_sample, self.control):
            lo, hi = seg.hit_rate_interval
            ci_label = "95% CI" if seg.z == 1.96 else f"CI(z={seg.z:.2f})"
            lines.append(f"[{seg.label}] {seg.ticks} ticks, {seg.bets} bets")
            lines.append(f"  hit rate   {seg.hit_rate:.3f}  ({ci_label} {lo:.3f}-{hi:.3f})")
        lines += [
            "",
            f"(a fair coin with no possible ties gives 0.500; the random control above is the real baseline —",
            f" see 'verdict' below for why those two numbers legitimately differ on real tick data)",
            "",
            f"verdict (out-of-sample only): {self.verdict}",
        ]
        return "\n".join(lines)


def _run_segment(strategy: ForexStrategy, ticks: Sequence[Tick], start: int, stop: int, label: str, z: float) -> ForexSegmentResult:
    seg = ForexSegmentResult(label=label, ticks=stop - start, z=z)
    for i in range(start, stop):
        history = History(ticks, i + 1)
        decision = strategy.decide(history)
        if decision is None:
            continue
        exit_index = i + decision.signal.horizon_ticks
        if exit_index >= stop:
            continue  # not enough future data left in this segment to grade it
        entry_price = float(ticks[i].price)
        exit_price = float(ticks[exit_index].price)
        seg.bets += 1
        seg.wins += decision.signal.wins(entry_price, exit_price)
    return seg


def replay(
    strategy: ForexStrategy,
    ticks: Sequence[Tick],
    *,
    split: float = 0.5,
    control: ForexStrategy | None = None,
    z: float = 1.96,
) -> ForexReplayResult:
    """Replay `strategy` over `ticks`: the first `split` fraction is in-sample, the rest is out-of-sample.
    `z` widens the interval for testing several strategies together — see `clicktrader.stats.bonferroni_z`
    and `clicktrader.harness.replay`'s own `z` parameter, which this mirrors exactly."""
    if not 0 < split < 1:
        raise ValueError("split must be strictly between 0 and 1 — an out-of-sample half is not optional")
    cut = int(len(ticks) * split)
    ins = _run_segment(strategy, ticks, 0, cut, "in-sample", z)
    oos = _run_segment(strategy, ticks, cut, len(ticks), "out-of-sample", z)
    if control is None:
        opportunities = max(1, len(ticks) - cut)
        control = RandomDirection(seed=12345, bet_probability=min(1.0, oos.bets / opportunities) or 1.0)
    ctl = _run_segment(control, ticks, cut, len(ticks), f"control: {control.name}", z)
    return ForexReplayResult(strategy.name, ins, oos, ctl)
