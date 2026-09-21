"""The context handed to every checkpoint function.

A checkpoint asserts *externally-observable* state — catalog objects, row
counts, tag/comment presence, metric-view resolvability, a sane Genie answer,
synced-table row parity. To do that on a live workspace it needs a Spark session
and the participant's catalog/schema. Those are bundled here so the
``workshop.check`` signature stays small and later tickets have one obvious
place to reach for what they need.

Every field is optional. The smoke checkpoint (and any other check that asserts
purely local state) ignores the context entirely, which is what lets the
framework return green from a fresh clone with no Databricks connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckContext:
    """Inputs available to a checkpoint function.

    Attributes:
        spark: The active ``SparkSession``, or ``None`` when running with no
            workspace. Use :meth:`require_spark` inside Databricks-dependent
            checkpoints to fail with a clear message instead of an
            ``AttributeError``.
        catalog: The participant's Unity Catalog catalog name, if known.
        schema: The participant's schema name, if known.
        extras: Free-form keyword arguments forwarded from ``workshop.check``.
            Later tickets can pass checkpoint-specific inputs (a table name, an
            expected row count, a Genie question) without changing this class.
    """

    spark: Any = None
    catalog: str | None = None
    schema: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def require_spark(self) -> Any:
        """Return the Spark session or raise a participant-friendly error.

        The runner turns the raised error into a failed ``CheckResult``, so a
        Databricks-dependent checkpoint run with no workspace fails loudly and
        legibly rather than exploding on a ``None`` attribute access.
        """
        if self.spark is None:
            raise RuntimeError(
                "This checkpoint needs a Databricks workspace, but no Spark "
                "session was provided. Run it from a Databricks notebook, or "
                "pass spark=spark to workshop.check(...)."
            )
        return self.spark

    def fully_qualified(self, table: str) -> str:
        """Build ``catalog.schema.table`` from the context.

        Convenience for the many later checkpoints that assert on a table in the
        participant's own schema. Raises if catalog/schema are unset so the
        mistake surfaces as a clear failure message.
        """
        if not self.catalog or not self.schema:
            raise RuntimeError(
                "catalog and schema must be set to resolve a table name; pass "
                "catalog=... and schema=... to workshop.check(...)."
            )
        return f"{self.catalog}.{self.schema}.{table}"
