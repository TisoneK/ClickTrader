import pytest

from clicktrader.model import Tick
from clicktrader.recording import Recorder, TickRecord, read_recording, read_ticks


def test_round_trip(tmp_path):
    path = tmp_path / "rec.jsonl"
    rec = TickRecord(Tick(1.5, "100.20", "R_100"), histogram={"0": 10.2}, payouts={"over 4": 0.9},
                     account={"balance": 10000})
    with Recorder(path) as r:
        r.write(rec)
        r.write(TickRecord(Tick(2.5, "100.27")))
    back = list(read_recording(path))
    assert back[0] == rec
    assert [t.digit for t in read_ticks(path)] == [0, 7]


def test_appends_across_sessions(tmp_path):
    path = tmp_path / "rec.jsonl"
    for i in range(3):
        with Recorder(path, fsync=False) as r:
            r.write(TickRecord(Tick(i, f"1.0{i}")))
    assert len(read_ticks(path)) == 3


def test_crash_loses_only_the_torn_last_line(tmp_path):
    path = tmp_path / "rec.jsonl"
    with Recorder(path, fsync=False) as r:
        r.write(TickRecord(Tick(1, "1.01")))
        r.write(TickRecord(Tick(2, "1.02")))
    with path.open("a") as f:
        f.write('{"ts":3,"price":"1.')
    assert [t.price for t in read_ticks(path)] == ["1.01", "1.02"]


def test_corruption_mid_file_raises(tmp_path):
    path = tmp_path / "rec.jsonl"
    path.write_text('{"ts":1,"price":"1.01"}\nnot json\n{"ts":2,"price":"1.02"}\n')
    with pytest.raises(ValueError, match=":2:"):
        read_ticks(path)


def test_stored_digit_must_agree_with_price(tmp_path):
    path = tmp_path / "rec.jsonl"
    path.write_text('{"ts":1,"price":"1.01","digit":7}\n{"ts":2,"price":"1.02"}\n')
    with pytest.raises(ValueError):
        read_ticks(path)
