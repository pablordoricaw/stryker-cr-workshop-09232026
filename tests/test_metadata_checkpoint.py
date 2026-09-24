"""Off-platform behavioral tests for the observable-state ``04_metadata`` check.

The checkpoint asserts only externally-observable Unity Catalog state: a
non-blank comment on each target table and every column, a non-blank PI
classification tag on at least ``min_pi_columns`` columns, and a non-blank
business-domain tag on each table. A fake Spark session answers the four
``information_schema`` queries the checkpoint issues (routed by SQL marker
comment), so the tests never touch a workspace and never depend on which columns
a domain happens to ship. Security (#13) and ITSM (#14) reuse the module with
their own gold tables and none of these tests change.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.metadata import (
    DEFAULT_PI_TAG_NAME,
    DEFAULT_TABLES,
    METADATA_CHECKPOINT_ID,
)


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
    """Answer the four checkpoint queries from a configurable observable state.

    Args:
        table_comments: ``{table_name: comment}`` (a table absent from the dict
            models a missing table; a blank/None comment models an uncommented
            table).
        columns: ``[(table_name, column_name, comment), ...]``.
        pi_tags: ``[(table_name, column_name, tag_value), ...]``, the rows
            information_schema.column_tags returns for the PI tag key.
        domain_tags: ``{table_name: tag_value}``, the table's domain tag value.
        missing_stage: marker name whose query should raise (unreadable view).
    """

    def __init__(
        self,
        *,
        table_comments: dict[str, str | None] | None = None,
        columns: list[tuple[str, str, str | None]] | None = None,
        pi_tags: list[tuple[str, str, str | None]] | None = None,
        domain_tags: dict[str, str | None] | None = None,
        missing_stage: str | None = None,
    ) -> None:
        self.table_comments = (
            table_comments
            if table_comments is not None
            else {name: f"{name} comment" for name in DEFAULT_TABLES}
        )
        self.columns = columns if columns is not None else _default_columns()
        self.pi_tags = (
            pi_tags
            if pi_tags is not None
            else [(DEFAULT_TABLES[0], "customer_name", "confidential")]
        )
        self.domain_tags = (
            domain_tags
            if domain_tags is not None
            else {name: "finance" for name in DEFAULT_TABLES}
        )
        self.missing_stage = missing_stage
        self.queries: list[str] = []

    def sql(self, query: str) -> _DF:
        self.queries.append(query)
        markers = {
            "tables": "metadata:tables",
            "columns": "metadata:columns",
            "column_tags": "metadata:column_tags",
            "table_tags": "metadata:table_tags",
        }
        stage = next((name for name, m in markers.items() if m in query), None)
        if stage is None:
            raise AssertionError(f"unexpected SQL: {query!r}")
        if self.missing_stage == stage:
            raise RuntimeError(f"TABLE_OR_VIEW_NOT_FOUND at {stage}")

        if stage == "tables":
            return _DF([_Row([n, c]) for n, c in self.table_comments.items()])
        if stage == "columns":
            return _DF([_Row([t, c, cm]) for t, c, cm in self.columns])
        if stage == "column_tags":
            return _DF([_Row([t, c, v]) for t, c, v in self.pi_tags])
        if stage == "table_tags":
            return _DF([_Row([n, v]) for n, v in self.domain_tags.items()])
        raise AssertionError(f"unhandled stage: {stage}")


def _default_columns() -> list[tuple[str, str, str | None]]:
    """A small, fully-commented column set for the two default tables."""
    return [
        (DEFAULT_TABLES[0], "transaction_id", "the transaction id"),
        (DEFAULT_TABLES[0], "customer_name", "the customer name"),
        (DEFAULT_TABLES[1], "contract_id", "the contract id"),
        (DEFAULT_TABLES[1], "net_sales", "net sales for the contract"),
    ]


def _check(spark, **kwargs):
    return workshop.check(
        METADATA_CHECKPOINT_ID,
        spark=spark,
        catalog="catalog",
        schema="schema",
        **kwargs,
    )


# --- framework wiring -------------------------------------------------------


def test_registered():
    assert METADATA_CHECKPOINT_ID in workshop.registry


def test_requires_workspace():
    result = workshop.check(METADATA_CHECKPOINT_ID)
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_requires_catalog_and_schema():
    result = workshop.check(METADATA_CHECKPOINT_ID, spark=FakeSpark())
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_invalid_tables_configuration_is_targeted():
    result = _check(FakeSpark(), tables=[""])
    assert result.passed is False
    assert result.details["stage"] == "configuration"


# --- comment coverage -------------------------------------------------------


def test_unreadable_tables_view_is_targeted():
    result = _check(FakeSpark(missing_stage="tables"))
    assert result.passed is False
    assert result.details["stage"] == "tables"
    assert "information_schema.tables" in result.message


def test_missing_target_table_fails():
    result = _check(FakeSpark(table_comments={DEFAULT_TABLES[0]: "only one"}))
    assert result.passed is False
    assert result.details["stage"] == "tables"
    assert DEFAULT_TABLES[1] in result.details["missing_tables"]


def test_missing_table_comment_fails():
    spark = FakeSpark(
        table_comments={DEFAULT_TABLES[0]: "documented", DEFAULT_TABLES[1]: None}
    )
    result = _check(spark)
    assert result.passed is False
    assert result.details["stage"] == "table_comment"
    assert DEFAULT_TABLES[1] in result.details["uncommented_tables"]


def test_blank_table_comment_fails():
    # A whitespace-only comment is not documentation.
    spark = FakeSpark(
        table_comments={DEFAULT_TABLES[0]: "   ", DEFAULT_TABLES[1]: "ok"}
    )
    result = _check(spark)
    assert result.passed is False
    assert result.details["stage"] == "table_comment"


def test_table_with_no_columns_fails():
    spark = FakeSpark(
        columns=[(DEFAULT_TABLES[0], "transaction_id", "id")]  # nothing for table[1]
    )
    result = _check(spark)
    assert result.passed is False
    assert result.details["stage"] == "columns"
    assert DEFAULT_TABLES[1] in result.details["tables_without_columns"]


def test_blank_column_comment_fails():
    columns = _default_columns()
    columns[1] = (DEFAULT_TABLES[0], "customer_name", "   ")  # whitespace comment
    result = _check(FakeSpark(columns=columns))
    assert result.passed is False
    assert result.details["stage"] == "column_comment"
    assert result.details["blank_count"] == 1
    assert f"{DEFAULT_TABLES[0]}.customer_name" in result.details["blank_comment_columns"]


def test_null_column_comment_fails():
    columns = _default_columns()
    columns[3] = (DEFAULT_TABLES[1], "net_sales", None)
    result = _check(FakeSpark(columns=columns))
    assert result.passed is False
    assert result.details["stage"] == "column_comment"
    assert f"{DEFAULT_TABLES[1]}.net_sales" in result.details["blank_comment_columns"]


# --- PI tagging -------------------------------------------------------------


def test_missing_pi_tag_fails():
    # pi mode never ran / tag key absent -> zero rows -> RED.
    result = _check(FakeSpark(pi_tags=[]))
    assert result.passed is False
    assert result.details["stage"] == "pi_tag"
    assert result.details["pi_tagged_columns"] == 0


def test_blank_pi_tag_value_fails():
    result = _check(
        FakeSpark(pi_tags=[(DEFAULT_TABLES[0], "customer_name", "")])
    )
    assert result.passed is False
    assert result.details["stage"] == "pi_tag"
    assert f"{DEFAULT_TABLES[0]}.customer_name" in result.details["blank_value_columns"]


def test_whitespace_only_pi_tag_value_fails():
    # A whitespace-only tag value is not a classification, since _is_blank() trims it.
    result = _check(
        FakeSpark(pi_tags=[(DEFAULT_TABLES[0], "customer_name", "   ")])
    )
    assert result.passed is False
    assert result.details["stage"] == "pi_tag"
    assert f"{DEFAULT_TABLES[0]}.customer_name" in result.details["blank_value_columns"]


def test_min_pi_columns_threshold_is_enforced():
    result = _check(FakeSpark(), min_pi_columns=2)  # only one column tagged
    assert result.passed is False
    assert result.details["stage"] == "pi_tag"
    assert result.details["min_pi_columns"] == 2
    assert result.details["pi_tagged_columns"] == 1


def test_expected_pi_columns_exact_set_mismatch_fails():
    result = _check(
        FakeSpark(),
        expected_pi_columns={
            f"{DEFAULT_TABLES[0]}.customer_name",
            f"{DEFAULT_TABLES[1]}.contract_id",
        },
    )
    assert result.passed is False
    assert result.details["stage"] == "pi_tag"
    assert f"{DEFAULT_TABLES[1]}.contract_id" in result.details["missing"]


def test_expected_pi_columns_exact_set_matches():
    result = _check(
        FakeSpark(),
        expected_pi_columns={f"{DEFAULT_TABLES[0]}.customer_name"},
    )
    assert result.passed is True


# --- domain tagging ---------------------------------------------------------


def test_missing_domain_tag_fails():
    spark = FakeSpark(domain_tags={DEFAULT_TABLES[0]: "finance"})  # table[1] absent
    result = _check(spark)
    assert result.passed is False
    assert result.details["stage"] == "domain_tag"
    assert DEFAULT_TABLES[1] in result.details["untagged_tables"]


def test_blank_domain_tag_value_fails():
    spark = FakeSpark(
        domain_tags={DEFAULT_TABLES[0]: "finance", DEFAULT_TABLES[1]: "  "}
    )
    result = _check(spark)
    assert result.passed is False
    assert result.details["stage"] == "domain_tag"
    assert DEFAULT_TABLES[1] in result.details["untagged_tables"]


# --- green + quoting --------------------------------------------------------


def test_green_when_all_metadata_applied():
    result = _check(FakeSpark())
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert sorted(result.details["tables"]) == sorted(DEFAULT_TABLES)
    assert result.details["total_columns"] == 4
    assert result.details["pi_tag_name"] == DEFAULT_PI_TAG_NAME
    assert len(result.details["pi_tagged_columns"]) == 1


def test_green_quotes_catalog_and_uses_literal_schema():
    spark = FakeSpark()
    result = workshop.check(
        METADATA_CHECKPOINT_ID,
        spark=spark,
        catalog="team-catalog",
        schema="finance data",
    )
    assert result.passed is True
    # Catalog is a backtick-quoted identifier prefix on every information_schema
    # query; the schema is a string literal (it filters by value in these views).
    assert all(
        "`team-catalog`.information_schema." in query for query in spark.queries
    )
    assert all("'finance data'" in query for query in spark.queries)


def test_custom_tables_and_tag_keys_are_honored():
    tables = ("gold incidents", "gold sla")
    spark = FakeSpark(
        table_comments={t: "documented" for t in tables},
        columns=[
            (tables[0], "incident id", "the incident"),
            (tables[1], "sla id", "the sla"),
        ],
        pi_tags=[(tables[0], "assignee", "internal")],
        domain_tags={t: "itsm" for t in tables},
    )
    result = _check(
        spark,
        tables=list(tables),
        pi_tag_name="sensitivity",
        domain_tag_name="business_domain",
    )
    assert result.passed is True
    rendered = "\n".join(spark.queries)
    assert "'gold incidents'" in rendered
    assert "'gold sla'" in rendered
    assert "'sensitivity'" in rendered
    assert "'business_domain'" in rendered


def test_string_literals_escape_embedded_quotes():
    # A schema/table/tag with an apostrophe must be escaped, not break the query.
    spark = FakeSpark(
        table_comments={"o'gold": "documented"},
        columns=[("o'gold", "col", "a column")],
        pi_tags=[("o'gold", "col", "pii")],
        domain_tags={"o'gold": "finance"},
    )
    result = workshop.check(
        METADATA_CHECKPOINT_ID,
        spark=spark,
        catalog="cat",
        schema="s'chema",
        tables=["o'gold"],
    )
    assert result.passed is True
    rendered = "\n".join(spark.queries)
    assert "'s''chema'" in rendered
    assert "'o''gold'" in rendered
