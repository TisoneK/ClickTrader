from clicktrader.cli import main


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
