"""Tests for the 01_bronze_docs checkpoint, off-platform via a fake Spark session.

The checkpoint asserts externally-observable state only: the count of ``*.pdf``
files on the UC Volume (via the ``binaryFile`` reader) and the bronze table's
existence and row count. The fake Spark below answers exactly those two probes.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.bronze_docs import (
    BRONZE_DOCS_CHECKPOINT_ID,
    DEFAULT_BRONZE_TABLE,
    MIN_DOCUMENTS,
)


class _DF:
    """Answers both ``.count()`` (volume probe) and ``.collect()`` (table probe)."""

    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count

    def collect(self) -> list[list[int]]:
        return [[self._count]]


class _Reader:
    def __init__(self, spark: "FakeSpark") -> None:
        self._spark = spark

    def format(self, _fmt: str) -> "_Reader":
        return self

    def option(self, _key: str, _value: object) -> "_Reader":
        return self

    def load(self, path: str) -> _DF:
        if path in self._spark.unreadable_paths:
            raise RuntimeError(f"Path does not exist: {path}")
        return _DF(self._spark.pdfs_by_path.get(path, 0))


class FakeSpark:
    """Answers the binaryFile volume read and the ``SELECT count(*)`` table read.

    Test identifiers carry no backticks, so stripping backticks recovers the
    fully-qualified table name the checkpoint built.
    """

    def __init__(
        self,
        *,
        pdfs_by_path: dict[str, int] | None = None,
        unreadable_paths: set[str] | None = None,
        rows_by_table: dict[str, int] | None = None,
    ) -> None:
        self.pdfs_by_path = pdfs_by_path or {}
        self.unreadable_paths = unreadable_paths or set()
        self.rows_by_table = rows_by_table or {}

    @property
    def read(self) -> _Reader:
        return _Reader(self)

    def sql(self, query: str) -> _DF:
        q = query.replace("`", "").strip()
        assert q.upper().startswith("SELECT COUNT(*) FROM "), f"unexpected SQL: {query!r}"
        table = q[len("SELECT count(*) FROM ") :].strip()
        if table not in self.rows_by_table:
            raise RuntimeError(f"Table or view not found: {table}")
        return _DF(self.rows_by_table[table])


def _check(spark, **kwargs):
    return workshop.check(BRONZE_DOCS_CHECKPOINT_ID, spark=spark, **kwargs)


_VOLUME_PATH = "/Volumes/c/finance/landing"
# What FakeSpark.sql sees after stripping backticks (its rows_by_table key)...
_TABLE = f"c.finance.{DEFAULT_BRONZE_TABLE}"
# ...and the backtick-quoted form the checkpoint reports in details["table"].
_TABLE_FQ = f"`c`.`finance`.`{DEFAULT_BRONZE_TABLE}`"


def test_registered():
    assert BRONZE_DOCS_CHECKPOINT_ID in workshop.registry


def test_requires_a_workspace():
    result = workshop.check(BRONZE_DOCS_CHECKPOINT_ID)  # no spark
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_missing_catalog_or_schema_args():
    result = _check(FakeSpark(), catalog=None, schema=None)
    assert result.passed is False
    assert "No catalog/schema to check" in result.message


def test_unreadable_volume_is_targeted():
    spark = FakeSpark(unreadable_paths={_VOLUME_PATH})
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["stage"] == "volume"
    assert "Could not read PDFs" in result.message
    assert "error_type" in result.details


def test_no_pdfs_in_volume():
    spark = FakeSpark(pdfs_by_path={_VOLUME_PATH: 0})
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["stage"] == "volume"
    assert "No PDFs found" in result.message


def test_too_few_pdfs_in_volume():
    spark = FakeSpark(pdfs_by_path={_VOLUME_PATH: MIN_DOCUMENTS - 1})
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["stage"] == "volume"
    assert result.details["pdf_count"] == MIN_DOCUMENTS - 1
    assert f">= {MIN_DOCUMENTS}" in result.message


def test_table_missing_after_pdfs_landed():
    spark = FakeSpark(pdfs_by_path={_VOLUME_PATH: 25})  # no table registered
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["stage"] == "table"
    assert "is missing or unreadable" in result.message
    assert result.details["table"] == _TABLE_FQ


def test_row_count_mismatch():
    spark = FakeSpark(
        pdfs_by_path={_VOLUME_PATH: 25},
        rows_by_table={_TABLE: 24},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["stage"] == "table"
    assert result.details["pdf_count"] == 25
    assert result.details["row_count"] == 24


def test_green_when_pdfs_and_table_match():
    spark = FakeSpark(
        pdfs_by_path={_VOLUME_PATH: 25},
        rows_by_table={_TABLE: 25},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["pdf_count"] == 25
    assert result.details["row_count"] == 25


def test_green_at_minimum_threshold():
    spark = FakeSpark(
        pdfs_by_path={_VOLUME_PATH: MIN_DOCUMENTS},
        rows_by_table={_TABLE: MIN_DOCUMENTS},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is True


def test_custom_table_name_extra():
    spark = FakeSpark(
        pdfs_by_path={_VOLUME_PATH: 25},
        rows_by_table={"c.finance.my_bronze": 25},  # stripped key FakeSpark.sql sees
    )
    result = _check(
        spark, catalog="c", schema="finance", volume="landing", table="my_bronze"
    )
    assert result.passed is True
    assert result.details["table"] == "`c`.`finance`.`my_bronze`"
