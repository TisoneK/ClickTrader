"""A synthetic forex-like price feed: a random walk, driftless by default.

For exercising the forex pipeline and calibrating its tests, never for conclusions about a real market.
Every record it produces is marked ``extra={"synthetic": True}``, the same convention the digit-contract
side's `clicktrader.synthetic` uses, so it can't be mistaken for a real recording.

No drift by default deliberately: driftless is the null hypothesis this project treats short-horizon
forex direction as obeying (see `forex/__init__.py`) — any "edge" a strategy finds against this data is
either noise or a real bug in the strategy or the harness, since the data has none by construction.
`drift` exists only so a test can build a positive control (an obviously trending series) to confirm the
harness can detect a real signal when one truly exists, not just correctly report "no edge" when there
isn't one.
"""

from __future__ import annotations

import random
from typing import Iterator

from ..model import Tick
from ..recording import TickRecord


def synthetic_price_ticks(
    count: int,
    *,
    seed: int = 0,
    start_ts: float = 1_700_000_000.0,
    symbol: str = "SYNTHFX",
    start_price: float = 1.10000,
    step_std: float = 0.00005,
    drift: float = 0.0,
    decimals: int = 5,
) -> Iterator[Tick]:
    """``count`` ticks one second apart, price += drift + gauss(0, step_std) each step."""
    rng = random.Random(seed)
    price = start_price
    for i in range(count):
        price += drift + rng.gauss(0, step_std)
        yield Tick(ts=start_ts + i, price=f"{price:.{decimals}f}", symbol=symbol)


def synthetic_price_records(count: int, *, seed: int = 0, **kwargs) -> Iterator[TickRecord]:
    for tick in synthetic_price_ticks(count, seed=seed, **kwargs):
        yield TickRecord(tick=tick, extra={"synthetic": True})
