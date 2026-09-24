"""Low-level connection plumbing shared by every Deriv call — market data today, trading (layer 3)
later. Nothing platform-specific about *what* is asked over the socket lives here, only *how to open
and identify one*.
"""

from __future__ import annotations

try:
    import websocket
except ImportError as exc:  # pragma: no cover - exercised only when the extra isn't installed
    raise ImportError("the 'deriv' extra is required: pip install -e '.[deriv]'") from exc

DEFAULT_APP_ID = 1089
"""Deriv's shared public "test" app_id, documented for exactly this kind of unauthenticated use.
A registered app_id (from developers.deriv.com) works identically here and is preferred for anything
longer-lived, since the shared one is rate-limited across everyone using it."""

WS_URL_TEMPLATE = "wss://api.derivws.com/trading/v1/options/ws/public?app_id={app_id}"
"""`ws.derivws.com/websockets/v3` (the URL Deriv's own developer docs and every third-party tutorial
still cite) is retired -- it returns a Cloudflare 520 from every network path we tested (US and Kenya
alike, ruling out geo-blocking), while this gateway responds with real tick data using the identical
JSON-RPC message shape. Confirmed live 2026-09-24 via a direct `ticks`/`subscribe` request. Worth
rechecking `developers.deriv.com/docs` occasionally in case they publish the migration officially."""


class DerivAPIError(Exception):
    """The API responded with an `error` object — a bad symbol, a bad app_id, a rate limit, etc."""


def connect(app_id: int = DEFAULT_APP_ID, *, timeout: float = 10.0) -> websocket.WebSocket:
    return websocket.create_connection(WS_URL_TEMPLATE.format(app_id=app_id), timeout=timeout)
