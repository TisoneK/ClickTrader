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
    horizon_ticks: int = 1
    """How many ticks ahead to check the outcome. Fixed per signal, not per strategy, so a replay can
    mix strategies with different horizons without the harness needing to know about it."""

    horizon_seconds: float | None = None
    """A wall-clock horizon, which **takes precedence** when set.

    It exists because a Rise/Fall contract's expiry is a length of *time* — two minutes — and a tick
    count is only the same thing when the feed ticks at a known rate. It is not: this project's own
    importer writes four points per bar, so "120 ticks" means two minutes on a one-second feed and half
    an hour on imported one-minute bars. Settling on the clock removes the guess, and matches the
    product the strategy is actually traded on.
    """

    def __post_init__(self) -> None:
        if self.horizon_ticks < 1:
            raise ValueError("horizon_ticks must be at least 1 — a signal about the past isn't one")
        if self.horizon_seconds is not None and self.horizon_seconds <= 0:
            raise ValueError("horizon_seconds must be positive — a signal about the past isn't one")

    def wins(self, entry_price: float, exit_price: float) -> bool:
        """Strictly higher/lower — an exact tie is a loss on both sides, the same asymmetry a real
        Rise/Fall contract without "allow equals" has."""
        if self.direction is Direction.UP:
            return exit_price > entry_price
        return exit_price < entry_price

    def __str__(self) -> str:
        if self.horizon_seconds is not None:
            return f"{self.direction.value} over {self.horizon_seconds:g}s"
        return f"{self.direction.value} over {self.horizon_ticks}"


@dataclass(frozen=True)
class TradePlan:
    """A trade with a stop and a target — the shape chart methods are actually written in, and one a
    `Signal` cannot express.

    A `Signal` says "which way, N ticks from now" and is graded by comparing two prices. A `TradePlan`
    says "which way, and here is where I am wrong", and can only be graded by walking the ticks between
    entry and resolution to see which level is reached first — a method can be right about direction and
    still be stopped out, or wrong and still reach its target, and `Signal.wins` sees neither.

    The entry price is deliberately **not** part of the plan: the harness reads it off the tick the
    decision was made on, so a strategy cannot state an entry it did not actually get. Distances are
    therefore derived against the entry rather than stored (`risk`, `reward`), and `is_well_formed` is
    the check that the two levels sit on the correct sides of it.
    """

    direction: Direction
    stop: float
    target: float

    def risk(self, entry: float) -> float:
        """Distance from entry to the stop: what 1R means for this trade."""
        return abs(entry - self.stop)

    def reward(self, entry: float) -> float:
        """Distance from entry to the target. Not required to exceed `risk` — how many R a win pays is a
        property of the method, and reporting it is the point; a strategy promising 3R and winning a
        third of the time is a different claim from one risking 1 to make 1."""
        return abs(self.target - entry)

    def reward_risk(self, entry: float) -> float:
        """R multiple a win pays. Meaningless unless `is_well_formed(entry)`."""
        risk = self.risk(entry)
        return self.reward(entry) / risk if risk else float("inf")

    def is_well_formed(self, entry: float) -> bool:
        """Are the stop and target on the correct sides of the entry, and neither equal to it?

        A plan that fails this cannot be graded as a trade at all — the "stop" is not a stop if price is
        already through it — so a harness must refuse it rather than resolve it into a number.
        """
        if self.direction is Direction.UP:
            return self.stop < entry < self.target
        return self.target < entry < self.stop
