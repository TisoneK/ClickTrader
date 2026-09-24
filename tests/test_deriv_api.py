import json

import pytest
import websocket

from clicktrader.api import deriv

SAMPLE_TICK = {"ask": 9531.23, "bid": 9530.73, "epoch": 1592642556, "id": "abc", "pip_size": 2, "quote": 9530.98, "symbol": "1HZ10V"}


def test_tick_record_from_message_keeps_trailing_zero():
    record = deriv.tick_record_from_message({**SAMPLE_TICK, "quote": 9530.9, "pip_size": 2})
    assert record.tick.price == "9530.90"
    assert record.tick.digit == 0
    assert record.tick.symbol == "1HZ10V"
    assert record.tick.ts == 1592642556.0


def test_tick_record_from_message_respects_pip_size():
    record = deriv.tick_record_from_message({**SAMPLE_TICK, "quote": 9530.987, "pip_size": 3})
    assert record.tick.price == "9530.987"


class FakeWS:
    def __init__(self, messages: list[dict]) -> None:
        self._messages = iter(messages)
        self.sent: list[str] = []

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str:
        return json.dumps(next(self._messages))

    def close(self) -> None:
        pass


def test_iter_ticks_sends_a_subscribe_request_and_yields_records():
    ws = FakeWS([{"msg_type": "tick", "tick": SAMPLE_TICK}, {"msg_type": "tick", "tick": {**SAMPLE_TICK, "quote": 9531.0}}])
    records = []
    it = deriv.iter_ticks(ws, "1HZ10V")
    records.append(next(it))
    records.append(next(it))
    assert json.loads(ws.sent[0]) == {"ticks": "1HZ10V", "subscribe": 1}
    assert [r.tick.price for r in records] == ["9530.98", "9531.00"]


def test_iter_ticks_raises_on_api_error():
    ws = FakeWS([{"error": {"code": "InvalidSymbol", "message": "Symbol not found"}}])
    with pytest.raises(deriv.DerivAPIError, match="Symbol not found"):
        next(deriv.iter_ticks(ws, "not-a-symbol"))


def test_iter_ticks_skips_irrelevant_messages():
    ws = FakeWS([{"msg_type": "ping"}, {"msg_type": "tick", "tick": SAMPLE_TICK}])
    record = next(deriv.iter_ticks(ws, "1HZ10V"))
    assert record.tick.price == "9530.98"


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(deriv.ticks.time, "sleep", lambda _seconds: None)


def test_stream_ticks_reconnects_on_a_dropped_connection(monkeypatch):
    connections = [
        FakeWS([websocket.WebSocketConnectionClosedException("dropped")]),
        FakeWS([{"msg_type": "tick", "tick": SAMPLE_TICK}]),
    ]

    def fake_recv(self):
        item = next(self._messages)
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)

    monkeypatch.setattr(FakeWS, "recv", fake_recv)
    monkeypatch.setattr(deriv.ticks, "connect", lambda app_id=deriv.DEFAULT_APP_ID: connections.pop(0))

    record = next(deriv.stream_ticks("1HZ10V", retries=3))
    assert record.tick.price == "9530.98"


def test_stream_ticks_does_not_retry_api_errors(monkeypatch):
    ws = FakeWS([{"error": {"code": "InvalidAppID", "message": "bad app_id"}}])
    monkeypatch.setattr(deriv.ticks, "connect", lambda app_id=deriv.DEFAULT_APP_ID: ws)
    with pytest.raises(deriv.DerivAPIError):
        next(deriv.stream_ticks("1HZ10V", retries=3))


def test_stream_ticks_gives_up_after_retries(monkeypatch):
    def always_broken(app_id=deriv.DEFAULT_APP_ID):
        ws = FakeWS([websocket.WebSocketConnectionClosedException("dropped")])

        def raising_recv(self):
            raise next(self._messages)

        ws.recv = raising_recv.__get__(ws)
        return ws

    monkeypatch.setattr(deriv.ticks, "connect", always_broken)
    with pytest.raises(websocket.WebSocketException):
        next(deriv.stream_ticks("1HZ10V", retries=2))
