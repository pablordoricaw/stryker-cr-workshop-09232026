"""Checkpoint for Finance transactional ingestion into bronze.

The participant may ingest from Lakebase CDF or from the committed Delta
fallback.  The checkpoint deliberately does not inspect the chosen path: it
only observes the shared bronze table and its row count.
"""

from __future__ import annotations

from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

BRONZE_TXN_CHECKPOINT_ID = "01_bronze_txn"
BRONZE_TXN_TABLE = "bronze_sales_transactions"
EXPECTED_ROW_COUNT = 3_000


@checkpoint(
    BRONZE_TXN_CHECKPOINT_ID,
    summary="The bronze sales-transactions table exists and contains all 3,000 seeded rows.",
)
def check_bronze_txn(ctx: CheckContext) -> CheckResult:
    """Assert the shared bronze table exists and has the seeded row count."""
    spark = ctx.require_spark()

    if not ctx.catalog or not ctx.schema:
        return CheckResult(
            BRONZE_TXN_CHECKPOINT_ID,
            False,
            "No catalog/schema to check. Pass the resolved workshop config to "
            "workshop.check('01_bronze_txn', spark=spark, "
            "catalog=config.catalog, schema=config.schema).",
            {"catalog": ctx.catalog, "schema": ctx.schema},
        )

    table = ctx.fully_qualified(BRONZE_TXN_TABLE)
    try:
        row_count = int(
            spark.sql(f"SELECT COUNT(*) AS row_count FROM {table}").collect()[0][0]
        )
    except Exception as exc:  # noqa: BLE001 - return a participant-facing failure
        return CheckResult(
            BRONZE_TXN_CHECKPOINT_ID,
            False,
            f"Table `{ctx.catalog}`.`{ctx.schema}`.`{BRONZE_TXN_TABLE}` could not "
            f"be read ({type(exc).__name__}). Run either the Lakebase CDF path or "
            "the Delta fallback ingestion cell, then retry this checkpoint.",
            {
                "table": f"{ctx.catalog}.{ctx.schema}.{BRONZE_TXN_TABLE}",
                "error_type": type(exc).__name__,
            },
        )

    if row_count != EXPECTED_ROW_COUNT:
        return CheckResult(
            BRONZE_TXN_CHECKPOINT_ID,
            False,
            f"Bronze table `{ctx.catalog}`.`{ctx.schema}`.`{BRONZE_TXN_TABLE}` "
            f"contains {row_count:,} rows; expected exactly "
            f"{EXPECTED_ROW_COUNT:,}. Re-run one ingestion path with overwrite "
            "mode. For Lakebase CDF, keep only the latest non-deleted row per "
            "transaction_id.",
            {
                "table": f"{ctx.catalog}.{ctx.schema}.{BRONZE_TXN_TABLE}",
                "row_count": row_count,
                "expected_row_count": EXPECTED_ROW_COUNT,
            },
        )

    return CheckResult(
        BRONZE_TXN_CHECKPOINT_ID,
        True,
        f"Bronze transactional ingestion is ready: `{ctx.catalog}`.`{ctx.schema}`."
        f"`{BRONZE_TXN_TABLE}` contains all {row_count:,} seeded rows.",
        {
            "table": f"{ctx.catalog}.{ctx.schema}.{BRONZE_TXN_TABLE}",
            "row_count": row_count,
            "expected_row_count": EXPECTED_ROW_COUNT,
        },
    )
