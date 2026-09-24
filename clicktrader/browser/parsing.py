"""Text parsing for the CryptonicHub DOM.

Split out from the Playwright adapter on purpose: the site has no `data-testid` hooks (checked by hand,
2026-09-24 — it's a plain Tailwind build), so every read is "find text that looks like X". These
functions take the *already-extracted* strings and turn them into numbers; they know nothing about
Playwright and are exercised directly in tests, without a browser.
"""

from __future__ import annotations

import re

_PRICE_RE = re.compile(r"^\d+\.\d+$")
_PERCENT_RE = re.compile(r"^(-?\d+(?:\.\d+)?)%$")
_MONEY_RE = re.compile(r"^\$?\s*(-?\d+(?:\.\d+)?)\s*(?:USD)?$")
_SESSION_PL_RE = re.compile(r"Session P/L:\s*\$?(-?\d+(?:\.\d+)?)\s*USD?", re.IGNORECASE)
_TRADE_COUNT_RE = re.compile(r"(\d+)\s*T\s*[·/\-]\s*(\d+)\s*W\s*[·/\-]\s*(\d+)\s*L")


def is_price(text: str) -> bool:
    """True for a bare price like ``"9438.19"`` — used to pick the right element out of the page."""
    return bool(_PRICE_RE.match(text.strip()))


def parse_percent(text: str) -> float:
    """``"10.4%"`` -> ``0.104``."""
    match = _PERCENT_RE.match(text.strip())
    if not match:
        raise ValueError(f"not a percentage: {text!r}")
    return float(match.group(1)) / 100


def parse_money(text: str) -> float:
    """``"$ 0.00"`` or ``"2.38 USD"`` -> a float."""
    match = _MONEY_RE.match(text.strip())
    if not match:
        raise ValueError(f"not a money amount: {text!r}")
    return float(match.group(1))


def parse_session_pl(text: str) -> float:
    """``"Session P/L:-1.00 USD"`` -> ``-1.0``. Takes the whole line; finds the number itself."""
    match = _SESSION_PL_RE.search(text)
    if not match:
        raise ValueError(f"can't find Session P/L in: {text!r}")
    return float(match.group(1))


def parse_trade_count(text: str) -> tuple[int, int, int]:
    """``"1T · 0W / 1L"`` -> ``(1, 0, 1)`` (trades, wins, losses)."""
    match = _TRADE_COUNT_RE.search(text)
    if not match:
        raise ValueError(f"can't parse trade count from: {text!r}")
    trades, wins, losses = (int(g) for g in match.groups())
    return trades, wins, losses


def parse_payout_box(inner_text: str) -> dict[str, float]:
    """The "Over"/"Under" box: a label line, a money line, a percent line, in no fixed order.

    Returns ``{"amount": <money>, "profit_ratio": <fraction>}``. Raises if either is missing rather
    than guessing — a half-read payout is worse than a loud failure (DESIGN.md: honesty of the numbers
    above all).
    """
    amount: float | None = None
    percent: float | None = None
    for line in (raw.strip() for raw in inner_text.splitlines()):
        if not line:
            continue
        if "%" in line:
            try:
                percent = parse_percent(line)
            except ValueError:
                pass
        else:
            try:
                amount = parse_money(line)
            except ValueError:
                pass
    if amount is None or percent is None:
        raise ValueError(f"can't parse payout box: {inner_text!r}")
    return {"amount": amount, "profit_ratio": percent}
