"""Off-platform behavioral tests for the observable-state ``03_gold`` check."""

from __future__ import annotations

import workshop
from workshop.checkpoints.gold import GOLD_CHECKPOINT_ID


class _Row:
    def __init__(self, values) -> None:
        self.values = values if isinstance(values, list) else [values]

    def __getitem__(self, index: int):
        return self.values[index]


class _DF:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    def collect(self) -> list[_Row]:
        return self.rows


class FakeSpark:
    """Answer each checkpoint query from a configurable observable state."""

    def __init__(
        self,
        *,
        source_keys: set[str] | None = None,
        source_total: int | None = None,
        source_null: int = 0,
        source_distinct: int | None = None,
        source_groups: set[str] | None = None,
        source_null_groups: int = 0,
        document_total: int = 2,
        document_null: int = 0,
        document_distinct: int | None = None,
        expected_enriched: set[str] | None = None,
        detail_keys: set[str] | None = None,
        detail_total: int | None = None,
        detail_null: int = 0,
        detail_distinct: int | None = None,
        observed_enriched: set[str] | None = None,
        detail_join_mismatches: int = 0,
        mart_keys: set[str] | None = None,
        mart_total: int | None = None,
        mart_null: int = 0,
        mart_distinct: int | None = None,
        reconciliation_mismatches: int = 0,
        missing_stage: str | None = None,
    ) -> None:
        self.source_keys = source_keys or {"txn-1", "txn-2", "txn-3"}
        self.source_total = (
            len(self.source_keys) if source_total is None else source_total
        )
        self.source_distinct = (
            len(self.source_keys) if source_distinct is None else source_distinct
        )
        self.source_null = source_null
        self.source_groups = source_groups or {"contract-a", "contract-b"}
        self.source_null_groups = source_null_groups
        self.document_total = document_total
        self.document_null = document_null
        self.document_distinct = (
            document_total if document_distinct is None else document_distinct
        )
        self.expected_enriched = expected_enriched or set(self.source_keys)
        self.detail_keys = detail_keys or set(self.source_keys)
        self.detail_total = (
            len(self.detail_keys) if detail_total is None else detail_total
        )
        self.detail_null = detail_null
        self.detail_distinct = (
            len(self.detail_keys) if detail_distinct is None else detail_distinct
        )
        self.observed_enriched = observed_enriched or set(self.expected_enriched)
        self.detail_join_mismatches = detail_join_mismatches
        self.mart_keys = mart_keys or set(self.source_groups)
        self.mart_total = len(self.mart_keys) if mart_total is None else mart_total
        self.mart_null = mart_null
        self.mart_distinct = (
            len(self.mart_keys) if mart_distinct is None else mart_distinct
        )
        self.reconciliation_mismatches = reconciliation_mismatches
        self.missing_stage = missing_stage
        self.queries: list[str] = []

    def sql(self, query: str) -> _DF:
        self.queries.append(query)
        markers = {
            "source_integrity": "gold:source_integrity",
            "source_keys": "gold:source_keys",
            "source_group_keys": "gold:source_group_keys",
            "documents": "gold:documents_integrity",
            "expected_enriched": "gold:expected_enriched_keys",
            "detail_integrity": "gold:detail_integrity",
            "detail_keys": "gold:detail_keys",
            "detail_join": "gold:detail_join_reconciliation",
            "observed_enriched": "gold:observed_enriched_keys",
            "mart_integrity": "gold:mart_integrity",
            "mart_keys": "gold:mart_keys",
            "reconciliation": "gold:mart_reconciliation",
        }
        stage = next((name for name, marker in markers.items() if marker in query), None)
        if stage is None:
            raise AssertionError(f"unexpected SQL: {query!r}")
        if self.missing_stage == stage:
            raise RuntimeError(f"TABLE_OR_VIEW_NOT_FOUND at {stage}")

        if stage == "source_integrity":
            return _DF(
                [
                    _Row(
                        [
                            self.source_total,
                            self.source_null,
                            self.source_distinct,
                            self.source_null_groups,
                        ]
                    )
                ]
            )
        if stage == "source_keys":
            return _DF([_Row(value) for value in sorted(self.source_keys)])
        if stage == "source_group_keys":
            return _DF([_Row(value) for value in sorted(self.source_groups)])
        if stage == "documents":
            return _DF(
                [
                    _Row(
                        [
                            self.document_total,
                            self.document_null,
                            self.document_distinct,
                        ]
                    )
                ]
            )
        if stage == "expected_enriched":
            return _DF([_Row(value) for value in sorted(self.expected_enriched)])
        if stage == "detail_integrity":
            return _DF(
                [
                    _Row(
                        [
                            self.detail_total,
                            self.detail_null,
                            self.detail_distinct,
                        ]
                    )
                ]
            )
        if stage == "detail_keys":
            return _DF([_Row(value) for value in sorted(self.detail_keys)])
        if stage == "detail_join":
            return _DF([_Row(self.detail_join_mismatches)])
        if stage == "observed_enriched":
            return _DF([_Row(value) for value in sorted(self.observed_enriched)])
        if stage == "mart_integrity":
            return _DF(
                [_Row([self.mart_total, self.mart_null, self.mart_distinct])]
            )
        if stage == "mart_keys":
            return _DF([_Row(value) for value in sorted(self.mart_keys)])
        if stage == "reconciliation":
            return _DF([_Row(self.reconciliation_mismatches)])
        raise AssertionError(f"unhandled stage: {stage}")


def _check(spark, **kwargs):
    return workshop.check(
        GOLD_CHECKPOINT_ID, spark=spark, catalog="catalog", schema="schema", **kwargs
    )


def test_registered():
    assert GOLD_CHECKPOINT_ID in workshop.registry


def test_requires_workspace():
    result = workshop.check(GOLD_CHECKPOINT_ID)
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_requires_catalog_and_schema():
    result = workshop.check(GOLD_CHECKPOINT_ID, spark=FakeSpark())
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_missing_source_is_targeted():
    result = _check(FakeSpark(missing_stage="source_integrity"))
    assert result.passed is False
    assert result.details["stage"] == "source"
    assert "transaction table" in result.message


def test_null_source_key_fails():
    result = _check(FakeSpark(source_total=4, source_null=1, source_distinct=3))
    assert result.passed is False
    assert result.details["stage"] == "source"
    assert result.details["null_keys"] == 1


def test_duplicate_source_key_fails():
    result = _check(FakeSpark(source_total=4, source_distinct=3))
    assert result.passed is False
    assert result.details["stage"] == "source"
    assert result.details["distinct_keys"] == 3


def test_missing_document_table_is_targeted():
    result = _check(FakeSpark(missing_stage="documents"))
    assert result.passed is False
    assert result.details["stage"] == "documents"
    assert "silver document stage" in result.message


def test_null_document_join_key_fails():
    result = _check(FakeSpark(document_total=3, document_null=1, document_distinct=2))
    assert result.passed is False
    assert result.details["stage"] == "documents"
    assert result.details["null_keys"] == 1


def test_duplicate_document_join_key_fails_before_it_multiplies_grain():
    result = _check(FakeSpark(document_total=3, document_distinct=2))
    assert result.passed is False
    assert result.details["stage"] == "documents"
    assert result.details["distinct_keys"] == 2


def test_upstream_join_must_produce_enrichment():
    spark = FakeSpark()
    spark.expected_enriched = set()
    result = _check(spark)
    assert result.passed is False
    assert result.details["stage"] == "upstream_join"


def test_missing_gold_detail_is_targeted():
    result = _check(FakeSpark(missing_stage="detail_integrity"))
    assert result.passed is False
    assert result.details["stage"] == "detail"
    assert "03_gold" in result.message


def test_null_detail_key_fails():
    result = _check(FakeSpark(detail_total=4, detail_null=1, detail_distinct=3))
    assert result.passed is False
    assert result.details["stage"] == "detail"
    assert result.details["null_keys"] == 1


def test_duplicate_detail_key_fails_even_when_total_matches_source():
    result = _check(FakeSpark(detail_total=3, detail_distinct=2))
    assert result.passed is False
    assert result.details["stage"] == "detail"
    assert result.details["row_count"] == result.details["expected_row_count"]


def test_wrong_detail_grain_fails():
    result = _check(
        FakeSpark(detail_keys={"txn-1", "txn-2"}, detail_total=2, detail_distinct=2)
    )
    assert result.passed is False
    assert result.details["stage"] == "detail"
    assert result.details["expected_row_count"] == 3


def test_detail_identity_swap_fails_even_when_count_and_uniqueness_match():
    result = _check(
        FakeSpark(detail_keys={"txn-1", "txn-2", "txn-unexpected"})
    )
    assert result.passed is False
    assert result.details["stage"] == "detail_identity"
    assert result.details["missing"] == ["txn-3"]
    assert result.details["unexpected"] == ["txn-unexpected"]


def test_missing_document_enrichment_identity_fails():
    result = _check(FakeSpark(observed_enriched={"txn-1", "txn-2"}))
    assert result.passed is False
    assert result.details["stage"] == "enrichment"
    assert result.details["missing"] == ["txn-3"]


def test_partial_document_coverage_passes_with_unenriched_fact_row():
    spark = FakeSpark(
        expected_enriched={"txn-1", "txn-2"},
        observed_enriched={"txn-1", "txn-2"},
    )
    result = _check(spark)
    assert result.passed is True
    assert result.details["enriched_rows"] == 2
    join_query = next(
        query for query in spark.queries if "gold:detail_join_reconciliation" in query
    )
    assert "g.`contract_agreement_id` IS NOT NULL" in join_query


def test_wrong_transaction_to_document_association_fails():
    result = _check(FakeSpark(detail_join_mismatches=1))
    assert result.passed is False
    assert result.details["stage"] == "detail_join"
    assert result.details["mismatched_rows"] == 1


def test_missing_gold_mart_is_targeted():
    result = _check(FakeSpark(missing_stage="mart_integrity"))
    assert result.passed is False
    assert result.details["stage"] == "mart"


def test_null_mart_key_fails():
    result = _check(FakeSpark(mart_total=3, mart_null=1, mart_distinct=2))
    assert result.passed is False
    assert result.details["stage"] == "mart"
    assert result.details["null_keys"] == 1


def test_duplicate_mart_key_fails_even_when_total_matches_expected():
    result = _check(FakeSpark(mart_total=2, mart_distinct=1))
    assert result.passed is False
    assert result.details["stage"] == "mart"
    assert result.details["distinct_keys"] == 1


def test_wrong_mart_grain_fails():
    result = _check(FakeSpark(mart_keys={"contract-a"}, mart_total=1))
    assert result.passed is False
    assert result.details["stage"] == "mart"
    assert result.details["expected_row_count"] == 2


def test_mart_identity_swap_fails_even_when_count_and_uniqueness_match():
    result = _check(FakeSpark(mart_keys={"contract-a", "contract-unexpected"}))
    assert result.passed is False
    assert result.details["stage"] == "mart_identity"
    assert result.details["missing"] == ["contract-b"]


def test_mart_measure_mismatch_fails():
    result = _check(FakeSpark(reconciliation_mismatches=1))
    assert result.passed is False
    assert result.details["stage"] == "mart_reconciliation"
    assert result.details["mismatched_groups"] == 1


def test_custom_additive_measure_list_is_honored():
    spark = FakeSpark()
    result = _check(
        spark,
        reconcile_measures=["finding_count", "affected_assets"],
    )
    assert result.passed is True
    assert result.details["reconciled_measures"] == [
        "finding_count",
        "affected_assets",
    ]
    reconciliation_query = next(
        query for query in spark.queries if "gold:mart_reconciliation" in query
    )
    assert "SUM(CAST(`finding_count` AS DECIMAL(38, 6)))" in reconciliation_query
    assert "SUM(CAST(`affected_assets` AS DECIMAL(38, 6)))" in reconciliation_query
    assert "`order_id`" not in reconciliation_query
    assert "`transaction_count`" not in reconciliation_query


def test_empty_measure_list_disables_only_measure_reconciliation():
    spark = FakeSpark()
    result = _check(spark, reconcile_measures=[])
    assert result.passed is True
    assert result.details["measures_reconciled"] is False
    assert result.details["reconciled_measures"] == []
    assert not any("gold:mart_reconciliation" in query for query in spark.queries)


def test_green_and_quotes_every_identifier():
    spark = FakeSpark()
    result = workshop.check(
        GOLD_CHECKPOINT_ID,
        spark=spark,
        catalog="team-catalog",
        schema="finance data",
    )
    assert result.passed is True
    assert result.details["source_rows"] == 3
    assert result.details["detail_rows"] == 3
    assert result.details["mart_rows"] == 2
    assert all("`team-catalog`.`finance data`." in query for query in spark.queries)
    assert any(
        "`team-catalog`.`finance data`.`gold_sales`" in query
        for query in spark.queries
    )
    assert any(
        "`team-catalog`.`finance data`.`gold_contract_performance`" in query
        for query in spark.queries
    )


def test_custom_names_and_columns_are_quoted():
    spark = FakeSpark()
    result = _check(
        spark,
        source_table="raw facts",
        document_table="doc-map",
        detail_table="gold detail",
        mart_table="gold mart",
        source_key="event id",
        detail_key="event id",
        source_group_key="entity id",
        document_key="entity id",
        detail_document_key="matched entity",
        detail_document_match="document path",
        mart_key="entity id",
        reconcile_measures=False,
    )
    assert result.passed is True
    rendered = "\n".join(spark.queries)
    for identifier in (
        "`raw facts`",
        "`doc-map`",
        "`gold detail`",
        "`gold mart`",
        "`event id`",
        "`entity id`",
        "`matched entity`",
        "`document path`",
    ):
        assert identifier in rendered
