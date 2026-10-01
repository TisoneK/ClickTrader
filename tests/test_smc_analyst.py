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


def test_an_order_that_price_never_comes_back_to_goes_stale_and_says_so():
    quiet = [(11.0, 11.2, 10.95, 11.1)] * 6
    (waiting,) = read((12.4, 12.45, 10.9, 11.0), *quiet).opportunities
    assert waiting.state is State.ARMED  # without an expiry it stands for ever
    (old,) = read((12.4, 12.45, 10.9, 11.0), *quiet, stale_bars=4).opportunities
    assert old.state is State.CANCELLED and old.reason.startswith("stale:") and "bars" in old.reason
    (young,) = read((12.4, 12.45, 10.9, 11.0), *quiet, stale_bars=50).opportunities
    assert young.state is State.ARMED


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
    # (bar 13 also wicks under the separate 10.6 stack of lows and closes back inside it: a pool sweep, correctly —
    # this test is about the 11.3 level only)
    kinds = [(e.index, e.kind, e.verdict) for e in r.events if e.index >= 12 and e.level == 11.3]
    assert kinds == [(12, EventKind.SWEEP, Verdict.FALSE), (13, EventKind.CHOCH, Verdict.TRUE)]


def test_a_wick_under_a_stacked_level_that_closes_back_inside_is_a_sweep_of_that_level():
    r = read((12.4, 12.45, 10.9, 11.6), (11.6, 11.65, 10.5, 10.7))
    pool = [e for e in r.events if e.kind is EventKind.SWEEP and e.index == 13]
    assert pool and pool[0].level == 10.6 and "turned at 2 times" in pool[0].reason


def test_a_reading_draws_to_a_png_with_every_kind_of_mark(tmp_path):
    from clicktrader.smc.draw import draw_reading

    r = read((12.4, 12.45, 10.9, 11.6), (11.6, 11.65, 10.5, 10.7), (10.7, 12.3, 10.6, 11.0))
    out = tmp_path / "reading.png"
    draw_reading(r, str(out), bars=40, width=800, height=400)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and out.stat().st_size > 2000


# --- supply / demand zones: the ORIGIN of an aggressive move, not a stack of swings -------------------------------
_BASE = [(10.3, 10.6, 10.0, 10.2), (10.2, 10.3, 10.0, 10.1)] * 6  # quiet: bodies ~0.1, a swing high at 10.6
_ORIGIN = (10.3, 10.35, 10.15, 10.2)  # the last bearish candle before the run
_RUN = [(10.3, 11.05, 10.3, 11.0), (11.0, 11.9, 10.95, 11.85), (11.85, 12.6, 11.3, 12.5)]  # three big bullish bars, a gap 11.05-11.3


def _zone_chart(*tail, base=None):
    return [Candle(*b) for b in (*(base or _BASE), _ORIGIN, *_RUN, *tail)]


def _zones(*tail, **kw):
    return read_chart(_zone_chart(*tail, **kw), lookback=6, strength=1).zones


def test_the_last_opposite_candle_before_an_aggressive_run_is_a_valid_demand_zone():
    (z,) = _zones()
    assert (z.kind, z.low, z.high) == ("DEMAND", 10.15, 10.35)  # wick to wick, on the candle before the run
    assert z.has_gap and z.has_bos and z.valid and z.status == "fresh"


def test_a_zone_is_fresh_until_price_first_comes_back_and_then_it_is_used():
    (z,) = _zones((12.5, 12.6, 12.3, 12.4), (12.4, 12.45, 10.3, 10.6), (10.6, 10.9, 10.4, 10.8))
    assert z.status == "used" and z.tapped_at is not None


def test_a_close_through_the_far_edge_kills_the_zone():
    (z,) = _zones((12.5, 12.6, 12.3, 12.4), (12.4, 12.45, 9.9, 10.05))
    assert z.status == "dead" and z.died_at is not None


def test_a_violent_return_is_flagged_as_a_falling_knife():
    (z,) = _zones((12.5, 12.6, 12.3, 12.4), (12.4, 12.45, 10.3, 10.4))  # one huge bearish bar straight into the zone
    assert z.status == "used" and z.knife


def test_a_run_that_does_not_break_structure_is_not_a_valid_zone():
    # a spike to 13 earlier means the run (to 12.6) never takes out the last swing high: no break of structure
    base = _BASE[:6] + [(10.3, 13.0, 10.2, 10.4), (10.4, 10.5, 10.1, 10.2)] + _BASE[6:]
    zs = _zones(base=base)
    assert zs and not zs[-1].has_bos and not zs[-1].valid and "no break of structure" in zs[-1].why_not


def test_ordinary_candles_make_no_zone():
    assert read_chart([Candle(*b) for b in _BASE * 3], lookback=6, strength=1).zones == []


def test_ordinary_candles_that_break_structure_make_a_false_zone_that_fails_aggression():
    # three bullish bars the size of the quiet base, still clearing the 10.6 swing high: the decks' "invalid: fails the
    # aggression rule". It is reported as a FALSE zone with the rule it failed, not silently dropped.
    weak = [(10.25, 10.45, 10.2, 10.35), (10.35, 10.55, 10.3, 10.45), (10.45, 10.7, 10.4, 10.55)]
    zs = read_chart([Candle(*b) for b in (*_BASE, _ORIGIN, *weak)], lookback=6, strength=1).zones
    assert zs and zs[-1].verdict == "FALSE" and not zs[-1].aggressive and zs[-1].has_bos
    assert "not aggressive" in zs[-1].why_not


def test_every_zone_has_one_of_three_verdicts_true_false_or_broken():
    base = _BASE[:6] + [(10.3, 13.0, 10.2, 10.4), (10.4, 10.5, 10.1, 10.2)] + _BASE[6:]
    assert _zones(base=base)[-1].verdict == "FALSE"  # no break of structure
    (true,) = _zones()
    assert true.verdict == "TRUE"
    (broken,) = _zones((12.5, 12.6, 12.3, 12.4), (12.4, 12.45, 9.9, 10.05))
    assert broken.verdict == "BROKEN"  # it was valid, then a bar closed through it


# --- the rest of the decks' zone rules, tested on the pure pieces --------------------------------------------
from clicktrader.forex.structure import SwingKind, SwingPoint  # noqa: E402
from clicktrader.smc.analyst import Structure, Zone, _mark_weaker, _zone_opportunity, fib_zone, read_structure  # noqa: E402
from clicktrader.smc.engine import Control  # noqa: E402


def _z(low, high, *, direction=Direction.UP, anchor=3, origin=5):
    z = Zone(direction, low, high, origin, origin + 1, origin + 3, origin + 3, has_gap=True, has_bos=True)
    z.leg_anchor = anchor
    return z


def test_the_lowest_demand_in_a_leg_is_strongest_and_the_others_are_weaker():
    a, b, c = _z(10.0, 10.3), _z(9.0, 9.3), _z(9.5, 9.8, anchor=99)  # c is in another leg
    _mark_weaker([a, b, c])
    assert (a.weaker, b.weaker, c.weaker) == (True, False, False)


def test_the_highest_supply_in_a_leg_is_strongest():
    a, b = _z(20.0, 20.3, direction=Direction.DOWN), _z(21.0, 21.3, direction=Direction.DOWN)
    _mark_weaker([a, b])
    assert (a.weaker, b.weaker) == (True, False)


def test_the_fibonacci_band_is_the_618_to_786_retracement():
    lo, hi = fib_zone(top=110.0, bottom=100.0, demand=True)  # measured down from the top
    assert (round(lo, 3), round(hi, 3)) == (102.14, 103.82)
    lo, hi = fib_zone(top=110.0, bottom=100.0, demand=False)  # measured up from the bottom
    assert (round(lo, 3), round(hi, 3)) == (106.18, 107.86)


_ROOM = [SwingPoint(0, 14.0, SwingKind.HIGH), SwingPoint(1, 11.0, SwingKind.LOW)]


def _opp(z, *, control=Control.DEMAND, structure=Structure.UP, clocks=()):
    return _zone_opportunity([Candle(10, 11, 9, 10)] * 20, 19, z, _ROOM, list(clocks), 1, 2.0, control, structure)


def test_a_fresh_true_demand_zone_with_the_trend_and_room_is_armed_with_the_decks_levels():
    opp = _opp(_z(10.0, 10.5))
    assert opp.state is State.ARMED and opp.source == "zone"
    assert (opp.entry, opp.stop) == (10.5, 10.0)  # limit at the near edge, stop just outside the far edge
    assert opp.target == 14.0 and opp.reward_risk == 7.0  # the nearest level leaving the floor


def test_a_demand_zone_in_a_down_trend_is_declined_because_the_decks_only_look_for_supply():
    opp = _opp(_z(10.0, 10.5), control=Control.SUPPLY, structure=Structure.DOWN)
    assert opp.state is State.DECLINED and "against the trend" in opp.reason
    assert "down-trend" in opp.reason and "demand zone" in opp.reason  # the message names the trend and the zone correctly


def test_a_weaker_zone_is_declined_in_favour_of_the_lowest_one():
    z = _z(10.0, 10.5)
    z.weaker = True
    opp = _opp(z)
    assert opp.state is State.DECLINED and "weaker zone" in opp.reason


def test_a_trade_with_no_level_leaving_the_floor_is_declined_for_room():
    z = _z(10.0, 12.9)  # a huge risk: no swing is 2x that far away
    assert "no room" in _opp(z).reason


def test_every_clock_in_a_chain_gets_a_say():
    down = [Candle(40 - o, 40 - l, 40 - h, 40 - c) for o, h, l, c in UP]  # the same zig-zag mirrored: a clear downtrend
    zigzag = [Candle(*b) for b in UP]  # another that reads up
    assert _opp(_z(10.0, 10.5), clocks=[zigzag]).state is State.ARMED  # agrees with the long
    blocked = _opp(_z(10.0, 10.5), clocks=[zigzag, down])
    assert blocked.state is State.DECLINED and "higher timeframe" in blocked.reason


# --- zones are judged every bar, not once at birth ----------------------------------------------------------------
def _rising_base():
    """A gently rising zig-zag (higher highs, higher lows) of small candles: structure UP, demand in control."""
    out = []
    for k in range(6):
        b = 10 + 0.25 * k
        out += [(b, b + 0.12, b - 0.04, b + 0.1), (b + 0.1, b + 0.24, b + 0.06, b + 0.22),
                (b + 0.22, b + 0.26, b + 0.1, b + 0.12), (b + 0.12, b + 0.16, b + 0.02, b + 0.05)]
    return out


def _trend_chart(*after):
    base = _rising_base()
    last = base[-1][3]
    origin = (last, last + 0.03, last - 0.12, last - 0.08)
    o = origin[3]
    run = [(o, o + 0.9, o - 0.02, o + 0.85), (o + 0.85, o + 1.8, o + 0.8, o + 1.75), (o + 1.75, o + 2.6, o + 1.2, o + 2.5)]
    return [Candle(*b) for b in (*base, origin, *run, *after)], o


def test_a_zone_that_cannot_be_traded_when_it_forms_is_armed_later_when_it_can():
    # The run ends on a bar that makes a HIGHER high, so at birth the run's top is not yet a confirmed swing and no level
    # lies far enough above the zone to target: declined for room. One bar later that high is a confirmed swing, and the
    # same zone — untapped, with the trend — qualifies and is armed from that later bar.
    _c, o = _trend_chart()
    candles, _ = _trend_chart((o + 2.5, o + 2.7, o + 2.2, o + 2.3), (o + 2.3, o + 2.4, o + 2.1, o + 2.2), (o + 2.2, o + 2.3, o + 2.0, o + 2.1))
    opps = [x for x in read_chart(candles, lookback=6, strength=1).opportunities if x.source == "zone"]
    assert opps[0].state is State.DECLINED and "no room" in opps[0].reason
    later = [x for x in opps if x.state is State.ARMED]
    assert later and later[0].armed_at > opps[0].armed_at
    assert later[0].entry == later[0].block.price_high and later[0].stop == later[0].block.price_low  # the decks' levels


def test_a_tapped_zone_is_not_a_standing_order():
    _c, o = _trend_chart()
    candles, _ = _trend_chart((o + 2.5, o + 2.7, o + 2.2, o + 2.3), (o + 2.3, o + 2.4, o + 2.1, o + 2.2), (o + 2.2, o + 2.3, o + 1.9, o + 2.0),
                              (o + 2.0, o + 2.05, o - 0.05, o + 0.1))  # price drops into the zone: first tap
    r = read_chart(candles, lookback=6, strength=1)
    z = next(z for z in r.zones if z.valid)
    assert z.status in ("used", "dead")
    opp = next(x for x in r.opportunities if x.source == "zone" and x.state is not State.DECLINED)
    assert opp.state is not State.ARMED  # it was armed, then filled/cancelled/dead once price reached it


def test_slower_clocks_are_read_as_they_stood_when_each_bar_closed_not_as_they_end_up():
    from clicktrader.forex.candles import TimedCandle
    from clicktrader.smc.analyst import _ClockView

    trigger = [TimedCandle(1, 2, 0, 1, opened_at=60.0 * i) for i in range(20)]  # 1-minute bars
    slow = [TimedCandle(1, 2, 0, 1, opened_at=300.0 * i) for i in range(4)]  # 5-minute bars at 0, 5, 10, 15 min
    view = _ClockView(trigger, [slow])
    assert len(view.at(3)[0]) == 0  # at 00:03 close (ends 00:04) the first 5-minute bar has not closed
    assert len(view.at(4)[0]) == 1  # at the 00:04 bar's close (ends 00:05) it has
    assert len(view.at(9)[0]) == 2 and len(view.at(19)[0]) == 4


def test_the_reading_is_causal_with_slower_clocks_too():
    import random

    from clicktrader.forex.candles import TimeCandleBuilder

    rng = random.Random(9)
    price, ticks = 100.0, []
    for i in range(6000):
        price += rng.gauss(0, 0.05)
        ticks.append((1_700_000_000.0 + i * 2, price))

    def bars(minutes, upto=None):
        b = TimeCandleBuilder(minutes * 60)
        for ts, p in ticks:
            if upto is None or ts < upto:
                b.feed(ts, p)
        return b.last(10**6)

    whole = read_chart(bars(1), higher=[bars(5), bars(15)], lookback=10, strength=2)
    cut = 1_700_000_000.0 + 3600 * 2
    part = read_chart(bars(1, cut), higher=[bars(5, cut), bars(15, cut)], lookback=10, strength=2)
    k = len(part.candles) - 1  # the last bar of the prefix may be cut mid-bar in the whole chart's builder; leave it out
    assert [(o.armed_at, o.direction, o.state.value if o.state.value in ("declined",) else "x") for o in part.opportunities if o.armed_at < k] == [
        (o.armed_at, o.direction, o.state.value if o.state.value in ("declined",) else "x") for o in whole.opportunities if o.armed_at < k
    ]
