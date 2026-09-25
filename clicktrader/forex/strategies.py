"""Forex strategies: given the prices seen so far, call a direction over some horizon, or pass.

Reuses `clicktrader.strategies.History` directly rather than a forex-specific subclass — it's already
just a read-only windowed view of `Tick`s, generic over price and digit alike.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Protocol

from ..strategies import History
from .model import Direction, Signal


@dataclass(frozen=True)
class SignalDecision:
    signal: Signal
    stake: float
    reason: str


class ForexStrategy(Protocol):
    name: str

    def decide(self, history: History) -> SignalDecision | None:
        """Call a direction over the signal's own horizon, or return None to pass."""
        ...


class RandomDirection:
    """The control every forex report should run alongside: picks a direction at random, knows
    nothing. Anything a strategy "achieves" that this also achieves is noise — the same role
    `strategies.RandomControl` plays on the digit-contract side."""

    def __init__(self, *, horizon_ticks: int = 10, stake: float = 1.0, seed: int = 0, bet_probability: float = 1.0) -> None:
        self.name = f"random-direction(seed={seed})"
        self._rng = random.Random(seed)
        self._horizon = horizon_ticks
        self._stake = stake
        self._bet_probability = bet_probability

    def decide(self, history: History) -> SignalDecision | None:
        if self._rng.random() >= self._bet_probability:
            return None
        direction = self._rng.choice((Direction.UP, Direction.DOWN))
        return SignalDecision(Signal(direction, self._horizon), self._stake, "random pick")


class MovingAverageCrossover:
    """The textbook baseline forex strategy: track a short-window and a long-window average price, and
    call a direction the instant the short average crosses the long one — not for as long as it merely
    stays on one side of it, which would count one crossing as many separate decisions.

    Included to be tested, not believed — whether this has any real directional accuracy is a genuinely
    open empirical question on this side of the project, unlike the digit contracts' provable -5%
    (DESIGN.md). The natural null it's compared against is `RandomDirection`, i.e. a coin flip.
    """

    def __init__(self, *, short_window: int = 10, long_window: int = 30, horizon_ticks: int = 10, stake: float = 1.0) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.name = f"ma-crossover(short={short_window}, long={long_window}, horizon={horizon_ticks})"
        self._short = short_window
        self._long = long_window
        self._horizon = horizon_ticks
        self._stake = stake

    def decide(self, history: History) -> SignalDecision | None:
        if len(history) < self._long + 1:
            return None
        prices = history.last_prices(self._long + 1)
        now, prev = prices[1:], prices[:-1]  # "prev" is the same window, one tick earlier
        now_short, now_long = _mean(now[-self._short :]), _mean(now)
        prev_short, prev_long = _mean(prev[-self._short :]), _mean(prev)
        if prev_short <= prev_long and now_short > now_long:
            direction = Direction.UP
        elif prev_short >= prev_long and now_short < now_long:
            direction = Direction.DOWN
        else:
            return None
        return SignalDecision(
            Signal(direction, self._horizon), self._stake,
            f"MA({self._short})={now_short:.5f} crossed MA({self._long})={now_long:.5f} {direction.value}",
        )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


REGISTRY: dict[str, Callable[[], ForexStrategy]] = {
    "random-direction": lambda: RandomDirection(),
    "ma-crossover": lambda: MovingAverageCrossover(),
}
