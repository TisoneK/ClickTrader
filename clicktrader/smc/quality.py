"""The three factors that make a zone valid — the material's own scorecard.

Its slide names them and then shows them: **inefficiency** (did the move leave unfilled orders behind),
**break of structure** (did it shatter previous market structure), and **pushed distance** (did price travel
a significant distance before returning). It draws the third with start and end arrows either side of the
rally out of a demand zone, captioned "great pushed distance" — a factor as equal as the other two, and one
nothing in this project has ever measured.

Pushed distance is expressed in **bands** rather than in price or in percent. That is the same decision the
level width already made: what counts as far is a question about the instrument's own volatility, so a
distance is only meaningful as a multiple of the typical candle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..forex.candles import Candle
from ..forex.model import Direction
from ..forex.structure import (
    broke_structure,
    fair_value_gaps,
    gap_untouched,
    last_swing,
    swing_points,
)
from .components import OrderBlock


def pushed_distance(candles: Sequence[Candle], *, block: OrderBlock, band: float) -> float:
    """How far price travelled away from the block before now, in bands.

    Measured from the block's own outer edge to the extreme reached since — the run-up the material marks
    with "start" and "end". `band` is the typical candle range, so the answer means the same thing on an
    index quoted at 945 and one quoted at 850,000.
    """
    if band <= 0:
        raise ValueError("band must be positive — a distance with no unit is not a distance")
    if block.direction is Direction.UP:
        return (max(c.high for c in candles[block.index :]) - block.price_high) / band
    return (block.price_low - min(c.low for c in candles[block.index :])) / band


@dataclass(frozen=True)
class ZoneQuality:
    """The scorecard: three questions, answered, with the reason written down either way."""

    inefficiency: bool
    structure_broken: bool
    pushed: float
    min_pushed: float

    @property
    def complete(self) -> bool:
        return self.inefficiency and self.structure_broken and self.pushed >= self.min_pushed

    @property
    def reason(self) -> str:
        parts = [
            f"inefficiency: {'yes' if self.inefficiency else 'NO — no unfilled gap out of the block'}",
            f"structure: {'yes' if self.structure_broken else 'NO — no break of structure'}",
            f"pushed distance: {self.pushed:.1f} bands (needs {self.min_pushed:.1f})",
        ]
        return "; ".join(parts)


def assess(
    candles: Sequence[Candle],
    *,
    block: OrderBlock,
    band: float,
    min_pushed: float = 3.0,
    strength: int = 2,
) -> ZoneQuality:
    """Run the material's three checks over a block.

    `min_pushed` is a reading, not a quote: the material shows the third factor and judges it by eye
    ("great pushed distance") without ever giving a number, so the threshold is a named parameter rather
    than a constant buried here. Three bands is the default — a move that travelled three typical candles
    away from its origin — and it is the single most likely thing to want changing after a measurement.
    """
    gaps = [g for g in fair_value_gaps(candles) if g.formed_index >= block.index]
    inefficiency = any(gap_untouched(g, candles[: block.index + 1]) for g in gaps) or block.gap is not None

    swings = swing_points(candles, strength=strength)
    prior = [s for s in swings if s.index < block.index]
    move = candles[block.index + 1 :]
    structure_broken = broke_structure(move, prior, direction=block.direction)
    # `last_swing` is called so the reason can name the level that was broken, if there was one
    _ = last_swing(prior, block.direction)
    return ZoneQuality(
        inefficiency=inefficiency,
        structure_broken=structure_broken,
        pushed=pushed_distance(candles, block=block, band=band),
        min_pushed=min_pushed,
    )
