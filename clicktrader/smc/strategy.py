"""Pillar 3: the operating manual — top-down alignment, the order-block entry, and a 1:2 floor.

**Perception now lives in `analyst.py`.** This class no longer has its own idea of what a level, a break or a block
is: on every closed trigger bar it asks `read_chart` what the chart says — the same reading `smc-chart` draws — and
trades only an opportunity that reading calls true and has just armed. What stays here is the tick path: holding the
order, filling it on the retrace, and dropping it when the zone dies. The constants this class used to own
(`band_bands`, `min_pushed`, `alignment_steps`) are gone; see `analyst.READINGS` for the few choices that remain.

This is the assembly the other three modules feed, and it is deliberately the *last* thing built rather
than the first: it consumes a control state, a graded order block and a break classification, and there is
nothing useful it could have said before those existed.

What it does, in the material's own order:

1. **Top-down.** Two clocks run at once: a trigger timeframe where the change of character is read, and a
   slower one that has to agree before anything is armed. The material's funnel is exactly this — the
   higher timeframe gives the bias and the level, the lower one gives the order block and the trigger — and
   a trigger that contradicts the higher clock is skipped, with the reason recorded.
2. **Wait for the retrace.** A valid change of character does *not* produce a trade. It arms one: the order
   block of the leg that broke the level, with the entry at the block, the stop just beyond its wick, and a
   target at the minimum risk-to-reward. Price has to come back to the block. Nothing here chases a break,
   which is the material's own instruction and its closing slide.
3. **Say no out loud.** Every bar that produced nothing records *why* — no break, a break that was a sweep,
   a break with no aligned higher timeframe, a block that failed the three-factor check. The difference
   between "no setup" and "a setup I declined" is the whole reason this package exists.

**Nothing here gates on a number nobody stated.** The material states a *minimum* 1:2 risk-to-reward — that
is implemented as a floor — and it describes three qualities of a valid zone without giving a threshold for
any of them. So pushed distance is **measured and reported, and by default not gated at all**: an earlier
version required three bands, a number invented here, and that single invented threshold was the entire
difference between an engine that never fired in 42 days and one that fires. Gating a method on a made-up
constant does not make it more faithful, it makes the constant the strategy.

The clocks default to the ratio the material itself draws — a 1-hour view above a 15-minute trigger — rather
than the 5m/60m first chosen here. The alignment reading defaults to two structural steps rather than three,
because three was strict enough that on real EUR/USD the higher timeframe read "range" at every one of 1,797
crossings, which is not a filter but an off switch. Both are still parameters, and both are still unmeasured.

The macro-level target the material names is not implemented — it needs the daily key levels, which are their
own piece of work.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..forex.candles import Candle, TimeCandleBuilder
from ..forex.model import Direction, TradePlan
from ..forex.trade_strategies import TradeDecision
from ..strategies import History
from .components import OrderBlock
from .analyst import State, read_chart


@dataclass
class _Armed:
    """A valid change of character, waiting for price to come back to its block."""

    plan: TradePlan
    block: OrderBlock
    reason: str


class SmcStrategy:
    """The assembled method: arm on an opportunity the analyst calls true, fill on the retrace into the block."""

    def __init__(
        self,
        *,
        trigger_minutes: float = 15.0,
        higher_minutes: float | tuple[float, ...] = 60.0,
        risk_reward: float = 2.0,
        strength: int = 2,
        lookback: int = 20,
        window: int = 400,
        stake: float = 1.0,
        stale_bars: int | None = None,
        counter_trend: bool = False,
        stop_buffer: float = 0.0,
        strict_choch: bool = False,
        confluence_beats_clock: bool = False,
        zones_block_path: bool = False,
        velocity_gate: bool = False,
        min_pushed: float = 0.0,
        equilibrium: bool = False,
    ) -> None:
        if risk_reward < 1:
            raise ValueError("the material's floor is a minimum of 1:2; anything below 1 risks more than it targets")
        chain = tuple(higher_minutes) if isinstance(higher_minutes, (tuple, list)) else (higher_minutes,)
        self.name = f"smc(trigger={trigger_minutes:g}m, higher={'/'.join(f'{m:g}' for m in chain)}m, rr>={risk_reward:g})"
        self._trigger = TimeCandleBuilder(trigger_minutes * 60.0)
        self._higher = [TimeCandleBuilder(m * 60.0) for m in chain]
        self._risk_reward = risk_reward
        self._strength = strength
        self._lookback = lookback
        self._window = window
        self._stale_bars = stale_bars
        self._counter_trend = counter_trend
        self._stop_buffer = stop_buffer
        self._strict_choch = strict_choch
        self._confluence = confluence_beats_clock
        self._walls = zones_block_path
        self._velocity = velocity_gate
        self._min_pushed = min_pushed
        self._equilibrium = equilibrium
        self._config = (trigger_minutes, tuple(chain), risk_reward, strength, lookback, stale_bars, counter_trend, stop_buffer, strict_choch, confluence_beats_clock, zones_block_path, velocity_gate, min_pushed, equilibrium)
        self._note = ""
        self.reading = None
        """The latest reading of the chart, made on the last closed bar (None before there is enough chart) — what a page shows."""
        self._stake = stake
        self._armed: _Armed | None = None
        self.last_view = "nothing seen yet"
        self._taken: set[tuple] = set()
        """Orders already filled, so the same standing zone is never traded twice."""
        self.passes: dict[str, int] = {}
        """Setups it saw and passed on, by reason: so \"it found nothing\" and \"it found things and said no\" read differently."""

    # --- the tick path --------------------------------------------------------------------------

    def decide(self, history: History) -> TradeDecision | None:
        if not len(history):
            return None
        tick = history[-1]
        price = float(tick.price)
        for builder in self._higher:
            builder.feed(tick.ts, price)
        closed = self._trigger.feed(tick.ts, price)
        if closed is not None:
            self._on_trigger_bar(closed)
        return self._fill(price)

    def warm(self, ticks) -> int:
        """Feed historical ticks into the bar builders WITHOUT reading the chart or placing anything.

        A live run starts with no bars, and the reading needs hours of them: this is how it starts with the
        chart a person would already have on screen. Nothing armed before the last warm-up tick can exist, so
        the first live bar is read as a fresh one. Returns how many ticks were fed."""
        fed = 0
        for tick in ticks:
            price = float(tick.price)
            for builder in self._higher:
                builder.feed(tick.ts, price)
            self._trigger.feed(tick.ts, price)
            fed += 1
        self._armed = None
        self.last_view = f"warmed with {fed} historical tick(s)"
        self.reading = self.read_now()
        return fed

    def _note_pass(self, reason: str) -> str:
        """Count a setup it saw and passed on, by why; returns the running breakdown, biggest first."""
        key = ("against the slower clock" if "higher timeframe" in reason else "against the trend" if "against the trend" in reason
               else "a weaker zone" if "weaker zone" in reason else "no room to 1:2" if "no room" in reason else "other")
        self.passes[key] = self.passes.get(key, 0) + 1
        return ", ".join(f"{v} {k}" for k, v in sorted(self.passes.items(), key=lambda kv: -kv[1]))

    def config_id(self) -> str:
        """A short fingerprint of the rules this strategy trades by (the rules' version plus every setting). A log row carries it, so
        a change of rules partway through a test is visible and the evidence counts only the rules in force now."""
        import hashlib

        from .analyst import RULES_VERSION

        return hashlib.sha1(repr((RULES_VERSION, self._config)).encode()).hexdigest()[:8]

    def read_now(self):
        """The reading of the chart as it stands (None until there are enough bars), and the candles it was made from."""
        candles = self._trigger.last(self._window)
        if len(candles) < self._lookback + self._strength * 2 + 2:
            return None
        return read_chart(candles, higher=[b.last(self._window) for b in self._higher] or None, strength=self._strength,
                          lookback=self._lookback, risk_reward=self._risk_reward, stale_bars=self._stale_bars, counter_trend=self._counter_trend,
                          stop_buffer=self._stop_buffer, strict_choch=self._strict_choch, confluence_beats_clock=self._confluence, zones_block_path=self._walls,
                          velocity_gate=self._velocity, min_pushed=self._min_pushed, equilibrium=self._equilibrium)

    def describe(self) -> str:
        """What the chart says right now, in a few words — for the moment a live run starts, so the person watching can
        check it is reading the chart they are looking at: structure, who is in control, the zones still standing."""
        candles = self._trigger.last(self._window)
        r = self.read_now()
        if r is None:
            return f"only {len(candles)} bar(s) so far — not enough to read yet"
        fresh = [z for z in r.zones if z.verdict == "TRUE" and z.status == "fresh"]
        zones = "; ".join(f"{z.kind} {z.low:.2f}-{z.high:.2f}" + (" (weaker)" if z.weaker else "") for z in fresh[-4:]) or "none"
        control = r.control[-1].value if r.control and r.control[-1] else "not yet decided"
        last = f"{r.events[-1].kind.value} {r.events[-1].verdict.value} at {r.events[-1].level:.2f}" if r.events else "none yet"
        price = candles[-1].close
        return (f"{len(candles)} bars, last close {price:.2f}; structure {r.structure[-1].value}, {control} in control; "
                f"fresh true zones: {zones}; last event: {last}")

    def _on_trigger_bar(self, closed: Candle) -> None:
        candles = self._trigger.last(self._window)
        if len(candles) < self._lookback + self._strength * 2 + 2:
            self.last_view = f"warming up ({len(candles)} bars)"
            return
        armed = self._armed
        if armed is not None:
            dead = closed.close > armed.block.price_high if armed.block.direction is Direction.DOWN else closed.close < armed.block.price_low
            if dead:
                self._armed = None
                self.last_view = "dropped: the bar closed through the block's far edge — dead zone"
        reading = read_chart(
            candles, higher=[b.last(self._window) for b in self._higher] or None, strength=self._strength,
            lookback=self._lookback, risk_reward=self._risk_reward, stale_bars=self._stale_bars, counter_trend=self._counter_trend,
            stop_buffer=self._stop_buffer, strict_choch=self._strict_choch, confluence_beats_clock=self._confluence, zones_block_path=self._walls,
            velocity_gate=self._velocity, min_pushed=self._min_pushed, equilibrium=self._equilibrium,
        )
        self.reading = reading
        last = len(candles) - 1
        # An order that left the book on this bar: say which and why, so the person watching never sees one vanish unexplained.
        for gone in reading.opportunities:
            if gone.closed_at == last and gone.state in (State.CANCELLED, State.DEAD):
                self._note = f"{'sell' if gone.direction is Direction.DOWN else 'buy'} order at {gone.entry:.2f} withdrawn — {gone.reason.removeprefix('withdrawn: ')}"
        # Standing orders, not just new ones: every opportunity the reading still has ARMED (a zone waiting to be tapped,
        # a block waiting for its retrace) is what the person would have a limit order at right now. Take the nearest.
        standing = [o for o in reading.opportunities if o.state is State.ARMED and o.target is not None
                    and self._signature(TradePlan(o.direction, stop=o.stop, target=o.target), o.block) not in self._taken]
        price = candles[-1].close
        if standing:
            opp = min(standing, key=lambda o: abs(o.entry - price))
            plan = TradePlan(opp.direction, stop=opp.stop, target=opp.target)
            same = self._armed is not None and self._armed.plan == plan and self._armed.block == opp.block
            self._armed = self._armed if same else _Armed(plan=plan, block=opp.block, reason=f"smc: {opp.reason}")
            self.last_view = self._waiting_words(opp, price, len(standing)) + (f" [last: {self._note}]" if self._note else "")
            return
        if self._armed is not None:
            self._armed = None  # nothing qualifies any more: the order is withdrawn
        fresh = [o for o in reading.opportunities if o.armed_at == last]
        if not fresh:
            latest = reading.events[-1] if reading.events else None
            what = f"{reading.structure[-1].value} structure" + (f"; last event {latest.kind.value} {latest.verdict.value} at {latest.level:.2f}" if latest else "")
            self.last_view = what + (f" [last: {self._note}]" if self._note else "")
            return
        opp = fresh[0]
        total = self._note_pass(opp.reason)
        self.last_view = f"passed on a setup — {opp.reason}. Passed on {sum(self.passes.values())} so far: {total}"

    @staticmethod
    def _waiting_words(opp, price: float, count: int) -> str:
        """The standing order as the trader would say it: what he waits for, where he is wrong, where it pays, and why."""
        long = opp.direction is Direction.UP
        lo, hi = sorted((opp.block.price_low, opp.block.price_high))
        why = ("a fresh true " + ("demand" if long else "supply") + " zone") if opp.source == "zone" else "the block left when the trend changed character"
        extras = opp.reason.split("conviction: ")[1] if "conviction: " in opp.reason else ""
        more = f" ({count - 1} more waiting)" if count > 1 else ""
        return (f"waiting to {'buy' if long else 'sell'} when price {'falls' if long else 'rises'} to {lo:.2f}-{hi:.2f}, "
                f"{abs(opp.entry - price):.2f} {'below' if long else 'above'} now. Wrong beyond {opp.stop:.2f}, target {opp.target:.2f}, "
                f"{opp.reward_risk:.1f} to 1. Why: {why}{' (' + extras + ')' if extras else ''}{more}")

    @staticmethod
    def _signature(plan: TradePlan, block: OrderBlock) -> tuple:
        return (plan.direction.value, round(plan.stop, 6), round(plan.target, 6), round(block.price_low, 6), round(block.price_high, 6))

    def _fill(self, price: float) -> TradeDecision | None:
        """Fill the waiting order the moment price trades back into the block."""
        armed = self._armed
        if armed is None:
            return None
        block = armed.block
        reached = price <= block.price_high if block.direction is Direction.UP else price >= block.price_low
        if not reached:
            return None
        if not armed.plan.is_well_formed(price):
            self.last_view = f"abandoned: price reached the block at {price:.5f} with the plan no longer valid"
            self._armed = None
            return None
        self._armed = None
        self._taken.add(self._signature(armed.plan, block))
        return TradeDecision(armed.plan, self._stake, f"{armed.reason}; filled at {price:.5f}")


def _typical_range(candles: Sequence, lookback: int) -> float:
    """The median candle range — what sets a level's width everywhere in this package."""
    recent = candles[-lookback:]
    if not recent:
        return 0.0
    ranges = sorted(c.range for c in recent)
    return ranges[len(ranges) // 2]
