"""Adapter for Deriv's public WebSocket API (developers.deriv.com).

Unlike `clicktrader.browser.cryptonichub`, this needs no scraping and no login: `ticks`/`ticks_history`
are public, unauthenticated market data, served as documented JSON over a WebSocket, with just an
`app_id`. No histogram or payout guessing either — the pricing table's inputs (win probability, the
0.95 constant) are already fixed in `model.py`, and the only thing a tick stream needs to supply is the
price itself. A trade-scoped API token becomes necessary only for layer 3 (placing contracts); nothing
here uses one.

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

try:
    import websocket
except ImportError as exc:  # pragma: no cover - exercised only when the extra isn't installed
    raise ImportError("the 'deriv' extra is required: pip install -e '.[deriv]'") from exc

from ..model import Tick
from ..recording import TickRecord

DEFAULT_APP_ID = 1089
"""Deriv's shared public "test" app_id, documented for exactly this kind of unauthenticated use.
A registered app_id (from developers.deriv.com) works identically here and is preferred for anything
longer-lived, since the shared one is rate-limited across everyone using it."""

WS_URL_TEMPLATE = "wss://ws.derivws.com/websockets/v3?app_id={app_id}"


class DerivAPIError(Exception):
    """The API responded with an `error` object — a bad symbol, a bad app_id, a rate limit, etc."""


def tick_record_from_message(tick: dict[str, Any]) -> TickRecord:
    """Turn one Deriv `tick` object into a `TickRecord`.

    `quote` arrives as a float; `pip_size` is how many decimal places that symbol displays. Formatting
    to exactly that many places matters the same way it did for CryptonicHub: `Tick.price` is kept as a
    *string* because a trailing zero (`"9520.20"`) is a real digit that `float()` would silently drop.
    """
    pip_size = tick["pip_size"]
    price = f"{tick['quote']:.{pip_size}f}"
    return TickRecord(tick=Tick(ts=float(tick["epoch"]), price=price, symbol=tick.get("symbol", "")))


def connect(app_id: int = DEFAULT_APP_ID, *, timeout: float = 10.0) -> websocket.WebSocket:
    return websocket.create_connection(WS_URL_TEMPLATE.format(app_id=app_id), timeout=timeout)


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
