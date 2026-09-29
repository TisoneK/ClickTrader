"""The trade log and its tally: what was *paid*, and whether that is enough to win.

The whole reason this module exists is that a live fill (88%) and the quote above it (95.35%) imply
break-evens two points apart, and two points is larger than the edge being looked for. So the tests care
about one thing above all: the tally uses the payout the broker paid, never a quoted one.
"""

import pytest

from clicktrader.trade_log import (
    MIN_TRADES_TO_READ,
    RiseFallTrade,
    TradeLog,
    read_trades,
    tally,
)


def _trade(**over):
    base = dict(
        settled_at=1_700_000_000.0, symbol="1HZ25V", direction="up", stake=1.0, buy_price=1.0,
        payout=1.88, status="won", profit=0.88, contract_id=1, duration=2, duration_unit="m",
        exit_spot="852816.86", currency="USD",
    )
    base.update(over)
    return RiseFallTrade(**base)


def test_a_row_survives_a_round_trip(tmp_path):
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        log.write(_trade())
        log.write(_trade(status="lost", profit=-1.0, contract_id=2))
    trades = list(read_trades(path))
    assert len(trades) == 2
    assert trades[0].payout == 1.88 and trades[1].status == "lost"
    assert trades[0].contract_id == 1


def test_a_truncated_final_line_costs_one_trade_not_the_log(tmp_path):
    path = tmp_path / "trades.jsonl"
    path.write_text(TradeLog and _trade().to_json() + "\n" + '{"settled_at": 1.0, "symbol": "1HZ2')
    assert len(list(read_trades(path))) == 1


def test_the_break_even_comes_from_the_payout_that_was_paid_not_a_quote():
    # 88% was a real fill; a 95.35% quote would have implied a bar two points lower
    assert _trade(payout=1.88).breakeven == pytest.approx(1 / 1.88)
    assert _trade(payout=1.9535).breakeven == pytest.approx(1 / 1.9535)


def test_the_tally_counts_trades_wins_and_the_money(tmp_path):
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        for i in range(6):
            log.write(_trade(contract_id=i, status="won" if i < 4 else "lost",
                             profit=0.88 if i < 4 else -1.0))
    t = tally(path)
    assert (t.trades, t.won, t.lost) == (6, 4, 2)
    assert t.net == pytest.approx(4 * 0.88 - 2 * 1.0)
    assert t.staked == pytest.approx(6.0)
    assert t.average_payout == pytest.approx(1.88)
    assert t.breakeven == pytest.approx(1 / 1.88)


def test_a_small_log_refuses_to_characterise_the_method(tmp_path):
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        for i in range(5):
            log.write(_trade(contract_id=i))
    said = tally(path).report()
    assert "too few to say" in said
    assert f"{MIN_TRADES_TO_READ} are needed" in said
    assert "breaking even needs" in said  # the bar is still reported, just not a verdict


def test_a_coin_flip_log_says_it_cannot_tell_yet(tmp_path):
    # 100 of 200 is 50%, which is below the 53.19% bar the fills imply -- but with 200 trades the honest
    # range runs from about 43% to about 57%, so it straddles and the tally must say exactly that rather
    # than picking a side
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        for i in range(200):
            won = i % 2 == 0
            log.write(_trade(contract_id=i, status="won" if won else "lost", profit=0.88 if won else -1.0))
    said = tally(path).report()
    assert "won 100 of 200 trades" in said
    assert "straddles" in said
    assert "still cannot say which side" in said


def test_a_log_that_clearly_wins_is_reported_as_winning(tmp_path):
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        for i in range(200):
            won = i % 4 != 0  # 75% winners
            log.write(_trade(contract_id=i, status="won" if won else "lost", profit=0.88 if won else -1.0))
    said = tally(path).report()
    assert "won 150 of 200 trades (75.0%)" in said
    assert "is above the" in said


def test_an_empty_log_says_so_rather_than_dividing_by_zero(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    assert "No settled trades" in tally(path).report()


def test_a_losing_log_is_reported_as_losing(tmp_path):
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        for i in range(200):
            won = i % 4 == 0  # 25% winners
            log.write(_trade(contract_id=i, status="won" if won else "lost", profit=0.88 if won else -1.0))
    assert "is below the" in tally(path).report()


def test_the_payout_is_averaged_over_every_trade_not_only_the_winners(tmp_path):
    # A log with no wins yet must still report the bar it has to clear. Averaging over winners alone
    # reported 100%, which is nonsense and moves with the win rate rather than with the payout.
    path = tmp_path / "trades.jsonl"
    with TradeLog(path) as log:
        for i in range(4):
            log.write(_trade(contract_id=i, status="lost", profit=-1.0))
    t = tally(path)
    assert t.trades == 4 and t.won == 0
    assert t.average_payout == pytest.approx(1.88)
    assert t.breakeven == pytest.approx(1 / 1.88)
    assert "53.19%" in t.report()


def test_a_hand_placed_trade_can_be_written_down_and_counted(tmp_path):
    # the user trades this by eye; a trade nobody writes down is what turns a count into a memory of wins
    from clicktrader.cli import main

    path = tmp_path / "hand.jsonl"
    assert main(["log-trade", "--log", str(path), "--direction", "up", "--stake", "10",
                 "--payout", "18.8", "--status", "won", "--reason", "rejection from a floor"]) == 0
    (trade,) = list(read_trades(path))
    assert trade.status == "won" and trade.profit == pytest.approx(8.8)
    assert trade.reason == "rejection from a floor"
    assert main(["log-trade", "--log", str(path), "--direction", "down", "--stake", "10",
                 "--payout", "18.8", "--status", "lost"]) == 0
    total = tally(path)
    assert (total.trades, total.won) == (2, 1)
    assert total.net == pytest.approx(8.8 - 10.0)
    assert total.breakeven == pytest.approx(1 / 1.88)
