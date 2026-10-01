"""Is the evidence there? A plain-words reading of the logs a live test produces.

It is **not a cap or a gate on the test**: the test trades whatever it finds. It only says what the logs do and do not
show, and the trade count it asks for is a statistical fact about how many settled trades it takes before a result can
be told from luck, not a rule carried over from the old digit work — pass `--min-trades` to change it.

It does not decide to trade. The bar is the project's own: at least
`MIN_TRADES` settled trades (the same 500 every verdict here needs), and the 95% interval of the mean result per unit
of risk sitting wholly above zero. Two kinds of rows are kept apart on purpose:

- **paper** rows (`"mode": "paper"`) come from `paper_run`: no orders, no commission, no slippage, exits exactly at the
  levels. Good for a first look; never evidence about the account.
- **placed** rows come from the demo-account loop: real (virtual-money) fills, commission and slippage included.

Only placed rows can make this gate READY, and READY still only means "the demo evidence clears the project's bar",
not "trade real money": there is no real-money path in this repository, and a demo result carries no promise about one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..stats import MIN_BETS_REPORT, mean_interval

MIN_TRADES = MIN_BETS_REPORT


@dataclass(frozen=True)
class Evidence:
    n: int
    wins: int
    net: float
    mean_r: float
    low: float
    high: float
    trades: int = 0
    """How many trades the n independent setups were made of (0 when counted trade by trade)."""

    @property
    def clears(self) -> bool:
        return self.n >= MIN_TRADES and self.low > 0


def _r_multiple(row: dict) -> float | None:
    """Profit in units of the money risked at the stop — comparable across stakes, multipliers and instruments."""
    try:
        risk = abs(float(row["entry"]) - float(row["stop"])) / float(row["entry"]) * float(row["stake"]) * float(row["multiplier"])
        risk = min(risk, float(row["stake"]))  # a Multiplier's stop-out caps the loss at the stake
        return float(row["profit"]) / risk if risk > 0 else None
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


INDEPENDENT_WITHIN = 3600.0
"""Trades in the same direction closer together than this (seconds) are one idea tested more than once, not separate tests."""


def independent_setups(rows: Iterable[dict], within: float = INDEPENDENT_WITHIN) -> list[list[dict]]:
    """Group rows into separate setups. Four sells within 45 minutes on one move are one idea, not four tests: counting them as
    four would overstate how much has been learned. A row joins the previous group when it has the same direction and its time
    is within `within` seconds of that group's last trade."""
    groups: list[list[dict]] = []
    for row in sorted(rows, key=lambda r: float(r.get("ts") or 0.0)):
        last = groups[-1][-1] if groups else None
        timed = last is not None and last.get("ts") is not None and row.get("ts") is not None  # no time, no way to say they are one idea
        if timed and last.get("direction") == row.get("direction") and float(row["ts"]) - float(last["ts"]) <= within:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def current_rules(rows: list[dict]) -> tuple[str | None, list[dict], int]:
    """(the rules fingerprint of the most recent row that has one, the rows made under it, how many rows were not).
    A change of rules restarts the count: evidence about one set of rules says nothing about another."""
    ids = [r.get("rules") for r in rows if r.get("rules")]
    if not ids:  # a log from before rules were recorded: nothing to tell sets apart, so it is taken as one
        return None, list(rows), 0
    cur = ids[-1]
    mine = [r for r in rows if r.get("rules") == cur]
    return cur, mine, len(rows) - len(mine)


def summarise_setups(rows: Iterable[dict]) -> Evidence:
    """`summarise`, but each independent setup counts once (its trades averaged), so n is the number of separate tests."""
    groups = independent_setups(rows)
    flat = []
    for g in groups:
        rs = [r for r in (_r_multiple(x) for x in g) if r is not None]
        if rs:
            flat.append({"entry": 1.0, "stop": 0.0, "stake": 1.0, "multiplier": 1, "profit": sum(rs) / len(rs), "_trades": len(g)})
    ev = summarise(flat)
    return Evidence(ev.n, ev.wins, ev.net, ev.mean_r, ev.low, ev.high, trades=sum(f["_trades"] for f in flat))


def summarise(rows: Iterable[dict]) -> Evidence:
    rs, wins, net = [], 0, 0.0
    for row in rows:
        r = _r_multiple(row)
        if r is None:
            continue
        rs.append(r)
        wins += 1 if float(row["profit"]) > 0 else 0
        net += float(row["profit"])
    mean, low, high = mean_interval(rs)
    return Evidence(len(rs), wins, net, mean, low, high)


def load(paths: Iterable[str]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def report(paths: Iterable[str], *, min_trades: int = MIN_TRADES) -> tuple[bool, str]:
    rows = load(paths)
    paper = summarise(r for r in rows if r.get("mode") == "paper")
    placed_rows = [r for r in rows if r.get("mode") != "paper"]
    cur, mine, earlier = current_rules(placed_rows)
    placed = summarise_setups(mine)
    lines = ["live-test evidence, in plain words", ""]

    def line(label: str, e: Evidence) -> str:
        if e.n == 0:
            return f"  {label}: no settled trades"
        trades = f" (from {e.trades} trades)" if e.trades and e.trades != e.n else ""
        return (f"  {label}: {e.n} settled{trades}, won {e.wins}, net {e.net:+.2f}; mean result {e.mean_r:+.2f} per unit risked "
                f"(95% interval {e.low:+.2f} to {e.high:+.2f})")

    lines += [line("paper (no orders, no costs)   ", paper), line("demo account, current rules      ", placed)]
    lines.append("  (independent setups: same-direction trades within an hour count once)")
    if earlier:
        lines.append(f"  {earlier} earlier demo trade(s) were made under different rules and are not counted: a change of rules restarts the count")
    lines.append("")
    ready = placed.n >= min_trades and placed.low > 0
    if ready:
        lines.append(f"READY on demo evidence: {placed.n} placed trades and the whole interval is above zero.")
        lines.append("That clears this project's bar on a demo account. It is not a promise about real money, and there is "
                     "no real-money path in this repository.")
    else:
        why = []
        if placed.n < min_trades:
            why.append(f"only {placed.n} of the {min_trades} independent demo setups it takes before a result can be told from luck"
                       + (f" ({paper.n} paper trades do not count: they carry no commission or slippage)" if paper.n else ""))
        elif placed.low <= 0:
            why.append(f"the interval ({placed.low:+.2f} to {placed.high:+.2f}) includes zero, so the result is not distinguishable from no edge")
        lines.append("NOT READY: " + "; ".join(why) + ".")
    return ready, "\n".join(lines)
