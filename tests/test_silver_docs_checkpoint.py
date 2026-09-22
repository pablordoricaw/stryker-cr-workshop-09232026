"""Tests for the 02_silver_docs checkpoint, off-platform via a fake Spark session.

The checkpoint asserts externally-observable state only: the consolidated
``silver_docs`` table (row count == shipped documents, every row has parsed text
and a valid predicted class) and one ``silver_<class>`` extraction table per
shipped class whose row counts sum to the shipped document count. Expected
classes and count are derived from the committed ``data/<domain>/documents``
tree, never hardcoded. The fake below answers exactly the three query shapes the
checkpoint issues (the ``silver_docs`` integrity aggregate, the DISTINCT-class
probe, and each per-class ``count(*)``) and records nothing else.
"""

from __future__ import annotations

import re

import workshop
from workshop.checkpoints.silver_docs import (
    SILVER_DOCS_CHECKPOINT_ID,
    _source_class_counts,
    silver_class_table,
)

# The committed Finance source ships these five classes, five PDFs each.
FINANCE_CLASSES = {
    "vendor_invoice",
    "purchase_order",
    "sales_contract_pricing_agreement",
    "quarterly_financial_statement",
    "other",
}
FINANCE_EXPECTED_DOCS = 25


class _Row:
    """Positional row: ``row[i]`` returns the i-th configured value."""

    def __init__(self, values: list) -> None:
        self._values = values

    def __getitem__(self, index: int):
        return self._values[index]


class _DF:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def collect(self) -> list[_Row]:
        return self._rows


class FakeSpark:
    """Answers the three query shapes the checkpoint issues.

    Test identifiers carry no backticks, so stripping backticks recovers the
    fully-qualified table names the checkpoint built.

    Args:
        total/blank_text/null_class: the ``silver_docs`` integrity aggregate.
        distinct_classes: the DISTINCT predicted-class values in ``silver_docs``.
        per_class_rows: row count for each per-class ``silver_<class>`` table;
            a class absent from this map models a missing table (query raises).
        docs_table_missing: model ``silver_docs`` itself being absent.
    """

    def __init__(
        self,
        *,
        total: int = FINANCE_EXPECTED_DOCS,
        blank_text: int = 0,
        null_class: int = 0,
        distinct_classes: set[str] | None = None,
        per_class_rows: dict[str, int] | None = None,
        docs_table_missing: bool = False,
    ) -> None:
        self.total = total
        self.blank_text = blank_text
        self.null_class = null_class
        self.distinct_classes = (
            distinct_classes if distinct_classes is not None else set(FINANCE_CLASSES)
        )
        self.per_class_rows = per_class_rows or {}
        self.docs_table_missing = docs_table_missing
        self.queries: list[str] = []

    def sql(self, query: str) -> _DF:
        self.queries.append(query)
        q = " ".join(query.replace("`", "").split())
        lowered = q.lower()

        # silver_docs integrity aggregate: count(*), count_if(...text...), count_if(...class...)
        if "count_if" in lowered and lowered.startswith("select count(*)"):
            if self.docs_table_missing:
                raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND: silver_docs")
            return _DF([_Row([self.total, self.blank_text, self.null_class])])

        # DISTINCT predicted classes.
        if lowered.startswith("select distinct"):
            return _DF([_Row([c]) for c in sorted(self.distinct_classes)])

        # Per-class count(*) FROM <...silver_class>.
        if lowered.startswith("select count(*) from "):
            table = q[len("SELECT count(*) FROM ") :].strip()
            cls = table.split(".")[-1]  # silver_<class>
            if cls not in self.per_class_rows:
                raise RuntimeError(f"TABLE_OR_VIEW_NOT_FOUND: {table}")
            return _DF([_Row([self.per_class_rows[cls]])])

        raise AssertionError(f"unexpected SQL: {query!r}")


def _check(spark, **kwargs):
    return workshop.check(SILVER_DOCS_CHECKPOINT_ID, spark=spark, **kwargs)


def _all_class_tables(counts: dict[str, int]) -> dict[str, int]:
    """Map each ``silver_<class>`` table name to a per-class row count."""
    return {silver_class_table(cls): n for cls, n in counts.items()}


# A well-formed Finance silver layer: 5 docs per class, tables named silver_<class>.
_FINANCE_PER_CLASS = _all_class_tables(dict.fromkeys(FINANCE_CLASSES, 5))


def test_finance_source_shape():
    # Anchors the domain-derived expectations to the committed tree, grounding
    # the rest of the Finance tests (25 docs across the five classes).
    counts = _source_class_counts("finance")
    assert counts is not None
    assert {c for c, n in counts.items() if n > 0} == FINANCE_CLASSES
    assert sum(counts.values()) == FINANCE_EXPECTED_DOCS


def test_registered():
    assert SILVER_DOCS_CHECKPOINT_ID in workshop.registry


def test_requires_a_workspace():
    result = workshop.check(SILVER_DOCS_CHECKPOINT_ID)  # no spark
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_missing_catalog_or_schema_args():
    result = _check(FakeSpark(), catalog=None, schema=None, domain="finance")
    assert result.passed is False
    assert "No catalog/schema to check" in result.message


def test_missing_domain_and_no_override():
    result = _check(FakeSpark(), catalog="c", schema="finance")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert "domain=config.domain" in result.message


def test_no_committed_source_docs_for_empty_domain():
    # security/itsm ship empty data/<domain>/documents placeholders today (their
    # PDFs land in #13/#14). The checkpoint refuses to validate against zero
    # shipped docs rather than passing on nothing.
    result = _check(FakeSpark(), catalog="c", schema="security", domain="security")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert result.details["expected_docs"] == 0
    assert "No committed source PDFs found" in result.message


def test_silver_docs_missing_is_targeted():
    spark = FakeSpark(docs_table_missing=True)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert "missing or unreadable" in result.message
    assert result.details["error_type"] == "RuntimeError"


def test_silver_docs_wrong_row_count():
    spark = FakeSpark(total=FINANCE_EXPECTED_DOCS - 1)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert result.details["row_count"] == FINANCE_EXPECTED_DOCS - 1
    assert result.details["expected_docs"] == FINANCE_EXPECTED_DOCS


def test_blank_parsed_text_fails():
    spark = FakeSpark(blank_text=2)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert result.details["blank_text"] == 2
    assert "no parsed text" in result.message


def test_null_class_fails():
    spark = FakeSpark(null_class=3)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert result.details["null_class"] == 3
    assert "no predicted class" in result.message


def test_unexpected_class_label_fails():
    spark = FakeSpark(distinct_classes=FINANCE_CLASSES | {"hallucinated_class"})
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert "hallucinated_class" in result.details["unexpected_classes"]


def test_missing_per_class_table_fails():
    # Drop one class's extraction table; the rest are present.
    per_class = dict(_FINANCE_PER_CLASS)
    del per_class[silver_class_table("other")]
    spark = FakeSpark(per_class_rows=per_class)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "extract"
    assert silver_class_table("other") in result.details["missing_tables"]


def test_per_class_row_total_mismatch_fails():
    # All tables present, but one is short a row -> total 24, expected 25.
    per_class = dict(_FINANCE_PER_CLASS)
    per_class[silver_class_table("other")] = 4
    spark = FakeSpark(per_class_rows=per_class)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is False
    assert result.details["stage"] == "extract"
    assert result.details["per_class_total"] == FINANCE_EXPECTED_DOCS - 1
    assert result.details["expected_docs"] == FINANCE_EXPECTED_DOCS


def test_green_when_parsed_classified_and_extracted():
    spark = FakeSpark(per_class_rows=_FINANCE_PER_CLASS)
    result = _check(spark, catalog="c", schema="finance", domain="finance")
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["row_count"] == FINANCE_EXPECTED_DOCS
    assert sorted(result.details["expected_classes"]) == sorted(FINANCE_CLASSES)
    assert sum(result.details["per_class_counts"].values()) == FINANCE_EXPECTED_DOCS


def test_green_quotes_identifiers():
    # Catalog/schema with a hyphen and a space must be backtick-quoted in every
    # query the checkpoint issues.
    spark = FakeSpark(per_class_rows=_FINANCE_PER_CLASS)
    result = _check(
        spark, catalog="team-catalog", schema="finance data", domain="finance"
    )
    assert result.passed is True
    docs_query = next(q for q in spark.queries if "count_if" in q)
    assert "`team-catalog`.`finance data`.`silver_docs`" in docs_query
    # Every per-class table is fully backtick-quoted too.
    per_class_queries = [
        q for q in spark.queries if q.strip().lower().startswith("select count(*) from")
    ]
    assert per_class_queries
    for q in per_class_queries:
        assert re.search(r"`team-catalog`\.`finance data`\.`silver_[a-z_]+`", q)


def test_expected_overrides_bypass_source_and_domain():
    # The documented fallback: explicit classes + count, no domain needed.
    per_class = _all_class_tables({"a": 2, "b": 1})
    spark = FakeSpark(
        total=3,
        distinct_classes={"a", "b"},
        per_class_rows=per_class,
    )
    result = _check(
        spark,
        catalog="c",
        schema="finance",
        expected_classes=["a", "b"],
        expected_docs=3,
    )
    assert result.passed is True
    assert result.details["row_count"] == 3
    assert sorted(result.details["expected_classes"]) == ["a", "b"]


def test_custom_class_table_prefix_extra():
    per_class = {f"slv_{cls}": 5 for cls in FINANCE_CLASSES}
    spark = FakeSpark(per_class_rows=per_class)
    result = _check(
        spark,
        catalog="c",
        schema="finance",
        domain="finance",
        class_table_prefix="slv_",
    )
    assert result.passed is True
    assert result.details["stage"] == "done"
