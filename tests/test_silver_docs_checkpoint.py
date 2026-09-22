"""Tests for the 02_silver_docs checkpoint, off-platform via a fake Spark session.

The checkpoint asserts externally-observable state only: ``silver_docs`` covers
the shipped document *identity set* exactly (one row per ``<class>/<filename>``,
non-blank parsed text, valid predicted class) and one ``silver_<class>`` table
per class extracts every document once with no ``ai_extract`` errors.

Behavioral tests inject the expected shape by **mocking the source-discovery
seam** (``_source_doc_keys``) or via the ``expected_doc_keys`` override, so they
never depend on which PDFs a domain happens to ship in the repo today — when #13
adds Security documents, none of these tests change. One test exercises the real
discovery function against this ticket's committed Finance tree, and one uses a
temp tree to pin the non-recursive globbing.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

import workshop
from workshop.checkpoints import silver_docs as mod
from workshop.checkpoints.silver_docs import (
    SILVER_DOCS_CHECKPOINT_ID,
    _source_doc_keys,
)

# A small, domain-neutral mocked source tree: two classes, three documents.
MOCK_KEYS = {"alpha/a1.pdf", "alpha/a2.pdf", "beta/b1.pdf"}


class _Row:
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
    """Answers the four query shapes the checkpoint issues, from configured state.

    Args:
        observed_keys: distinct ``source_class/filename`` identities in silver_docs.
        total/blank_text/null_class/distinct_keys: the silver_docs integrity
            aggregate (default consistent with ``observed_keys``).
        predicted_classes: distinct ``doc_class`` values (default = key prefixes).
        per_class: ``{table_name: (row_count, error_count, distinct_paths)}``; a
            class whose table is absent models a missing table (query raises).
        docs_missing: model ``silver_docs`` itself being absent.
    """

    def __init__(
        self,
        *,
        observed_keys: set[str] | None = None,
        total: int | None = None,
        blank_text: int = 0,
        null_class: int = 0,
        distinct_keys: int | None = None,
        predicted_classes: set[str] | None = None,
        per_class: dict[str, tuple[int, int, int]] | None = None,
        docs_missing: bool = False,
    ) -> None:
        self.observed_keys = set(observed_keys) if observed_keys is not None else set()
        self.total = total if total is not None else len(self.observed_keys)
        self.blank_text = blank_text
        self.null_class = null_class
        self.distinct_keys = (
            distinct_keys if distinct_keys is not None else len(self.observed_keys)
        )
        self.predicted_classes = (
            set(predicted_classes)
            if predicted_classes is not None
            else {k.split("/", 1)[0] for k in self.observed_keys}
        )
        self.per_class = per_class or {}
        self.docs_missing = docs_missing
        self.queries: list[str] = []

    def sql(self, query: str) -> _DF:
        self.queries.append(query)
        q = " ".join(query.replace("`", "").split())
        ql = q.lower()

        if ql.startswith("select distinct concat_ws"):  # observed identity set
            return _DF([_Row([k]) for k in sorted(self.observed_keys)])
        if ql.startswith("select distinct"):  # predicted classes
            return _DF([_Row([c]) for c in sorted(self.predicted_classes)])
        if "as total" in ql:  # silver_docs integrity aggregate
            if self.docs_missing:
                raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND: silver_docs")
            return _DF([_Row([self.total, self.blank_text, self.null_class, self.distinct_keys])])
        if "distinct_paths" in ql:  # per-class extraction aggregate
            table = q.rsplit(" FROM ", 1)[-1].strip()
            cls_table = table.split(".")[-1]
            if cls_table not in self.per_class:
                raise RuntimeError(f"TABLE_OR_VIEW_NOT_FOUND: {table}")
            n, errs, distinct_paths = self.per_class[cls_table]
            return _DF([_Row([n, errs, distinct_paths])])

        raise AssertionError(f"unexpected SQL: {query!r}")


def _healthy(keys: set[str], *, prefix: str = "silver_") -> FakeSpark:
    """A FakeSpark whose state exactly satisfies the checkpoint for ``keys``."""
    by_class = Counter(k.split("/", 1)[0] for k in keys)
    per_class = {f"{prefix}{c}": (n, 0, n) for c, n in by_class.items()}
    return FakeSpark(observed_keys=set(keys), per_class=per_class)


@pytest.fixture
def mock_source(monkeypatch):
    """Patch the source-discovery seam to return a controlled identity set."""

    def _set(keys):
        monkeypatch.setattr(mod, "_source_doc_keys", lambda domain: keys)

    return _set


def _check(spark, **kwargs):
    return workshop.check(SILVER_DOCS_CHECKPOINT_ID, spark=spark, **kwargs)


# --- framework wiring -------------------------------------------------------


def test_registered():
    assert SILVER_DOCS_CHECKPOINT_ID in workshop.registry


def test_requires_a_workspace():
    result = workshop.check(SILVER_DOCS_CHECKPOINT_ID)  # no spark
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_missing_catalog_or_schema_args(mock_source):
    mock_source(MOCK_KEYS)
    result = _check(FakeSpark(), catalog=None, schema=None, domain="demo")
    assert result.passed is False
    assert "No catalog/schema to check" in result.message


def test_missing_domain_and_no_override():
    result = _check(FakeSpark(), catalog="c", schema="s")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert "domain=config.domain" in result.message


def test_source_seam_returns_none(mock_source):
    # Repo root / source tree not locatable -> distinct "cannot locate" failure.
    mock_source(None)
    result = _check(FakeSpark(), catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert "Could not locate" in result.message


def test_empty_source_tree(mock_source):
    # A domain that ships no documents yet (e.g. Security/ITSM before #13/#14):
    # refuse to validate against nothing rather than pass on zero docs.
    mock_source(set())
    result = _check(FakeSpark(), catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "expected"
    assert result.details["expected_docs"] == 0
    assert "No committed source PDFs found" in result.message


# --- silver_docs integrity / identity ---------------------------------------


def test_silver_docs_missing_is_targeted(mock_source):
    mock_source(MOCK_KEYS)
    result = _check(FakeSpark(docs_missing=True), catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert "missing or unreadable" in result.message
    assert result.details["error_type"] == "RuntimeError"


def test_blank_parsed_text_fails(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.blank_text = 1
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert result.details["blank_text"] == 1
    assert "blank parsed text" in result.message


def test_integrity_query_uses_trim(mock_source):
    # Blocking #3: whitespace-only text must fail, so the predicate must trim.
    # Assert the issued SQL actually trims (the live test proves the behavior on
    # a real "   " row); count_if(... trim(text) = '' ...) feeds blank_text.
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    _check(spark, catalog="c", schema="s", domain="demo")
    integrity_q = next(q for q in spark.queries if "AS total" in q)
    assert "trim(" in integrity_q.lower()


def test_null_class_fails(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.null_class = 2
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert result.details["null_class"] == 2
    assert "no predicted class" in result.message


def test_duplicate_document_fails(mock_source):
    # Blocking #2: a missing doc + a duplicate doc keeps TOTAL correct but must
    # still fail. Here alpha/a1 is duplicated and alpha/a2 is missing: total=3
    # but only 2 distinct identities.
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.observed_keys = {"alpha/a1.pdf", "beta/b1.pdf"}  # a2 missing, a1 duped
    spark.total = 3
    spark.distinct_keys = 2
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert result.details["row_count"] == 3
    assert result.details["distinct_keys"] == 2
    assert "duplicate" in result.message


def test_missing_document_fails(mock_source):
    # A document simply absent (no duplicate): total/distinct agree but the
    # observed identity set != expected.
    mock_source(MOCK_KEYS)
    spark = FakeSpark(
        observed_keys={"alpha/a1.pdf", "beta/b1.pdf"},  # alpha/a2 missing
        per_class={"silver_alpha": (1, 0, 1), "silver_beta": (1, 0, 1)},
    )
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert "alpha/a2.pdf" in result.details["missing"]
    assert result.details["expected_docs"] == 3


def test_unexpected_document_fails(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.observed_keys = MOCK_KEYS | {"gamma/g1.pdf"}
    spark.total = 4
    spark.distinct_keys = 4
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert "gamma/g1.pdf" in result.details["unexpected"]


def test_unexpected_class_label_fails(mock_source):
    # Identity is fine, but ai_classify produced a label off the fixed set.
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.predicted_classes = {"alpha", "beta", "hallucinated"}
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "silver_docs"
    assert "hallucinated" in result.details["unexpected_classes"]


# --- per-class extraction ----------------------------------------------------


def test_missing_per_class_table_fails(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    del spark.per_class["silver_beta"]
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "extract"
    assert "silver_beta" in result.details["missing_tables"]


def test_extraction_error_fails(mock_source):
    # Blocking #1: row count is correct, but a row carries a non-null
    # extract_error (ai_extract failed) -> must NOT pass.
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.per_class["silver_alpha"] = (2, 1, 2)  # 2 rows, 1 with an error
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "extract"
    assert result.details["extract_errors"] == 1
    assert "extraction error" in result.message.lower() or "non-null" in result.message


def test_per_class_duplicate_fails(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.per_class["silver_alpha"] = (2, 0, 1)  # 2 rows, 1 distinct path
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "extract"
    assert "duplicate" in result.message


def test_per_class_row_total_mismatch_fails(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    spark.per_class["silver_beta"] = (0, 0, 0)  # beta lost its row -> total 2, want 3
    result = _check(spark, catalog="c", schema="s", domain="demo")
    assert result.passed is False
    assert result.details["stage"] == "extract"
    assert result.details["per_class_total"] == 2
    assert result.details["expected_docs"] == 3


# --- green paths -------------------------------------------------------------


def test_green_when_parsed_classified_and_extracted(mock_source):
    mock_source(MOCK_KEYS)
    result = _check(_healthy(MOCK_KEYS), catalog="c", schema="s", domain="demo")
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["expected_docs"] == 3
    assert sorted(result.details["expected_classes"]) == ["alpha", "beta"]
    assert sum(result.details["per_class_counts"].values()) == 3


def test_green_quotes_identifiers(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS)
    result = _check(spark, catalog="team-catalog", schema="finance data", domain="demo")
    assert result.passed is True
    integrity_q = next(q for q in spark.queries if "AS total" in q)
    assert "`team-catalog`.`finance data`.`silver_docs`" in integrity_q
    per_class_queries = [q for q in spark.queries if "distinct_paths" in q]
    assert per_class_queries
    for q in per_class_queries:
        assert re.search(r"`team-catalog`\.`finance data`\.`silver_[a-z_]+`", q)


def test_expected_doc_keys_override_bypasses_domain():
    # The documented fallback: explicit identity set, no domain / filesystem.
    keys = {"x/one.pdf", "x/two.pdf", "y/three.pdf"}
    result = _check(_healthy(keys), catalog="c", schema="s", expected_doc_keys=keys)
    assert result.passed is True
    assert result.details["expected_docs"] == 3
    assert sorted(result.details["expected_classes"]) == ["x", "y"]


def test_custom_class_table_prefix_extra(mock_source):
    mock_source(MOCK_KEYS)
    spark = _healthy(MOCK_KEYS, prefix="slv_")
    result = _check(
        spark, catalog="c", schema="s", domain="demo", class_table_prefix="slv_"
    )
    assert result.passed is True
    assert result.details["stage"] == "done"


# --- source discovery (real committed data + non-recursive globbing) ---------


def test_source_discovery_reads_committed_finance_tree():
    # This ticket ships the Finance tree; anchor the discovery seam to it. Stable
    # regardless of future domains (Security/ITSM live under their own folders).
    keys = _source_doc_keys("finance")
    assert keys is not None
    classes = {k.split("/", 1)[0] for k in keys}
    assert classes == {
        "vendor_invoice",
        "purchase_order",
        "sales_contract_pricing_agreement",
        "quarterly_financial_statement",
        "other",
    }
    assert len(keys) == 25
    assert "vendor_invoice/vendor_invoice_01.pdf" in keys


def test_source_discovery_is_nonrecursive(tmp_path, monkeypatch):
    # Fold-in #5: only direct <class>/*.pdf count; a nested PDF must be ignored.
    docs = tmp_path / "data" / "demo" / "documents"
    (docs / "alpha").mkdir(parents=True)
    (docs / "alpha" / "a1.pdf").write_bytes(b"%PDF-1.4")
    (docs / "alpha" / "nested").mkdir()
    (docs / "alpha" / "nested" / "buried.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(mod, "find_repo_root", lambda start=None: str(tmp_path))
    keys = _source_doc_keys("demo")
    assert keys == {"alpha/a1.pdf"}  # buried.pdf under nested/ is excluded
