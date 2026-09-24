"""Create a participant's schema and UC Volume inside their existing catalog.

This is the logic the setup notebook (``notebooks/00_setup``) runs, factored out
of the notebook so it is unit-testable and so maintainer validation can drive the
*exact* same code against a live workspace. It is idempotent (``IF NOT EXISTS``
everywhere) so a participant can re-run the setup cell freely.

**Bring-your-own-catalog.** Participants do not have permission to create
catalogs, and each team already has its own. So this never runs ``CREATE CATALOG``.
It assumes the participant has ``USE CATALOG`` plus ``CREATE SCHEMA`` (and volume
creation) on their *own* catalog, and creates only the schema and volume with
plain SQL. Both work on Databricks Free Edition with no web terminal and no
workspace-admin toggle (decision Q20 = B).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import WorkshopConfig


@dataclass
class ProvisionReport:
    """What :func:`provision` did, for notebook logging and tests.

    Attributes:
        config: The resolved names that were provisioned.
        statements: The SQL statements executed, in order.
    """

    config: WorkshopConfig
    statements: list[str] = field(default_factory=list)


def provision(config: WorkshopConfig, spark: Any) -> ProvisionReport:
    """Create ``config``'s schema and UC Volume in its (existing) catalog.

    The catalog is assumed to already exist and be accessible to the participant;
    this function does not create it. Both statements use ``IF NOT EXISTS`` so
    re-running is safe.

    Args:
        config: Resolved environment names (see ``workshop.resolve_config``).
        spark: An active ``SparkSession``.

    Returns:
        A :class:`ProvisionReport` describing what ran.
    """
    report = ProvisionReport(config=config)

    schema_stmt = f"CREATE SCHEMA IF NOT EXISTS {config.quoted_schema()}"
    spark.sql(schema_stmt)
    report.statements.append(schema_stmt)

    volume_stmt = f"CREATE VOLUME IF NOT EXISTS {config.quoted_volume()}"
    spark.sql(volume_stmt)
    report.statements.append(volume_stmt)

    return report
