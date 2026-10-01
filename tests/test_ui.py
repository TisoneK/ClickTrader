"""The one page: a watcher fed ticks, a server that shows the same state as a page and as data."""

import json
import math
import threading
import urllib.request

from clicktrader.model import Tick
from clicktrader.recording import TickRecord
from clicktrader.smc.strategy import SmcStrategy
from clicktrader.ui.server import Watcher, serve


def _ticks(minutes=130):
    out = []
    for m in range(minutes):
        base = 100 + 8 * math.sin(m / 23.0) + 3 * math.sin(m / 7.0)
        for k, off in enumerate((0.0, 0.6, -0.5, 0.2)):  # four points a bar
            out.append(TickRecord(tick=Tick(m * 60.0 + k * 10, f"{base + off:.2f}", "R_100")))
    return out


def _running(tmp_path):
    strategy = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0,), stale_bars=60)
    watcher = Watcher(strategy, symbol="R_100", chart_path=str(tmp_path / "chart.png"), now=lambda: 1_790_000_000.0)
    watcher.follow(iter(_ticks()))  # finite feed: runs to the end on this thread
    server = serve(watcher, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return watcher, server


def test_the_page_and_the_data_show_the_same_state_and_only_on_this_machine(tmp_path):
    watcher, server = _running(tmp_path)
    try:
        host, port = server.server_address
        assert host == "127.0.0.1"  # never reachable from another machine
        base = f"http://127.0.0.1:{port}"
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "watch-only" in page.lower() or "Watch-only" in page and "/api/state" in page
        state = json.loads(urllib.request.urlopen(base + "/api/state").read())
        assert state["symbol"] == "R_100" and state["price"] is not None and state["chart"]["candles"]
        assert json.loads(urllib.request.urlopen(base + "/api/chart").read())["candles"] == state["chart"]["candles"]  # one fact, two doors
        assert state["waiting"] and state["trend"].startswith("PRICE")  # the same sentences the picture carries
        assert isinstance(state["events"], list) and isinstance(state["orders"], list)
        assert urllib.request.urlopen(base + "/chart.png").read()[:8] == b"\x89PNG\r\n\x1a\n"
        try:
            urllib.request.urlopen(base + "/nope")
            raise AssertionError("expected a 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown()


def test_a_dead_feed_is_said_on_the_page_not_hidden(tmp_path):
    def broken():
        yield from _ticks(50)
        raise ConnectionError("socket closed")

    strategy = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0,))
    watcher = Watcher(strategy, symbol="R_100", chart_path=str(tmp_path / "c.png"), now=lambda: 1.0)
    watcher.follow(broken())
    snap = watcher.snapshot()
    assert snap["status"].startswith("STOPPED") and "socket closed" in snap["status"]
    assert any("feed stopped" in e["text"] for e in snap["events"])


def test_attaching_the_page_to_a_running_engine_costs_it_nothing_and_never_changes_what_it_does(tmp_path):
    """`run-smc --ui` feeds the page with `observe` after each tick. The strategy must decide exactly as it does without."""
    from clicktrader.strategies import History

    plain = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0,), stale_bars=60)
    watched = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0,), stale_bars=60)
    page = Watcher(watched, symbol="R_100", chart_path=str(tmp_path / "c.png"), mode="paper run")
    a, b, ha, hb = [], [], [], []
    for record in _ticks():
        ha.append(record.tick)
        hb.append(record.tick)
        a.append(plain.decide(History(ha, len(ha))))
        b.append(watched.decide(History(hb, len(hb))))
        page.observe(float(record.tick.price))
    assert [x and x.plan for x in a] == [x and x.plan for x in b]
    assert page.snapshot()["mode"] == "paper run" and page.snapshot()["chart"]["candles"]


def test_the_run_has_an_argument_for_the_page(capsys):
    import pytest

    from clicktrader.cli import main

    with pytest.raises(SystemExit):
        main(["run-smc", "--help"])
    out = capsys.readouterr().out
    assert "--ui" in out and "--ui-port" in out and "--no-browser" in out  # off unless asked: a store_true flag


def test_a_busy_port_never_kills_the_run_it_takes_the_next_free_one(tmp_path, monkeypatch, capsys):
    import argparse
    import socket

    from clicktrader.cli import _start_page

    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    busy = blocker.getsockname()[1]
    monkeypatch.chdir(tmp_path)
    strategy = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0,))
    args = argparse.Namespace(ui_port=busy, no_balance=True, no_browser=True)
    watcher = _start_page(strategy, args, symbol="R_100", mode="paper run")  # must not raise
    out = capsys.readouterr().out
    blocker.close()
    assert watcher is not None and "was busy" in out
