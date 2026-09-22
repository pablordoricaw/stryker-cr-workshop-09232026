"""The ``03_gold`` checkpoint: analytics-ready detail and aggregate marts.

The check observes Unity Catalog state only.  It does not inspect the notebook
or require a particular implementation API.  By default it validates the
Finance slice built by ``03_gold``:

* ``gold_sales`` has exactly one row per upstream transaction;
* document enrichment covers exactly the transactions whose ``contract_id``
  joins a unique ``agreement_id`` in
  ``silver_sales_contract_pricing_agreement``; and
* ``gold_contract_performance`` has exactly one row per upstream contract and
  reconciles its core additive measures to the transaction source.

All expected counts and key sets come from the upstream tables at check time.
There are no Finance seed counts in this module.  Table and column names are
also overridable through ``workshop.check`` extras so Security (#13) and ITSM
(#14) can reuse the observable grain/identity checks with their own sources.
"""

from __future__ import annotations

from typing import Any

from workshop.context import CheckContext
from workshop.identifiers import quote_identifier
from workshop.registry import checkpoint
from workshop.results import CheckResult

GOLD_CHECKPOINT_ID = "03_gold"

DEFAULT_SOURCE_TABLE = "bronze_sales_transactions"
DEFAULT_DOCUMENT_TABLE = "silver_sales_contract_pricing_agreement"
DEFAULT_DETAIL_TABLE = "gold_sales"
DEFAULT_MART_TABLE = "gold_contract_performance"

DEFAULT_SOURCE_KEY = "transaction_id"
DEFAULT_DETAIL_KEY = "transaction_id"
DEFAULT_SOURCE_GROUP_KEY = "contract_id"
DEFAULT_DOCUMENT_KEY = "agreement_id"
DEFAULT_DETAIL_DOCUMENT_KEY = "contract_agreement_id"
DEFAULT_DETAIL_DOCUMENT_MATCH = "contract_document_path"
DEFAULT_MART_KEY = "contract_id"


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(GOLD_CHECKPOINT_ID, False, message, details)


def _collect_keys(spark: Any, query: str) -> set[str]:
    """Collect the first column as a string identity set."""
    return {str(row[0]) for row in spark.sql(query).collect()}


@checkpoint(
    GOLD_CHECKPOINT_ID,
    summary=(
        "Gold detail preserves every upstream transaction exactly once, "
        "document enrichment matches the upstream join, and the aggregate "
        "mart has one reconciled row per business key."
    ),
)
def check_gold(ctx: CheckContext) -> CheckResult:
    """Validate gold detail/enrichment and aggregate grain from UC state."""
    spark = ctx.require_spark()
    if not ctx.catalog or not ctx.schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('03_gold', "
            "spark=spark, catalog=config.catalog, schema=config.schema).",
            {"catalog": ctx.catalog, "schema": ctx.schema},
        )

    source_name = ctx.extras.get("source_table") or DEFAULT_SOURCE_TABLE
    document_name = ctx.extras.get("document_table") or DEFAULT_DOCUMENT_TABLE
    detail_name = ctx.extras.get("detail_table") or DEFAULT_DETAIL_TABLE
    mart_name = ctx.extras.get("mart_table") or DEFAULT_MART_TABLE

    source = ctx.fully_qualified(source_name)
    documents = ctx.fully_qualified(document_name)
    detail = ctx.fully_qualified(detail_name)
    mart = ctx.fully_qualified(mart_name)

    source_key_name = ctx.extras.get("source_key") or DEFAULT_SOURCE_KEY
    detail_key_name = ctx.extras.get("detail_key") or DEFAULT_DETAIL_KEY
    source_group_name = (
        ctx.extras.get("source_group_key") or DEFAULT_SOURCE_GROUP_KEY
    )
    document_key_name = ctx.extras.get("document_key") or DEFAULT_DOCUMENT_KEY
    detail_document_key_name = (
        ctx.extras.get("detail_document_key") or DEFAULT_DETAIL_DOCUMENT_KEY
    )
    detail_match_name = (
        ctx.extras.get("detail_document_match") or DEFAULT_DETAIL_DOCUMENT_MATCH
    )
    mart_key_name = ctx.extras.get("mart_key") or DEFAULT_MART_KEY

    source_key = quote_identifier(source_key_name)
    detail_key = quote_identifier(detail_key_name)
    source_group = quote_identifier(source_group_name)
    document_key = quote_identifier(document_key_name)
    detail_document_key = quote_identifier(detail_document_key_name)
    detail_match = quote_identifier(detail_match_name)
    mart_key = quote_identifier(mart_key_name)

    # The source defines both expected grains.  Refuse to validate gold against
    # a broken upstream identity set; a correct total can otherwise hide a null
    # key or duplicate replacing a missing transaction.
    try:
        source_stats = spark.sql(
            f"""/* gold:source_integrity */
            SELECT
              COUNT(*) AS total_rows,
              COUNT_IF({source_key} IS NULL OR
                       TRIM(CAST({source_key} AS STRING)) = '') AS null_keys,
              COUNT(DISTINCT {source_key}) AS distinct_keys,
              COUNT_IF({source_group} IS NULL OR
                       TRIM(CAST({source_group} AS STRING)) = '') AS null_group_keys
            FROM {source}"""
        ).collect()[0]
    except Exception as exc:  # noqa: BLE001 - participant-facing RED state
        return _fail(
            f"Upstream transaction table {source} is missing or unreadable "
            f"({type(exc).__name__}). Finish transactional ingestion first.",
            {"stage": "source", "table": source, "error_type": type(exc).__name__},
        )

    source_total = int(source_stats[0])
    source_null = int(source_stats[1])
    source_distinct = int(source_stats[2])
    source_null_groups = int(source_stats[3])
    if (
        source_total <= 0
        or source_null
        or source_null_groups
        or source_distinct != source_total
    ):
        return _fail(
            f"Upstream table {source} must have non-null, unique "
            f"{source_key_name} values and non-null {source_group_name} values "
            "before gold can be checked.",
            {
                "stage": "source",
                "row_count": source_total,
                "null_keys": source_null,
                "distinct_keys": source_distinct,
                "null_group_keys": source_null_groups,
            },
        )

    try:
        source_keys = _collect_keys(
            spark,
            f"""/* gold:source_keys */
            SELECT CAST({source_key} AS STRING) AS entity_key FROM {source}""",
        )
        source_group_keys = _collect_keys(
            spark,
            f"""/* gold:source_group_keys */
            SELECT DISTINCT CAST({source_group} AS STRING) AS entity_key
            FROM {source}
            WHERE {source_group} IS NOT NULL""",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read identities from upstream table {source} "
            f"({type(exc).__name__}).",
            {"stage": "source", "table": source, "error_type": type(exc).__name__},
        )

    # A many-to-one enrichment needs a non-null, unique document key; otherwise
    # a join can silently multiply the transaction grain.
    try:
        document_stats = spark.sql(
            f"""/* gold:documents_integrity */
            SELECT
              COUNT(*) AS total_rows,
              COUNT_IF({document_key} IS NULL OR
                       TRIM(CAST({document_key} AS STRING)) = '') AS null_keys,
              COUNT(DISTINCT {document_key}) AS distinct_keys
            FROM {documents}"""
        ).collect()[0]
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Document enrichment table {documents} is missing or unreadable "
            f"({type(exc).__name__}). Finish the silver document stage first.",
            {
                "stage": "documents",
                "table": documents,
                "error_type": type(exc).__name__,
            },
        )

    document_total = int(document_stats[0])
    document_null = int(document_stats[1])
    document_distinct = int(document_stats[2])
    if document_total <= 0 or document_null or document_distinct != document_total:
        return _fail(
            f"Document table {documents} must contain a non-null, unique "
            f"{document_key_name} for a grain-safe gold join.",
            {
                "stage": "documents",
                "row_count": document_total,
                "null_keys": document_null,
                "distinct_keys": document_distinct,
            },
        )

    try:
        expected_enriched_keys = _collect_keys(
            spark,
            f"""/* gold:expected_enriched_keys */
            SELECT CAST(s.{source_key} AS STRING) AS entity_key
            FROM {source} AS s
            INNER JOIN {documents} AS d
              ON CAST(s.{source_group} AS STRING) =
                 CAST(d.{document_key} AS STRING)""",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(
            "Could not evaluate the upstream transaction-to-document join "
            f"({type(exc).__name__}). Confirm both join columns exist.",
            {"stage": "upstream_join", "error_type": type(exc).__name__},
        )
    if not expected_enriched_keys:
        return _fail(
            f"No {source_group_name} values in {source} match "
            f"{document_key_name} values in {documents}; gold would contain no "
            "document-derived enrichment.",
            {"stage": "upstream_join", "expected_enriched_rows": 0},
        )

    try:
        detail_stats = spark.sql(
            f"""/* gold:detail_integrity */
            SELECT
              COUNT(*) AS total_rows,
              COUNT_IF({detail_key} IS NULL OR
                       TRIM(CAST({detail_key} AS STRING)) = '') AS null_keys,
              COUNT(DISTINCT {detail_key}) AS distinct_keys
            FROM {detail}"""
        ).collect()[0]
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Gold detail table {detail} is missing or unreadable "
            f"({type(exc).__name__}). Run the 03_gold build cells.",
            {"stage": "detail", "table": detail, "error_type": type(exc).__name__},
        )

    detail_total = int(detail_stats[0])
    detail_null = int(detail_stats[1])
    detail_distinct = int(detail_stats[2])
    if detail_null or detail_distinct != detail_total or detail_total != source_total:
        return _fail(
            f"Gold detail {detail} has the wrong grain: expected exactly one "
            f"non-null, unique {detail_key_name} row for each of the "
            f"{source_total:,} upstream transactions.",
            {
                "stage": "detail",
                "row_count": detail_total,
                "expected_row_count": source_total,
                "null_keys": detail_null,
                "distinct_keys": detail_distinct,
            },
        )

    try:
        detail_keys = _collect_keys(
            spark,
            f"""/* gold:detail_keys */
            SELECT CAST({detail_key} AS STRING) AS entity_key FROM {detail}""",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read identities from gold detail {detail} "
            f"({type(exc).__name__}).",
            {"stage": "detail", "table": detail, "error_type": type(exc).__name__},
        )
    if detail_keys != source_keys:
        return _fail(
            "Gold detail identities do not exactly match the upstream "
            "transaction identities; a correct total cannot mask a missing or "
            "unexpected row.",
            {
                "stage": "detail_identity",
                "missing": sorted(source_keys - detail_keys)[:20],
                "unexpected": sorted(detail_keys - source_keys)[:20],
            },
        )

    # Exact transaction identities are necessary but not sufficient: a broken
    # join could preserve every transaction id while attaching contract B's
    # document to contract A's row.  Reconcile the association per identity.
    try:
        join_mismatches = int(
            spark.sql(
                f"""/* gold:detail_join_reconciliation */
                SELECT COUNT(*) AS mismatched_rows
                FROM {source} AS s
                FULL OUTER JOIN {detail} AS g
                  ON CAST(s.{source_key} AS STRING) = CAST(g.{detail_key} AS STRING)
                WHERE s.{source_key} IS NULL OR g.{detail_key} IS NULL
                   OR NOT (CAST(s.{source_group} AS STRING) <=>
                           CAST(g.{detail_document_key} AS STRING))"""
            ).collect()[0][0]
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not reconcile document join keys in {detail} "
            f"({type(exc).__name__}). Confirm {detail_document_key_name} is present.",
            {"stage": "detail_join", "error_type": type(exc).__name__},
        )
    if join_mismatches:
        return _fail(
            f"Gold detail {detail} has {join_mismatches} transaction row(s) "
            "whose attached document key does not match the upstream business "
            "key.",
            {"stage": "detail_join", "mismatched_rows": join_mismatches},
        )

    try:
        observed_enriched_keys = _collect_keys(
            spark,
            f"""/* gold:observed_enriched_keys */
            SELECT CAST({detail_key} AS STRING) AS entity_key
            FROM {detail}
            WHERE {detail_match} IS NOT NULL
              AND {detail_document_key} IS NOT NULL""",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not inspect document enrichment in {detail} "
            f"({type(exc).__name__}). Confirm {detail_match_name} and "
            f"{detail_document_key_name} are present.",
            {"stage": "enrichment", "error_type": type(exc).__name__},
        )
    if observed_enriched_keys != expected_enriched_keys:
        return _fail(
            "Gold document enrichment does not match the observable upstream "
            "join identity set.",
            {
                "stage": "enrichment",
                "expected_enriched_rows": len(expected_enriched_keys),
                "observed_enriched_rows": len(observed_enriched_keys),
                "missing": sorted(expected_enriched_keys - observed_enriched_keys)[:20],
                "unexpected": sorted(observed_enriched_keys - expected_enriched_keys)[
                    :20
                ],
            },
        )

    try:
        mart_stats = spark.sql(
            f"""/* gold:mart_integrity */
            SELECT
              COUNT(*) AS total_rows,
              COUNT_IF({mart_key} IS NULL OR
                       TRIM(CAST({mart_key} AS STRING)) = '') AS null_keys,
              COUNT(DISTINCT {mart_key}) AS distinct_keys
            FROM {mart}"""
        ).collect()[0]
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Gold aggregate mart {mart} is missing or unreadable "
            f"({type(exc).__name__}). Run the 03_gold aggregate cell.",
            {"stage": "mart", "table": mart, "error_type": type(exc).__name__},
        )

    mart_total = int(mart_stats[0])
    mart_null = int(mart_stats[1])
    mart_distinct = int(mart_stats[2])
    expected_mart_total = len(source_group_keys)
    if (
        mart_null
        or mart_distinct != mart_total
        or mart_total != expected_mart_total
    ):
        return _fail(
            f"Gold mart {mart} has the wrong grain: expected one non-null, "
            f"unique {mart_key_name} row for each of the "
            f"{expected_mart_total:,} upstream business keys.",
            {
                "stage": "mart",
                "row_count": mart_total,
                "expected_row_count": expected_mart_total,
                "null_keys": mart_null,
                "distinct_keys": mart_distinct,
            },
        )

    try:
        mart_keys = _collect_keys(
            spark,
            f"""/* gold:mart_keys */
            SELECT CAST({mart_key} AS STRING) AS entity_key FROM {mart}""",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read business keys from {mart} ({type(exc).__name__}).",
            {"stage": "mart", "table": mart, "error_type": type(exc).__name__},
        )
    if mart_keys != source_group_keys:
        return _fail(
            "Gold mart business-key identities do not exactly match the "
            "upstream business-key set.",
            {
                "stage": "mart_identity",
                "missing": sorted(source_group_keys - mart_keys)[:20],
                "unexpected": sorted(mart_keys - source_group_keys)[:20],
            },
        )

    # Finance's additive mart measures are part of the default contract.  A
    # future domain can set reconcile_measures=False while using the generic
    # grain/identity checks, or provide a domain-specific follow-on check.
    reconcile = ctx.extras.get("reconcile_measures", True)
    if reconcile:
        try:
            mismatches = int(
                spark.sql(
                    f"""/* gold:mart_reconciliation */
                    WITH expected AS (
                      SELECT
                        {source_group} AS business_key,
                        COUNT(*) AS transaction_count,
                        COUNT(DISTINCT `order_id`) AS order_count,
                        SUM(CAST(`units` AS DECIMAL(38, 6))) AS total_units,
                        SUM(CAST(`gross_sales` AS DECIMAL(38, 6))) AS gross_sales,
                        SUM(CAST(`net_sales` AS DECIMAL(38, 6))) AS net_sales,
                        SUM(CAST(`gross_margin` AS DECIMAL(38, 6))) AS gross_margin
                      FROM {source}
                      GROUP BY {source_group}
                    )
                    SELECT COUNT(*) AS mismatched_groups
                    FROM expected AS e
                    FULL OUTER JOIN {mart} AS m
                      ON CAST(e.business_key AS STRING) = CAST(m.{mart_key} AS STRING)
                    WHERE e.business_key IS NULL OR m.{mart_key} IS NULL
                       OR NOT (e.transaction_count <=> m.`transaction_count`)
                       OR NOT (e.order_count <=> m.`order_count`)
                       OR NOT (e.total_units <=>
                               CAST(m.`total_units` AS DECIMAL(38, 6)))
                       OR NOT (e.gross_sales <=>
                               CAST(m.`gross_sales` AS DECIMAL(38, 6)))
                       OR NOT (e.net_sales <=>
                               CAST(m.`net_sales` AS DECIMAL(38, 6)))
                       OR NOT (e.gross_margin <=>
                               CAST(m.`gross_margin` AS DECIMAL(38, 6)))"""
                ).collect()[0][0]
            )
        except Exception as exc:  # noqa: BLE001
            return _fail(
                f"Could not reconcile aggregate measures in {mart} "
                f"({type(exc).__name__}).",
                {
                    "stage": "mart_reconciliation",
                    "error_type": type(exc).__name__,
                },
            )
        if mismatches:
            return _fail(
                f"Gold mart {mart} has {mismatches} business key(s) whose "
                "additive measures do not reconcile to the transaction source.",
                {"stage": "mart_reconciliation", "mismatched_groups": mismatches},
            )

    return CheckResult(
        GOLD_CHECKPOINT_ID,
        True,
        f"Gold is ready: {detail} preserves all {source_total:,} transactions "
        f"with {len(expected_enriched_keys):,} document-enriched rows, and "
        f"{mart} has one reconciled row for each of the "
        f"{expected_mart_total:,} business keys.",
        {
            "stage": "done",
            "source_table": source,
            "detail_table": detail,
            "mart_table": mart,
            "source_rows": source_total,
            "detail_rows": detail_total,
            "enriched_rows": len(observed_enriched_keys),
            "mart_rows": mart_total,
            "measures_reconciled": bool(reconcile),
        },
    )
