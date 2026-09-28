"""The candle importer: the paging loop, the rate-limit wait, and the bar reconstruction.

Everything here runs against a fake request function rather than the live API — the one property that
actually matters is that four points per bar rebuild the *identical* bar, and that can be checked exactly
with a `TimeCandleBuilder` instead of approximately against a network.
"""

import pytest

from clicktrader.api.deriv.history import candles_backwards, ticks_from_candles
from clicktrader.api.deriv.trading import DerivAPIError
from clicktrader.forex.candles import TimeCandleBuilder


_BASE = 1_699_999_200
"""Aligned to the 900-second grid, which a real candle epoch always is and a made-up one may not be."""


def _candle(epoch, open_, high, low, close):
    return {"epoch": epoch, "open": open_, "high": high, "low": low, "close": close}


def _block(start_epoch, count, *, granularity=900, base=4100.0):
    """`count` candles ascending from `start_epoch`, prices walking up so each bar is distinct."""
    return [
        _candle(start_epoch + i * granularity, base + i, base + i + 2, base + i - 2, base + i + 1)
        for i in range(count)
    ]


class FakeAPI:
    """A stand-in for the endpoint: history laid out in time, paged backwards, with a rate limit."""

    def __init__(self, candles, *, rate_limit_at=(), short_at=None):
        self.candles = candles
        self.calls = []
        self.rate_limit_at = set(rate_limit_at)
        self.short_at = short_at

    def __call__(self, symbol, *, granularity, count, end):
        self.calls.append((symbol, granularity, count, end))
        if len(self.calls) in self.rate_limit_at:
            raise DerivAPIError("RateLimit: You have reached the rate limit for ticks_history.")
        if self.short_at is not None and len(self.calls) > self.short_at:
            return []
        if end == "latest":
            return self.candles[-count:]
        return [c for c in self.candles if c["epoch"] <= end][-count:]


def test_paging_collects_the_requested_bars_oldest_first():
    history = _block(_BASE, 30)
    api = FakeAPI(history)
    got = candles_backwards("frxXAUUSD", bars=20, batch=8, pace=0, request=api)
    assert len(got) == 20
    assert [c["epoch"] for c in got] == sorted(c["epoch"] for c in got)  # ascending, not in fetch order
    assert got == history[-20:]


def test_it_pages_back_rather_than_asking_for_everything_at_once():
    api = FakeAPI(_block(_BASE, 30))
    candles_backwards("frxXAUUSD", bars=20, batch=8, pace=0, request=api)
    assert len(api.calls) == 3
    assert api.calls[0][3] == "latest"
    first_batch_epoch = api.calls and _block(_BASE, 30)[-8]["epoch"]
    assert isinstance(api.calls[1][3], int)
    assert api.calls[1][3] < first_batch_epoch  # the second request continues below the first batch


def test_a_short_batch_ends_the_walk_without_an_error():
    # the server having no more history is a fact about the instrument, not a failure
    api = FakeAPI(_block(_BASE, 10))
    got = candles_backwards("frxXAUUSD", bars=50, batch=4, pace=0, request=api)
    assert len(got) == 10
    assert len(api.calls) == 3  # 4 + 4 + the short one that ended it


def test_a_rate_limit_is_waited_out_and_retried():
    slept = []
    api = FakeAPI(_block(_BASE, 12), rate_limit_at={1})
    got = candles_backwards("frxXAUUSD", bars=8, batch=8, pace=1.0, request=api, sleep=slept.append)
    assert len(got) == 8  # the first call was refused and the retry succeeded
    assert slept and slept[0] >= 15.0  # backed off well past the ordinary pace


def test_a_rate_limit_that_never_lets_up_is_raised_not_retried_forever():
    api = FakeAPI(_block(_BASE, 12), rate_limit_at={1, 2, 3, 4, 5, 6})
    with pytest.raises(DerivAPIError):
        candles_backwards("frxXAUUSD", bars=8, batch=8, pace=0, request=api, sleep=lambda _s: None)


def test_the_pace_is_waited_between_requests():
    slept = []
    api = FakeAPI(_block(_BASE, 30))
    candles_backwards("frxXAUUSD", bars=20, batch=8, pace=6.0, request=api, sleep=slept.append)
    assert slept == [6.0, 6.0]  # between batches, but never after the last one


def test_progress_is_reported_per_batch():
    seen = []
    api = FakeAPI(_block(_BASE, 30))
    candles_backwards(
        "frxXAUUSD", bars=20, batch=8, pace=0, request=api,
        on_batch=lambda batch, total, oldest: seen.append((batch, total, oldest)),
    )
    assert [s[1] for s in seen] == [8, 16, 20]
    assert seen[-1][2] == _block(_BASE, 30)[-20]["epoch"]


def test_a_candle_off_the_bar_grid_is_refused_rather_than_mis_bucketed():
    # four points per bar only rebuild the bar if the bar starts on the grid the builder buckets by
    off_grid = [_candle(_BASE + 1, 4100.0, 4102.0, 4098.0, 4101.0)]
    with pytest.raises(ValueError):
        ticks_from_candles(off_grid, symbol="frxXAUUSD")


def test_a_silly_bar_count_is_refused_up_front():
    with pytest.raises(ValueError):
        candles_backwards("frxXAUUSD", bars=0, request=FakeAPI([]))
    with pytest.raises(ValueError):
        candles_backwards("frxXAUUSD", bars=1, batch=0, request=FakeAPI([]))


# --- the conversion, which is the part that has to be exactly right ------------------------------


def test_four_points_per_candle_rebuild_the_identical_bar():
    # the reason the importer can feed a tick harness at all: the wall-clock builder reads the first
    # price as the open, the max as the high, the min as the low and the last as the close
    candle = _candle(_BASE, 4100.5, 4123.75, 4094.25, 4111.0)
    records = ticks_from_candles([candle], symbol="frxXAUUSD")
    assert len(records) == 4
    builder = TimeCandleBuilder(900)
    rebuilt = None
    for record in records:
        builder.feed(record.tick.ts, float(record.tick.price))
    # a bar closes when a later one is traded in, so one more bar is needed to close this one
    builder.feed(1_700_000_900, 4111.0)
    (rebuilt,) = builder.last(1)
    assert (rebuilt.open, rebuilt.high, rebuilt.low, rebuilt.close) == (4100.5, 4123.75, 4094.25, 4111.0)
    assert rebuilt.opened_at == _BASE


def test_the_converted_ticks_are_ascending_and_inside_their_own_bar():
    candles = _block(_BASE, 5)
    records = ticks_from_candles(candles, symbol="frxXAUUSD")
    stamps = [r.tick.ts for r in records]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)  # four distinct instants per bar, not four identical ones
    for i, candle in enumerate(candles):
        inside = [r.tick.ts for r in records[i * 4 : i * 4 + 4]]
        assert all(candle["epoch"] <= ts < candle["epoch"] + 900 for ts in inside)


def test_imported_bars_are_marked_so_they_are_never_mistaken_for_a_recording():
    records = ticks_from_candles([_candle(_BASE, 4100.0, 4102.0, 4098.0, 4101.0)], symbol="frxXAUUSD")
    assert all(r.extra.get("source") == "deriv-history" for r in records)
    assert all(not r.extra.get("synthetic") for r in records)  # real prices, so not synthetic either


def test_prices_are_stored_at_the_symbols_own_precision():
    records = ticks_from_candles([_candle(_BASE, 4100.5, 4123.75, 4094.25, 4111.0)], symbol="frxXAUUSD")
    assert [r.tick.price for r in records] == ["4100.50", "4123.75", "4094.25", "4111.00"]
