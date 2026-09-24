"""The structured result returned by every ``workshop.check`` call.

A :class:`CheckResult` is the single, stable contract between the checkpoint
framework and everything that consumes it, such as participant notebooks, the
Genie-Code hint agent, and maintainer CI. Later tickets add checkpoints, but
they all return this same shape, so downstream code never has to special-case a
checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    """The outcome of running one checkpoint.

    Attributes:
        checkpoint: The checkpoint id that was run (e.g. ``"smoke"``).
        passed: ``True`` when the observable state satisfies the checkpoint.
        message: A human-readable, targeted explanation. On failure this should
            tell the participant *what* is wrong and *where* to look, never a
            bare "failed".
        details: Optional structured extras (row counts, missing objects, the
            Genie answer that was scored, ...). Kept machine-readable so CI and
            the hint agent can branch on it without parsing ``message``.
    """

    checkpoint: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Allow ``if workshop.check(...):`` to read naturally."""
        return self.passed

    def __str__(self) -> str:
        mark = "✅ PASS" if self.passed else "❌ FAIL"
        return f"[{mark}] {self.checkpoint}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable view, for CI logs and the hint agent."""
        return {
            "checkpoint": self.checkpoint,
            "passed": self.passed,
            "message": self.message,
            "details": dict(self.details),
        }
