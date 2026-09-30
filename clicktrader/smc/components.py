"""Pillar 1: the raw materials — order blocks, the zones they refine, and the gaps they leave.

The material names three components: supply and demand zones, order blocks, and inefficiencies (fair value
gaps). The code already measures all three — `forex/structure.py` has zones, gaps and displacement — so
this module's job is not to re-derive them but to name the SMC-level object the rest of the package needs:
an **order block** is not just a candle, it is the *refined origin* of a move, boxed wick to wick, with the
imbalance the move left recorded alongside it.

Keeping that as one object matters because every later decision asks about it together: where the entry
sits (at the block), where the stop sits (just beyond its wick, on the losing side), and whether the move
out of it left an unfilled gap — which is one of the three factors that qualify the zone at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..forex.candles import Candle
from ..forex.model import Direction
from ..forex.structure import FairValueGap, fair_value_gaps, gap_untouched


@dataclass(frozen=True)
class OrderBlock:
    """The single candle where institutional pressure originated, and the gap it left.

    Boxed wick to wick — the material's "order block refiner", which takes a wide macro zone and isolates
    the one candle responsible for the imbalance, on the stated grounds that it lets the stop sit tighter
    for the same idea.
    """

    price_low: float
    price_high: float
    index: int
    direction: Direction
    """The direction of the move the block produced — not the colour of the candle itself."""
    gap: FairValueGap | None = None

    @property
    def size(self) -> float:
        return self.price_high - self.price_low

    def contains(self, price: float) -> bool:
        return self.price_low <= price <= self.price_high

    @property
    def stop_level(self) -> float:
        """Where the material puts the stop: just beyond the wick, on the side that would prove it wrong.

        Below the low for a block that produced a rise; above the high for one that produced a fall. The
        entry goes *at* the block, so this is the whole risk of the trade.
        """
        return self.price_low if self.direction is Direction.UP else self.price_high


def order_block(candles: Sequence[Candle], *, index: int, gap_search: int = 3) -> OrderBlock:
    """The order block at `index`, paired with the first unfilled gap the move out of it left.

    `index` is the candle *before* the impulse — the last opposite-coloured one, which is what the material
    boxes. `direction` is therefore the direction of the move that followed it, decided by the next candle
    rather than by this one's colour, because a doji before a rally is still the rally's origin.

    `gap_search` is how many candles after the block to look for its imbalance; a displacement's gap is
    created by the three candles it spans, so a small window is enough and a large one would start
    attributing later gaps to this block.
    """
    if not 0 <= index < len(candles) - 1:
        raise ValueError("an order block needs a candle after it — otherwise nothing followed it")
    block = candles[index]
    direction = Direction.UP if candles[index + 1].close >= block.close else Direction.DOWN
    window = candles[: index + 1 + gap_search]
    for gap in fair_value_gaps(window, from_index=max(1, index)):
        if gap.formed_index <= index + gap_search and gap_untouched(gap, candles[:index + 1]):
            return OrderBlock(block.low, block.high, index, direction, gap)
    return OrderBlock(block.low, block.high, index, direction)
