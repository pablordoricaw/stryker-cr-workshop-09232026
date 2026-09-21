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

# The name column each SHOW result exposes (header varies by Databricks version).
# We read *only* the name column — never every string cell — because
# ``SHOW VOLUMES`` also returns the schema/database name, so scanning all cells
# would let a volume whose name equals the schema name false-pass.
_SCHEMA_NAME_COLUMNS = ("databaseName", "schemaName", "schema_name", "namespace")
_VOLUME_NAME_COLUMNS = ("volume_name", "volumeName")


def _column_values(df: Any, candidates: tuple[str, ...]) -> set[str]:
    """The values of the first candidate column present in each row.

    Reads only the object-name column so unrelated columns (e.g. the schema name
    in a ``SHOW VOLUMES`` result) can't cause a false match.
    """
    values: set[str] = set()
    for row in df.collect():
        as_dict = row.asDict() if hasattr(row, "asDict") else dict(row)
        for column in candidates:
            value = as_dict.get(column)
            if isinstance(value, str):
                values.add(value)
                break
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
        schemas = _column_values(
            spark.sql(f"SHOW SCHEMAS IN {quote_identifier(catalog)}"),
            _SCHEMA_NAME_COLUMNS,
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

    # Listing volumes probes schema access (USE SCHEMA); handle it separately so a
    # permission/listing failure gets a targeted message, not a raw traceback.
    try:
        volumes = _column_values(
            spark.sql(f"SHOW VOLUMES IN {fully_qualified(catalog, schema)}"),
            _VOLUME_NAME_COLUMNS,
        )
    except Exception as exc:  # noqa: BLE001 - turn into a targeted failure
        return CheckResult(
            SETUP_CHECKPOINT_ID,
            False,
            f"Schema `{catalog}`.`{schema}` exists but its UC Volumes could not be "
            f"listed ({type(exc).__name__}). Confirm you have USE SCHEMA on it, "
            f"then re-run the setup notebook (notebooks/00_setup).",
            {
                "missing": "volume",
                "catalog": catalog,
                "schema": schema,
                "error_type": type(exc).__name__,
            },
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
