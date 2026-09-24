"""Market-data reads: Deriv's `ticks` stream, turned into `TickRecord`s. Public and unauthenticated —
nothing here needs the Trade-scoped token layer 3 will eventually use.

Written against Deriv's documented message shapes, not verified against a live connection — their
WebSocket backend was returning Cloudflare 520s (every documented endpoint, confirmed from both a raw
client and a real browser on deriv.com's own origin — a Deriv-side issue, not a block on us) at the time
this was written. `tick_record_from_message` is unit-tested against the documented shape regardless;
`stream_ticks` itself needs a live smoke test once the API is reachable again.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

import websocket

from ...model import Tick
from ...recording import TickRecord
from .connection import DEFAULT_APP_ID, DerivAPIError, connect


def tick_record_from_message(tick: dict[str, Any]) -> TickRecord:
    """Turn one Deriv `tick` object into a `TickRecord`.

    `quote` arrives as a float; `pip_size` is how many decimal places that symbol displays. Formatting
    to exactly that many places matters the same way it did for CryptonicHub: `Tick.price` is kept as a
    *string* because a trailing zero (`"9520.20"`) is a real digit that `float()` would silently drop.
    """
    pip_size = tick["pip_size"]
    price = f"{tick['quote']:.{pip_size}f}"
    return TickRecord(tick=Tick(ts=float(tick["epoch"]), price=price, symbol=tick.get("symbol", "")))


def iter_ticks(ws: websocket.WebSocket, symbol: str) -> Iterator[TickRecord]:
    """Subscribe to `symbol` on an already-open connection and yield one `TickRecord` per tick.

    Deriv's first response to a `ticks` subscribe is already a tick (not a separate ack), so every
    message from here on is either a tick, an error, or something irrelevant (e.g. a keepalive) to skip.
    Runs until the socket closes or raises.
    """
    ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
    while True:
        message = json.loads(ws.recv())
        if "error" in message:
            raise DerivAPIError(message["error"].get("message", str(message["error"])))
        if "tick" in message:
            yield tick_record_from_message(message["tick"])


def stream_ticks(
    symbol: str,
    *,
    app_id: int = DEFAULT_APP_ID,
    retries: int = 5,
    backoff: float = 2.0,
) -> Iterator[TickRecord]:
    """`iter_ticks`, reconnecting through a dropped connection instead of dying on the first one.

    Only `websocket.WebSocketException` (a real connection problem) is treated as recoverable; a
    `DerivAPIError` (the API is up and told us something is wrong — a bad symbol, an invalid app_id) is
    not retried, since reconnecting won't fix a request that's wrong on its face.
    """
    attempt = 0
    while True:
        try:
            ws = connect(app_id=app_id)
            try:
                yield from iter_ticks(ws, symbol)
            finally:
                ws.close()
        except websocket.WebSocketException:
            attempt += 1
            if attempt >= retries:
                raise
            time.sleep(backoff)
