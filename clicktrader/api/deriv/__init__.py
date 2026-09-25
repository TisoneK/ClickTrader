"""Adapter for Deriv's public WebSocket API (developers.deriv.com).

Unlike `clicktrader.browser.cryptonichub`, this needs no scraping and no login: `ticks`/`ticks_history`
are public, unauthenticated market data, served as documented JSON over a WebSocket, with just an
`app_id`. A Trade-scoped API token becomes necessary only for layer 3 (placing contracts); nothing here
uses one.

Split by concern:

- `connection.py` — opening and identifying a socket. Shared by every call this adapter makes.
- `ticks.py` — turning the `ticks` stream into `TickRecord`s. Everything layer 1 needs.
- `trading.py` — layer 3: the OTP handshake and one price-then-buy round trip. Gated behind `RiskGuard`
  and a demo account by the caller, not by anything enforced here except `get_otp_url`'s demo-only default.
"""

from .connection import DEFAULT_APP_ID, WS_URL_TEMPLATE, DerivAPIError, connect
from .ticks import iter_ticks, stream_ticks, tick_record_from_message
from .trading import BuyResult, DemoGateError, get_balance, get_otp_url, place_digit_contract

__all__ = [
    "DEFAULT_APP_ID",
    "WS_URL_TEMPLATE",
    "DerivAPIError",
    "connect",
    "iter_ticks",
    "stream_ticks",
    "tick_record_from_message",
    "BuyResult",
    "DemoGateError",
    "get_balance",
    "get_otp_url",
    "place_digit_contract",
]
