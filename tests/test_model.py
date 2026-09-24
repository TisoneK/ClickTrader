import pytest

from clicktrader.model import HOUSE_EDGE, Contract, Side, Tick, last_digit

# Read off the live interface — the table at the top of DESIGN.md.
OBSERVED = [
    (Side.OVER, 0, 0.90, 0.056),
    (Side.OVER, 2, 0.70, 0.357),
    (Side.OVER, 4, 0.50, 0.900),
    (Side.UNDER, 1, 0.10, 8.500),
    (Side.UNDER, 3, 0.30, 2.167),
]


@pytest.mark.parametrize("side,barrier,p,shown", OBSERVED)
def test_pricing_matches_the_observed_payouts(side, barrier, p, shown):
    c = Contract(side, barrier)
    assert c.win_probability == pytest.approx(p)
    assert c.profit_ratio == pytest.approx(shown, abs=0.0005)


def test_every_contract_has_the_same_expected_value():
    for side, barriers in ((Side.OVER, range(0, 9)), (Side.UNDER, range(1, 10))):
        for b in barriers:
            c = Contract(side, b)
            ev = sum(c.settle(1.0, d) for d in range(10)) / 10
            assert ev == pytest.approx(-HOUSE_EDGE)


@pytest.mark.parametrize("side,barrier", [(Side.OVER, 9), (Side.UNDER, 0), (Side.OVER, -1), (Side.UNDER, 10)])
def test_degenerate_barriers_are_rejected(side, barrier):
    with pytest.raises(ValueError):
        Contract(side, barrier)


def test_settlement_edges():
    assert Contract(Side.OVER, 4).wins(5) and not Contract(Side.OVER, 4).wins(4)
    assert Contract(Side.UNDER, 5).wins(4) and not Contract(Side.UNDER, 5).wins(5)


def test_even_odd_is_a_fixed_50_50_split():
    even, odd = Contract(Side.EVEN), Contract(Side.ODD)
    assert even.win_probability == odd.win_probability == pytest.approx(0.5)
    assert even.profit_ratio == odd.profit_ratio == pytest.approx(0.90, abs=0.0005)
    for d in range(10):
        assert even.wins(d) == (d % 2 == 0)
        assert odd.wins(d) == (d % 2 == 1)
    assert str(even) == "even" and str(odd) == "odd"


def test_even_odd_rejects_a_barrier():
    with pytest.raises(ValueError):
        Contract(Side.EVEN, 4)


@pytest.mark.parametrize("side", [Side.OVER, Side.UNDER])
def test_over_under_require_a_barrier(side):
    with pytest.raises(ValueError):
        Contract(side)


def test_last_digit_keeps_trailing_zeros():
    assert last_digit("1234.50") == 0
    assert Tick(0, "987.123").digit == 3
    with pytest.raises(ValueError):
        last_digit("12.3x")
