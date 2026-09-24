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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
