"""Strategies: given the ticks seen so far, bet on the next one or pass.

A strategy only ever sees a ``History`` — a read-only view that ends at the current tick — so a
replay cannot leak the future into a decision. It is platform-agnostic: ticks and digits only.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable, Protocol, overload

from .model import Contract, Side, Tick


class History(Sequence[Tick]):
    """Ticks ``0 .. end-1`` of a recording. Indexing past ``end`` is impossible by construction."""

    def __init__(self, ticks: Sequence[Tick], end: int) -> None:
        self._ticks = ticks
        self._end = end

    def __len__(self) -> int:
        return self._end

    @overload
    def __getitem__(self, index: int) -> Tick: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[Tick]: ...
    def __getitem__(self, index: int | slice) -> Tick | Sequence[Tick]:
        if isinstance(index, slice):
            return [self._ticks[i] for i in range(*index.indices(self._end))]
        if index < 0:
            index += self._end
        if not 0 <= index < self._end:
            raise IndexError(index)
        return self._ticks[index]

    def last_digits(self, count: int) -> list[int]:
        return [self._ticks[i].digit for i in range(max(0, self._end - count), self._end)]

    def last_prices(self, count: int) -> list[float]:
        """Recent prices as floats — for strategies that care about the value, not the last digit
        (moving averages and the like; forex strategies use this, digit strategies use `last_digits`)."""
        return [float(self._ticks[i].price) for i in range(max(0, self._end - count), self._end)]


@dataclass(frozen=True)
class Decision:
    contract: Contract
    stake: float
    reason: str


class Strategy(Protocol):
    name: str

    def decide(self, history: History) -> Decision | None:
        """Bet on the tick after ``history[-1]``, or return None to pass."""
        ...


def _all_contracts() -> list[Contract]:
    return [Contract(Side.OVER, b) for b in range(0, 9)] + [Contract(Side.UNDER, b) for b in range(1, 10)]


class RandomControl:
    """The control every report runs alongside: picks a contract at random, knows nothing.

    Anything a strategy "achieves" that this also achieves is noise.
    """

    def __init__(self, seed: int = 0, stake: float = 1.0, bet_probability: float = 1.0) -> None:
        self.name = f"random-control(seed={seed})"
        self._rng = random.Random(seed)
        self._stake = stake
        self._bet_probability = bet_probability
        self._contracts = _all_contracts()

    def decide(self, history: History) -> Decision | None:
        if self._rng.random() >= self._bet_probability:
            return None
        return Decision(self._rng.choice(self._contracts), self._stake, "random pick")


class FixedContract:
    """Always the same contract — the simplest baseline, and the pricing rule's own prediction."""

    def __init__(self, contract: Contract, stake: float = 1.0) -> None:
        self.name = f"fixed({contract})"
        self._decision = Decision(contract, stake, f"always {contract}")

    def decide(self, history: History) -> Decision | None:
        return self._decision


class StreakReversal:
    """The claim sold most often: after ``run`` high digits (5-9) in a row, low is "due" — and vice
    versa. Bets under 5 / over 4, each a 50% contract. Included to be tested, not believed."""

    def __init__(self, run: int = 4, stake: float = 1.0) -> None:
        if run < 1:
            raise ValueError("run must be at least 1")
        self.name = f"streak-reversal(run={run})"
        self._run = run
        self._stake = stake

    def decide(self, history: History) -> Decision | None:
        if len(history) < self._run:
            return None
        recent = history.last_digits(self._run)
        if all(d >= 5 for d in recent):
            return Decision(Contract(Side.UNDER, 5), self._stake, f"{self._run} high digits in a row {recent}")
        if all(d <= 4 for d in recent):
            return Decision(Contract(Side.OVER, 4), self._stake, f"{self._run} low digits in a row {recent}")
        return None


def _digit_frequencies(digits: Sequence[int]) -> list[float]:
    """Fraction of ``digits`` equal to each value 0-9, as a length-10 list indexed by digit."""
    n = len(digits)
    return [digits.count(d) / n for d in range(10)] if n else [0.0] * 10


class ColdTailOverUnder:
    """A "last-digit-stats" claim: trade Over(barrier) once every digit *strictly below* the barrier
    has stayed under ``threshold`` frequency over the recent window; Under is the mirror (every digit
    strictly above). The barrier digit itself is never checked — that's the claim as given, not a typo:
    e.g. "Over 3" only requires 0, 1, 2 to be cold, not 3. Included to be tested, not believed: a cold
    digit in a window of independent draws predicts nothing about the next one (DESIGN.md)."""

    def __init__(self, side: Side, barrier: int, *, window: int = 100, threshold: float = 0.10, stake: float = 1.0) -> None:
        self._contract = Contract(side, barrier)  # validates the barrier
        self.name = f"cold-tail-{side.value}(barrier={barrier}, window={window}, threshold={threshold:.0%})"
        self._watch = range(0, barrier) if side is Side.OVER else range(barrier + 1, 10)
        self._window = window
        self._threshold = threshold
        self._stake = stake

    def decide(self, history: History) -> Decision | None:
        if len(history) < self._window:
            return None
        freqs = _digit_frequencies(history.last_digits(self._window))
        if any(freqs[d] >= self._threshold for d in self._watch):
            return None
        return Decision(self._contract, self._stake, f"digits {list(self._watch)} all under {self._threshold:.0%} (window={self._window})")


class ColdTailReactiveOver:
    """A third digit-stats video's claim, layering a reactive trigger on top of the cold-tail filter:
    trade Over(barrier) only once every digit strictly below the barrier is under ``threshold``
    frequency (``ColdTailOverUnder``'s own pre-filter) *and* the most recent live tick's digit is itself
    low — in ``0..barrier`` inclusive. The video's own example (barrier=2) checks 0 and 1 are cold, then
    fires the instant a tick lands on 0, 1, *or* 2. Included to be tested, not believed: neither
    condition carries information about the next digit on an independent, uniform feed (DESIGN.md)."""

    def __init__(self, barrier: int, *, window: int = 100, threshold: float = 0.10, stake: float = 1.0) -> None:
        self._contract = Contract(Side.OVER, barrier)  # validates the barrier
        self.name = f"cold-tail-reactive-over(barrier={barrier}, window={window}, threshold={threshold:.0%})"
        self._watch = range(0, barrier)
        self._trigger = range(0, barrier + 1)
        self._window = window
        self._threshold = threshold
        self._stake = stake

    def decide(self, history: History) -> Decision | None:
        if len(history) < self._window or history[-1].digit not in self._trigger:
            return None
        freqs = _digit_frequencies(history.last_digits(self._window))
        if any(freqs[d] >= self._threshold for d in self._watch):
            return None
        return Decision(
            self._contract,
            self._stake,
            f"last digit {history[-1].digit} in {list(self._trigger)}, and {list(self._watch)} all under {self._threshold:.0%}",
        )


class ParityCounterTrend:
    """Two Even/Odd videos' claim, differing only in how "dominant" gets decided:

    - ``dominance="threshold"``: count how many of the 5 even digits, and how many of the 5 odd
      digits, individually exceed ``threshold`` frequency over the window; more digits above wins.
    - ``dominance="majority"``: whichever parity's *combined* frequency (sum of its 5 digits) is
      higher over the window — a stand-in for "the green circle position," which that source video
      never gives an exact formula for.

    Either way: once a dominant parity is picked, bet it the instant the last two digits are both the
    *opposite* parity. Included to be tested, not believed — parity is 50/50 on independent uniform
    digits regardless of any window snapshot (DESIGN.md)."""

    def __init__(self, *, dominance: str = "threshold", window: int = 100, threshold: float = 0.10, stake: float = 1.0) -> None:
        if dominance not in ("threshold", "majority"):
            raise ValueError(f"dominance must be 'threshold' or 'majority', got {dominance!r}")
        self.name = f"parity-counter-trend({dominance}, window={window}, stake={stake})"
        self._dominance = dominance
        self._window = window
        self._threshold = threshold
        self._stake = stake

    def _dominant_side(self, freqs: list[float]) -> Side | None:
        evens, odds = freqs[0::2], freqs[1::2]
        if self._dominance == "threshold":
            even_score = sum(1 for f in evens if f > self._threshold)
            odd_score = sum(1 for f in odds if f > self._threshold)
        else:
            even_score, odd_score = sum(evens), sum(odds)
        if even_score == odd_score:
            return None
        return Side.EVEN if even_score > odd_score else Side.ODD

    def decide(self, history: History) -> Decision | None:
        if len(history) < self._window + 2:
            return None
        dominant = self._dominant_side(_digit_frequencies(history.last_digits(self._window)))
        if dominant is None:
            return None
        last_two = history.last_digits(2)
        wants_even_pair = dominant is Side.ODD  # waiting for 2 of the parity OPPOSITE the dominant one
        if all((d % 2 == 0) == wants_even_pair for d in last_two):
            return Decision(Contract(dominant), self._stake, f"dominant={dominant.value} ({self._dominance}), opposite pair {last_two}")
        return None


class MartingaleOnLoss:
    """Wraps another strategy's entry signal and controls only the stake: doubles after a loss, resets
    to the base stake after a win, and never bets more than ``max_fraction_of_balance`` of a tracked
    balance. The wrapped strategy decides what to bet; this decides how much.

    Included to be tested, not believed: doubling can't turn a fixed -5% EV positive — it only enlarges
    the eventual losing run that ends the sequence (DESIGN.md). There is no outcome callback in this
    harness, so this settles its own previous bet by reading the settling digit off ``history`` the next
    time ``decide`` runs — correct because the harness calls ``decide`` on every tick in order, and a bet
    placed at tick i always settles at tick i+1 (harness.py). State (balance, next stake) carries
    continuously across the in-sample/out-of-sample split, the same way ``RandomControl``'s own RNG
    does — a real bankroll doesn't reset there either."""

    def __init__(
        self,
        base: Strategy,
        *,
        starting_balance: float,
        base_stake: float,
        multiplier: float = 2.0,
        max_fraction_of_balance: float = 0.05,
    ) -> None:
        self.name = f"martingale({base.name}, x{multiplier}, cap={max_fraction_of_balance:.0%})"
        self._base = base
        self._balance = starting_balance
        self._base_stake = base_stake
        self._multiplier = multiplier
        self._cap_fraction = max_fraction_of_balance
        self._next_stake = base_stake
        self._pending: tuple[Contract, float] | None = None

    def decide(self, history: History) -> Decision | None:
        if self._pending is not None:
            contract, stake = self._pending
            digit = history[-1].digit
            won = contract.wins(digit)
            self._balance += contract.settle(stake, digit)
            self._next_stake = self._base_stake if won else self._next_stake * self._multiplier
            self._pending = None

        decision = self._base.decide(history)
        if decision is None:
            return None
        stake = min(self._next_stake, self._balance * self._cap_fraction)
        if stake <= 0:
            return None  # ruined -- can't cover even a capped stake
        self._pending = (decision.contract, stake)
        return Decision(
            decision.contract, stake, f"{decision.reason} [martingale stake={stake:.2f}, balance={self._balance:.2f}]"
        )


class LowDigitOver:
    """The user's own claim: after a low digit, bet it bounces. Bets Over(``barrier``) the instant the
    last digit is at or below ``barrier`` — no run required, and it re-fires on every tick the trigger
    still holds, even right after a loss. Included to be tested, not believed: digits are independent
    (DESIGN.md), so the last one tells the next nothing, whatever the barrier."""

    def __init__(self, barrier: int = 1, stake: float = 0.10) -> None:
        self._contract = Contract(Side.OVER, barrier)  # validates barrier is a legal Over barrier
        self.name = f"low-digit-over(barrier={barrier}, stake={stake})"
        self._barrier = barrier
        self._stake = stake

    def decide(self, history: History) -> Decision | None:
        if len(history) == 0:
            return None
        last = history[-1].digit
        if last > self._barrier:
            return None
        return Decision(self._contract, self._stake, f"last digit {last} <= barrier {self._barrier}")


REGISTRY: dict[str, Callable[[], Strategy]] = {
    "random": lambda: RandomControl(seed=1),
    "over-4": lambda: FixedContract(Contract(Side.OVER, 4)),
    "over-0": lambda: FixedContract(Contract(Side.OVER, 0)),
    "under-1": lambda: FixedContract(Contract(Side.UNDER, 1)),
    "streak-reversal": lambda: StreakReversal(run=4),
    "low-digit-over": lambda: LowDigitOver(barrier=1, stake=0.10),
    "cold-tail-over-2": lambda: ColdTailOverUnder(Side.OVER, 2),
    "cold-tail-over-3": lambda: ColdTailOverUnder(Side.OVER, 3),
    "cold-tail-under-6": lambda: ColdTailOverUnder(Side.UNDER, 6),
    "cold-tail-under-7": lambda: ColdTailOverUnder(Side.UNDER, 7),
    "cold-tail-reactive-over-2": lambda: ColdTailReactiveOver(barrier=2),
    "parity-counter-trend-threshold": lambda: ParityCounterTrend(dominance="threshold"),
    "parity-counter-trend-majority": lambda: ParityCounterTrend(dominance="majority"),
    "martingale-low-digit-over": lambda: MartingaleOnLoss(
        LowDigitOver(barrier=1, stake=0.10), starting_balance=1000.0, base_stake=0.10
    ),
}
