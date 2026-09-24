"""Ticks, digit contracts, and the pricing rule every barrier obeys.

The platform pays ``RETURN_FACTOR / p(win)`` back per unit staked (stake included), at every barrier on
both sides — see the table at the top of DESIGN.md. Expected value per unit staked is therefore
``RETURN_FACTOR - 1 = -0.05`` for every contract, whatever the barrier. This module encodes that rule
once, so the harness can compare what a strategy got against what the pricing says it should get.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

RETURN_FACTOR = 0.95
"""Total return (stake + profit) per unit staked, times p(win). Measured, not assumed — DESIGN.md."""

HOUSE_EDGE = 1 - RETURN_FACTOR


class Side(str, Enum):
    OVER = "over"
    UNDER = "under"


def last_digit(price: str) -> int:
    """Last digit of a price *as displayed*.

    Takes the string, not a float: ``"1234.50"`` ends in 0, but ``float("1234.50")`` prints as
    ``1234.5`` and would end in 5. Trailing zeros are the most common way to mis-grade a digit.
    """
    text = price.strip()
    if not text or not text[-1].isdigit():
        raise ValueError(f"price has no trailing digit: {price!r}")
    return int(text[-1])


@dataclass(frozen=True)
class Tick:
    """One tick of the feed. ``price`` is kept as the displayed string; ``digit`` is derived from it."""

    ts: float
    price: str
    symbol: str = ""

    @property
    def digit(self) -> int:
        return last_digit(self.price)


@dataclass(frozen=True)
class Contract:
    """A digit contract: will the next tick's last digit be over / under ``barrier``?"""

    side: Side
    barrier: int

    def __post_init__(self) -> None:
        low, high = (0, 8) if self.side is Side.OVER else (1, 9)
        if not low <= self.barrier <= high:
            raise ValueError(f"{self.side.value} {self.barrier} can never win or never lose")

    @property
    def win_probability(self) -> float:
        """Chance of winning if digits are uniform and independent."""
        if self.side is Side.OVER:
            return (9 - self.barrier) / 10
        return self.barrier / 10

    @property
    def profit_ratio(self) -> float:
        """Profit per unit staked on a win — the "+90.0%" the page shows, as 0.90."""
        return RETURN_FACTOR / self.win_probability - 1

    def wins(self, digit: int) -> bool:
        if self.side is Side.OVER:
            return digit > self.barrier
        return digit < self.barrier

    def settle(self, stake: float, digit: int) -> float:
        """Net P/L of this contract for ``stake`` when the settling tick shows ``digit``."""
        return stake * self.profit_ratio if self.wins(digit) else -stake

    def __str__(self) -> str:
        return f"{self.side.value} {self.barrier}"
