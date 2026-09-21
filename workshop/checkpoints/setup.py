"""The ``00_setup`` checkpoint: the participant's environment exists.

Returns green once the setup notebook has created the schema and UC Volume named
by the run's :class:`~workshop.config.WorkshopConfig` inside the participant's
existing catalog. It asserts only externally-observable state — that the catalog
is *accessible* and the schema and volume *exist* — never how the notebook
created them, and never that a catalog was created (participants bring their own).

Run it as::

    workshop.check("00_setup", spark=spark,
                   catalog=config.catalog, schema=config.schema,
                   volume=config.volume)
"""

from __future__ import annotations

from typing import Any

from workshop.config import DEFAULT_VOLUME
from workshop.context import CheckContext
from workshop.identifiers import fully_qualified, quote_identifier
from workshop.registry import checkpoint
from workshop.results import CheckResult

SETUP_CHECKPOINT_ID = "00_setup"


def _string_values(df: Any) -> set[str]:
    """All string cell values across a SHOW result.

    ``SHOW SCHEMAS`` / ``SHOW VOLUMES`` return the object name in a column whose
    header differs by Databricks version (``databaseName`` vs ``volume_name``).
    Scanning every string cell finds the name without hard-coding a column, and
    these SHOW results carry no free-text columns that could cause a false match.
    """
    values: set[str] = set()
    for row in df.collect():
        as_dict = row.asDict() if hasattr(row, "asDict") else dict(row)
        for value in as_dict.values():
            if isinstance(value, str):
                values.add(value)
    return values


@checkpoint(
    SETUP_CHECKPOINT_ID,
    summary="Your schema and UC Volume exist in your catalog (run the 00_setup notebook first).",
)
def check_setup(ctx: CheckContext) -> CheckResult:
    """Assert the catalog is accessible and the schema and UC Volume exist."""
    spark = ctx.require_spark()
    catalog = ctx.catalog
    schema = ctx.schema
    volume = ctx.extras.get("volume") or DEFAULT_VOLUME

    if not catalog or not schema:
        return CheckResult(
            SETUP_CHECKPOINT_ID,
            False,
            "No catalog/schema to check. Call workshop.check('00_setup', "
            "spark=spark, catalog=config.catalog, schema=config.schema, "
            "volume=config.volume) — the setup notebook does this for you.",
            {"catalog": catalog, "schema": schema},
        )

    hint = "Run the setup notebook (notebooks/00_setup) to provision it."

    # Listing schemas in the catalog doubles as the accessibility probe: if the
    # catalog is missing or the participant lacks USE CATALOG, this raises.
    try:
        schemas = _string_values(
            spark.sql(f"SHOW SCHEMAS IN {quote_identifier(catalog)}")
        )
    except Exception as exc:  # noqa: BLE001 - turn into a targeted failure
        return CheckResult(
            SETUP_CHECKPOINT_ID,
            False,
            f"Catalog `{catalog}` is not accessible ({type(exc).__name__}). Enter "
            f"your team's existing catalog name and confirm you have USE CATALOG "
            f"on it — the workshop does not create the catalog.",
            {"missing": "catalog", "catalog": catalog, "error_type": type(exc).__name__},
        )

    if schema not in schemas:
        return CheckResult(
            SETUP_CHECKPOINT_ID,
            False,
            f"Catalog `{catalog}` is accessible but schema `{schema}` is missing. "
            f"{hint}",
            {"missing": "schema", "catalog": catalog, "schema": schema},
        )

    volumes = _string_values(
        spark.sql(f"SHOW VOLUMES IN {fully_qualified(catalog, schema)}")
    )
    if volume not in volumes:
        return CheckResult(
            SETUP_CHECKPOINT_ID,
            False,
            f"Schema `{catalog}`.`{schema}` exists but UC Volume `{volume}` is "
            f"missing. {hint}",
            {
                "missing": "volume",
                "catalog": catalog,
                "schema": schema,
                "volume": volume,
            },
        )

    volume_path = f"/Volumes/{catalog}/{schema}/{volume}"
    return CheckResult(
        SETUP_CHECKPOINT_ID,
        True,
        f"Environment ready: schema `{schema}` and UC Volume `{volume}` exist in "
        f"catalog `{catalog}`. Land documents in {volume_path}.",
        {
            "catalog": catalog,
            "schema": schema,
            "volume": volume,
            "volume_path": volume_path,
        },
    )
