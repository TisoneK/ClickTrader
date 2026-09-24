"""Adapter for CryptonicHub Trader (cryptonichub.pro) — a Deriv-style digit-contract UI.

The site has no `data-testid` hooks (a plain Tailwind React build, checked by hand 2026-09-24), so this
reads DOM *structure* instead of CSS classes: each histogram badge is a container whose whole text is
exactly one digit followed by its percentage, the trade panel is mounted twice (a compact and a full
layout, same underlying values — either copy is read), and the payout boxes are the buttons labelled
"Over"/"Under". All of that runs as one `page.evaluate()` call — one place to fix when the markup shifts,
not several Playwright locators each guessing at a class name that Tailwind will happily reuse elsewhere.

Read-only. Nothing here clicks anything — see DESIGN.md: the executor is a separate, later, gated layer.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..model import Tick
from ..recording import TickRecord
from . import parsing

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Runs in the page. Returns plain JSON-able values only — Playwright hands them back as a Python dict.
_SNAPSHOT_JS = """
() => {
  const allEls = Array.from(document.querySelectorAll('*'));
  const leaf = (pred) => allEls.filter(e => e.children.length === 0 && pred(e.textContent.trim()));

  const priceEl = leaf(t => /^\\d+\\.\\d+$/.test(t))[0];

  const seenDigits = {};
  for (const el of leaf(t => /^\\d{1,3}(?:\\.\\d+)?%$/.test(t))) {
    const pctText = el.textContent.trim();
    const parentText = el.parentElement.textContent.trim();
    const digitText = parentText.slice(0, parentText.length - pctText.length);
    if (/^\\d$/.test(digitText) && !(digitText in seenDigits)) {
      seenDigits[digitText] = pctText;
    }
  }

  const splEl = allEls.find(e => /^Session P\\/L:-?\\d+(?:\\.\\d+)?\\s*USD$/.test(e.textContent.trim()));
  const tcEl = allEls.find(e => /^\\d+T\\s*[·/-]\\s*\\d+W\\s*[·/-]\\s*\\d+L$/.test(e.textContent.trim()));

  let balanceRaw = null;
  for (const btn of Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim() === 'Deposit')) {
    let sib = btn.previousElementSibling;
    for (let i = 0; i < 3 && sib && !balanceRaw; i++, sib = sib.previousElementSibling) {
      const m = sib.textContent.trim().match(/\\$\\s?[\\d,]+\\.\\d{2}/);
      if (m) balanceRaw = m[0];
    }
    if (balanceRaw) break;
  }

  function payoutBox(label) {
    const labelEl = leaf(t => t === label)[0];
    if (!labelEl) return null;
    let node = labelEl;
    for (let i = 0; i < 4; i++) {
      node = node.parentElement;
      if (node && node.tagName === 'BUTTON') break;
    }
    return node ? node.textContent.trim() : null;
  }

  const instrEl = leaf(t => t.includes('Index'))[0];

  return {
    price: priceEl ? priceEl.textContent.trim() : null,
    instrument: instrEl ? instrEl.textContent.trim() : null,
    histogram: seenDigits,
    sessionPl: splEl ? splEl.textContent.trim() : null,
    tradeCount: tcEl ? tcEl.textContent.trim() : null,
    balanceRaw,
    overBox: payoutBox('Over'),
    underBox: payoutBox('Under'),
  };
}
"""


def read_snapshot(page: Page) -> dict[str, Any]:
    """Raw page state, barely touched — everything here is still a string. See `to_tick_record`."""
    return page.evaluate(_SNAPSHOT_JS)


def to_tick_record(snapshot: dict[str, Any], ts: float) -> TickRecord:
    """Turn a `read_snapshot` result into the `TickRecord` shape `recording.py` stores.

    Raises `ValueError` on anything missing or malformed rather than writing a half-populated record —
    a loud failure here is cheaper than a quietly wrong recording (DESIGN.md: honesty of the numbers
    above all).
    """
    if not snapshot.get("price"):
        raise ValueError(f"no price found on the page: {snapshot!r}")
    histogram = snapshot.get("histogram") or {}
    if len(histogram) != 10:
        raise ValueError(f"expected 10 histogram digits, found {len(histogram)}: {histogram!r}")
    histogram = {digit: parsing.parse_percent(pct) for digit, pct in histogram.items()}

    payouts: dict[str, float] = {}
    for label in ("overBox", "underBox"):
        box = snapshot.get(label)
        if box:
            payouts[label.removesuffix("Box")] = parsing.parse_payout_box(box)["profit_ratio"]

    account: dict[str, Any] = {}
    if snapshot.get("balanceRaw"):
        account["balance"] = parsing.parse_money(snapshot["balanceRaw"])
    if snapshot.get("sessionPl"):
        account["session_pl"] = parsing.parse_session_pl(snapshot["sessionPl"])
    if snapshot.get("tradeCount"):
        trades, wins, losses = parsing.parse_trade_count(snapshot["tradeCount"])
        account["trades"], account["wins"], account["losses"] = trades, wins, losses

    tick = Tick(ts=ts, price=snapshot["price"], symbol=snapshot.get("instrument") or "")
    return TickRecord(tick=tick, histogram=histogram, payouts=payouts or None, account=account or None)


class CryptonicHubAdapter:
    """Wraps a logged-in `Page` on cryptonichub.pro/trade. Read-only — see the module docstring."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def read_tick_record(self, ts: float | None = None) -> TickRecord:
        return to_tick_record(read_snapshot(self.page), ts if ts is not None else time.time())

    def wait_for_new_tick(
        self, last_price: str | None, *, poll_seconds: float = 0.2, timeout_seconds: float = 5.0
    ) -> TickRecord:
        """Block until the displayed price differs from `last_price`; return the new tick's record.

        The site ticks roughly once a second (DESIGN.md); polling every 200ms keeps this well under
        that without hammering `evaluate()` every frame. Returns the full snapshot already parsed, so
        the caller doesn't re-read the DOM a second time for the price it just found.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            snapshot = read_snapshot(self.page)
            price = snapshot.get("price")
            if price and price != last_price:
                return to_tick_record(snapshot, time.time())
            time.sleep(poll_seconds)
        raise TimeoutError(f"price didn't change from {last_price!r} within {timeout_seconds:.0f}s")
