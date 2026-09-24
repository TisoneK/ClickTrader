"""The limits layer 3 must run inside — built before the executor, because they are the feature.

``RiskGuard.check`` runs before every trade and answers with a refusal reason or ``None``. Breaching
the session-loss or losing-streak limit trips a kill switch that stays tripped: nothing in this module
un-trips it except ``rearm`` with a named human. There is no timeout, no auto-reset, no override flag.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_stake: float
    max_session_loss: float
    max_consecutive_losses: int

    def __post_init__(self) -> None:
        if self.max_stake <= 0 or self.max_session_loss <= 0 or self.max_consecutive_losses < 1:
            raise ValueError("every limit must be set, and positive — an unset limit is not a limit")
        if self.max_stake > self.max_session_loss:
            raise ValueError("max_stake larger than max_session_loss lets one trade breach the session cap")


class RiskGuard:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits
        self.session_pnl = 0.0
        self.consecutive_losses = 0
        self.trades = 0
        self.halted_reason: str | None = None
        self.rearmed_by: list[str] = []

    @property
    def halted(self) -> bool:
        return self.halted_reason is not None

    def check(self, stake: float) -> str | None:
        """Why this trade must not be placed, or None if it may. Checked before *every* trade."""
        if self.halted_reason is not None:
            return f"halted: {self.halted_reason}"
        if stake <= 0:
            return f"stake {stake} is not positive"
        if stake > self.limits.max_stake:
            return f"stake {stake} exceeds max stake {self.limits.max_stake}"
        # Refuse a trade whose loss would breach the cap, not only after the cap is already breached.
        if -self.session_pnl + stake > self.limits.max_session_loss:
            return (
                f"losing this {stake} would take session loss to {-self.session_pnl + stake:.2f}, "
                f"over the cap {self.limits.max_session_loss}"
            )
        return None

    def record(self, pnl: float) -> None:
        """Record a settled trade; may trip the kill switch."""
        self.trades += 1
        self.session_pnl += pnl
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0
        if self.consecutive_losses >= self.limits.max_consecutive_losses:
            self._trip(f"{self.consecutive_losses} consecutive losses (limit {self.limits.max_consecutive_losses})")
        elif -self.session_pnl >= self.limits.max_session_loss:
            self._trip(f"session loss {-self.session_pnl:.2f} reached the cap {self.limits.max_session_loss}")

    def kill(self, reason: str) -> None:
        """Manual kill switch — same latch as an automatic trip."""
        self._trip(f"manual: {reason}")

    def rearm(self, human: str) -> None:
        """Only a named human restarts a halted guard. Resets the streak, not the session's P/L:
        the session cap still counts everything already lost."""
        if not human.strip():
            raise ValueError("rearming requires the name of the human doing it")
        self.rearmed_by.append(human.strip())
        self.halted_reason = None
        self.consecutive_losses = 0

    def _trip(self, reason: str) -> None:
        if self.halted_reason is None:
            self.halted_reason = reason
