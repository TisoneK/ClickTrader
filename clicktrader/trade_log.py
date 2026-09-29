"""A log of real Rise/Fall trades, and the tally that turns them into an answer.

Everywhere else in this project the count comes from a replay. This module is for trades that actually
happened: one line per contract, written when the broker settles it, carrying what was *paid* rather than
what was quoted. That distinction is the reason this file exists — a live fill on Volatility 25 came back
at 88% while the proposal above it quoted 95.35%, and the break-even those two imply differs by two
points of win rate, which is larger than the edge a replay is trying to detect.

Plain JSONL, append-only, in the same spirit as `recording.py` and `ledger.py`: a crash loses the row
being written and nothing else, and the file can be read by anything.

The tally deliberately reports in the order a person needs it — trades taken, how many won, the payout
actually received, and the win rate that payout requires — because the alternative (a hit rate and a
confidence interval, both correct and neither usable) is where this project's reporting went wrong once
already.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from .stats import wilson_interval

MIN_TRADES_TO_READ = 100
"""Below this the tally refuses to characterise the method.

Lower than `stats.MIN_BETS_REPORT` (500) because these are settled live contracts rather than replay
decisions — expensive to gather and each one real — but the honesty rule is the same: below the gate it
says "too few to conclude" instead of printing a rate that looks like a result. A hundred trades still
only brackets the rate to within roughly ±10 points, which the tally says out loud.
"""


@dataclass(frozen=True)
class RiseFallTrade:
    """One settled Rise/Fall contract, as the broker reported it."""

    settled_at: float
    symbol: str
    direction: str
    stake: float
    buy_price: float
    payout: float
    """What the contract paid if it won — the *bought* payout, not the quote."""
    status: str
    """`"won"` or `"lost"`."""
    profit: float
    contract_id: int = 0
    duration: int = 0
    duration_unit: str = ""
    exit_spot: str | None = None
    currency: str = "USD"
    reason: str = ""

    @property
    def roi(self) -> float:
        """Profit per unit staked on a win, as the contract actually paid it."""
        return (self.payout - self.buy_price) / self.buy_price if self.buy_price else 0.0

    @property
    def breakeven(self) -> float:
        """The win rate this contract needed to break even, from its own payout."""
        return 1.0 / (1.0 + self.roi) if self.roi > 0 else 1.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "RiseFallTrade":
        return cls(**json.loads(line))


class TradeLog:
    """Append-only writer for settled trades. Use as a context manager."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")
        self.count = 0

    def write(self, trade: RiseFallTrade) -> None:
        self._file.write(trade.to_json() + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        self.count += 1

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "TradeLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_trades(path: str | os.PathLike[str]) -> Iterator[RiseFallTrade]:
    """Every complete row, in order. A truncated final line is dropped rather than raising — the same
    rule the tick recordings follow, so a crash mid-write costs one trade and not the log."""
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield RiseFallTrade.from_json(line)
            except (ValueError, TypeError):
                continue


@dataclass
class TradeTally:
    trades: int = 0
    won: int = 0
    staked: float = 0.0
    net: float = 0.0
    payouts: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.payouts is None:
            self.payouts = []

    @property
    def lost(self) -> int:
        return self.trades - self.won

    @property
    def win_rate(self) -> float:
        return self.won / self.trades if self.trades else 0.0

    @property
    def win_rate_range(self) -> tuple[float, float]:
        return wilson_interval(self.won, self.trades)

    @property
    def average_payout(self) -> float:
        """Return per unit staked, averaged over **every** settled trade.

        Not only the winners: the payout is a property of the contract that was bought, and every row
        carries it whether the trade won or lost. Averaging over winners alone made a log with no wins
        yet report a break-even of 100%, which is the opposite of informative — and it would drift as the
        win rate moved, which is not what a payout does.
        """
        return sum(self.payouts) / len(self.payouts) if self.payouts else 0.0

    @property
    def breakeven(self) -> float:
        """The win rate the trades needed, from the payout they were actually paid."""
        return 1.0 / self.average_payout if self.average_payout > 0 else 1.0

    def report(self) -> str:
        if not self.trades:
            return "No settled trades in this log yet."
        lo, hi = self.win_rate_range
        lines = [
            f"trades                {self.trades}",
            f"won                   {self.won}  ({self.win_rate:.1%})",
            f"lost                  {self.lost}",
            f"staked                {self.staked:.2f}",
            f"net profit/loss       {self.net:+.2f}",
            "",
            f"average payout paid   {self.average_payout:.4f} per 1.00 staked "
            f"({(self.average_payout - 1) * 100:.2f}%)",
            f"breaking even needs   {self.breakeven:.2%} of trades won at that payout",
            "",
        ]
        if self.trades < MIN_TRADES_TO_READ:
            lines.append(
                f"In plain words: it won {self.won} of {self.trades} trades, which is too few to say "
                f"anything yet — {MIN_TRADES_TO_READ} are needed before the rate means much."
            )
            return "\n".join(lines)
        verdict = (
            "above" if lo > self.breakeven else "below" if hi < self.breakeven else "straddling"
        )
        if verdict == "straddling":
            lines.append(
                f"In plain words: it won {self.won} of {self.trades} trades ({self.win_rate:.1%}), and the "
                f"honest range around that ({lo:.1%} to {hi:.1%}) straddles the {self.breakeven:.2%} needed "
                "to break even — so this many trades still cannot say which side of the line it is on."
            )
        else:
            lines.append(
                f"In plain words: it won {self.won} of {self.trades} trades ({self.win_rate:.1%}), and every "
                f"plausible value for that ({lo:.1%} to {hi:.1%}) is {verdict} the {self.breakeven:.2%} needed "
                f"to break even."
            )
        return "\n".join(lines)


def tally(path: str | os.PathLike[str]) -> TradeTally:
    """Add up every settled trade in `path`."""
    result = TradeTally()
    for trade in read_trades(path):
        result.trades += 1
        result.won += 1 if trade.status == "won" else 0
        result.staked += trade.buy_price
        result.net += trade.profit
        result.payouts.append(trade.payout / trade.buy_price if trade.buy_price else 0.0)
    return result
