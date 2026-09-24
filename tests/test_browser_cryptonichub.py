import pytest

from clicktrader.browser.cryptonichub import to_tick_record

FULL_SNAPSHOT = {
    "price": "9481.68",
    "instrument": "Volatility 10 (1s) Index",
    "histogram": {str(d): f"{9 + d}.0%" for d in range(10)},
    "sessionPl": "Session P/L:-1.00 USD",
    "tradeCount": "1T · 0W / 1L",
    "balanceRaw": "$ 0.00",
    "overBox": "Over137.5%$2.38Payout",
    "underBox": "Under90.0%$1.90Payout",
}


def test_full_snapshot_round_trips():
    record = to_tick_record(FULL_SNAPSHOT, ts=1.0)
    assert record.tick.price == "9481.68"
    assert record.tick.digit == 8
    assert record.tick.symbol == "Volatility 10 (1s) Index"
    assert record.histogram["0"] == pytest.approx(0.09)
    assert record.histogram["9"] == pytest.approx(0.18)
    assert record.payouts == {"over": pytest.approx(1.375), "under": pytest.approx(0.9)}
    assert record.account == {"balance": 0.0, "session_pl": -1.0, "trades": 1, "wins": 0, "losses": 1}


def test_missing_price_raises():
    with pytest.raises(ValueError, match="no price"):
        to_tick_record({**FULL_SNAPSHOT, "price": None}, ts=1.0)


def test_incomplete_histogram_raises():
    snapshot = {**FULL_SNAPSHOT, "histogram": {"0": "10.0%"}}
    with pytest.raises(ValueError, match="10 histogram digits"):
        to_tick_record(snapshot, ts=1.0)


def test_missing_optional_fields_are_omitted_not_guessed():
    snapshot = {**FULL_SNAPSHOT, "sessionPl": None, "tradeCount": None, "balanceRaw": None, "overBox": None, "underBox": None}
    record = to_tick_record(snapshot, ts=1.0)
    assert record.account is None
    assert record.payouts is None
