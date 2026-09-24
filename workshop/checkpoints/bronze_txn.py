"""Checkpoint for domain transactional ingestion into bronze.

The participant may ingest from Lakebase CDF or from the committed Delta
fallback.  The checkpoint deliberately does not inspect the chosen path: it
only observes the shared bronze table and its row count.

Extras forwarded through ``ctx.extras``:

* ``bronze_txn_table`` is the transactional bronze table in the caller's schema
  (default ``bronze_sales_transactions``).
* ``expected_txn_rows`` is the exact seeded-row count (default ``3_000``).
* ``transaction_key`` is the key named in the Lakebase CDF deduplication hint
  (default ``transaction_id``).
"""

from __future__ import annotations

from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

BRONZE_TXN_CHECKPOINT_ID = "01_bronze_txn"
BRONZE_TXN_TABLE = "bronze_sales_transactions"
EXPECTED_ROW_COUNT = 3_000
DEFAULT_TRANSACTION_KEY = "transaction_id"


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

    table_name = ctx.extras.get("bronze_txn_table") or BRONZE_TXN_TABLE
    expected_row_count = ctx.extras.get("expected_txn_rows", EXPECTED_ROW_COUNT)
    transaction_key = ctx.extras.get("transaction_key") or DEFAULT_TRANSACTION_KEY
    table = ctx.fully_qualified(table_name)
    try:
        row_count = int(
            spark.sql(f"SELECT COUNT(*) AS row_count FROM {table}").collect()[0][0]
        )
    except Exception as exc:  # noqa: BLE001 - return a participant-facing failure
        return CheckResult(
            BRONZE_TXN_CHECKPOINT_ID,
            False,
            f"Table `{ctx.catalog}`.`{ctx.schema}`.`{table_name}` could not "
            f"be read ({type(exc).__name__}). Run either the Lakebase CDF path or "
            "the Delta fallback ingestion cell, then retry this checkpoint.",
            {
                "table": f"{ctx.catalog}.{ctx.schema}.{table_name}",
                "error_type": type(exc).__name__,
            },
        )

    if row_count != expected_row_count:
        return CheckResult(
            BRONZE_TXN_CHECKPOINT_ID,
            False,
            f"Bronze table `{ctx.catalog}`.`{ctx.schema}`.`{table_name}` "
            f"contains {row_count:,} rows; expected exactly "
            f"{expected_row_count:,}. Re-run one ingestion path with overwrite "
            "mode. For Lakebase CDF, keep only the latest non-deleted row per "
            f"{transaction_key}.",
            {
                "table": f"{ctx.catalog}.{ctx.schema}.{table_name}",
                "row_count": row_count,
                "expected_row_count": expected_row_count,
            },
        )

    return CheckResult(
        BRONZE_TXN_CHECKPOINT_ID,
        True,
        f"Bronze transactional ingestion is ready: `{ctx.catalog}`.`{ctx.schema}`."
        f"`{table_name}` contains all {row_count:,} seeded rows.",
        {
            "table": f"{ctx.catalog}.{ctx.schema}.{table_name}",
            "row_count": row_count,
            "expected_row_count": expected_row_count,
        },
    )
