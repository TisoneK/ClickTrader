import pytest

import clicktrader.api.deriv as deriv_api
from clicktrader.cli import main

_RUN_DERIV_LIMITS = ["--max-stake", "1", "--max-session-loss", "5", "--max-consecutive-losses", "5"]


@pytest.fixture(autouse=True)
def _clear_deriv_env(monkeypatch):
    """Isolate these tests from whatever the real shell has sourced from .env — a developer running
    the suite after `source .env` shouldn't get a different (or worse, network-attempting) result."""
    for name in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID", "DERIV_REAL_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)


def test_run_deriv_defaults_to_demo_and_reports_the_demo_var_missing(capsys):
    assert main(["run-deriv", *_RUN_DERIV_LIMITS]) == 2
    out = capsys.readouterr().out
    assert "DERIV_DEMO_ACCOUNT_ID" in out
    assert "DERIV_REAL_ACCOUNT_ID" not in out  # demo path never even looks for the real var


def test_run_deriv_real_account_needs_its_own_separate_id(monkeypatch, capsys):
    # even with a demo ID present, --account real must not fall back to it
    monkeypatch.setenv("DERIV_DEMO_ACCOUNT_ID", "DOT00000000")
    assert main(["run-deriv", "--account", "real", *_RUN_DERIV_LIMITS]) == 2
    out = capsys.readouterr().out
    assert "DERIV_REAL_ACCOUNT_ID" in out
    assert "never silently reuses the demo account" in out


def test_record_deriv_reports_a_clean_message_on_a_deriv_api_error(tmp_path, monkeypatch, capsys):
    # e.g. the forex market being closed for the weekend -- a real, expected condition, not a bug,
    # and previously recorded ticks (however few) must survive it rather than being lost to a traceback.
    from clicktrader.recording import TickRecord
    from clicktrader.model import Tick

    def fake_stream_ticks(symbol, *, app_id):
        yield TickRecord(tick=Tick(ts=1.0, price="1.10000", symbol=symbol))
        yield TickRecord(tick=Tick(ts=2.0, price="1.10001", symbol=symbol))
        raise deriv_api.DerivAPIError("This market is presently closed. Market will open at 2026-09-28 00:00:00.")

    monkeypatch.setattr(deriv_api, "stream_ticks", fake_stream_ticks)
    out_path = tmp_path / "eurusd.jsonl"
    assert main(["record-deriv", str(out_path), "--symbol", "frxEURUSD"]) == 2
    out = capsys.readouterr().out
    assert "Deriv API error: This market is presently closed" in out
    assert "wrote 2 ticks" in out
    assert out_path.exists()
    assert len(out_path.read_text().splitlines()) == 2


def test_run_deriv_reports_a_clean_message_when_the_otp_request_fails(monkeypatch, capsys):
    monkeypatch.setenv("DERIV_API_TOKEN", "fake-token")
    monkeypatch.setenv("DERIV_APP_ID", "1")
    monkeypatch.setenv("DERIV_DEMO_ACCOUNT_ID", "VRTC0000000")

    def fake_get_otp_url(account_id, token, app_id, *, require_demo=True):
        raise deriv_api.DerivAPIError("401: invalid token")

    monkeypatch.setattr(deriv_api, "get_otp_url", fake_get_otp_url)
    assert main(["run-deriv", *_RUN_DERIV_LIMITS]) == 2
    out = capsys.readouterr().out
    assert "Deriv API error: 401: invalid token" in out


def test_simulate_check_replay(tmp_path, capsys):
    rec = tmp_path / "synthetic.jsonl"
    assert main(["simulate", str(rec), "--ticks", "5000", "--seed", "4"]) == 0
    assert main(["check", str(rec)]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out and "digit uniformity" in out and "independence" in out
    assert main(["replay", str(rec), "--strategy", "streak-reversal", "--ledger", str(tmp_path / "l.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "out-of-sample" in out and "control" in out and "verdict" in out


def test_check_refuses_a_short_recording(tmp_path, capsys):
    rec = tmp_path / "short.jsonl"
    main(["simulate", str(rec), "--ticks", "300"])
    assert main(["check", str(rec)]) == 2
    assert "too small" in capsys.readouterr().out


def test_risk_replay(tmp_path, capsys):
    rec = tmp_path / "synthetic.jsonl"
    main(["simulate", str(rec), "--ticks", "20000", "--seed", "5"])
    capsys.readouterr()
    assert main([
        "risk-replay", str(rec),
        "--strategy", "martingale-low-digit-over",
        "--session-ticks", "500",
        "--max-stake", "10", "--max-session-loss", "10", "--max-consecutive-losses", "10",
    ]) == 0
    out = capsys.readouterr().out
    assert "guard intervened in" in out and "guarded" in out and "unbounded" in out
