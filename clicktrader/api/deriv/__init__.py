"""Adapter for Deriv's public WebSocket API (developers.deriv.com).

Unlike `clicktrader.browser.cryptonichub`, this needs no scraping and no login: `ticks`/`ticks_history`
are public, unauthenticated market data, served as documented JSON over a WebSocket, with just an
`app_id`. A Trade-scoped API token becomes necessary only for layer 3 (placing contracts); nothing here
uses one.

Split by concern rather than kept as one file, since this is expected to grow a second, genuinely
different piece (`trading.py`, once layer 3 exists) alongside the market-data reads here:

- `connection.py` — opening and identifying a socket. Shared by every call this adapter will ever make.
- `ticks.py` — turning the `ticks` stream into `TickRecord`s. Everything layer 1 needs.
"""

from .connection import DEFAULT_APP_ID, WS_URL_TEMPLATE, DerivAPIError, connect
from .ticks import iter_ticks, stream_ticks, tick_record_from_message

__all__ = [
    "DEFAULT_APP_ID",
    "WS_URL_TEMPLATE",
    "DerivAPIError",
    "connect",
    "iter_ticks",
    "stream_ticks",
    "tick_record_from_message",
]
