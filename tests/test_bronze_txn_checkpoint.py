"""Off-platform tests for the observable-state bronze transaction check."""

from __future__ import annotations

import workshop
from workshop.checkpoints.bronze_txn import (
    BRONZE_TXN_CHECKPOINT_ID,
    BRONZE_TXN_TABLE,
    EXPECTED_ROW_COUNT,
)


class _Row:
    def __init__(self, value: int) -> None:
        self.value = value

    def __getitem__(self, index: int) -> int:
        assert index == 0
        return self.value


class _DF:
    def __init__(self, value: int) -> None:
        self.value = value

    def collect(self) -> list[_Row]:
        return [_Row(self.value)]


class FakeSpark:
    def __init__(self, count: int | None = EXPECTED_ROW_COUNT) -> None:
        self.count = count
        self.queries: list[str] = []

    def sql(self, query: str) -> _DF:
        self.queries.append(query)
        if self.count is None:
            raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")
        return _DF(self.count)


def _check(spark, **kwargs):
    return workshop.check(BRONZE_TXN_CHECKPOINT_ID, spark=spark, **kwargs)


def test_registered():
    assert BRONZE_TXN_CHECKPOINT_ID in workshop.registry


def test_requires_workspace():
    result = workshop.check(BRONZE_TXN_CHECKPOINT_ID)
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_requires_catalog_and_schema():
    result = _check(FakeSpark(), catalog=None, schema=None)
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_missing_table_has_targeted_failure():
    result = _check(FakeSpark(None), catalog="c", schema="finance")
    assert result.passed is False
    assert result.details["error_type"] == "RuntimeError"
    assert BRONZE_TXN_TABLE in result.message
    assert "either the Lakebase CDF path or the Delta fallback" in result.message


def test_wrong_count_has_targeted_failure():
    result = _check(FakeSpark(2_999), catalog="c", schema="finance")
    assert result.passed is False
    assert result.details["row_count"] == 2_999
    assert result.details["expected_row_count"] == EXPECTED_ROW_COUNT
    assert "expected exactly 3,000" in result.message


def test_green_for_seeded_row_count_and_quotes_identifiers():
    spark = FakeSpark()
    result = _check(spark, catalog="team-catalog", schema="finance data")
    assert result.passed is True
    assert result.details["row_count"] == EXPECTED_ROW_COUNT
    assert spark.queries == [
        (
            "SELECT COUNT(*) AS row_count FROM "
            "`team-catalog`.`finance data`.`bronze_sales_transactions`"
        )
    ]


def test_domain_overrides_use_callers_namespaced_table_and_expected_count():
    spark = FakeSpark(42)

    result = _check(
        spark,
        catalog="team-catalog",
        schema="workshop_itsm_1234abcd",
        bronze_txn_table="bronze_service_tickets",
        expected_txn_rows=42,
        transaction_key="ticket_id",
    )

    assert result.passed is True
    assert result.details == {
        "table": "team-catalog.workshop_itsm_1234abcd.bronze_service_tickets",
        "row_count": 42,
        "expected_row_count": 42,
    }
    assert spark.queries == [
        (
            "SELECT COUNT(*) AS row_count FROM "
            "`team-catalog`.`workshop_itsm_1234abcd`.`bronze_service_tickets`"
        )
    ]


def test_overridden_config_wrong_count_keeps_targeted_guard():
    result = _check(
        FakeSpark(41),
        catalog="c",
        schema="itsm",
        bronze_txn_table="bronze_service_tickets",
        expected_txn_rows=42,
        transaction_key="ticket_id",
    )

    assert result.passed is False
    assert result.details["table"] == "c.itsm.bronze_service_tickets"
    assert result.details["expected_row_count"] == 42
    assert "expected exactly 42" in result.message
    assert "ticket_id" in result.message


def test_overridden_config_missing_table_keeps_targeted_guard():
    result = _check(
        FakeSpark(None),
        catalog="c",
        schema="itsm",
        bronze_txn_table="bronze_service_tickets",
        expected_txn_rows=42,
    )

    assert result.passed is False
    assert result.details["table"] == "c.itsm.bronze_service_tickets"
    assert "bronze_service_tickets" in result.message
    assert "either the Lakebase CDF path or the Delta fallback" in result.message
