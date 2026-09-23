"""The context and result types handed to and returned by seed hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from workshop.config import WorkshopConfig


@dataclass
class SeedContext:
    """Inputs available to a seed hook.

    A seed hook loads a domain's data into the participant's freshly-provisioned
    catalog/schema/volume. It gets the resolved :class:`WorkshopConfig` (so it
    knows *where* to write) and the active Spark session (so it can write).

    Attributes:
        config: The resolved environment names for this run.
        spark: Active ``SparkSession``, or ``None`` when run with no workspace.
            Use :meth:`require_spark` to fail with a clear message instead of an
            ``AttributeError``.
        extras: Free-form keyword arguments forwarded from ``run_seeds`` — a
            later hook can accept tuning inputs without changing this class.
    """

    config: WorkshopConfig
    spark: Any = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str:
        """The workshop domain being seeded (``config.domain``)."""
        return self.config.domain

    def require_spark(self) -> Any:
        """Return the Spark session or raise a hook-friendly error."""
        if self.spark is None:
            raise RuntimeError(
                "This seed hook needs a Databricks workspace, but no Spark "
                "session was provided. Run it from a Databricks notebook, or "
                "pass spark=spark to workshop.run_seeds(...)."
            )
        return self.spark


@dataclass(frozen=True)
class SeedResult:
    """The outcome of running one seed hook.

    Mirrors :class:`workshop.CheckResult` so notebooks and CI render seed output
    the same way they render checkpoint output.

    Attributes:
        seed: The hook name that ran.
        ok: ``True`` when the hook completed (a placeholder/no-op is still ``ok``).
        message: Human-readable description of what happened.
        details: Optional machine-readable extras (row counts, table names, ...).
    """

    seed: str
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        mark = "✅ SEEDED" if self.ok else "❌ SEED FAILED"
        return f"[{mark}] {self.seed}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ok": self.ok,
            "message": self.message,
            "details": dict(self.details),
        }
