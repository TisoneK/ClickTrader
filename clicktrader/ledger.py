"""The decision ledger: one row per decision — what was seen, what was decided, why, what happened.

Replay and (later) the executor write the same rows, so a live session and its replay can be diffed
line for line. A bot you cannot interrogate afterwards is a bot you cannot fix (DESIGN.md).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Literal

Action = Literal["bet", "skip", "blocked"]


@dataclass(frozen=True)
class LedgerRow:
    ts: float
    tick_index: int
    digit_seen: int
    strategy: str
    action: Action
    reason: str
    contract: str | None = None
    stake: float | None = None
    settle_digit: int | None = None
    won: bool | None = None
    pnl: float | None = None
    balance: float | None = None
    """Running session P/L after this row — our own tally, not a real account balance."""
    account_balance: float | None = None
    """The broker's own reported balance after this row settled. Only the live executor ever sets
    this (via a real API call); replay has no real account, so it's always None there."""


class DecisionLedger:
    """Append-only JSONL writer. ``path=None`` keeps rows in memory only (tests, quick replays)."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.rows: list[LedgerRow] = []
        self._file = None
        if path is not None:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._file = target.open("a", encoding="utf-8")

    def append(self, row: LedgerRow) -> None:
        self.rows.append(row)
        if self._file is not None:
            self._file.write(json.dumps(asdict(row), separators=(",", ":")) + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> "DecisionLedger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_ledger(path: str | os.PathLike[str]) -> Iterator[LedgerRow]:
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield LedgerRow(**json.loads(line))
