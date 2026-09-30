"""Is the evidence there? A plain-words gate over the logs a live test produces.

It does not decide to trade, it says what the logs do and do not show. The bar is the project's own: at least
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


def report(paths: Iterable[str]) -> tuple[bool, str]:
    rows = load(paths)
    paper = summarise(r for r in rows if r.get("mode") == "paper")
    placed = summarise(r for r in rows if r.get("mode") != "paper")
    lines = ["live-test evidence, in plain words", ""]

    def line(label: str, e: Evidence) -> str:
        if e.n == 0:
            return f"  {label}: no settled trades"
        return (f"  {label}: {e.n} settled, won {e.wins}, net {e.net:+.2f}; mean result {e.mean_r:+.2f} per unit risked "
                f"(95% interval {e.low:+.2f} to {e.high:+.2f})")

    lines += [line("paper (no orders, no costs)   ", paper), line("placed on the demo account      ", placed), ""]
    ready = placed.clears
    if ready:
        lines.append(f"READY on demo evidence: {placed.n} placed trades and the whole interval is above zero.")
        lines.append("That clears this project's bar on a demo account. It is not a promise about real money, and there is "
                     "no real-money path in this repository.")
    else:
        why = []
        if placed.n < MIN_TRADES:
            why.append(f"only {placed.n} of the {MIN_TRADES} placed demo trades the project needs before it reads a result"
                       + (f" ({paper.n} paper trades do not count: they carry no commission or slippage)" if paper.n else ""))
        elif placed.low <= 0:
            why.append(f"the interval ({placed.low:+.2f} to {placed.high:+.2f}) includes zero, so the result is not distinguishable from no edge")
        lines.append("NOT READY: " + "; ".join(why) + ".")
    return ready, "\n".join(lines)
