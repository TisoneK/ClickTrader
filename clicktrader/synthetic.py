"""A synthetic tick feed with uniform, independent digits — the platform's advertised behaviour.

For exercising the pipeline and calibrating the tests, never for conclusions about a real feed.
Every record it produces is marked ``extra={"synthetic": True}`` so it cannot be mistaken for one.
"""

from __future__ import annotations

import random
from typing import Iterator

from .model import Tick
from .recording import TickRecord


def synthetic_ticks(count: int, *, seed: int = 0, start_ts: float = 1_700_000_000.0,
                    symbol: str = "SYNTH", digit_weights: list[float] | None = None) -> Iterator[Tick]:
    """``count`` ticks one second apart. ``digit_weights`` (ten values) biases the last digit — used by
    the tests to check that the uniformity test can actually see a bias."""
    rng = random.Random(seed)
    price = 1000.0
    for i in range(count):
        price = max(1.0, price + rng.gauss(0, 0.5))
        digit = rng.choices(range(10), weights=digit_weights)[0] if digit_weights else rng.randrange(10)
        yield Tick(ts=start_ts + i, price=f"{price:.1f}{digit}", symbol=symbol)


def synthetic_records(count: int, *, seed: int = 0, **kwargs) -> Iterator[TickRecord]:
    for tick in synthetic_ticks(count, seed=seed, **kwargs):
        yield TickRecord(tick=tick, extra={"synthetic": True})
