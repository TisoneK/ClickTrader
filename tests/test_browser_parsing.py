import pytest

from clicktrader.browser.parsing import (
    is_price,
    parse_money,
    parse_payout_box,
    parse_percent,
    parse_session_pl,
    parse_trade_count,
)


def test_is_price():
    assert is_price("9481.68")
    assert not is_price("9481.68%")
    assert not is_price("abc")


def test_parse_percent():
    assert parse_percent("10.4%") == pytest.approx(0.104)
    assert parse_percent(" 100% ") == pytest.approx(1.0)
    with pytest.raises(ValueError):
        parse_percent("10.4")


def test_parse_money():
    assert parse_money("$ 0.00") == 0.0
    assert parse_money("2.38 USD") == pytest.approx(2.38)
    assert parse_money("-1.00") == -1.0
    with pytest.raises(ValueError):
        parse_money("free")


def test_parse_session_pl():
    assert parse_session_pl("Session P/L:-1.00 USD") == -1.0
    assert parse_session_pl("● Auto-Trading1 trades (0W / 1L)Session P/L:-1.00 USD") == -1.0
    with pytest.raises(ValueError):
        parse_session_pl("no such field here")


def test_parse_trade_count():
    assert parse_trade_count("1T · 0W / 1L") == (1, 0, 1)
    assert parse_trade_count("12T · 3W · 9L") == (12, 3, 9)
    with pytest.raises(ValueError):
        parse_trade_count("garbage")


def test_parse_payout_box():
    # .textContent runs sibling elements together with no separator — this is the real shape.
    assert parse_payout_box("Over137.5%$2.38Payout") == {"amount": 2.38, "profit_ratio": 1.375}
    assert parse_payout_box("Under90.0%$1.90Payout") == {"amount": 1.90, "profit_ratio": 0.9}
    with pytest.raises(ValueError):
        parse_payout_box("OverPayout")
