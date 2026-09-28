"""Trading sessions: which day a tick belongs to, and what the completed ones looked like.

A "day" here is a fixed-length window on the wall clock, not a calendar date, because that is what the
vertical gridlines on a chart are and what "yesterday's high" means to a trader. The boundary is a
convention rather than a fact about the market — the FX week runs continuously from Sunday evening, so
where one day ends and the next begins is a choice (midnight UTC, 5pm New York, a broker's own roll) —
which is why `start_hour_utc` is a parameter here and not a constant buried somewhere.

Sessions are tracked incrementally, one tick at a time, for the same reason `candles.CandleBuilder` is:
a strategy's `decide()` is called once per tick with a growing history, so anything that re-derived the
day structure from the whole history on every call would be quadratic in a recording's length and would
make a long replay unusable.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True)
class SessionExtremes:
    """One completed session, reduced to what a later session can be drawn against."""

    opened_at: float
    high: float
    low: float


class SessionTracker:
    """Assigns ticks to sessions and keeps the most recent completed sessions' extremes.

    `keep` bounds how much history is retained: the range lines need the session immediately before the
    current one, and the swing lines need up to `swing_lookback` sessions before that, so a strategy
    wanting *n* sessions of lookback constructs this with `keep=n` and no more.
    """

    def __init__(self, *, start_hour_utc: int = 0, keep: int = 4) -> None:
        if not 0 <= start_hour_utc < 24:
            raise ValueError("start_hour_utc must be an hour of the day (0-23)")
        if keep < 1:
            raise ValueError("keep must retain at least one completed session")
        self._origin = start_hour_utc * 3600.0
        self._keep = keep
        self._completed: deque[SessionExtremes] = deque(maxlen=keep)
        self._bucket: int | None = None
        self._high = 0.0
        self._low = 0.0

    def bucket_of(self, ts: float) -> int:
        return int((ts - self._origin) // SECONDS_PER_DAY)

    def _start_of(self, bucket: int) -> float:
        return bucket * SECONDS_PER_DAY + self._origin

    def session_start(self, ts: float) -> float:
        """The instant the session containing `ts` began."""
        return self._start_of(self.bucket_of(ts))

    def feed(self, ts: float, price: float) -> bool:
        """Add one tick. Returns True when that tick opened a new session (closing the previous one).

        Ticks must arrive in time order, for the same reason `TimeCandleBuilder` requires it.
        """
        bucket = self.bucket_of(ts)
        if self._bucket is None:
            self._bucket = bucket
            self._high = self._low = price
            return False
        if bucket < self._bucket:
            raise ValueError(
                f"tick at ts={ts} belongs to an earlier session (bucket {bucket} < {self._bucket})"
            )
        if bucket == self._bucket:
            self._high = max(self._high, price)
            self._low = min(self._low, price)
            return False
        self._completed.append(
            SessionExtremes(opened_at=self._start_of(self._bucket), high=self._high, low=self._low)
        )
        self._bucket = bucket
        self._high = self._low = price
        return True

    @property
    def session_opened_at(self) -> float | None:
        """Start of the session currently being built, or None before the first tick."""
        return None if self._bucket is None else self._start_of(self._bucket)

    def completed(self, count: int) -> list[SessionExtremes]:
        """The most recently completed sessions, oldest first, at most `count` of them."""
        if count <= 0:
            return []
        return list(self._completed)[-count:]


@dataclass(frozen=True)
class SessionLevels:
    """The levels a range method is drawn from, all read off sessions that have already closed.

    `swing_high`/`swing_low` are `None` when no earlier session reached beyond the range line on that
    side — a real state, not an error: with no outer boundary there is no zone to trade from, so the
    side is simply not tradeable rather than being given an invented line.
    """

    range_high: float
    range_low: float
    swing_high: float | None
    swing_low: float | None

    @property
    def sell_zone(self) -> tuple[float, float] | None:
        """`(low, high)` of the zone above the range, or None when there is no swing line above it."""
        return None if self.swing_high is None else (self.range_high, self.swing_high)

    @property
    def buy_zone(self) -> tuple[float, float] | None:
        """`(low, high)` of the zone below the range, or None when there is no swing line below it."""
        return None if self.swing_low is None else (self.swing_low, self.range_low)


def levels_from_sessions(
    completed: Sequence[SessionExtremes], *, swing_lookback: int = 1
) -> SessionLevels | None:
    """Build the levels for the session now starting, from the sessions already closed.

    `completed` is oldest-first and ends with the session immediately before the current one, which is
    where the range lines come from. The swing lines come from the `swing_lookback` sessions before
    *that* one, and only when they actually reach beyond the range — which is what the source method
    means by scrolling left for "the next level" outside the range.

    Returns None when there is no previous session at all (the first session in a recording). It does not
    fall back to the current session's own range, which would be a lookahead: the lines have to be
    knowable before the session they are traded in starts.
    """
    if swing_lookback < 0:
        raise ValueError("swing_lookback cannot be negative")
    if not completed:
        return None
    previous = completed[-1]
    if swing_lookback == 0:
        window: Sequence[SessionExtremes] = ()
    else:
        window = completed[-(1 + swing_lookback) : -1]

    swing_high = max((s.high for s in window), default=None)
    swing_low = min((s.low for s in window), default=None)
    return SessionLevels(
        range_high=previous.high,
        range_low=previous.low,
        swing_high=swing_high if swing_high is not None and swing_high > previous.high else None,
        swing_low=swing_low if swing_low is not None and swing_low < previous.low else None,
    )
