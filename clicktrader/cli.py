"""``clicktrader`` — check a recording, replay a strategy over it, or make a synthetic one."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .forex.harness import replay as forex_replay
from .forex.strategies import REGISTRY as FOREX_REGISTRY
from .forex.synthetic import synthetic_price_records
from .forex.trade_harness import replay_trades
from .forex.trade_strategies import TRADE_REGISTRY, build as build_trade_strategy
from .harness import replay
from .ledger import DecisionLedger
from .recording import Recorder, read_recording
from .risk_replay import replay_sessions
from .stats import SampleTooSmall, digit_independence, digit_uniformity
from .strategies import REGISTRY
from .synthetic import synthetic_records


def _load(path: str):
    records = list(read_recording(path))
    synthetic = sum(1 for r in records if r.extra.get("synthetic"))
    if synthetic:
        print(f"note: {synthetic}/{len(records)} records are SYNTHETIC — nothing here describes a real feed\n")
    imported = sum(1 for r in records if r.extra.get("source") == "deriv-history")
    if imported:
        print(
            f"note: {imported}/{len(records)} records were reconstructed from imported candles (four points "
            "per bar) — the prices are the broker's, the timestamps inside each bar are not\n"
        )
    return [r.tick for r in records]


def cmd_buy_multiplier(args: argparse.Namespace) -> int:
    """Place ONE Multipliers contract carrying a stop and a target — the product this project's trade plans
    are actually written for. Rise/Fall expires and pays; only this one accepts the two levels a plan is
    made of, which is why the SMC engine could never be traded without it."""
    import os

    import websocket

    from .api.deriv import DerivAPIError, get_otp_url
    from .api.deriv.trading import MAX_MULTIPLIER_NOTIONAL, get_balance, place_multiplier

    if args.stake > args.max_stake:
        print(f"stake {args.stake} exceeds --max-stake {args.max_stake}; refusing.")
        return 2
    if args.stake * args.multiplier > MAX_MULTIPLIER_NOTIONAL:
        print(f"{args.stake:g} at multiplier {args.multiplier} is {args.stake * args.multiplier:g} of "
              f"exposure; this account refuses more than {MAX_MULTIPLIER_NOTIONAL:g}.")
        return 2
    missing = [n for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID") if not os.environ.get(n)]
    if missing:
        print(f"missing {', '.join(missing)} — demo only. Nothing placed.")
        return 2
    token, app_id, account_id = (os.environ[n] for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID"))
    print(f"demo account (id from .env): pricing {args.direction} {args.symbol} stake {args.stake} "
          f"x{args.multiplier} = {args.stake * args.multiplier:g} exposure; stop {args.stop} target {args.take_profit}")

    trade_ws = None
    try:
        trade_ws = websocket.create_connection(get_otp_url(account_id, token, app_id, require_demo=True), timeout=20)
        balance, currency = get_balance(trade_ws)
        bought = place_multiplier(
            trade_ws, args.direction == "up", symbol=args.symbol, stake=args.stake,
            multiplier=args.multiplier, stop_loss=args.stop, take_profit=args.take_profit, currency=currency,
        )
        print(f"bought contract {bought.contract_id}: {bought.buy_price:.2f} {currency} at risk, "
              f"balance {balance:.2f} -> {bought.balance_after:.2f}, stop and target attached")
    except DerivAPIError as exc:
        print(f"Deriv API error: {exc}. Nothing further placed.")
        return 2
    except websocket.WebSocketException as exc:
        print(f"socket error: {exc}")
        return 2
    finally:
        if trade_ws is not None:
            trade_ws.close()
    return 0


def cmd_run_rise_fall(args: argparse.Namespace) -> int:
    """Run the method live: place a Rise/Fall on every signal, log it, and score variants in the shadows."""
    import os

    from .api.deriv import DerivAPIError
    from .limits import RiskLimits
    from .runner import run

    if args.stake > args.max_stake:
        print(f"stake {args.stake} exceeds --max-stake {args.max_stake}; refusing.")
        return 2
    if not args.paper:
        missing = [n for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID") if not os.environ.get(n)]
        if missing:
            print(f"missing {', '.join(missing)} — or pass --paper to score signals without placing anything.")
            return 2
    try:
        run(
            symbol=args.symbol, log_path=args.log, stake=args.stake, duration=args.duration,
            duration_unit=args.duration_unit, max_trades=args.max_trades, max_ticks=args.ticks,
            paper=args.paper, report_every=args.report_every,
            limits=RiskLimits(
                max_stake=args.max_stake, max_session_loss=args.max_session_loss,
                max_consecutive_losses=args.max_consecutive_losses,
            ),
        )
    except DerivAPIError as exc:
        print(f"Deriv API error: {exc}. Stopped; whatever was logged is written.")
        return 2
    return 0


def cmd_log_trade(args: argparse.Namespace) -> int:
    """Record a trade placed by hand, so it counts in the same tally as the loop's.

    A person watching the chart and pressing the button is the method as its author trades it — arguably
    the *best* evidence there is, since their eye carries context no rule does. That evidence was
    invisible to this project until it could be written down, and a trade that is not written down is
    exactly what turns a count into a collection of remembered wins.
    """
    import time

    from .trade_log import RiseFallTrade, TradeLog, tally

    profit = (args.payout - args.stake) if args.status == "won" else -args.stake
    with TradeLog(args.log) as log:
        log.write(
            RiseFallTrade(
                settled_at=args.settled_at or time.time(), symbol=args.symbol, direction=args.direction,
                stake=args.stake, buy_price=args.stake, payout=args.payout, status=args.status,
                profit=profit, duration=args.duration, duration_unit=args.duration_unit,
                currency=args.currency, reason=args.reason or "placed by hand",
            )
        )
    print(f"recorded: {args.direction} {args.symbol}, staked {args.stake:.2f}, "
          f"payout {args.payout:.2f}, {args.status} ({profit:+.2f})")
    print()
    print(tally(args.log).report())
    return 0


def cmd_trade_log(args: argparse.Namespace) -> int:
    from .trade_log import tally

    print(tally(args.log).report())
    return 0


def cmd_history_deriv(args: argparse.Namespace) -> int:
    # deferred like the other deriv commands: the extra is only needed if one of them actually runs
    from .api.deriv.history import candles_backwards, ticks_from_candles

    out = Path(args.out)
    if out.exists() and out.stat().st_size and not args.overwrite:
        print(
            f"{out} already holds data and recordings are append-only, so importing history into it would "
            "interleave old bars with new ones and break the time order every bar builder depends on.\n"
            "Pass --overwrite to replace it, or choose another path."
        )
        return 2
    if args.overwrite and out.exists():
        out.unlink()

    def progress(batch: int, total: int, oldest: int) -> None:
        stamp = datetime.fromtimestamp(oldest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"  +{batch} candles ({total}/{args.bars}) back to {stamp}")

    print(f"fetching up to {args.bars} x {args.granularity}s candles of {args.symbol} (paced at {args.pace}s)")
    candles = candles_backwards(
        args.symbol, bars=args.bars, granularity=args.granularity, batch=args.batch, pace=args.pace,
        on_batch=progress,
    )
    if not candles:
        print("no candles came back — nothing written")
        return 2
    records = ticks_from_candles(
        candles, symbol=args.symbol, granularity=args.granularity, decimals=args.decimals
    )
    with Recorder(args.out, fsync=False) as recorder:
        for record in records:
            recorder.write(record)
    first = datetime.fromtimestamp(int(candles[0]["epoch"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    last = datetime.fromtimestamp(int(candles[-1]["epoch"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(
        f"wrote {len(candles)} candles ({first} -> {last}) as {recorder.count} ticks to {args.out}\n"
        f"four points per bar: `forex-trade-replay`/`forex-replay` rebuild the identical bars from them"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    digits = [t.digit for t in _load(args.recording)]
    status = 0
    for test in (digit_uniformity, digit_independence):
        try:
            result = test(digits)
        except SampleTooSmall as refused:
            print(f"refused — {refused}")
            status = 2
            continue
        print(result.summary(args.alpha))
        if test is digit_uniformity:
            n = result.n
            print("  " + "  ".join(f"{d}:{c / n:.1%}" for d, c in result.counts.items()))
    return status


def cmd_replay(args: argparse.Namespace) -> int:
    ticks = _load(args.recording)
    strategy = REGISTRY[args.strategy]()
    with DecisionLedger(args.ledger) as ledger:
        result = replay(strategy, ticks, split=args.split, ledger=ledger, log_skips=args.log_skips)
    print(result.report())
    if args.ledger:
        print(f"\n{len(ledger.rows)} ledger rows appended to {args.ledger}")
    return 0


def cmd_replay_all(args: argparse.Namespace) -> int:
    from .stats import bonferroni_z

    ticks = _load(args.recording)
    names = args.strategies or sorted(REGISTRY)
    z = bonferroni_z(len(names), alpha=args.alpha)
    print(
        f"testing {len(names)} strategies together — interval widened to z={z:.2f} "
        f"(family-wise alpha={args.alpha:g}, vs. z=1.96 for one strategy alone) so a false positive from "
        f"testing this many at once stays about as unlikely as testing one alone\n"
    )
    of_note = []
    for name in names:
        result = replay(REGISTRY[name](), ticks, split=args.split, z=z)
        print(result.report())
        print()
        if not result.verdict.startswith(("No edge", "NO VERDICT")):
            of_note.append(name)
    if of_note:
        print(f"worth a second look (verdict was neither 'No edge' nor 'NO VERDICT'): {', '.join(of_note)}")
    else:
        print(f"all {len(names)} strategies: 'No edge' or 'NO VERDICT' even at the corrected interval width")
    return 0


def cmd_risk_replay(args: argparse.Namespace) -> int:
    from .limits import RiskLimits

    ticks = _load(args.recording)
    limits = RiskLimits(args.max_stake, args.max_session_loss, args.max_consecutive_losses)
    report = replay_sessions(REGISTRY[args.strategy], ticks, limits, session_ticks=args.session_ticks)
    print(report.report())
    return 0


def cmd_forex_replay(args: argparse.Namespace) -> int:
    ticks = _load(args.recording)
    result = forex_replay(FOREX_REGISTRY[args.strategy](), ticks, split=args.split)
    result.breakeven = args.breakeven
    print(result.report())
    return 0


def _parse_utc(text: str) -> float:
    """'2026-09-30 10:00' (UTC) or a bare epoch number, for --from / --to."""
    try:
        return float(text)
    except ValueError:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def cmd_smc_chart(args: argparse.Namespace) -> int:
    """Read a recording the way a person reads a chart, at one or several zoom levels, and draw what was seen.

    Zooming is the bar size (`--minutes 1 5 15` draws each); dragging is the time window (`--from` / `--to`, UTC).
    The reading is always of the whole recording, so moving the window never changes what is seen in it.
    `--mark PRICE` overlays a level you drew by hand and says how it compares with the engine's own levels."""
    from .forex.candles import TimeCandleBuilder
    from .forex.structure import SwingKind
    from .smc.analyst import READINGS, read_chart
    from .smc.draw import draw_reading

    def bars(minutes: float):
        builder = TimeCandleBuilder(minutes * 60.0)
        for record in read_recording(args.recording):
            builder.feed(record.tick.ts, float(record.tick.price))
        return builder.last(10**7)

    sizes = args.minutes or [15.0]
    lo_ts = _parse_utc(args.start) if args.start else None
    hi_ts = _parse_utc(args.end) if args.end else None
    structures: dict[float, str] = {}
    last_reading = None
    for minutes in sizes:
        candles = bars(minutes)
        if len(candles) < 30:
            print(f"{minutes:g}m: only {len(candles)} closed bar(s) in that recording — nothing worth reading")
            continue
        chain = [m for m in (args.higher_minutes or []) if m and m > minutes]
        higher = [bars(m) for m in chain] or None
        reading = read_chart(candles, higher=higher, stale_bars=_stale_for(args.stale_bars, minutes), counter_trend=args.counter_trend,
                              confluence_beats_clock=not args.strict_clock, zones_block_path=not args.no_zone_walls, min_pushed=2.0)
        first = next((i for i, c in enumerate(candles) if lo_ts is None or c.opened_at >= lo_ts), 0)
        stop = next((i for i, c in enumerate(candles) if hi_ts is not None and c.opened_at >= hi_ts), len(candles))
        out = args.out if len(sizes) == 1 else args.out.replace(".png", f".{minutes:g}m.png")
        if args.detail or args.mark:
            draw_reading(reading, out, bars=args.bars, start=first if (lo_ts or hi_ts) else None, end=stop if (lo_ts or hi_ts) else None, marks_owner=tuple(args.mark or ()))
        else:
            from .smc.trader_view import draw_trader_view

            # the picture is as the chart stood on its last drawn bar: a reading of the prefix is the same as the whole's up to there
            shown = reading if not hi_ts else read_chart(candles[:stop], higher=higher, stale_bars=_stale_for(args.stale_bars, minutes), counter_trend=args.counter_trend,
                                                       confluence_beats_clock=not args.strict_clock, zones_block_path=not args.no_zone_walls, min_pushed=2.0)
            for sentence in draw_trader_view(shown, out, bars=args.bars):
                print("  " + sentence)
        structures[minutes] = reading.structure[min(stop, len(candles)) - 1].value
        print(f"{minutes:g}m -> {out}")
        print("  " + reading.summary())
        for opp in reading.opportunities[-args.list :]:
            print(f"    bar {opp.armed_at}: {opp.direction.value} {opp.state.value}" + (f" ({opp.outcome})" if opp.outcome else "") + f" — {opp.reason}")
        last_reading = reading
        if args.mark:
            end_i = min(stop, len(candles)) - 1
            typical = sorted(c.range for c in candles[max(0, end_i - 20) : end_i + 1])[10 if end_i >= 20 else 0]
            for price in args.mark:
                inside = [b for b, born, died in reading.levels if born <= end_i and (died is None or died > end_i) and b.low - typical <= price <= b.high + typical]
                touches = [s for s in reading.swings if s.swing.index <= end_i and abs(s.swing.price - price) <= typical]
                lows = sum(1 for s in touches if s.swing.kind is SwingKind.LOW)
                print(f"  your level {price:.2f}: {len(touches)} swing(s) within one typical candle range ({typical:.2f}), {lows} of them lows; "
                      + (f"engine level(s) there: " + ", ".join(f"{b.low:.2f}-{b.high:.2f} ({b.touches} touches)" for b in inside) if inside else "NO engine level within one candle range of it"))
    if len(structures) > 1:
        print("structure by zoom: " + ", ".join(f"{m:g}m {v}" for m, v in structures.items()))
    if args.readings and last_reading is not None:
        print("choices this reading makes that are the project's own:")
        for line in READINGS:
            print("  -", line)
    return 0 if structures else 1


def cmd_smc_compare(args: argparse.Namespace) -> int:
    """Compare a person's markup of a chart with what the engine read, mark by mark.

    The markup is a JSON file (see docs/evidence/markup/): levels, zones, changes of character, sweeps, trades and
    no-trade windows, in prices and UTC times. Nothing here scores the engine as right or wrong; it says, for each
    mark, whether the engine said the same thing and, where it did not, what it said instead."""
    import json

    from .forex.candles import TimeCandleBuilder
    from .smc.analyst import EventKind, State, read_chart

    mk = json.loads(Path(args.markup).read_text())
    minutes = float(mk.get("minutes", 15))
    builder = TimeCandleBuilder(minutes * 60.0)
    for record in read_recording(args.recording):
        builder.feed(record.tick.ts, float(record.tick.price))
    candles = builder.last(10**7)
    clocks = []
    for hm in args.higher_minutes:
        if hm > minutes:
            hb = TimeCandleBuilder(hm * 60.0)
            for record in read_recording(args.recording):
                hb.feed(record.tick.ts, float(record.tick.price))
            clocks.append(hb.last(10**7))
    reading = read_chart(candles, higher=clocks or None)
    ts = lambda text: _parse_utc(text)  # noqa: E731
    lo_ts, hi_ts = ts(mk["from"]), ts(mk["to"])
    idx = [i for i, c in enumerate(candles) if lo_ts <= c.opened_at <= hi_ts]
    if not idx:
        print("no bars of that recording fall inside the markup's window")
        return 1
    first, last = idx[0], idx[-1]
    typical = sorted(c.range for c in candles[first : last + 1])[len(idx) // 2]
    at = lambda text: min(range(len(candles)), key=lambda i: abs(candles[i].opened_at - ts(text)))  # noqa: E731
    when = lambda i: datetime.fromtimestamp(candles[i].opened_at, tz=timezone.utc).strftime("%H:%M")  # noqa: E731
    in_win = lambda i: first <= i <= last  # noqa: E731
    print(f"window {mk['from']} -> {mk['to']} ({len(idx)} bars of {minutes:g}m; typical candle range {typical:.2f}); marker: {mk.get('marker', '?')}")

    bands = [(b, born, died) for b, born, died in reading.levels if born <= last and (died is None or died >= first)]
    hits = misses = label_only = 0
    for lv in mk.get("levels", []):
        near = [(b, born, died) for b, born, died in bands if b.low - typical <= lv["price"] <= b.high + typical]
        hits += bool(near); misses += not near
        print(f"level {lv['price']:.2f}: " + ("engine found " + "; ".join(f"{b.low:.2f}-{b.high:.2f} ({b.touches} touches, {'alive' if d is None else 'deleted at ' + when(d)})" for b, _, d in near[:4]) if near else "NO engine level within one candle range of it"))
    for z in mk.get("zones", []):
        over = [(b, born, died) for b, born, died in bands if b.low <= z["high"] and z["low"] <= b.high]
        dz = [d for d in reading.zones if d.valid and d.origin_index <= last and d.low <= z["high"] and z["low"] <= d.high
              and (d.died_at is None or d.died_at >= first) and (z.get("kind") is None or d.kind.lower() == z["kind"])]
        hits += bool(over or dz); misses += not (over or dz)
        said = []
        if dz:
            said.append(f"{len(dz)} supply/demand zone(s): " + ", ".join(f"{d.kind} {d.low:.2f}-{d.high:.2f} ({d.status})" for d in dz[:3]))
        if over:
            said.append(f"{len(over)} level band(s), e.g. " + ", ".join(f"{b.low:.2f}-{b.high:.2f}" for b, _, _ in over[:3]))
        print(f"zone {z['low']:.2f}-{z['high']:.2f}: " + ("; ".join(said) if said else "NO engine zone or band overlaps it"))
    marked_choch = []
    for ch in mk.get("changes_of_character", []):
        i = at(ch["at"]); marked_choch.append(i)
        want = "down" if ch["direction"] == "down" else "up"
        cand = [e for e in reading.events if e.kind is EventKind.CHOCH and abs(e.index - i) <= args.tolerance]
        same = [e for e in cand if e.direction.value == want]
        if same:
            hits += 1
            print(f"CHOCH {want} ~{ch['at'][-5:]} @{ch.get('price', '?')}: engine CHOCH at {when(same[0].index)} level {same[0].level:.2f}")
        else:
            # the same break at the same price under another name is a different disagreement from no break at all
            price = ch.get("price")
            alt = [e for e in reading.events if e.kind in (EventKind.BOS, EventKind.CHOCH) and e.direction.value == want
                   and abs(e.index - i) <= args.tolerance * 2 and price is not None and abs(e.level - float(price)) <= typical]
            alt.sort(key=lambda e: abs(e.level - float(price)))  # the event at the marked level, not merely a nearby one
            if alt:
                label_only += 1
                flipped = [e for e in reading.events if e.kind is EventKind.CHOCH and e.direction.value == want and e.index < alt[0].index][-1:]
                print(f"CHOCH {want} ~{ch['at'][-5:]} @{price}: SAME BREAK, DIFFERENT LABEL — engine has a {alt[0].kind.value} at {when(alt[0].index)} level {alt[0].level:.2f}"
                      + (f" (it had already called a CHOCH {want} at {when(flipped[0].index)}, so this one was a continuation)" if flipped else ""))
            else:
                misses += 1
                print(f"CHOCH {want} ~{ch['at'][-5:]} @{price}: " + ("engine had a CHOCH the other way at " + when(cand[0].index) if cand else "engine had NO break there within %d bars" % (args.tolerance * 2)))
    for sw in mk.get("sweeps", []):
        i = at(sw["at"])
        found = [e for e in reading.events if e.kind is EventKind.SWEEP and abs(e.index - i) <= args.tolerance]
        hits += bool(found); misses += not found
        print(f"sweep ~{sw['at'][-5:]} @{sw['price']}: " + (f"engine SWEEP at {when(found[0].index)} level {found[0].level:.2f}" if found else "engine did NOT call a sweep there"))
    marked_trades = []
    for tr in mk.get("trades", []):
        i = at(tr["at"]); marked_trades.append(i)
        want = "up" if tr["direction"] == "up" else "down"
        cand = [o for o in reading.opportunities if abs(o.armed_at - i) <= args.tolerance * 3]
        same = [o for o in cand if o.direction.value == want]
        ok = [o for o in same if o.is_true]
        hits += bool(ok); misses += not ok
        if ok:
            o = ok[0]; print(f"trade {want} ~{tr['at'][-5:]} entry {tr['entry']}: engine armed one at {when(o.armed_at)}: entry {o.entry:.2f} stop {o.stop:.2f} target {o.target:.2f} ({o.state.value}, {o.outcome or 'no outcome'})")
        elif same:
            print(f"trade {want} ~{tr['at'][-5:]}: engine saw it and REJECTED it — {same[0].state.value}: {same[0].reason}")
        else:
            print(f"trade {want} ~{tr['at'][-5:]}: engine found NO opportunity near it" + (f" (it had {len(cand)} the other way)" if cand else ""))
    for nt in mk.get("no_trade", []):
        a, b = at(nt["from"]), at(nt["to"])
        chs = [e for e in reading.events if e.kind is EventKind.CHOCH and a <= e.index <= b]
        opps = [o for o in reading.opportunities if a <= o.armed_at <= b and o.is_true]
        ok = not opps
        hits += ok; misses += not ok
        print(f"no-trade {nt['from'][-5:]}-{nt['to'][-5:]}: engine called {len(chs)} CHOCH and armed {len(opps)} trade(s) there" + ("" if ok else "  <-- it traded where the marker would not"))

    extra_ch = [e for e in reading.events if e.kind is EventKind.CHOCH and in_win(e.index) and not any(abs(e.index - m) <= args.tolerance for m in marked_choch)]
    extra_tr = [o for o in reading.opportunities if in_win(o.armed_at) and o.is_true and not any(abs(o.armed_at - m) <= args.tolerance * 3 for m in marked_trades)]
    print(f"engine CHOCHs the marker did not mark: {len(extra_ch)} (of {sum(1 for e in reading.events if e.kind is EventKind.CHOCH and in_win(e.index))} in the window)")
    print(f"engine trades the marker did not mark: {len(extra_tr)} (of {sum(1 for o in reading.opportunities if in_win(o.armed_at) and o.is_true)} armed in the window)")
    print(f"agreement on the marks given: {hits} of {hits + misses + label_only}" + (f" (+{label_only} with the level right and a different label)" if label_only else ""))
    return 0


def load_env_file(path: str = ".env") -> list[str]:
    """Fill in environment variables from a `KEY=VALUE` file, only those not already set; return the names it set.

    Values are never printed or returned. Understands `export KEY=value`, single or double quotes and `#` comments.
    Exists so a demo run does not depend on remembering `set -a && source .env && set +a` in every new terminal."""
    import os

    file = Path(path)
    if not file.is_file():
        return []
    loaded: list[str] = []
    for raw in file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def cmd_run_smc(args: argparse.Namespace) -> int:
    """Run the SMC engine on the live feed: PAPER by default (places nothing), or on the DEMO account with --place.

    There is no real-money option: the broker session is opened with require_demo=True and reads only
    DERIV_DEMO_ACCOUNT_ID. Paper mode needs no credentials at all."""
    import os

    from .api.deriv import DerivAPIError
    from .api.deriv.ticks import stream_ticks
    from .multipliers import DerivMultiplierBroker, run as run_multipliers
    from .smc.live import paper_run, warm_from_history
    from .smc.strategy import SmcStrategy

    if args.preset == "decks":
        args.minutes, args.higher_minutes = 60.0, [240.0, 1440.0]
        if args.warm_bars == 1000:
            args.warm_bars = 600  # 600 hourly bars = 25 days: enough for the 4-hour and daily charts to have swings
    chain = tuple(args.higher_minutes)  # an empty chain means no slower-clock veto at all
    inner = SmcStrategy(trigger_minutes=args.minutes, higher_minutes=chain, risk_reward=args.risk_reward,
                           stale_bars=_stale_for(args.stale_bars, args.minutes), counter_trend=args.counter_trend,
                           stop_buffer=args.stop_buffer, strict_choch=args.strict_trend_change,
                           confluence_beats_clock=not args.strict_clock, zones_block_path=not args.no_zone_walls,
                           velocity_gate=args.velocity_gate, min_pushed=args.min_pushed, equilibrium=args.equilibrium,
                           entry_model=args.entry, confirm_bars=args.confirm_bars)
    strategy = inner
    if args.smoke_test:
        from .smc.live import SmokeTest

        strategy = SmokeTest(inner, side=args.smoke_side, stake=args.stake, multiplier=args.multiplier)
        if args.max_trades is None:
            args.max_trades = 1
        if not args.log:
            args.log = "recordings/smc-smoke-trades.jsonl"  # its own file: a forced trade must never count as evidence
        print("SMOKE TEST: one forced small trade to check the whole path (place, watch, close, log, page). It is not a signal and is not logged as evidence.", flush=True)
    max_loss = args.max_loss_per_trade
    mode = "DEMO ACCOUNT (virtual money)" if args.place else "PAPER (nothing is placed)"
    caps = ", ".join(x for x in (
        f"at most {args.max_trades} trade(s)" if args.max_trades is not None else "",
        f"{args.max_seconds:.0f}s" if args.max_seconds is not None else "",
        f"max {max_loss:g} at risk per trade" if max_loss is not None else "") if x) or "no caps: it trades what it finds until you stop it (Ctrl-C)"
    print(f"{mode}: {args.symbol}, {args.minutes:g}m bars with slower clocks {'/'.join(f'{m:g}' for m in chain) or 'none (no veto)'}m, "
          f"stake {args.stake:g} x{args.multiplier}; {caps}", flush=True)
    if args.place:
        loaded = load_env_file()
        if loaded:
            print(f"read {', '.join(loaded)} from .env (values not shown)", flush=True)
        missing = [n for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID") if not os.environ.get(n)]
        if missing:
            print(f"missing {', '.join(missing)} — put them in .env in the project folder (KEY=value, one per line). Demo only. Nothing placed.")
            return 2
    if sys.stdin.isatty():  # a person at a terminal; a log-redirected or test run keeps Python's own handling
        _ctrl_c_always_works()
    try:
        if args.warm_bars:
            warm_from_history(strategy, args.symbol, minutes=_warm_granularity(args.minutes), bars=args.warm_bars, decimals=_decimals_for(args.symbol, args.decimals))
            print(f"right now it sees: {strategy.describe()}", flush=True)
        feed = stream_ticks(args.symbol)
        page = None
        if args.ui:
            page = _start_page(strategy, args, symbol=args.symbol, mode="demo account run" if args.place else "paper run")

            def _teed(source):
                for record in source:
                    page.observe(float(record.tick.price))
                    yield record

            feed = _teed(feed)
        log = args.log or ("recordings/smc-demo-trades.jsonl" if args.place else "recordings/smc-paper-trades.jsonl")
        if not args.place:
            paper_run(symbol=args.symbol, log_path=log, stake=args.stake, multiplier=args.multiplier, strategy=strategy,
                      ticks=feed, max_trades=args.max_trades, max_seconds=args.max_seconds, max_loss_per_trade=max_loss,
                      report_every=args.report_every, on_state=page.set_open if page else None)
            return 0
        broker = DerivMultiplierBroker(symbol=args.symbol, stake=args.stake, multiplier=args.multiplier)
        try:
            run_multipliers(symbol=args.symbol, log_path=log, stake=args.stake, multiplier=args.multiplier, strategy=strategy,
                            max_trades=args.max_trades, max_seconds=args.max_seconds, max_loss_per_trade=max_loss,
                            ticks=feed, broker=broker, report_every=args.report_every, on_state=page.set_open if page else None,
                            daily_loss_cap=args.daily_loss_cap)
        finally:
            broker.close()
    except DerivAPIError as exc:
        print(f"Deriv API error: {exc}")
        return 2
    except KeyboardInterrupt:
        print("stopped by you; whatever was logged is written.")
    return 0


def _ctrl_c_always_works(*, grace: float = 3.0) -> None:
    """Make Ctrl-C answer at once, whatever the main thread is blocked in.

    A signal handler only runs when the main thread next executes Python, so a live run stuck inside a socket call
    can ignore Ctrl-C for as long as the call lasts. Here SIGINT is taken by a dedicated thread: the first press
    says so immediately and asks the main thread to stop cleanly; if it has not stopped within `grace` seconds, or
    on a second press, the process leaves at once. Anything logged was fsynced row by row, and an open position
    keeps its stop and target at the broker."""
    import _thread
    import os
    import signal
    import threading

    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "pthread_sigmask"):
        return

    def leave(why: str) -> None:
        print(f"{why} — leaving now. Whatever was logged is written; an open position keeps its stop and target at the broker.", flush=True)
        os._exit(130)

    def waiter() -> None:
        signal.sigwait({signal.SIGINT})
        print("Ctrl-C received — stopping. Press it again to leave at once.", flush=True)
        _thread.interrupt_main()
        timer = threading.Timer(grace, leave, args=("not stopped after a few seconds",))
        timer.daemon = True
        timer.start()
        signal.sigwait({signal.SIGINT})
        leave("second Ctrl-C")

    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})  # the threads started below inherit the block
    threading.Thread(target=waiter, daemon=True).start()


def _decimals_for(symbol: str, given: int | None) -> int:
    """Price decimals the market quotes: gold and indices two, a yen pair three, other currency pairs five, synthetics two."""
    if given is not None:
        return given
    if symbol.startswith("frx"):
        return 2 if symbol[3:6] in ("XAU", "XAG") else 3 if symbol.endswith("JPY") else 5
    return 2


def _warm_granularity(minutes: float) -> float:
    """The candle size to warm with: the trigger's own when Deriv serves it, else one minute."""
    return minutes if minutes in (1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 480, 1440) else 1.0


def _stale_for(value: int | None, minutes: float) -> int | None:
    """How many bars an order may stand unfilled. Left alone it is automatic: 60 bars on a 1-minute chart (an hour), none on a
    slower one, where an order is meant to wait days. 0 means never; any other number is taken as given."""
    if value is None:
        return 60 if minutes <= 1 else None
    return value or None


def _start_page(strategy, args, *, symbol: str, mode: str):
    """Start the watch-only page on this machine and return the watcher that feeds it (the caller feeds it with `observe`)."""
    import threading
    import webbrowser

    from .ui.server import Watcher, balance_loop, serve

    os.makedirs("recordings/ui", exist_ok=True)
    watcher = Watcher(strategy, symbol=symbol, chart_path="recordings/ui/chart.png", mode=mode)
    if not getattr(args, "no_balance", False):
        threading.Thread(target=balance_loop, args=(watcher, symbol), daemon=True).start()
    first = getattr(args, "ui_port", None) or getattr(args, "port", 8765)
    server = None
    for port in range(first, first + 10):  # a busy port must never cost the run: take the next free one
        try:
            server = serve(watcher, port=port)
            break
        except OSError:
            continue
    if server is None:
        print(f"page not started: ports {first}-{first + 9} are all busy. The run carries on without it.", flush=True)
        return watcher
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    note = "" if port == first else f" (port {first} was busy)"
    print(f"page: {url}{note}  (watch-only: it shows this engine and cannot place a trade)", flush=True)
    if not getattr(args, "no_browser", False):
        webbrowser.open(url)
    return watcher


def cmd_ui(args: argparse.Namespace) -> int:
    """Stand-alone page: read the live feed with the same engine (paper, never placing) and serve it on 127.0.0.1."""
    from .api.deriv.ticks import stream_ticks
    from .smc.live import warm_from_history
    from .smc.strategy import SmcStrategy

    load_env_file()
    strategy = SmcStrategy(trigger_minutes=1.0, higher_minutes=tuple(args.higher_minutes), stale_bars=_stale_for(args.stale_bars, 1.0), counter_trend=args.counter_trend,
                           confluence_beats_clock=True, zones_block_path=True, min_pushed=2.0)
    warm_from_history(strategy, args.symbol, minutes=1.0, bars=args.warm_bars, decimals=_decimals_for(args.symbol, args.decimals))
    watcher = _start_page(strategy, args, symbol=args.symbol, mode="watching the live feed")
    try:
        watcher.follow(stream_ticks(args.symbol))
    except KeyboardInterrupt:
        print("stopped.")
    return 0


def cmd_smc_readiness(args: argparse.Namespace) -> int:
    """Say, in plain words, whether the logs of a live test are enough evidence. Exit code 0 only when READY."""
    from .smc.readiness import report

    ready, text = report(args.logs, min_trades=args.min_trades)
    print(text)
    return 0 if ready else 1


def cmd_forex_replay_all(args: argparse.Namespace) -> int:
    from .stats import bonferroni_z

    ticks = _load(args.recording)
    names = args.strategies or sorted(FOREX_REGISTRY)
    z = bonferroni_z(len(names), alpha=args.alpha)
    print(
        f"testing {len(names)} forex strategies together — interval widened to z={z:.2f} "
        f"(family-wise alpha={args.alpha:g}, vs. z=1.96 for one strategy alone) so a false positive from "
        f"testing this many at once stays about as unlikely as testing one alone\n"
    )
    of_note = []
    for name in names:
        result = forex_replay(FOREX_REGISTRY[name](), ticks, split=args.split, z=z)
        print(result.report())
        print()
        if not result.verdict.startswith(("No directional edge", "NO VERDICT")):
            of_note.append(name)
    if of_note:
        print(
            f"worth a second look (verdict was neither 'no directional edge' nor 'NO VERDICT'): "
            f"{', '.join(of_note)}"
        )
    else:
        print(
            f"all {len(names)} strategies: 'no directional edge' or 'NO VERDICT' even at the corrected "
            "interval width"
        )
    return 0


def cmd_forex_trade_replay(args: argparse.Namespace) -> int:
    ticks = _load(args.recording)
    strategy = build_trade_strategy(args.strategy, session_start_hour_utc=args.session_start_hour)
    result = replay_trades(strategy, ticks, split=args.split)
    print(result.report())
    return 0


def cmd_forex_simulate(args: argparse.Namespace) -> int:
    with Recorder(args.out, fsync=False) as recorder:
        for record in synthetic_price_records(args.ticks, seed=args.seed, drift=args.drift):
            recorder.write(record)
    print(f"wrote {recorder.count} synthetic price ticks to {args.out}")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    with Recorder(args.out, fsync=False) as recorder:
        for record in synthetic_records(args.ticks, seed=args.seed):
            recorder.write(record)
    print(f"wrote {recorder.count} synthetic ticks to {args.out}")
    return 0


def cmd_record_live(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .browser.cryptonichub import CryptonicHubAdapter
    from .browser.driver import DEFAULT_PROFILE_DIR, call_with_reconnect, open_page, wait_for_login

    profile_dir = Path(args.profile_dir) if args.profile_dir else DEFAULT_PROFILE_DIR
    page = open_page(args.url, profile_dir=profile_dir)
    wait_for_login(page)
    adapter = CryptonicHubAdapter(page)

    with Recorder(args.out) as recorder:
        record = call_with_reconnect(page, adapter.read_tick_record)
        recorder.write(record)
        last_price = record.tick.price
        print(f"recording to {args.out} — Ctrl+C to stop")
        try:
            while args.ticks is None or recorder.count < args.ticks:
                record = call_with_reconnect(page, lambda: adapter.wait_for_new_tick(last_price))
                recorder.write(record)
                last_price = record.tick.price
        except KeyboardInterrupt:
            pass
    print(f"wrote {recorder.count} ticks to {args.out}")
    return 0


def _now() -> float:
    """Indirection around `time.monotonic` so a test can drive the progress clock without patching the
    global `time` module out from under pytest itself."""
    return time.monotonic()


def _hms(seconds: float) -> str:
    """A duration as `8m20s`, or `2h05m00s` once it passes an hour — short enough to sit on one line."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s" if hours else f"{minutes}m{secs:02d}s"


def _progress_line(count: int, elapsed: float, target: int | None) -> str:
    """One plain-text progress line, not a TUI: ticks so far, time elapsed, and — only when a `--ticks`
    target was set — a rough time remaining, extrapolated from the average rate so far (which is all a
    steady feed honestly supports)."""
    line = f"{count} ticks  |  {_hms(elapsed)} elapsed"
    if target is not None and count:
        line += f"  |  ~{_hms((target - count) * (elapsed / count))} left of {target}"
    return line


def cmd_record_deriv(args: argparse.Namespace) -> int:
    from .api.deriv import DEFAULT_APP_ID, DerivAPIError, stream_ticks

    status = 0
    with Recorder(args.out) as recorder:
        print(f"recording {args.symbol} to {args.out} — Ctrl+C to stop")
        started = _now()
        last_progress = started
        try:
            for record in stream_ticks(args.symbol, app_id=args.app_id or DEFAULT_APP_ID):
                recorder.write(record)
                if args.ticks is not None and recorder.count >= args.ticks:
                    break
                now = _now()
                if args.progress_every > 0 and now - last_progress >= args.progress_every:
                    print(_progress_line(recorder.count, now - started, args.ticks))
                    last_progress = now
        except KeyboardInterrupt:
            pass
        except DerivAPIError as exc:
            print(f"\nDeriv API error: {exc}")
            status = 2
    print(f"wrote {recorder.count} ticks to {args.out}")
    return status


def _print_live_row(row) -> None:
    if row.action == "skip":
        print(".", end="", flush=True)
        return
    print()  # end the run of dots before a real event gets its own line
    if row.action == "bet":
        outcome = "WIN" if row.won else "LOSS"
        balance_note = f"  balance={row.account_balance:.2f}" if row.account_balance is not None else ""
        print(f"  {row.contract}  stake={row.stake:.2f}  -> {outcome}  pnl={row.pnl:+.2f}  session={row.balance:+.2f}{balance_note}")
    elif row.action == "blocked":
        print(f"  BLOCKED  {row.contract}  stake={row.stake:.2f}  — {row.reason}")


def cmd_buy_rise_fall(args: argparse.Namespace) -> int:
    """Place one Rise/Fall contract on the demo account and report the broker's own settlement.

    One contract, on purpose, and deliberately not a runner: the point of this command is to prove the
    path the method's product actually needs — price, buy, settle, and read back the payout the trade was
    really paid at — against a live broker rather than a reconstruction. Anything that trades repeatedly
    belongs behind its own command and its own limits discussion, which this is not.
    """
    import os

    import websocket

    from .api.deriv import DerivAPIError, get_otp_url
    from .api.deriv.trading import get_balance, place_rise_fall, wait_for_settlement

    if args.stake > args.max_stake:
        print(f"stake {args.stake} exceeds --max-stake {args.max_stake}; refusing. Raise the cap deliberately.")
        return 2
    missing = [n for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID") if not os.environ.get(n)]
    if missing:
        print(f"missing {', '.join(missing)} — see .context_ledger/memory/secrets/README.md. Nothing placed.")
        return 2
    token, app_id, account_id = (os.environ[n] for n in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID"))
    print(f"demo account (id from .env): pricing {args.direction} {args.symbol} "
          f"{args.duration}{args.duration_unit}, stake {args.stake} (cap {args.max_stake})")

    trade_ws = None
    try:
        trade_ws = websocket.create_connection(get_otp_url(account_id, token, app_id, require_demo=True), timeout=20)
        balance, currency = get_balance(trade_ws)
        bought = place_rise_fall(
            trade_ws, args.direction == "up", symbol=args.symbol, stake=args.stake, currency=currency,
            duration=args.duration, duration_unit=args.duration_unit,
        )
        roi = (bought.payout - bought.buy_price) / bought.buy_price
        # "matching the quote" was ambiguous and misled a reader once: it means the buy matched the
        # proposal *this account* was shown, which is not the number the public feed advertises.
        print(f"bought contract {bought.contract_id}: paid {bought.buy_price:.2f} {currency}, "
              f"payout {bought.payout:.2f} — a {roi:.2%} return, at this account's own quoted price")
        print(f"balance before {balance:.2f}, after {bought.balance_after:.2f}")
        print(f"waiting for the broker to settle {args.duration}{args.duration_unit}...")
        settled = wait_for_settlement(trade_ws, bought.contract_id, timeout=args.timeout)
        print(f"settled: {settled.status}, profit {settled.profit:+.2f} {currency}, "
              f"exit spot {settled.exit_spot}")
        if args.log:
            import time as _time

            from .trade_log import RiseFallTrade, TradeLog, tally

            with TradeLog(args.log) as log:
                log.write(
                    RiseFallTrade(
                        settled_at=_time.time(), symbol=args.symbol, direction=args.direction,
                        stake=args.stake, buy_price=bought.buy_price, payout=bought.payout,
                        status=settled.status, profit=settled.profit, contract_id=bought.contract_id,
                        duration=args.duration, duration_unit=args.duration_unit,
                        exit_spot=settled.exit_spot, currency=currency, reason=args.reason,
                    )
                )
            print(f"logged to {args.log} — {tally(args.log).trades} settled trade(s) in it now")
    except DerivAPIError as exc:
        print(f"Deriv API error: {exc}. Nothing further placed.")
        return 2
    except websocket.WebSocketException as exc:
        print(f"socket error: {exc}")
        return 2
    finally:
        if trade_ws is not None:
            trade_ws.close()
    return 0


def cmd_run_deriv(args: argparse.Namespace) -> int:
    import os

    import websocket

    from .api.deriv import DerivAPIError, get_otp_url, stream_ticks
    from .executor import run
    from .limits import RiskGuard, RiskLimits

    is_real = args.account == "real"
    account_env_var = "DERIV_REAL_ACCOUNT_ID" if is_real else "DERIV_DEMO_ACCOUNT_ID"

    missing = [name for name in ("DERIV_API_TOKEN", "DERIV_APP_ID", account_env_var) if not os.environ.get(name)]
    if missing:
        print(f"missing from the environment: {', '.join(missing)} — run `set -a && source .env && set +a` first")
        if is_real and account_env_var in missing:
            print(
                "note: DERIV_REAL_ACCOUNT_ID is separate from DERIV_DEMO_ACCOUNT_ID on purpose — "
                "switching to --account real never silently reuses the demo account's ID."
            )
        return 2

    token = os.environ["DERIV_API_TOKEN"]
    app_id = os.environ["DERIV_APP_ID"]
    account_id = os.environ[account_env_var]

    strategy = REGISTRY[args.strategy]()
    risk = RiskGuard(RiskLimits(args.max_stake, args.max_session_loss, args.max_consecutive_losses))

    if is_real:
        print("=" * 60)
        print("REAL-MONEY ACCOUNT SELECTED (--account real). Trades placed")
        print("from here use actual funds, not demo credit. Ctrl+C now to")
        print("back out if this wasn't intentional.")
        print("=" * 60)
    print(f"requesting an OTP session for {account_id} ({'REAL' if is_real else 'demo'})...")
    try:
        otp_url = get_otp_url(account_id, token, app_id, require_demo=not is_real)
    except DerivAPIError as exc:
        print(f"Deriv API error: {exc}")
        return 2

    trade_ws = websocket.create_connection(otp_url)
    ledger = DecisionLedger(args.ledger) if args.ledger else None
    print(f"running {strategy.name} live on {args.symbol} — Ctrl+C to stop")
    status = 0
    try:
        run(
            strategy,
            stream_ticks(args.symbol),
            trade_ws,
            symbol=args.symbol,
            currency=args.currency,
            risk=risk,
            min_stake=args.min_stake,
            ledger=ledger,
            on_row=_print_live_row,
            settle_timeout=args.settle_timeout,
        )
    except KeyboardInterrupt:
        pass
    except DerivAPIError as exc:
        print(f"\nDeriv API error: {exc}")
        status = 2
    finally:
        final_balance_note = ""
        try:
            from .api.deriv import get_balance

            balance, currency = get_balance(trade_ws)
            final_balance_note = f", balance {balance:.2f} {currency}"
        except Exception:
            pass  # best-effort -- the connection may already be unusable by the time we get here
        trade_ws.close()
        if ledger is not None:
            ledger.close()
    print(f"stopped — {risk.trades} trades, session P/L {risk.session_pnl:+.2f}{final_balance_note}, halted: {risk.halted_reason or 'no'}")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clicktrader", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="is the recorded feed uniform and independent?")
    check.add_argument("recording")
    check.add_argument("--alpha", type=float, default=0.01)
    check.set_defaults(func=cmd_check)

    rep = sub.add_parser("replay", help="replay a strategy over a recording, with a random control")
    rep.add_argument("recording")
    rep.add_argument("--strategy", choices=sorted(REGISTRY), default="random")
    rep.add_argument("--split", type=float, default=0.5, help="in-sample fraction (default 0.5)")
    rep.add_argument("--ledger", help="append every decision to this JSONL file")
    rep.add_argument("--log-skips", action="store_true", help="also log ticks where the strategy passed")
    rep.set_defaults(func=cmd_replay)

    rep_all = sub.add_parser(
        "replay-all",
        help="replay several strategies together, with the confidence interval widened for multiple comparisons",
    )
    rep_all.add_argument("recording")
    rep_all.add_argument("--strategies", nargs="*", choices=sorted(REGISTRY), help="default: every registered strategy")
    rep_all.add_argument("--split", type=float, default=0.5, help="in-sample fraction (default 0.5)")
    rep_all.add_argument("--alpha", type=float, default=0.05, help="family-wise false-positive rate to hold across the whole batch (default 0.05)")
    rep_all.set_defaults(func=cmd_replay_all)

    risk_rep = sub.add_parser(
        "risk-replay",
        help="session-by-session replay: measure how RiskGuard bounds drawdown vs. the same decisions unbounded",
    )
    risk_rep.add_argument("recording")
    risk_rep.add_argument("--strategy", choices=sorted(REGISTRY), default="martingale-low-digit-over")
    risk_rep.add_argument("--session-ticks", type=int, default=500, help="ticks per simulated session (default 500)")
    risk_rep.add_argument("--max-stake", type=float, required=True)
    risk_rep.add_argument("--max-session-loss", type=float, required=True)
    risk_rep.add_argument("--max-consecutive-losses", type=int, required=True)
    risk_rep.set_defaults(func=cmd_risk_replay)

    sim = sub.add_parser("simulate", help="write a SYNTHETIC uniform recording (pipeline testing only)")
    sim.add_argument("out")
    sim.add_argument("--ticks", type=int, default=10_000)
    sim.add_argument("--seed", type=int, default=0)
    sim.set_defaults(func=cmd_simulate)

    fx_rep = sub.add_parser("forex-replay", help="replay a forex directional strategy over a recording, horizon-based settlement")
    fx_rep.add_argument("recording")
    fx_rep.add_argument("--strategy", choices=sorted(FOREX_REGISTRY), default="random-direction")
    fx_rep.add_argument("--split", type=float, default=0.5, help="in-sample fraction (default 0.5)")
    fx_rep.add_argument(
        "--breakeven", type=float,
        help="win rate this contract needs to break even, e.g. 0.5119 for a 95.35%% Rise/Fall payout — "
             "prints the result as an answer instead of a hit rate",
    )
    fx_rep.set_defaults(func=cmd_forex_replay)

    smc_chart = sub.add_parser("smc-chart", help="read a recording like a trader at one or more zoom levels and draw it (PNG)")
    smc_chart.add_argument("recording")
    smc_chart.add_argument("out", help="PNG path to write (several --minutes write out.<m>m.png)")
    smc_chart.add_argument("--minutes", type=float, nargs="+", help="bar length(s) in minutes — the zoom (default 15)")
    smc_chart.add_argument("--higher-minutes", type=float, nargs="*", default=[60.0], help="slower clock(s) that must not contradict a trade — give several for a chain, none to disable (default 60)")
    smc_chart.add_argument("--from", dest="start", help="drag: first moment to show, UTC ('2026-09-30 07:00') or epoch")
    smc_chart.add_argument("--to", dest="end", help="drag: last moment to show (exclusive), UTC or epoch")
    smc_chart.add_argument("--bars", type=int, default=160, help="without --from/--to, how many of the latest bars to draw (default 160)")
    smc_chart.add_argument("--mark", type=float, nargs="+", help="price level(s) you drew by hand; overlaid and compared with the engine's levels")
    smc_chart.add_argument("--list", type=int, default=12, help="how many of the latest opportunities to print (default 12)")
    smc_chart.add_argument("--stale-bars", type=int, default=None, help="withdraw an order price has not come back to within this many bars (default: 60 on a 1-minute chart, none on slower ones; 0 = never)")
    smc_chart.add_argument("--counter-trend", action=argparse.BooleanOptionalAction, default=True, help="also take a zone against the trend when it is a premium/discount zone (Fibonacci 61.8-78.6 or a flip zone), like selling the supply above a long rally (default on; --no-counter-trend keeps the decks' with-the-trend-only rule)")
    smc_chart.add_argument("--no-zone-walls", action="store_true")
    smc_chart.add_argument("--strict-clock", action="store_true")
    smc_chart.add_argument("--detail", action="store_true", help="draw everything the engine knows (swings, every break, false zones) instead of the trader's few areas and the plan")
    smc_chart.add_argument("--readings", action="store_true", help="also print the choices this reading makes that are the project's own")
    smc_chart.set_defaults(func=cmd_smc_chart)

    ui = sub.add_parser("ui", help="one local page showing the engine's chart, plan, balance and trades (watch-only)")
    ui.add_argument("--symbol", default="R_100")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--higher-minutes", type=float, nargs="*", default=[5.0, 15.0])
    ui.add_argument("--stale-bars", type=int, default=None)
    ui.add_argument("--counter-trend", action=argparse.BooleanOptionalAction, default=True)
    ui.add_argument("--warm-bars", type=int, default=1000)
    ui.add_argument("--decimals", type=int, default=None)
    ui.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    ui.add_argument("--no-balance", action="store_true", help="do not look up the demo balance")
    ui.set_defaults(func=cmd_ui)

    smc_cmp = sub.add_parser("smc-compare", help="compare a person's markup of a chart (JSON) with what the engine read, mark by mark")
    smc_cmp.add_argument("markup", help="markup JSON, see docs/evidence/markup/")
    smc_cmp.add_argument("recording", help="recording of the same instrument and window (history-deriv makes one)")
    smc_cmp.add_argument("--higher-minutes", type=float, nargs="*", default=[5.0], help="slower clock(s) for the higher-timeframe veto (default 5)")
    smc_cmp.add_argument("--tolerance", type=int, default=8, help="bars either side within which an engine event counts as the marked one (default 8)")
    smc_cmp.set_defaults(func=cmd_smc_compare)

    run_smc = sub.add_parser("run-smc", help="run the SMC engine on the live feed: PAPER by default, --place for the DEMO account (never real money)")
    run_smc.add_argument("--symbol", default="R_100", help="Deriv symbol (default R_100; 1HZ100V is the 1-second index)")
    run_smc.add_argument("--minutes", type=float, default=1.0, help="trigger bar length in minutes (default 1, the view the owner charts)")
    run_smc.add_argument("--higher-minutes", type=float, nargs="*", default=[5.0, 15.0], help="slower clock(s) that must not contradict a trade (default 5 15, the decks' alignment across timeframes). Measured causally on 16-25h of data: 5+15 arms 0.4-0.7 trades/h, 5 alone 0.8-0.9/h, none 1.1-1.4/h (about half of those cancelled as falling knives). Give none (`--higher-minutes` alone) to drop the veto")
    run_smc.add_argument("--entry", choices=("limit", "confirm"), default="limit", help="limit: a resting order at the zone's near edge (the decks' aggressive entry, the default). confirm: wait inside the zone for a confirming candle and enter on its close (the decks' normal/conservative entry). On 1-minute synthetic data confirmation left only 0.07-0.15 trades an hour, so it is for hourly charts of real markets")
    run_smc.add_argument("--confirm-bars", type=int, default=5, help="with --entry confirm: bars to wait for the confirming candle before dropping the order (default 5)")
    run_smc.add_argument("--equilibrium", action="store_true", help="ALSO require a sell to sit in the upper half of the last 100 bars' range and a buy in the lower half (Institutional deck p10: demand 'in deep discount'). Off by default: measured properly it LOWERED the net result per hour in hindsight")
    run_smc.add_argument("--min-pushed", type=float, default=2.0, help="a zone is traded only if price travelled at least this many typical candle ranges away from it before coming back (the SMC deck's 'pushed distance'; default 2, 0 = off). In hindsight 2 kept most of the better win rate; 3 was stricter and traded less often")
    run_smc.add_argument("--velocity-gate", action="store_true", help="ALSO skip a zone when the last three bars of the return were violent, not only the bar that touched it (the Ultimate deck's checklist item 4). Off by default: in hindsight it removed 40%% of the trades and lowered the net result per hour; the falling-knife check on the touching bar stays on")
    run_smc.add_argument("--no-zone-walls", action="store_true", help="let a plan run through an opposing zone. By default a buy cannot target through a seller zone nor a sell through a buyer zone (the decks' 'room to move'); in hindsight that gave fewer, better trades")
    run_smc.add_argument("--strict-clock", action="store_true", help="the slower charts can never be overridden (the decks' top-down rule as written). By default the strongest zones - Fibonacci 61.8-78.6 or a flip zone - may go against a slower chart that has not turned yet; in hindsight that added trades at a slightly better result")
    run_smc.add_argument("--stop-buffer", type=float, default=0.0, help="put the stop this many typical candle ranges beyond the zone's far edge instead of on it (default 0; in hindsight a tighter stop did better, so this is only for testing)")
    run_smc.add_argument("--strict-trend-change", action="store_true", help="only take a trend-change (CHOCH) block when the slower charts have already turned the same way. In hindsight this removes almost all such trades (the slower charts lag), so it is off by default")
    run_smc.add_argument("--daily-loss-cap", type=float, default=None, help="stop the run for the day once the demo account is this much down since midnight UTC (default: none; decide this before the test, see docs/live-demo-test-protocol.md)")
    run_smc.add_argument("--smoke-test", action="store_true", help="place ONE small forced trade at once to test the whole path in minutes (not a signal; logged separately, never evidence)")
    run_smc.add_argument("--smoke-side", choices=("buy", "sell"), default="buy", help="direction of the --smoke-test trade (default buy)")
    run_smc.add_argument("--ui", action="store_true", help="also serve the one-page watch-only view of this run on 127.0.0.1 and open it in a browser")
    run_smc.add_argument("--ui-port", type=int, default=8765, help="port for --ui (default 8765)")
    run_smc.add_argument("--no-browser", action="store_true", help="with --ui: do not open a browser tab, just print the address")
    run_smc.add_argument("--stale-bars", type=int, default=None, help="withdraw an order price has not come back to within this many trigger bars (default: 60 on 1-minute bars, none on slower ones; 0 = never)")
    run_smc.add_argument("--counter-trend", action=argparse.BooleanOptionalAction, default=True, help="also take a zone against the trend when it is a premium/discount zone (Fibonacci 61.8-78.6 or a flip zone), like selling the supply above a long rally (default on; --no-counter-trend keeps the decks' with-the-trend-only rule)")
    run_smc.add_argument("--risk-reward", type=float, default=2.0, help="minimum reward:risk (default 2, the material's floor)")
    run_smc.add_argument("--stake", type=float, default=1.0)
    run_smc.add_argument("--multiplier", type=int, default=100)
    run_smc.add_argument("--max-trades", type=int, default=None, help="stop after this many trades (default: no cap — it trades what it finds until you stop it)")
    run_smc.add_argument("--max-seconds", type=float, default=None, help="stop after this many seconds (default: no cap)")
    run_smc.add_argument("--max-loss-per-trade", type=float, default=None, help="optional: refuse a plan whose stop is worth more than this (default: no limit)")
    run_smc.add_argument("--warm-bars", type=int, default=1000, help="one-minute bars of history to start with (default 1000; 0 = start blind)")
    run_smc.add_argument("--decimals", type=int, default=None, help="price decimals (default: by symbol - gold 2, a yen pair 3, other pairs 5, synthetics 2)")
    run_smc.add_argument("--preset", choices=("decks", "fast-test"), default=None, help="decks: the method as the decks teach it - 1-hour trigger, 4-hour and daily slower charts (hours to days per trade; use a real market such as frxXAUUSD or frxGBPAUD). fast-test: 1-minute bars, a plumbing test only (the default settings)")
    run_smc.add_argument("--report-every", type=float, default=60.0, help="seconds between status lines saying what the engine sees (default 60)")
    run_smc.add_argument("--log", default=None)
    run_smc.add_argument("--place", action="store_true", help="actually place orders on the DEMO account (default is paper: nothing placed)")
    run_smc.set_defaults(func=cmd_run_smc)

    smc_ready = sub.add_parser("smc-readiness", help="is the evidence from a live test enough? plain words; exit 0 only when READY")
    smc_ready.add_argument("logs", nargs="+", help="trade log file(s), paper and/or placed")
    smc_ready.add_argument("--min-trades", type=int, default=500, help="settled placed trades before a result can be told from luck (default 500; not a cap on the test)")
    smc_ready.set_defaults(func=cmd_smc_readiness)

    fx_rep_all = sub.add_parser(
        "forex-replay-all",
        help="replay several forex strategies together, with the confidence interval widened for multiple comparisons",
    )
    fx_rep_all.add_argument("recording")
    fx_rep_all.add_argument("--strategies", nargs="*", choices=sorted(FOREX_REGISTRY), help="default: every registered forex strategy")
    fx_rep_all.add_argument("--split", type=float, default=0.5, help="in-sample fraction (default 0.5)")
    fx_rep_all.add_argument("--alpha", type=float, default=0.05, help="family-wise false-positive rate to hold across the whole batch (default 0.05)")
    fx_rep_all.set_defaults(func=cmd_forex_replay_all)

    fx_sim = sub.add_parser("forex-simulate", help="write a SYNTHETIC driftless random-walk price recording (pipeline testing only)")
    fx_sim.add_argument("out")
    fx_sim.add_argument("--ticks", type=int, default=10_000)
    fx_sim.add_argument("--seed", type=int, default=0)
    fx_sim.add_argument("--drift", type=float, default=0.0, help="per-tick price drift (default 0.0 -- driftless is the null hypothesis)")
    fx_sim.set_defaults(func=cmd_forex_simulate)

    fx_trade = sub.add_parser(
        "forex-trade-replay",
        help="replay a stop/target forex strategy, reporting expectancy in R against the mirror of its own trades",
    )
    fx_trade.add_argument("recording")
    fx_trade.add_argument("--strategy", choices=sorted(TRADE_REGISTRY), default="sneaky-pivot")
    fx_trade.add_argument("--split", type=float, default=0.5, help="in-sample fraction (default 0.5)")
    fx_trade.add_argument(
        "--session-start-hour", type=int, default=0,
        help="UTC hour a trading day starts on (default 0) -- sets what \"yesterday's range\" means",
    )
    fx_trade.set_defaults(func=cmd_forex_trade_replay)

    live = sub.add_parser(
        "record-live", help="record real ticks from a live site (layer 1 — observes, trades nothing)"
    )
    live.add_argument("out")
    live.add_argument("--url", default="https://cryptonichub.pro/trade")
    live.add_argument("--profile-dir", help="persistent browser profile dir (default: ~/.clicktrader/browser-profile)")
    live.add_argument("--ticks", type=int, help="stop after this many ticks (default: run until Ctrl+C)")
    live.set_defaults(func=cmd_record_live)

    rf = sub.add_parser(
        "buy-rise-fall",
        help="place ONE Rise/Fall contract on the Deriv demo account and report the broker's settlement",
    )
    rf.add_argument("--direction", choices=("up", "down"), default="up")
    rf.add_argument("--symbol", default="1HZ25V", help="default 1HZ25V = Volatility 25 (the method's index)")
    rf.add_argument("--stake", type=float, default=1.0)
    rf.add_argument("--max-stake", type=float, default=1.0, help="hard cap this command will not exceed (default 1)")
    rf.add_argument("--duration", type=int, default=2, help="expiry length (default 2)")
    rf.add_argument("--duration-unit", default="m", choices=("m", "t"), help="minutes, or ticks (1-10)")
    rf.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for settlement")
    rf.add_argument("--log", help="append the settled trade to this log file (see trade-log)")
    rf.add_argument("--reason", default="", help="why this trade was taken, for the log")
    rf.set_defaults(func=cmd_buy_rise_fall)

    run_rf = sub.add_parser(
        "run-rise-fall",
        help="run the price-action method live: place one Rise/Fall per signal, log it, score variants in shadow",
    )
    run_rf.add_argument("--symbol", default="1HZ25V")
    run_rf.add_argument("--log", default="runs/rise-fall.jsonl", help="where settled trades are appended")
    run_rf.add_argument("--stake", type=float, default=1.0)
    run_rf.add_argument("--max-stake", type=float, default=1.0, help="hard cap this run will not exceed")
    run_rf.add_argument("--max-session-loss", type=float, default=10.0)
    run_rf.add_argument("--max-consecutive-losses", type=int, default=5)
    run_rf.add_argument("--duration", type=int, default=2)
    run_rf.add_argument("--duration-unit", default="m", choices=("m", "t"))
    run_rf.add_argument("--max-trades", type=int, help="stop after this many placed trades")
    run_rf.add_argument("--ticks", type=int, help="stop after this many ticks")
    run_rf.add_argument("--paper", action="store_true", help="score the signals and the shadows, place nothing")
    run_rf.add_argument("--report-every", type=float, default=900.0, help="seconds between readouts")
    run_rf.set_defaults(func=cmd_run_rise_fall)

    lt = sub.add_parser(
        "log-trade",
        help="record a trade placed by hand so it counts in the same tally as the loop's",
    )
    lt.add_argument("--log", default="recordings/rise-fall-demo.jsonl")
    lt.add_argument("--direction", choices=("up", "down"), required=True)
    lt.add_argument("--stake", type=float, required=True)
    lt.add_argument("--payout", type=float, required=True, help="what the contract paid if it won")
    lt.add_argument("--status", choices=("won", "lost"), required=True)
    lt.add_argument("--symbol", default="1HZ25V")
    lt.add_argument("--duration", type=int, default=2)
    lt.add_argument("--duration-unit", default="m")
    lt.add_argument("--currency", default="USD")
    lt.add_argument("--reason", default="", help="why you took it, in a sentence")
    lt.add_argument("--settled-at", type=float, help="epoch seconds; default now")
    lt.set_defaults(func=cmd_log_trade)

    tl = sub.add_parser(
        "trade-log",
        help="add up a log of real Rise/Fall trades and say whether it is winning in plain words",
    )
    tl.add_argument("log")
    tl.set_defaults(func=cmd_trade_log)

    bm = sub.add_parser(
        "buy-multiplier",
        help="place ONE Multipliers contract with a stop and a target (demo only) — the product a trade plan fits",
    )
    bm.add_argument("--direction", choices=("up", "down"), default="up")
    bm.add_argument("--symbol", default="1HZ100V")
    bm.add_argument("--stake", type=float, default=1.0)
    bm.add_argument("--max-stake", type=float, default=1.0)
    bm.add_argument("--multiplier", type=int, default=100)
    bm.add_argument("--stop", type=float, required=True, help="stop-loss price level")
    bm.add_argument("--take-profit", type=float, required=True, help="take-profit price level")
    bm.set_defaults(func=cmd_buy_multiplier)

    hist = sub.add_parser(
        "history-deriv",
        help="import candles from Deriv's public API as a recording (paced, and it refuses to append)",
    )
    hist.add_argument("out")
    hist.add_argument("--symbol", default="frxXAUUSD", help="default frxXAUUSD = gold; frxEURUSD = EUR/USD")
    hist.add_argument("--granularity", type=int, default=900, help="candle size in seconds (default 900 = 15m)")
    hist.add_argument("--bars", type=int, default=2000, help="how many candles to fetch, back from now")
    hist.add_argument("--batch", type=int, default=5000, help="candles to ask for per request")
    hist.add_argument("--pace", type=float, default=6.0, help="seconds between requests; the endpoint rate-limits")
    hist.add_argument("--decimals", type=int, default=2, help="price decimals to store (gold quotes 2)")
    hist.add_argument("--overwrite", action="store_true", help="replace the file if it already has data")
    hist.add_argument("--app-id", type=int, help="default: Deriv's shared public test app_id (1089)")
    hist.set_defaults(func=cmd_history_deriv)

    deriv = sub.add_parser(
        "record-deriv", help="record real ticks from Deriv's public WebSocket API (layer 1, no auth needed)"
    )
    deriv.add_argument("out")
    deriv.add_argument("--symbol", default="1HZ10V", help="Deriv symbol, e.g. 1HZ10V = Volatility 10 (1s) Index")
    deriv.add_argument("--app-id", type=int, help="default: Deriv's shared public test app_id (1089)")
    deriv.add_argument("--ticks", type=int, help="stop after this many ticks (default: run until Ctrl+C)")
    deriv.add_argument(
        "--progress-every", type=float, default=60.0, metavar="SECONDS",
        help="print a progress line every SECONDS while recording (0 disables; default 60)",
    )
    deriv.set_defaults(func=cmd_record_deriv)

    run_deriv = sub.add_parser(
        "run-deriv",
        help="layer 3: watch live Deriv ticks and place contracts (demo by default, --account real for live funds), gated by RiskGuard on every trade",
    )
    run_deriv.add_argument(
        "--account", choices=("demo", "real"), default="demo",
        help="demo (default) uses DERIV_DEMO_ACCOUNT_ID; real uses the separate DERIV_REAL_ACCOUNT_ID and places live trades",
    )
    run_deriv.add_argument("--strategy", choices=sorted(REGISTRY), default="low-digit-over")
    run_deriv.add_argument("--symbol", default="1HZ10V")
    run_deriv.add_argument("--currency", default="USD")
    run_deriv.add_argument("--min-stake", type=float, default=0.35, help="broker minimum for this contract/symbol/duration")
    run_deriv.add_argument("--max-stake", type=float, required=True)
    run_deriv.add_argument("--max-session-loss", type=float, required=True)
    run_deriv.add_argument("--max-consecutive-losses", type=int, required=True)
    run_deriv.add_argument("--ledger", help="append every decision to this JSONL file")
    run_deriv.add_argument("--settle-timeout", type=float, default=10.0, help="seconds to wait for the broker's own settlement before raising (default 10)")
    run_deriv.set_defaults(func=cmd_run_deriv)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
