"""Paper mode, warm-up and the readiness gate. All on fake feeds: nothing here touches the network or an account."""

import json

import pytest

from clicktrader.forex.model import Direction, TradePlan
from clicktrader.forex.trade_strategies import TradeDecision
from clicktrader.model import Tick
from clicktrader.recording import TickRecord
from clicktrader.smc.live import paper_run
from clicktrader.smc.readiness import MIN_TRADES, report, summarise
from clicktrader.smc.strategy import SmcStrategy


class OneLong:
    """Offers a single long plan on the first tick, then nothing."""

    name = "one-long"

    def __init__(self, stop=99.0, target=102.0, direction=Direction.UP):
        self._plan, self._fired = TradePlan(direction, stop=stop, target=target), False

    def decide(self, history):
        if self._fired:
            return None
        self._fired = True
        return TradeDecision(self._plan, 1.0, "test plan")


def _ticks(*prices):
    return iter([TickRecord(tick=Tick(float(i), f"{p:.5f}", "R_100")) for i, p in enumerate(prices)])


def _run(tmp_path, strategy, prices, **kw):
    said = []
    result = paper_run(symbol="R_100", log_path=str(tmp_path / "p.jsonl"), stake=1.0, multiplier=100, strategy=strategy,
                       ticks=_ticks(*prices), emit=said.append, report_every=0, **kw)
    return result, said, [json.loads(line) for line in (tmp_path / "p.jsonl").read_text().splitlines()]


def test_a_paper_trade_that_reaches_its_target_is_a_logged_win_and_places_nothing(tmp_path):
    result, said, rows = _run(tmp_path, OneLong(), [100.0, 100.5, 101.0, 102.0])
    assert (result.placed, result.won) == (1, 1) and result.net == pytest.approx(2.0)  # 2% of 100 exposure
    assert rows[0]["mode"] == "paper" and rows[0]["contract_id"].startswith("paper-")
    assert any("PAPER plan taken (nothing placed)" in line for line in said)


def test_a_paper_trade_stopped_out_loses_the_move_to_the_stop(tmp_path):
    result, _said, rows = _run(tmp_path, OneLong(), [100.0, 99.5, 99.0])
    assert (result.placed, result.won) == (1, 0) and result.net == pytest.approx(-1.0)
    assert rows[0]["profit"] == pytest.approx(-1.0)


def test_a_loss_is_capped_at_the_stake_like_a_multipliers_stop_out(tmp_path):
    result, _s, rows = _run(tmp_path, OneLong(stop=90.0, target=110.0), [100.0, 89.0])
    assert rows[0]["profit"] == pytest.approx(-1.0)  # a 10% move on 100 exposure would be -10; the stake is all that can be lost


def test_a_short_wins_when_price_falls_to_its_target(tmp_path):
    result, _s, rows = _run(tmp_path, OneLong(stop=101.0, target=98.0, direction=Direction.DOWN), [100.0, 99.0, 98.0])
    assert result.net == pytest.approx(2.0) and rows[0]["direction"] == "down"


def test_a_plan_whose_stop_risks_more_than_allowed_is_refused_in_paper_too(tmp_path):
    result, said, rows = _run(tmp_path, OneLong(stop=95.0, target=110.0), [100.0, 101.0], max_loss_per_trade=2.0)
    assert result.placed == 0 and result.refused == 1 and rows == []
    assert any("over the 2.00 limit" in line for line in said)


def test_the_trade_cap_stops_the_run(tmp_path):
    result, said, _r = _run(tmp_path, OneLong(), [100.0, 102.0, 103.0, 104.0], max_trades=1)
    assert result.placed == 1 and any("cap of 1 paper trades" in line for line in said)


def test_warm_up_feeds_bars_without_reading_the_chart_or_arming_anything():
    strategy = SmcStrategy(trigger_minutes=1.0, higher_minutes=(5.0, 15.0))
    ticks = [Tick(float(i * 15), f"{100 + (i % 7) * 0.1:.2f}", "R_100") for i in range(400)]
    assert strategy.warm(ticks) == 400 and strategy._armed is None
    assert "warmed with 400" in strategy.last_view
    assert len(strategy._higher) == 2  # the chain of slower clocks is fed too


def _row(profit, mode=None, stop=99.0):
    row = {"entry": 100.0, "stop": stop, "stake": 1.0, "multiplier": 100, "profit": profit}
    if mode:
        row["mode"] = mode
    return row


def test_readiness_counts_paper_and_placed_separately_and_needs_placed_trades(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(_row(1.0 if i % 2 else -1.0, mode="paper")) for i in range(600)) + "\n")
    ready, text = report([str(path)])
    assert not ready and "paper (no orders, no costs)" in text and "NOT READY" in text
    assert "do not count" in text  # 600 paper trades still do not make the demo evidence


def test_readiness_is_ready_only_when_enough_placed_trades_have_an_interval_above_zero(tmp_path):
    good = tmp_path / "good.jsonl"
    # a stop 1% away on 100 exposure risks 1.00; +1.2 twice as often as -1.0 is clearly positive
    rows = [_row(1.2 if i % 3 else -1.0) for i in range(MIN_TRADES)]
    good.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ready, text = report([str(good)])
    assert ready and "READY on demo evidence" in text and "no real-money path" in text
    flat = tmp_path / "flat.jsonl"
    flat.write_text("\n".join(json.dumps(_row(1.0 if i % 2 else -1.0)) for i in range(MIN_TRADES)) + "\n")
    ready, text = report([str(flat)])
    assert not ready and "includes zero" in text


def test_a_small_clearly_positive_sample_is_still_not_ready(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(_row(1.2)) for i in range(20)) + "\n")
    ready, text = report([str(path)])
    assert not ready and f"only 20 of the {MIN_TRADES}" in text
    ready, text = report([str(path)], min_trades=10)  # the count is a parameter, not a fixed cap
    assert ready


def test_summary_expresses_results_in_units_of_risk_so_stakes_and_multipliers_compare():
    big = {"entry": 100.0, "stop": 99.0, "stake": 10.0, "multiplier": 100, "profit": 20.0}  # risks 10.00, won 2R
    small = {"entry": 100.0, "stop": 99.0, "stake": 1.0, "multiplier": 100, "profit": 2.0}  # risks 1.00, won 2R
    assert summarise([big, small]).mean_r == pytest.approx(2.0)


def test_run_smc_has_no_default_caps_so_it_trades_what_it_finds_until_stopped(monkeypatch):
    from clicktrader import cli

    seen = {}
    monkeypatch.setattr(cli, "cmd_run_smc", lambda args: seen.setdefault("args", args) and 0)
    cli.main(["run-smc"])
    args = seen["args"]
    assert args.max_trades is None and args.max_seconds is None and args.max_loss_per_trade is None
    assert args.place is False  # and it is still paper unless --place is given


def test_a_live_loop_says_it_is_connected_and_shows_the_price_in_its_status(tmp_path):
    said = []
    clock = iter(range(0, 10_000, 100))  # each call to now() jumps 100s, so every tick is a status interval
    paper_run(symbol="R_100", log_path=str(tmp_path / "p.jsonl"), stake=1.0, multiplier=100, strategy=OneLong(),
              ticks=_ticks(100.0, 100.1, 100.2), emit=said.append, report_every=60, now=lambda: next(clock))
    assert said[0].startswith("connecting to the live feed")
    assert any(line.startswith("live feed connected: first tick 100.0") for line in said)
    assert any("price 100." in line and "no trades yet" in line for line in said)  # a status line carries the current price
