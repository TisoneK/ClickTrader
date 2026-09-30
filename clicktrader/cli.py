"""``clicktrader`` — check a recording, replay a strategy over it, or make a synthetic one."""

from __future__ import annotations

import argparse
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


def cmd_smc_chart(args: argparse.Namespace) -> int:
    """Read a recording the way a person reads a chart, and draw what the analyst saw (PNG) with a summary."""
    from .forex.candles import TimeCandleBuilder
    from .smc.analyst import READINGS, read_chart
    from .smc.draw import draw_reading

    def bars(minutes: float):
        builder = TimeCandleBuilder(minutes * 60.0)
        for record in read_recording(args.recording):
            builder.feed(record.tick.ts, float(record.tick.price))
        return builder.last(10**7)

    candles = bars(args.minutes)
    if len(candles) < 30:
        print(f"only {len(candles)} closed bar(s) of {args.minutes:g} minutes in that recording — nothing worth reading")
        return 1
    higher = bars(args.higher_minutes) if args.higher_minutes else None
    reading = read_chart(candles, higher=higher)
    draw_reading(reading, args.out, bars=args.bars)
    print(f"wrote {args.out}")
    print(reading.summary())
    for opp in reading.opportunities[-args.list :]:
        print(f"  bar {opp.armed_at}: {opp.direction.value} {opp.state.value}" + (f" ({opp.outcome})" if opp.outcome else "") + f" — {opp.reason}")
    if args.readings:
        print("choices this reading makes that are the project's own:")
        for line in READINGS:
            print("  -", line)
    return 0


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

    smc_chart = sub.add_parser("smc-chart", help="read a recording like a trader (swings, levels, gaps, breaks, opportunities) and draw it (PNG)")
    smc_chart.add_argument("recording")
    smc_chart.add_argument("out", help="PNG path to write")
    smc_chart.add_argument("--minutes", type=float, default=15.0, help="bar length in minutes (default 15)")
    smc_chart.add_argument("--higher-minutes", type=float, default=60.0, help="slower clock that must not contradict a trade; 0 disables (default 60)")
    smc_chart.add_argument("--bars", type=int, default=160, help="how many of the most recent bars to draw (default 160)")
    smc_chart.add_argument("--list", type=int, default=12, help="how many of the latest opportunities to print (default 12)")
    smc_chart.add_argument("--readings", action="store_true", help="also print the choices this reading makes that are the project's own")
    smc_chart.set_defaults(func=cmd_smc_chart)

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
