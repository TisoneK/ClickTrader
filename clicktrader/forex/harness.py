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
from ..stats import MIN_BETS_REPORT, difference_interval, wilson_interval
from ..strategies import History
from .model import Signal
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
    breakeven: float | None = None
    """The win rate this contract needs to break even, if the caller knows it.

    Not an assumption this module makes: hit rate is all it can honestly report without a verified payout.
    But when a contract's own quoted payout is known — Rise/Fall on Volatility 25 pays a flat 95.35%, so
    51.19% of bets covers the rake — saying so in plain words is what turns a hit rate into an answer.
    """

    @property
    def verdict(self) -> str:
        """Compared against the random control's *own measured rate*, not a fixed 50% — a literal coin
        flip only averages exactly 50% when every comparison has a winner. Real tick data doesn't: an
        exact tie (price unchanged over the horizon) is a loss for either direction, so even a strategy
        with zero real skill lands below 50% by an amount that depends on how often ties actually happen
        (confirmed against a real recording: 14.8% ties dragging the empirical baseline down to ~43%,
        not 50%). The control measures that baseline directly instead of assuming it.

        The control is an estimate too, so the verdict reads the interval of the *difference* between the
        strategy and the control (`stats.difference_interval`), not the strategy against a point."""
        oos = self.out_of_sample
        if oos.bets < MIN_BETS_REPORT:
            return (
                f"NO VERDICT — only {oos.bets} trades in the second half of the data; at least "
                f"{MIN_BETS_REPORT} are needed before the numbers mean anything. Get more data rather than "
                "reading this one."
            )
        ctl = self.control
        baseline = ctl.hit_rate
        lo, hi = oos.hit_rate_interval
        # The control is an estimate too: comparing the strategy's interval with the control's point rate
        # would treat it as exact. The verdict reads the interval of the *difference* instead.
        dlo, dhi = difference_interval(oos.wins, oos.bets, ctl.wins, ctl.bets, z=oos.z)
        if dlo > 0:
            return (
                f"POSITIVE directional accuracy: {oos.hit_rate:.3f} ({lo:.3f}-{hi:.3f}) beats the random "
                f"control's {baseline:.3f} by {dlo:+.3f} to {dhi:+.3f} (not a fixed 50% — see this property's "
                "own docstring for why). Unlike digit contracts there is no algebra ruling this out, but it "
                "is still a surprising result — re-record on a fresh period and confirm before trusting it."
            )
        if dhi < 0:
            return (
                f"Worse than the random control: {oos.hit_rate:.3f} ({lo:.3f}-{hi:.3f}) against its "
                f"{baseline:.3f}, a gap of {dlo:+.3f} to {dhi:+.3f}."
            )
        return (
            f"No directional edge: hit rate {oos.hit_rate:.3f} ({lo:.3f}-{hi:.3f}); the gap to the control's "
            f"{baseline:.3f} ({dlo:+.3f} to {dhi:+.3f}) includes zero."
        )

    def report(self) -> str:
        lines = [f"strategy: {self.strategy}", ""]
        for seg in (self.in_sample, self.out_of_sample, self.control):
            lo, hi = seg.hit_rate_interval
            ci_label = "95% CI" if seg.z == 1.96 else f"CI(z={seg.z:.2f})"
            lines.append(f"[{seg.label}] {seg.ticks} ticks, {seg.bets} bets")
            lines.append(f"  hit rate   {seg.hit_rate:.3f}  ({ci_label} {lo:.3f}-{hi:.3f})")
        oos = self.out_of_sample
        lines += ["", self.plain_words()]
        if self.breakeven is not None:
            lines += ["", f"  breaking even needs {self.breakeven:.1%} of trades won (the contract's own payout)"]
        lines += ["", f"verdict (out-of-sample only): {self.verdict}"]
        return "\n".join(lines)

    def plain_words(self) -> str:
        """The same result as a sentence, because a hit rate and an interval are not an answer anyone can use.

        Written for the person who watched the method work on a chart and wants to know whether it makes
        money — not for someone who already knows what a Wilson interval is. Every number it prints is
        also in the block above it; this is the reading of them.
        """
        oos, ctl = self.out_of_sample, self.control
        if oos.bets == 0:
            return "In plain words: it found no trades to judge in the second half of the data at all."
        said = (
            f"In plain words: it won {oos.wins} of {oos.bets} trades taken ({oos.hit_rate:.1%}) in the second "
            f"half of the data, where {ctl.wins} of {ctl.bets} ({ctl.hit_rate:.1%}) is what taking those same "
            "trades at random would have won."
        )
        if oos.bets < MIN_BETS_REPORT:
            return said + f" That is too few trades to conclude anything from — {MIN_BETS_REPORT} are needed."
        lo, hi = oos.hit_rate_interval
        if self.breakeven is not None:
            if lo > self.breakeven:
                return said + f" Every plausible value ({lo:.1%} to {hi:.1%}) is above the {self.breakeven:.1%} needed to break even."
            if hi < self.breakeven:
                return said + f" Every plausible value ({lo:.1%} to {hi:.1%}) is below the {self.breakeven:.1%} needed to break even."
            return (
                said + f" The uncertainty ({lo:.1%} to {hi:.1%}) straddles the {self.breakeven:.1%} needed to "
                "break even, so this many trades cannot say which side of it the method is on."
            )
        dlo, dhi = difference_interval(oos.wins, oos.bets, ctl.wins, ctl.bets, z=oos.z)
        if dlo > 0:
            return said + f" Allowing for the random result's own uncertainty, it beats it (by {dlo:.1%} to {dhi:.1%}), which is a real signal."
        if dhi < 0:
            return said + f" Allowing for the random result's own uncertainty, it is worse than it (by {-dhi:.1%} to {-dlo:.1%})."
        return said + f" The plausible range ({lo:.1%} to {hi:.1%}) includes the random result, so this says nothing yet."


def _run_segment(strategy: ForexStrategy, ticks: Sequence[Tick], start: int, stop: int, label: str, z: float) -> ForexSegmentResult:
    seg = ForexSegmentResult(label=label, ticks=stop - start, z=z)
    for i in range(start, stop):
        history = History(ticks, i + 1)
        decision = strategy.decide(history)
        if decision is None:
            continue
        exit_index = _settle_index(ticks, i, decision.signal, stop)
        if exit_index is None:
            continue  # not enough future data left in this segment to grade it
        entry_price = float(ticks[i].price)
        exit_price = float(ticks[exit_index].price)
        seg.bets += 1
        seg.wins += decision.signal.wins(entry_price, exit_price)
    return seg


def _settle_index(ticks: Sequence[Tick], entry: int, signal: Signal, stop: int) -> int | None:
    """Where the contract settles: the first tick at or after the horizon.

    By the clock when the signal carries a wall-clock horizon — which is what a Rise/Fall expiry actually
    is — and by tick count otherwise, so every strategy written before this keeps its exact behaviour.
    `None` when the segment ends first, which is a skip rather than a grade.
    """
    if signal.horizon_seconds is None:
        index = entry + signal.horizon_ticks
        return index if index < stop else None
    target = ticks[entry].ts + signal.horizon_seconds
    for index in range(entry + 1, stop):
        if ticks[index].ts >= target:
            return index
    return None


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
