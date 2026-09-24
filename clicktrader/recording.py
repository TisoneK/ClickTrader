"""Layer 1 storage: one JSON line per tick, appended and flushed as it arrives.

A crash loses at most the tick being written — the reader drops a truncated final line and keeps the
rest. Anything the page showed alongside the tick (digit histogram, payouts on offer, account state) is
kept verbatim so later analysis can check the page against itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .model import Tick


@dataclass(frozen=True)
class TickRecord:
    tick: Tick
    histogram: dict[str, float] | None = None
    """Digit -> percentage as the page displays it, if it displays one."""
    payouts: dict[str, float] | None = None
    """Contract label (e.g. ``"over 4"``) -> profit ratio shown on the page."""
    account: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        row: dict[str, Any] = {
            "ts": self.tick.ts,
            "price": self.tick.price,
            "digit": self.tick.digit,
        }
        if self.tick.symbol:
            row["symbol"] = self.tick.symbol
        for key in ("histogram", "payouts", "account"):
            value = getattr(self, key)
            if value is not None:
                row[key] = value
        if self.extra:
            row["extra"] = self.extra
        return json.dumps(row, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "TickRecord":
        row = json.loads(line)
        tick = Tick(ts=float(row["ts"]), price=str(row["price"]), symbol=row.get("symbol", ""))
        if "digit" in row and row["digit"] != tick.digit:
            raise ValueError(f"stored digit {row['digit']} disagrees with price {tick.price!r}")
        return cls(
            tick=tick,
            histogram=row.get("histogram"),
            payouts=row.get("payouts"),
            account=row.get("account"),
            extra=row.get("extra", {}),
        )


class Recorder:
    """Append-only tick writer. Use as a context manager; each ``write`` is durable on return."""

    def __init__(self, path: str | os.PathLike[str], *, fsync: bool = True) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fsync = fsync
        self._file = self.path.open("a", encoding="utf-8")
        self.count = 0

    def write(self, record: TickRecord) -> None:
        self._file.write(record.to_json() + "\n")
        self._file.flush()
        if self._fsync:
            os.fsync(self._file.fileno())
        self.count += 1

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_recording(path: str | os.PathLike[str]) -> Iterator[TickRecord]:
    """Yield every complete record. A truncated *final* line is a crash artefact and is skipped;
    a corrupt line anywhere else is real damage and raises."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            yield TickRecord.from_json(line)
        except (json.JSONDecodeError, KeyError):
            if number == len(lines):
                return
            raise ValueError(f"{path}:{number}: corrupt record") from None


def read_ticks(path: str | os.PathLike[str]) -> list[Tick]:
    return [record.tick for record in read_recording(path)]
