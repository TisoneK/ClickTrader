"""A directional signal: will price be higher or lower `horizon_ticks` from now?

Deliberately smaller than `clicktrader.model.Contract`: no payout, no win probability. Pricing a real
Rise/Fall contract needs Deriv's live quoted terms at the moment of entry (implied volatility priced in,
not a closed form the way `0.95 / p(win)` is for digit contracts) — recording those at scale is its own
future piece of work, not worth building before knowing whether any signal here has directional accuracy
worth pricing at all. This module answers the cheaper, prior question first.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class Signal:
    direction: Direction
    horizon_ticks: int
    """How many ticks ahead to check the outcome. Fixed per signal, not per strategy, so a replay can
    mix strategies with different horizons without the harness needing to know about it."""

    def __post_init__(self) -> None:
        if self.horizon_ticks < 1:
            raise ValueError("horizon_ticks must be at least 1 — a signal about the past isn't one")

    def wins(self, entry_price: float, exit_price: float) -> bool:
        """Strictly higher/lower — an exact tie is a loss on both sides, the same asymmetry a real
        Rise/Fall contract without "allow equals" has."""
        if self.direction is Direction.UP:
            return exit_price > entry_price
        return exit_price < entry_price

    def __str__(self) -> str:
        return f"{self.direction.value} over {self.horizon_ticks}"
