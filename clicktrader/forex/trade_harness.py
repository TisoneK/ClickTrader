"""Layer 2 for trades that carry a stop and a target — a different question from `harness.py`'s.

`harness.replay` grades a direction call by comparing the price at the entry tick against the price at a
fixed horizon (`Signal.wins`). That comparison cannot grade a `TradePlan`, whose entire content is *which
level price reaches first*: a method can be right about direction and still be stopped out, or wrong and
still reach its target. Reading only the two endpoints would silently answer a different question than
the one the strategy asked, which is the failure this module exists to avoid.

So every tick between entry and resolution is walked, and the outcome is reported as **expectancy in R**,
where 1R is the distance from entry to the stop.

**The null, precisely.** For a driftless walk with a stop one distance away and a target another, the two
barriers are reached first with probabilities proportional to the *opposite* distance, which makes
expectancy exactly zero for every geometry — a house edge of zero, unlike the digit contracts' structural
−5%. That is the continuous case, and tick data is not continuous: one tick can jump clean past a level,
which biases the result toward whichever side the first move goes. With a barrier smaller than a typical
tick step, a 2:1 trade wins about half the time instead of a third, and *both* directions show a positive
expectancy that has nothing to do with skill (this is measured, not assumed — see the tests). Three
things follow, and they shape everything below:

- **Raw expectancy is not the verdict.** It mixes a real directional result with whatever the tick grid
  and any drift in the sample contribute.
- **The control is the mirror of each trade** — entered on the same tick, with the same two distances, in
  the opposite direction. A strategy with no directional information scores the same as its own mirror.
  (The mirror is not the trade's complement: its barriers sit at the same distances but not at the same
  prices, so the two score independently.)
- **The verdict is the *paired* difference, not two absolute numbers compared.** Trade and mirror share
  the tick grid, the entry moments and the geometry, so their difference cancels whatever those
  contribute on their own and leaves the one thing the strategy actually claims: that its direction call
  is better than its opposite. Comparing the two absolute expectancies instead would bury a real edge
  under a shared artifact — and would let the artifact be read as an edge. Both numbers are still
  printed, because the mirror's absolute level is how a reader sees how much of the strategy's own
  number is artifact.

There is no way to randomise the entry *moment* here, the way `harness.RandomDirection` does for a
direction call: a trade's stop and target are read off the market's own structure, so a random entry
means a different geometry, which is a different question. The mirror is the control this question has,
and it is the lower-variance form of it — a coin-flip-direction control at the same entries averages to
the same comparison with more noise.

**What this cannot do, stated plainly.** The paired edge is a claim about *direction on this sample*, and
a market that simply trended the strategy's way will make any direction-aligned method look good on it.
Nothing in a single recording separates "the price went up" from "the method knew it would", and a
control cannot: flipping the direction does not remove the trend, it is the trend that the comparison
measures. The mitigations are the ones already built in — the out-of-sample half, and re-running on a
fresh period and a different instrument before believing anything — and this is why the verdict's
positive wording tells the reader to go and do exactly that rather than reporting a number as a result.

Two further stated limits. A trade that reaches neither level before the segment ends is **unresolved
and excluded**, not marked to market — the source method has no time exit ("as long as the price holds
the low, the trade is mathematically valid"), so inventing one would be inventing a different strategy —
and unresolved trades are counted and printed rather than dropped silently, because excluding them is a
real sampling choice. And the interval assumes the trades are independent, which is the strategy's
responsibility to respect: a strategy that fires on every tick produces heavily overlapping trades, whose
shared outcome makes the stated interval narrower than the sample deserves. The methods this exists for
fire rarely, on a pattern; one that fires constantly should be read with that in mind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..model import Tick
from ..stats import MIN_BETS_REPORT, mean_interval, wilson_interval
from ..strategies import History
from .model import Direction, TradePlan
from .trade_strategies import TradeDecision, TradeStrategy


@dataclass
class TradeSegmentResult:
    label: str
    ticks: int
    trades: int = 0
    wins: int = 0
    losses: int = 0
    unresolved: int = 0
    malformed: int = 0
    r_multiples: list[float] = field(default_factory=list)
    paired_r_differences: list[float] = field(default_factory=list)
    """Per-trade `(this trade's R − its mirror's R)`, for the pairs where both reached a level. Filled on
    the strategy's own segment only: it is the same set of numbers, negated, on the mirror's."""
    z: float = 1.96

    @property
    def resolved(self) -> int:
        """Trades that reached a level and so carry an outcome."""
        return self.wins + self.losses

    @property
    def expectancy(self) -> float:
        """Mean R per resolved trade. Not the verdict on its own — see this module's docstring."""
        return sum(self.r_multiples) / len(self.r_multiples) if self.r_multiples else 0.0

    @property
    def expectancy_interval(self) -> tuple[float, float, float]:
        return mean_interval(self.r_multiples, z=self.z)

    @property
    def paired_interval(self) -> tuple[float, float, float]:
        """Mean and interval of the paired edge over the mirror — the statistic the verdict uses."""
        return mean_interval(self.paired_r_differences, z=self.z)

    @property
    def win_rate(self) -> float:
        return self.wins / self.resolved if self.resolved else 0.0

    @property
    def win_rate_interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.resolved, z=self.z)


@dataclass
class TradeReplayResult:
    strategy: str
    in_sample: TradeSegmentResult
    out_of_sample: TradeSegmentResult
    control: TradeSegmentResult

    @property
    def verdict(self) -> str:
        """Out-of-sample only, and on the paired edge rather than on either absolute expectancy."""
        oos = self.out_of_sample
        paired = len(oos.paired_r_differences)
        if paired < MIN_BETS_REPORT:
            return (
                f"NO VERDICT — {paired} resolved out-of-sample trades; at least {MIN_BETS_REPORT} are "
                "needed. This is not a near miss to read into: a stop/target outcome is wider-tailed than "
                "a hit rate, so a trade method needs *more* resolved trades than a direction call does, "
                "not fewer. Record more sessions rather than reading anything into this."
            )
        mean, lo, hi = oos.paired_interval
        if lo > 0:
            return (
                f"POSITIVE edge over its own mirror: {mean:+.3f}R per trade (interval {lo:+.3f} to "
                f"{hi:+.3f}). The direction call is worth something on this sample. Unlike the digit "
                "contracts nothing rules this out algebraically — but it is still a surprising result, "
                "and the honest next step is a fresh period and a fresh instrument before trusting it."
            )
        if hi < 0:
            return (
                f"Worse than its own mirror: {mean:+.3f}R per trade (interval {lo:+.3f} to {hi:+.3f}). "
                "Flipping every direction would have done better on this sample."
            )
        return (
            f"No edge over its own mirror: {mean:+.3f}R per trade (interval {lo:+.3f} to {hi:+.3f} "
            "includes zero). The direction call is indistinguishable from its opposite."
        )

    def report(self) -> str:
        lines = [f"strategy: {self.strategy}", ""]
        for seg in (self.in_sample, self.out_of_sample, self.control):
            mean, lo, hi = seg.expectancy_interval
            wlo, whi = seg.win_rate_interval
            ci_label = "95% CI" if seg.z == 1.96 else f"CI(z={seg.z:.2f})"
            lines.append(
                f"[{seg.label}] {seg.ticks} ticks, {seg.trades} trades "
                f"({seg.resolved} resolved, {seg.unresolved} still open at the segment's end"
                + (f", {seg.malformed} refused as malformed" if seg.malformed else "")
                + ")"
            )
            lines.append(f"  expectancy {mean:+.3f}R  ({ci_label} {lo:+.3f} to {hi:+.3f})")
            lines.append(f"  win rate   {seg.win_rate:.3f}  ({ci_label} {wlo:.3f}-{whi:.3f})")
        edge_mean, edge_lo, edge_hi = self.out_of_sample.paired_interval
        lines += [
            "",
            f"paired edge over the mirror (out-of-sample, the statistic the verdict uses): "
            f"{edge_mean:+.3f}R  ({edge_lo:+.3f} to {edge_hi:+.3f}) over "
            f"{len(self.out_of_sample.paired_r_differences)} trades",
            "",
            "(expectancy is mean R per resolved trade, 1R being the distance from entry to the stop. A",
            " driftless walk that cannot jump a level expects 0.000R for any geometry, but a tick grid",
            " coarse enough to jump one biases both a trade and its mirror the same way — which is why",
            " the verdict reads the paired difference over the mirror, not either number above it.)",
            "",
            f"verdict (out-of-sample only): {self.verdict}",
        ]
        return "\n".join(lines)


def mirrored_plan(plan: TradePlan, entry: float) -> TradePlan:
    """The same trade with the direction flipped and both *distances* preserved.

    A long risking 100 ticks to make 250 mirrors into a short risking 100 to make 250. The mirrored
    barriers land at different prices than the original's, so this is a genuinely separate trade that
    scores independently rather than the original's complement.
    """
    risk, reward = plan.risk(entry), plan.reward(entry)
    if plan.direction is Direction.UP:
        return TradePlan(Direction.DOWN, stop=entry + risk, target=entry - reward)
    return TradePlan(Direction.UP, stop=entry - risk, target=entry + reward)


def resolve(plan: TradePlan, entry: float, ticks: Sequence[Tick], first: int, stop: int) -> float | None:
    """Walk `ticks[first:stop]` for the first level the plan reaches, returning the outcome in R.

    `-1.0` for a stop, `+reward/risk` for a target, `None` if neither is reached before the segment ends.

    Resolution is judged on the tick prices as recorded, and a tick is a *point*: a price that passed
    through a level between two recorded ticks is not seen, and neither is the order two levels were
    touched within one tick's own interval. That is a real limit of tick data, not of this function, and
    it leans toward flattering a strategy rather than penalising it — a stop hit mid-tick whose closing
    price sits back above it reads as no stop at all.
    """
    risk = plan.risk(entry)
    if risk == 0:
        return None
    payoff = plan.reward(entry) / risk
    for i in range(first, stop):
        price = float(ticks[i].price)
        # A well-formed plan has its two levels on opposite sides of the entry, so no single tick can
        # satisfy both; the stop is tested first anyway, so the ordering never depends on tick detail.
        if plan.direction is Direction.UP:
            if price <= plan.stop:
                return -1.0
            if price >= plan.target:
                return payoff
        else:
            if price >= plan.stop:
                return -1.0
            if price <= plan.target:
                return payoff
    return None


def _run_trade_segment(
    strategy: TradeStrategy, ticks: Sequence[Tick], start: int, stop: int, label: str, z: float
) -> tuple[TradeSegmentResult, TradeSegmentResult]:
    """Grade one segment for both the strategy and its mirror, from the same decisions.

    Returns `(strategy, mirror)`. Grading the mirror here rather than replaying a second strategy object
    keeps the pairing exact: there is no way for the control to see a different set of entries than the
    strategy did, and no way for the two to end up on different samples.
    """
    seg = TradeSegmentResult(label=label, ticks=stop - start, z=z)
    mirror = TradeSegmentResult(label=f"control: mirror of {strategy.name}", ticks=stop - start, z=z)
    for i in range(start, stop):
        history = History(ticks, i + 1)
        decision: TradeDecision | None = strategy.decide(history)
        if decision is None:
            continue
        entry = float(ticks[i].price)
        if not decision.plan.is_well_formed(entry):
            seg.malformed += 1
            continue
        graded: list[float] = []
        for target, plan in ((seg, decision.plan), (mirror, mirrored_plan(decision.plan, entry))):
            target.trades += 1
            r = resolve(plan, entry, ticks, i + 1, stop)
            if r is None:
                target.unresolved += 1
                continue
            target.r_multiples.append(r)
            if r > 0:
                target.wins += 1
            else:
                target.losses += 1
            graded.append(r)
        if len(graded) == 2:
            seg.paired_r_differences.append(graded[0] - graded[1])
    return seg, mirror


def replay_trades(
    strategy: TradeStrategy, ticks: Sequence[Tick], *, split: float = 0.5, z: float = 1.96
) -> TradeReplayResult:
    """Replay a stop/target strategy over `ticks`: the first `split` fraction in-sample, the rest
    out-of-sample, with the mirror control graded on the out-of-sample half.

    `z` widens the expectancy interval for testing several strategies together — see
    `clicktrader.stats.bonferroni_z` and `harness.replay`, which this mirrors.
    """
    if not 0 < split < 1:
        raise ValueError("split must be strictly between 0 and 1 — an out-of-sample half is not optional")
    cut = int(len(ticks) * split)
    ins, _ = _run_trade_segment(strategy, ticks, 0, cut, "in-sample", z)
    oos, control = _run_trade_segment(strategy, ticks, cut, len(ticks), "out-of-sample", z)
    return TradeReplayResult(strategy.name, ins, oos, control)
