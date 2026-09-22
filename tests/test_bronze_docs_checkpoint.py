"""Tests for the 01_bronze_docs checkpoint, off-platform via a fake Spark session.

The checkpoint asserts externally-observable state only: the count of ``*.pdf``
files under the volume's ``documents/`` folder (via the ``binaryFile`` reader)
and the bronze table's existence and row count, both compared against the number
of PDFs the workshop *ships* for the domain (counted from the committed
``data/<domain>/documents`` tree). The fake Spark below answers exactly those
two probes and records the reader shape so the probe can't silently regress.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.bronze_docs import (
    BRONZE_DOCS_CHECKPOINT_ID,
    DEFAULT_BRONZE_TABLE,
    _count_source_pdfs,
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
        self._format: str | None = None
        self._options: dict[str, object] = {}

    def format(self, fmt: str) -> "_Reader":
        self._format = fmt
        return self

    def option(self, key: str, value: object) -> "_Reader":
        self._options[key] = value
        return self

    def load(self, path: str) -> _DF:
        # Record the full reader shape so a regression (wrong format, dropped
        # recursive/glob option, or wrong path) is caught by assertions.
        self._spark.reads.append(
            {"format": self._format, "options": dict(self._options), "path": path}
        )
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
        self.reads: list[dict] = []  # every reader.load(...) call, in order

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


# The volume's documents/ folder the checkpoint probes, and the bronze table.
_DOCS_PATH = "/Volumes/c/finance/landing/documents"
_TABLE = f"c.finance.{DEFAULT_BRONZE_TABLE}"  # stripped key FakeSpark.sql sees
_TABLE_FQ = f"`c`.`finance`.`{DEFAULT_BRONZE_TABLE}`"  # backtick-quoted, in details

# The committed Finance source ships this many PDFs; the checkpoint derives it.
FINANCE_EXPECTED = 25


def test_finance_source_count_is_25():
    # Anchors the domain-derived expected count to the committed tree, so the
    # rest of the Finance tests (24 fails, 25 passes) are grounded in reality.
    assert _count_source_pdfs("finance") == FINANCE_EXPECTED


def test_registered():
    assert BRONZE_DOCS_CHECKPOINT_ID in workshop.registry


def test_requires_a_workspace():
    result = workshop.check(BRONZE_DOCS_CHECKPOINT_ID)  # no spark
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_missing_catalog_or_schema_args():
    result = _check(FakeSpark(), catalog=None, schema=None, domain="finance")
    assert result.passed is False
    assert "No catalog/schema to check" in result.message


def test_missing_domain_and_no_override():
    result = _check(FakeSpark(), catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert "domain=config.domain" in result.message


def test_no_committed_source_docs_for_empty_domain():
    # 'security'/'itsm' ship an empty data/<domain>/documents placeholder today
    # (their PDFs land in #13/#14). The checkpoint refuses to validate against
    # zero shipped docs rather than passing on nothing.
    result = _check(FakeSpark(), catalog="c", schema="security", volume="landing", domain="security")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert result.details["expected"] == 0
    assert "No committed source PDFs found" in result.message


def test_unreadable_volume_is_targeted():
    spark = FakeSpark(unreadable_paths={_DOCS_PATH})
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "volume"
    assert "Could not read PDFs" in result.message
    assert result.details["error_type"]


def test_no_pdfs_in_volume():
    spark = FakeSpark(pdfs_by_path={_DOCS_PATH: 0})
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "volume"
    assert "No PDFs found" in result.message
    assert result.details["expected"] == FINANCE_EXPECTED


def test_finance_24_landed_fails():
    # One document short of what Finance ships -> RED (the old >=20 floor bug).
    spark = FakeSpark(
        pdfs_by_path={_DOCS_PATH: 24},
        rows_by_table={_TABLE: 24},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "volume"
    assert result.details["pdf_count"] == 24
    assert result.details["expected"] == FINANCE_EXPECTED


def test_finance_25_landed_passes():
    spark = FakeSpark(
        pdfs_by_path={_DOCS_PATH: FINANCE_EXPECTED},
        rows_by_table={_TABLE: FINANCE_EXPECTED},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["pdf_count"] == FINANCE_EXPECTED
    assert result.details["row_count"] == FINANCE_EXPECTED
    assert result.details["expected"] == FINANCE_EXPECTED


def test_stray_pdf_outside_documents_does_not_affect_result():
    # A stray PDF at the volume root must not count: the checkpoint probes only
    # the documents/ subpath, so a valid 25-doc bronze table stays green.
    spark = FakeSpark(
        pdfs_by_path={
            _DOCS_PATH: FINANCE_EXPECTED,
            "/Volumes/c/finance/landing": FINANCE_EXPECTED + 99,  # stray, elsewhere
            "/Volumes/c/finance/landing/stray.pdf": 1,
        },
        rows_by_table={_TABLE: FINANCE_EXPECTED},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is True
    # Confirm the probe only ever read the documents/ subpath.
    assert [r["path"] for r in spark.reads] == [_DOCS_PATH]


def test_table_missing_after_pdfs_landed():
    spark = FakeSpark(pdfs_by_path={_DOCS_PATH: FINANCE_EXPECTED})  # no table
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "table"
    assert "is missing or unreadable" in result.message
    assert result.details["table"] == _TABLE_FQ


def test_row_count_mismatch():
    spark = FakeSpark(
        pdfs_by_path={_DOCS_PATH: FINANCE_EXPECTED},
        rows_by_table={_TABLE: FINANCE_EXPECTED - 1},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "table"
    assert result.details["expected"] == FINANCE_EXPECTED
    assert result.details["row_count"] == FINANCE_EXPECTED - 1


def test_reader_probe_shape():
    # Guard the probe: binaryFile + recursive lookup + *.pdf glob + documents/ path.
    spark = FakeSpark(
        pdfs_by_path={_DOCS_PATH: FINANCE_EXPECTED},
        rows_by_table={_TABLE: FINANCE_EXPECTED},
    )
    _check(spark, catalog="c", schema="finance", volume="landing", domain="finance")
    read = spark.reads[0]
    assert read["format"] == "binaryFile"
    assert read["options"]["recursiveFileLookup"] == "true"
    assert read["options"]["pathGlobFilter"] == "*.pdf"
    assert read["path"] == _DOCS_PATH
    assert read["path"].endswith("/documents")


def test_expected_docs_override_bypasses_source_and_domain():
    # The documented fallback: an explicit expected count, no domain needed.
    spark = FakeSpark(
        pdfs_by_path={_DOCS_PATH: 3},
        rows_by_table={_TABLE: 3},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing", expected_docs=3)
    assert result.passed is True
    assert result.details["expected"] == 3


def test_custom_table_name_extra():
    spark = FakeSpark(
        pdfs_by_path={_DOCS_PATH: FINANCE_EXPECTED},
        rows_by_table={"c.finance.my_bronze": FINANCE_EXPECTED},
    )
    result = _check(
        spark,
        catalog="c",
        schema="finance",
        volume="landing",
        domain="finance",
        table="my_bronze",
    )
    assert result.passed is True
    assert result.details["table"] == "`c`.`finance`.`my_bronze`"
