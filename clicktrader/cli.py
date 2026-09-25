"""``clicktrader`` — check a recording, replay a strategy over it, or make a synthetic one."""

from __future__ import annotations

import argparse
import sys

from .harness import replay
from .ledger import DecisionLedger
from .recording import Recorder, read_recording
from .stats import SampleTooSmall, digit_independence, digit_uniformity
from .strategies import REGISTRY
from .synthetic import synthetic_records


def _load(path: str):
    records = list(read_recording(path))
    synthetic = sum(1 for r in records if r.extra.get("synthetic"))
    if synthetic:
        print(f"note: {synthetic}/{len(records)} records are SYNTHETIC — nothing here describes a real feed\n")
    return [r.tick for r in records]


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


def cmd_record_deriv(args: argparse.Namespace) -> int:
    from .api.deriv import DEFAULT_APP_ID, stream_ticks

    with Recorder(args.out) as recorder:
        print(f"recording {args.symbol} to {args.out} — Ctrl+C to stop")
        try:
            for record in stream_ticks(args.symbol, app_id=args.app_id or DEFAULT_APP_ID):
                recorder.write(record)
                if args.ticks is not None and recorder.count >= args.ticks:
                    break
        except KeyboardInterrupt:
            pass
    print(f"wrote {recorder.count} ticks to {args.out}")
    return 0


def _print_live_row(row) -> None:
    if row.action == "skip":
        print(".", end="", flush=True)
        return
    print()  # end the run of dots before a real event gets its own line
    if row.action == "bet":
        outcome = "WIN" if row.won else "LOSS"
        print(f"  {row.contract}  stake={row.stake:.2f}  -> {outcome}  pnl={row.pnl:+.2f}  session={row.balance:+.2f}")
    elif row.action == "blocked":
        print(f"  BLOCKED  {row.contract}  stake={row.stake:.2f}  — {row.reason}")


def cmd_run_deriv(args: argparse.Namespace) -> int:
    import os

    import websocket

    from .api.deriv import get_otp_url, stream_ticks
    from .executor import run
    from .limits import RiskGuard, RiskLimits

    missing = [name for name in ("DERIV_API_TOKEN", "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID") if not os.environ.get(name)]
    if missing:
        print(f"missing from the environment: {', '.join(missing)} — run `set -a && source .env && set +a` first")
        return 2

    token = os.environ["DERIV_API_TOKEN"]
    app_id = os.environ["DERIV_APP_ID"]
    account_id = os.environ["DERIV_DEMO_ACCOUNT_ID"]

    strategy = REGISTRY[args.strategy]()
    risk = RiskGuard(RiskLimits(args.max_stake, args.max_session_loss, args.max_consecutive_losses))

    print(f"requesting an OTP session for {account_id} (demo only — this refuses a real-money URL)...")
    otp_url = get_otp_url(account_id, token, app_id, require_demo=True)
    trade_ws = websocket.create_connection(otp_url)
    ledger = DecisionLedger(args.ledger) if args.ledger else None
    print(f"running {strategy.name} live on {args.symbol} — Ctrl+C to stop")
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
        )
    except KeyboardInterrupt:
        pass
    finally:
        trade_ws.close()
        if ledger is not None:
            ledger.close()
    print(f"stopped — {risk.trades} trades, session P/L {risk.session_pnl:+.2f}, halted: {risk.halted_reason or 'no'}")
    return 0


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

    sim = sub.add_parser("simulate", help="write a SYNTHETIC uniform recording (pipeline testing only)")
    sim.add_argument("out")
    sim.add_argument("--ticks", type=int, default=10_000)
    sim.add_argument("--seed", type=int, default=0)
    sim.set_defaults(func=cmd_simulate)

    live = sub.add_parser(
        "record-live", help="record real ticks from a live site (layer 1 — observes, trades nothing)"
    )
    live.add_argument("out")
    live.add_argument("--url", default="https://cryptonichub.pro/trade")
    live.add_argument("--profile-dir", help="persistent browser profile dir (default: ~/.clicktrader/browser-profile)")
    live.add_argument("--ticks", type=int, help="stop after this many ticks (default: run until Ctrl+C)")
    live.set_defaults(func=cmd_record_live)

    deriv = sub.add_parser(
        "record-deriv", help="record real ticks from Deriv's public WebSocket API (layer 1, no auth needed)"
    )
    deriv.add_argument("out")
    deriv.add_argument("--symbol", default="1HZ10V", help="Deriv symbol, e.g. 1HZ10V = Volatility 10 (1s) Index")
    deriv.add_argument("--app-id", type=int, help="default: Deriv's shared public test app_id (1089)")
    deriv.add_argument("--ticks", type=int, help="stop after this many ticks (default: run until Ctrl+C)")
    deriv.set_defaults(func=cmd_record_deriv)

    run_deriv = sub.add_parser(
        "run-deriv",
        help="layer 3: watch live Deriv ticks and place real contracts on the DEMO account, gated by RiskGuard on every trade",
    )
    run_deriv.add_argument("--strategy", choices=sorted(REGISTRY), default="low-digit-over")
    run_deriv.add_argument("--symbol", default="1HZ10V")
    run_deriv.add_argument("--currency", default="USD")
    run_deriv.add_argument("--min-stake", type=float, default=0.35, help="broker minimum for this contract/symbol/duration")
    run_deriv.add_argument("--max-stake", type=float, required=True)
    run_deriv.add_argument("--max-session-loss", type=float, required=True)
    run_deriv.add_argument("--max-consecutive-losses", type=int, required=True)
    run_deriv.add_argument("--ledger", help="append every decision to this JSONL file")
    run_deriv.set_defaults(func=cmd_run_deriv)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
