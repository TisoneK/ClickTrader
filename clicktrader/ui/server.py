"""The one page. A background watcher reads the live feed with the same engine the live run uses (paper, never placing),
keeps the latest reading, and serves it two ways from the same state:

- `/`            the page a person looks at: the trader's chart, what the engine is waiting for in plain words, the
                 balance, the trades so far and how far they are from being evidence
- `/api/state`   the same facts as JSON, plus the engine's own wording and the last events, for whoever is looking at
                 the back end (curl it, or read it next to a screenshot of the page)
- `/api/chart`   the chart's data (candles, zones, levels, orders) the page draws in the browser
- `/chart.png`   the same chart as a picture

Bound to 127.0.0.1 only. It never holds or shows credentials; the balance is a read-only lookup on the demo account.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..forex.model import Direction
from ..multipliers import tidy
from ..smc.readiness import load
from ..smc.trader_view import draw_trader_view, trader_view
from ..smc.trader_view import sentences as trader_sentences
from ..strategies import History

TRADE_LOGS = ("recordings/smc-demo-trades.jsonl", "recordings/smc-paper-trades.jsonl")


class Watcher:
    """What a page needs from a running engine: the latest reading as state, and the engine's own words as events.

    It never drives the engine. Either something else feeds it (`observe(price)` after every tick of a live run, which
    is how `run-smc --ui` works) or `follow(ticks)` feeds the strategy itself (the stand-alone `ui` command). The picture
    is drawn only when a page asks for it, so keeping the state costs the trading loop almost nothing."""

    def __init__(self, strategy, *, symbol: str, chart_path: str, mode: str = "watching", decimals: int | None = None, now=time.time) -> None:
        self.strategy, self.symbol, self.chart_path, self.mode, self.decimals, self.now = strategy, symbol, chart_path, mode, decimals, now
        self.lock = threading.Lock()
        self.state: dict = {"symbol": symbol, "mode": mode, "status": "starting - reading the chart", "updated": None, "price": None}
        self.events: deque = deque(maxlen=40)
        self._seen = None  # the reading the state was last built from
        self._last_view = None
        self.error: str | None = None
        self.balance = None

    def note(self, text: str) -> None:
        self.events.appendleft({"t": time.strftime("%H:%M:%S", time.localtime(self.now())), "text": text})

    def _build(self, reading, price) -> dict:
        sentences = trader_sentences(reading, decimals=self.decimals)
        view = trader_view(reading)
        lo, cs = view["lo"], view["candles"]
        long = lambda o: o.direction is Direction.UP  # noqa: E731
        prices = [c.low for c in cs] + [c.high for c in cs] + [z.low for z in view["zones"]] + [z.high for z in view["zones"]]
        for o in view["orders"]:
            prices += [o.stop, o.target, o.entry]
        pad = (max(prices) - min(prices)) * 0.05
        return {
            "trend": sentences[0], "waiting": sentences[1], "why": sentences[2], "bars_read": len(reading.candles),
            "orders": [{"side": "buy" if long(o) else "sell", "zone": [min(o.block.price_low, o.block.price_high), max(o.block.price_low, o.block.price_high)],
                        "entry": o.entry, "stop": o.stop, "target": o.target, "reward_to_risk": round(o.reward_risk, 2), "source": o.source,
                        "armed_at_bar": o.armed_at} for o in view["orders"]],
            "chart": {
                "candles": [[c.opened_at, c.open, c.high, c.low, c.close] for c in cs],
                "range": [min(prices) - pad, max(prices) + pad],
                "zones": [{"kind": z.kind, "low": z.low, "high": z.high, "start": max(0, z.origin_index - lo)} for z in view["zones"]],
                "levels": [{"low": b.low, "high": b.high, "touches": b.touches, "start": max(0, b.first_index - lo)} for b, _ in view["levels"]],
                "orders": [{"side": "buy" if long(o) else "sell", "entry": o.entry, "stop": o.stop, "target": o.target,
                            "rr": round(o.reward_risk, 1), "start": max(0, o.armed_at - lo)} for o in view["orders"]],
            },
        }

    def observe(self, price: float) -> None:
        """Call after each tick has been given to the strategy: record the price, and rebuild the state if a bar has closed."""
        try:
            reading = getattr(self.strategy, "reading", None)
            if reading is not None and reading is not self._seen:
                self._seen = reading
                built = self._build(reading, price)
                with self.lock:
                    self.state.update(built)
            view = tidy(self.strategy.last_view or "")
            key = view.split(" now.")[0].split(", ")[0][:80]
            if view and key != self._last_view:
                self._last_view = key
                self.note(view)
            with self.lock:
                self.state.update(price=price, updated=self.now(), mode=self.mode,
                                  status=("watching" if self.state.get("trend") else "reading the first bars - not enough of a chart yet"))
        except Exception as exc:  # a page problem must never reach the trading loop
            self.error = f"{type(exc).__name__}: {exc}"
            self.note(f"the page could not read the engine: {self.error}")

    def stopped(self, why: str) -> None:
        self.error = why
        self.note(f"the live feed stopped: {why}")
        with self.lock:
            self.state.update(status=f"STOPPED - {why}")

    def follow(self, ticks) -> None:
        """Stand-alone: feed the strategy from `ticks` and observe it, until the feed ends or fails."""
        history: list = []
        try:
            self.observe(float(self.strategy._trigger.last(1)[-1].close) if self.strategy._trigger.last(1) else 0.0)
            for record in ticks:
                history.append(record.tick)
                self.strategy.decide(History(history, len(history)))
                self.observe(float(record.tick.price))
        except Exception as exc:
            self.stopped(f"{type(exc).__name__}: {exc}")

    def png(self) -> bytes | None:
        """The chart as a picture, drawn now from the latest reading."""
        reading = self._seen
        if reading is None:
            return None
        draw_trader_view(reading, self.chart_path, decimals=self.decimals)
        with open(self.chart_path, "rb") as handle:
            return handle.read()

    def snapshot(self) -> dict:
        with self.lock:
            state = dict(self.state)
        state["events"] = list(self.events)
        state["trades"] = recent_trades()
        state["evidence"] = evidence()
        state["balance"] = self.balance
        return state


def evidence(need: int = 500) -> dict:
    """Counts for the progress meter: settled trades on the demo account and on paper, and how many are needed."""
    from ..smc.readiness import summarise

    out = {"need": need}
    for key, path in (("demo", TRADE_LOGS[0]), ("paper", TRADE_LOGS[1])):
        e = summarise(load([path])) if os.path.exists(path) else summarise([])
        out[key] = {"n": e.n, "wins": e.wins, "net": round(e.net, 2)}
    return out


def recent_trades(limit: int = 15) -> list[dict]:
    rows = []
    for path in TRADE_LOGS:
        if os.path.exists(path):
            for r in load([path]):
                rows.append({"when": r.get("ts"), "mode": r.get("mode", "demo"), "side": "buy" if r.get("direction") == "up" else "sell",
                             "entry": r.get("entry"), "stop": r.get("stop"), "target": r.get("target"), "profit": r.get("profit")})
    rows.sort(key=lambda r: r["when"] or 0, reverse=True)
    return rows[:limit]


def balance_loop(watcher: Watcher, symbol: str, every: float = 60.0) -> None:
    """Read-only: the demo account's balance, now and every minute. A failure just means 'unavailable'."""
    try:
        from ..multipliers import DerivMultiplierBroker

        broker = DerivMultiplierBroker(symbol=symbol, stake=1, multiplier=100)
    except Exception as exc:  # no credentials, or no connection: the page shows nothing rather than a guess
        watcher.balance = {"error": f"{type(exc).__name__}"}
        return
    while True:
        try:
            amount, currency = broker.balance()
            watcher.balance = {"amount": amount, "currency": currency, "at": time.strftime("%H:%M:%S")}
        except Exception as exc:
            watcher.balance = {"error": type(exc).__name__}
        time.sleep(every)


PAGE = open(os.path.join(os.path.dirname(__file__), "page.html"), encoding="utf-8").read()


def make_handler(watcher: Watcher):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, json.dumps(watcher.snapshot(), default=str).encode(), "application/json")
            elif path == "/api/chart":
                self._send(200, json.dumps(watcher.snapshot().get("chart"), default=str).encode(), "application/json")
            elif path == "/chart.png" and (png := watcher.png()) is not None:
                self._send(200, png, "image/png")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args) -> None:  # the terminal is for the engine's own words
            pass

    return Handler


def serve(watcher: Watcher, *, port: int = 8765) -> ThreadingHTTPServer:
    """Bind to this machine only and return the server (the caller runs `serve_forever`)."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(watcher))
