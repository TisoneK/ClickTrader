"""Fifteen-minute candles from Deriv's public API — the history a chart method needs to be judged on.

Layer 1 records ticks, and the tick recorders are what makes this project's numbers trustworthy. But a
chart method is written on *bars* and its verdict needs hundreds of resolved trades, which at one setup
a day is months of ticks nobody has recorded: every price-action claim in this repo has sat at
`NO VERDICT` for exactly that reason. `ticks_history` serves the bars themselves over the same public,
unauthenticated endpoint the recorder already uses, so the wait becomes a fetch.

Two properties of that endpoint shape everything here, both established by probing it rather than by
reading documentation:

- **It pages, but it rate-limits.** `count` plus an `end` epoch walks backwards through history; the
  server then refuses rapid repeats (`RateLimit` on `ticks_history`), so requests have to be paced.
- **A response is capped well below what was asked for.** Asking for 5,000 candles returned 577, which is
  why paging is a loop over batches rather than one large request.

**Candles are converted to four ticks each — open, high, low, close.** That is not a stylistic choice: the
wall-clock bar builder takes the first price as the open, the maximum as the high, the minimum as the low
and the last as the close, so four points per bar reproduce the bar exactly, which is what lets the whole
existing stack — bars, structure, the trade harness, the verdict — run on imported history without a
single change. The cost is honest and worth stating plainly: the path *inside* a bar is not recoverable
from a bar, so a bar wide enough to contain both a stop and a target is resolved by the order those four
points were written, which is a convention and not information. It matters less than it sounds for the
verdict, which reads the *paired* difference between a trade and its own mirror — both walk the same
invented path on the same bar — but the absolute expectancy numbers are softer than they would be on real
ticks, and anything read off them should say so.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Any

from ...model import Tick
from ...recording import TickRecord
from .connection import DEFAULT_APP_ID, DerivAPIError, connect

DEFAULT_GRANULARITY = 900
"""Fifteen minutes, in seconds — the interval the supply-and-demand material is drawn on."""


def fetch_candles(
    symbol: str,
    *,
    granularity: int = DEFAULT_GRANULARITY,
    count: int = 5000,
    end: str | int = "latest",
    app_id: int = DEFAULT_APP_ID,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """One batch of candles, newest last. `end` is `"latest"` or an epoch to page back from.

    Raises `DerivAPIError` on the broker's own error response, including the rate limit — the caller is
    the one that knows how to wait.
    """
    socket = connect(app_id, timeout=timeout)
    try:
        socket.send(
            json.dumps(
                {
                    "ticks_history": symbol,
                    "adjust_start_time": 1,
                    "count": count,
                    "end": end,
                    "granularity": granularity,
                    "style": "candles",
                }
            )
        )
        message = json.loads(socket.recv())
    finally:
        socket.close()
    if "error" in message:
        error = message["error"]
        raise DerivAPIError(f"{error.get('code')}: {error.get('message')}")
    return message.get("candles") or []


def candles_backwards(
    symbol: str,
    *,
    bars: int,
    granularity: int = DEFAULT_GRANULARITY,
    batch: int = 5000,
    pace: float = 6.0,
    rate_limit_retries: int = 3,
    request: Callable[..., list[dict[str, Any]]] = fetch_candles,
    sleep: Callable[[float], None] = time.sleep,
    on_batch: Callable[[int, int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Page back from the newest candle until `bars` are collected, returned oldest first.

    Backwards paging with the batches prepended, rather than a `start`/`end` window walked forwards,
    because the backwards form is the one verified against the live API — building on the request shape
    that was actually observed beats building on the shape the documentation implies.

    Stops early, without complaint, when the server returns a short batch: that means it has no more
    history to give, which is a fact about the instrument rather than an error. A rate limit is waited
    out and retried, up to `rate_limit_retries` times, because the endpoint refuses rapid repeats and
    that is the normal cost of asking for a lot of history.
    """
    if bars < 1:
        raise ValueError("bars must be at least 1")
    if batch < 1:
        raise ValueError("batch must be at least 1")
    collected: list[dict[str, Any]] = []
    end: str | int = "latest"
    retries = rate_limit_retries
    while len(collected) < bars:
        want = min(batch, bars - len(collected))
        try:
            rows = request(symbol, granularity=granularity, count=want, end=end)
        except DerivAPIError as exc:
            if "rate" in str(exc).lower() and retries > 0:
                retries -= 1
                sleep(max(pace * 3, 15.0))
                continue
            raise
        if not rows:
            break
        collected = rows + collected
        if on_batch is not None:
            on_batch(len(rows), len(collected), int(rows[0]["epoch"]))
        end = int(rows[0]["epoch"]) - 1
        if len(rows) < want:
            break  # the server had nothing older to give
        if len(collected) < bars:
            sleep(pace)
    return collected


def ticks_from_candles(
    candles: Sequence[dict[str, Any]], *, symbol: str, granularity: int = DEFAULT_GRANULARITY, decimals: int = 2
) -> list[TickRecord]:
    """Four ticks per candle — open, high, low, close — ascending in time.

    Marked `extra={"source": "deriv-history"}` so a file that is four points per bar is never mistaken for
    a recording of a real feed: the prices are real, the timestamps inside each bar are invented.
    """
    out: list[TickRecord] = []
    for candle in candles:
        epoch = int(candle["epoch"])
        if epoch % granularity:
            raise ValueError(
                f"candle epoch {epoch} is not aligned to a {granularity}s boundary, so its four points "
                "would straddle two bars and rebuild a bar that does not exist — refusing rather than "
                "importing a silently wrong one"
            )
        for offset, price in enumerate((candle["open"], candle["high"], candle["low"], candle["close"])):
            out.append(
                TickRecord(
                    tick=Tick(float(epoch + offset), f"{float(price):.{decimals}f}", symbol),
                    extra={"source": "deriv-history", "granularity": granularity},
                )
            )
    return out
