"""The analyst's judgement, on charts small enough to check by eye.

The base chart is an up-trend: swing highs 12.0 -> 12.5 -> 12.8 and swing lows 10.6 -> 11.3. The last swing low
(11.3) is the level the trend has to hold. Each test changes one thing after it and asks what the analyst called it.
"""

from clicktrader.forex.candles import Candle
from clicktrader.forex.model import Direction
from clicktrader.smc.analyst import EventKind, State, Verdict, read_chart

UP = [
    (10, 10.5, 9.5, 10.2), (10.2, 11.0, 10.0, 10.8), (10.8, 12.0, 10.7, 11.9), (11.9, 11.95, 11.0, 11.1),
    (11.1, 11.2, 10.6, 10.7), (10.7, 11.6, 10.65, 11.5), (11.5, 12.5, 11.4, 12.4), (12.4, 12.45, 12.0, 12.1),
    (12.1, 12.2, 11.3, 11.4), (11.4, 12.4, 11.35, 12.3), (12.3, 12.8, 12.25, 12.7), (12.7, 12.75, 12.3, 12.4),
]


def chart(*tail):
    return [Candle(*b) for b in (*UP, *tail)]


def read(*tail, **kw):
    return read_chart(chart(*tail), lookback=3, strength=1, **kw)


def test_swings_are_named_against_the_previous_swing_of_their_kind():
    r = read((12.4, 12.45, 11.8, 11.9))
    assert [(s.swing.index, s.label) for s in r.swings] == [(2, "H"), (4, "L"), (6, "HH"), (8, "HL"), (10, "HH")]


def test_carrying_the_trend_through_its_last_extreme_is_a_bos_not_a_reversal():
    r = read((12.4, 12.45, 11.8, 11.9))
    bos = [e for e in r.events if e.kind is EventKind.BOS]
    assert bos and bos[0].verdict is Verdict.CONTINUATION and bos[0].index == 10


def test_a_close_through_the_level_the_trend_has_to_hold_is_a_true_change_of_character():
    r = read((12.4, 12.45, 10.9, 11.0))
    choch = [e for e in r.events if e.kind is EventKind.CHOCH]
    assert len(choch) == 1 and choch[0].verdict is Verdict.TRUE
    assert choch[0].level == 11.3 and choch[0].direction is Direction.DOWN


def test_the_same_wick_that_closes_back_is_a_sweep_and_arms_nothing():
    r = read((12.4, 12.45, 10.9, 11.6))  # identical to the CHOCH bar except for where it closed
    assert [e.kind for e in r.events if e.index == 12] == [EventKind.SWEEP]
    assert [e.verdict for e in r.events if e.index == 12] == [Verdict.FALSE]
    assert r.opportunities == []


def test_a_true_change_of_character_arms_a_short_at_the_origin_block():
    (opp,) = read((12.4, 12.45, 10.9, 11.0)).opportunities
    assert opp.state is State.ARMED and opp.direction is Direction.DOWN
    # the origin is the last opposite-coloured (bullish) candle before the down leg: bar 10, boxed wick to wick
    assert (opp.block.index, opp.block.price_low, opp.block.price_high) == (10, 12.25, 12.8)
    assert (opp.entry, opp.stop) == (12.25, 12.8)
    assert opp.target == 10.6 and opp.reward_risk >= 2.0  # the nearest level that leaves the 1:2 floor


def test_no_level_with_room_means_no_trade_and_it_says_so():
    (opp,) = read((12.4, 12.45, 10.9, 11.0), risk_reward=5.0).opportunities
    assert opp.state is State.DECLINED and "no room" in opp.reason


def test_a_trade_against_the_higher_timeframe_is_declined():
    higher = [Candle(*b) for b in UP]  # the slower clock is itself an up-trend
    (opp,) = read((12.4, 12.45, 10.9, 11.0), higher=higher).opportunities
    assert opp.state is State.DECLINED and "higher timeframe" in opp.reason


def test_closing_through_the_blocks_far_edge_before_the_tap_kills_the_zone():
    # the same spike also closes through the last swing high, so it is a second change of character: the first
    # opportunity is the one this test is about
    opp = read((12.4, 12.45, 10.9, 11.0), (11.0, 12.9, 10.95, 12.85)).opportunities[0]
    assert opp.state is State.DEAD and "dead zone" in opp.reason


def test_a_violent_approach_into_the_zone_cancels_the_order():
    (opp,) = read((12.4, 12.45, 10.9, 11.0), (11.0, 12.3, 10.95, 12.25)).opportunities
    assert opp.state is State.CANCELLED and "falling knife" in opp.reason


def test_a_slow_return_fills_on_the_first_tap_and_hindsight_grades_it():
    win = read((12.4, 12.45, 10.9, 11.0), (11.6, 12.3, 11.5, 11.8), (11.8, 11.85, 10.5, 10.55)).opportunities[0]
    assert win.state is State.FILLED and win.filled_at == 13 and win.outcome == "win"
    loss = read((12.4, 12.45, 10.9, 11.0), (11.6, 12.3, 11.5, 11.8), (11.8, 12.9, 11.7, 12.85)).opportunities[0]
    assert loss.state is State.FILLED and loss.outcome == "loss"


def test_the_reading_is_causal_a_prefix_reads_the_same_as_the_whole():
    import random

    rng = random.Random(4)
    price, candles = 100.0, []
    for _ in range(260):
        o = price
        c = o + rng.gauss(0, 1.0)
        candles.append(Candle(o, max(o, c) + abs(rng.gauss(0, 0.5)), min(o, c) - abs(rng.gauss(0, 0.5)), c))
        price = c
    whole = read_chart(candles, lookback=10, strength=2)
    for k in (80, 140, 200):
        part = read_chart(candles[:k], lookback=10, strength=2)
        assert [(e.index, e.kind, e.verdict) for e in part.events] == [
            (e.index, e.kind, e.verdict) for e in whole.events if e.index < k
        ], k
        assert [(o.armed_at, o.direction) for o in part.opportunities] == [
            (o.armed_at, o.direction) for o in whole.opportunities if o.armed_at < k
        ], k


def test_a_sweep_does_not_use_the_level_up_a_later_close_through_it_is_still_a_change_of_character():
    # bar 12 wicks through 11.3 and closes back (a sweep); bar 13 then closes through it for real
    r = read((12.4, 12.45, 10.9, 11.6), (11.6, 11.65, 10.5, 10.7))
    kinds = [(e.index, e.kind, e.verdict) for e in r.events if e.index >= 12]
    assert kinds == [(12, EventKind.SWEEP, Verdict.FALSE), (13, EventKind.CHOCH, Verdict.TRUE)]


def test_a_reading_draws_to_a_png_with_every_kind_of_mark(tmp_path):
    from clicktrader.smc.draw import draw_reading

    r = read((12.4, 12.45, 10.9, 11.6), (11.6, 11.65, 10.5, 10.7), (10.7, 12.3, 10.6, 11.0))
    out = tmp_path / "reading.png"
    draw_reading(r, str(out), bars=40, width=800, height=400)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and out.stat().st_size > 2000
