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


def test_progress_line_includes_remaining_only_with_a_target():
    from clicktrader.cli import _progress_line

    assert _progress_line(1000, 500.0, None) == "1000 ticks  |  8m20s elapsed"
    assert _progress_line(1000, 500.0, 2000) == "1000 ticks  |  8m20s elapsed  |  ~8m20s left of 2000"


def test_record_deriv_prints_a_progress_line_at_the_interval(tmp_path, monkeypatch, capsys):
    # The progress clock is driven directly so the test neither sleeps nor patches the global time module.
    import clicktrader.cli as cli
    from clicktrader.model import Tick
    from clicktrader.recording import TickRecord

    def fake_stream_ticks(symbol, *, app_id):
        for i in range(5):
            yield TickRecord(tick=Tick(ts=float(i), price="1.10000", symbol=symbol))

    monkeypatch.setattr(deriv_api, "stream_ticks", fake_stream_ticks)
    times = [0.0, 1.0, 2.0, 61.0, 62.0, 63.0]
    state = {"i": 0}

    def fake_now():
        value = times[min(state["i"], len(times) - 1)]
        state["i"] += 1
        return value

    monkeypatch.setattr(cli, "_now", fake_now)
    out_path = tmp_path / "eurusd.jsonl"
    assert main(["record-deriv", str(out_path), "--symbol", "frxEURUSD", "--progress-every", "60"]) == 0
    out = capsys.readouterr().out
    assert "3 ticks  |  1m01s elapsed" in out  # a single line, at the 61s mark
    assert "wrote 5 ticks" in out


def test_record_deriv_progress_can_be_disabled(tmp_path, monkeypatch, capsys):
    import clicktrader.cli as cli
    from clicktrader.model import Tick
    from clicktrader.recording import TickRecord

    def fake_stream_ticks(symbol, *, app_id):
        yield TickRecord(tick=Tick(ts=1.0, price="1.10000", symbol=symbol))

    monkeypatch.setattr(deriv_api, "stream_ticks", fake_stream_ticks)
    monkeypatch.setattr(cli, "_now", lambda: 0.0)
    out_path = tmp_path / "eurusd.jsonl"
    assert main(["record-deriv", str(out_path), "--symbol", "frxEURUSD", "--progress-every", "0"]) == 0
    assert "elapsed" not in capsys.readouterr().out


def test_forex_replay_all_widens_the_interval_and_reports_the_batch(tmp_path, capsys):
    rec = tmp_path / "fx.jsonl"
    assert main(["forex-simulate", str(rec), "--ticks", "3000", "--seed", "7"]) == 0
    capsys.readouterr()
    assert main(["forex-replay-all", str(rec), "--strategies", "random-direction", "ma-crossover"]) == 0
    out = capsys.readouterr().out
    assert "testing 2 forex strategies together" in out
    assert "z=2.24" in out  # widened past the single-strategy 1.96 for two comparisons
    assert "family-wise alpha" in out
    assert "NO VERDICT" in out  # 3000 ticks is far under the report gate, as intended
    assert "all 2 strategies: 'no directional edge' or 'NO VERDICT'" in out


def test_forex_replay_all_flags_only_the_non_null_verdict(tmp_path, monkeypatch, capsys):
    # The batch summary is the only new logic that isn't shared with `forex-replay`, so drive it with
    # constructed results rather than waiting on a real recording to clear the 500-bet gate.
    import clicktrader.cli as cli
    from clicktrader.forex.harness import ForexReplayResult, ForexSegmentResult

    def seg(label, wins, bets=600):
        return ForexSegmentResult(label=label, ticks=bets, bets=bets, wins=wins)

    def fake_replay(strategy, ticks, *, split, z):
        # 400/600 clears the control's 0.500 outright; 300/600 straddles it.
        oos, ctl = (seg("out-of-sample", 400), seg("control", 300))
        if not strategy.name.startswith("ma-crossover"):
            oos = seg("out-of-sample", 300)
        return ForexReplayResult(strategy.name, seg("in-sample", 300), oos, ctl)

    monkeypatch.setattr(cli, "forex_replay", fake_replay)
    rec = tmp_path / "fx.jsonl"
    rec.write_text("")
    assert main(["forex-replay-all", str(rec), "--strategies", "random-direction", "ma-crossover"]) == 0
    out = capsys.readouterr().out
    assert "worth a second look" in out
    assert "ma-crossover" in out.split("worth a second look")[1]
    assert "random-direction" not in out.split("worth a second look")[1]


def test_forex_trade_replay_reports_the_mirror_control_and_refuses_a_thin_sample(tmp_path, capsys):
    # A driftless synthetic walk is the null, and it is also far too short to clear the trade gate, so
    # this pins the plumbing (segments, the mirror control, the paired statistic, the refusal) rather
    # than any claim about the strategy.
    rec = tmp_path / "fx.jsonl"
    assert main(["forex-simulate", str(rec), "--ticks", "20000", "--seed", "4"]) == 0
    capsys.readouterr()
    assert main(["forex-trade-replay", str(rec), "--session-start-hour", "0"]) == 0
    out = capsys.readouterr().out
    assert "strategy: sneaky-pivot" in out
    assert "[in-sample]" in out and "[out-of-sample]" in out
    assert "control: mirror of sneaky-pivot" in out
    assert "expectancy" in out and "paired edge over the mirror" in out
    assert "NO VERDICT" in out
    assert "verdict (out-of-sample only)" in out


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


def test_buy_rise_fall_refuses_to_exceed_its_own_stake_cap(capsys):
    # the guard that matters: one contract, on a demo account, and a cap it will not cross even if a
    # flag asks it to
    assert main(["buy-rise-fall", "--stake", "25", "--max-stake", "1"]) == 2
    out = capsys.readouterr().out
    assert "exceeds --max-stake" in out
    assert "refusing" in out


def test_buy_rise_fall_says_what_is_missing_before_touching_the_network(monkeypatch, capsys):
    for name in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert main(["buy-rise-fall"]) == 2
    out = capsys.readouterr().out
    assert "DERIV_API_TOKEN" in out and "Nothing placed" in out


def test_buy_rise_fall_never_reaches_for_the_real_account(monkeypatch, capsys):
    # a demo-only command: it reads the demo var and nothing else, so there is no path from it to real money
    import clicktrader.cli as cli
    source = __import__("inspect").getsource(cli.cmd_buy_rise_fall)
    assert "DERIV_REAL_ACCOUNT_ID" not in source
    assert "require_demo=True" in source


def test_smc_chart_writes_a_png(tmp_path):
    from clicktrader.cli import main
    from clicktrader.model import Tick
    from clicktrader.recording import Recorder, TickRecord

    rec, out = tmp_path / "t.jsonl", tmp_path / "chart.png"
    with Recorder(rec) as recorder:
        for i in range(4000):
            price = f"{1 + ((i * 7) % 97) / 1000:.5f}"
            recorder.write(TickRecord(Tick(ts=1_700_000_000.0 + i * 5, price=price, symbol="X")))
    assert main(["smc-chart", str(rec), str(out), "--minutes", "5", "--bars", "60"]) == 0
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
