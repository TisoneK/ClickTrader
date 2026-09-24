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
}
