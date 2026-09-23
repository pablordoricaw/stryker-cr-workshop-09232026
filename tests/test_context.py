"""Tests for CheckContext, including safe identifier quoting."""

from __future__ import annotations

import pytest

from workshop import CheckContext


def test_fully_qualified_quotes_each_component():
    ctx = CheckContext(catalog="main", schema="participant_01")
    assert ctx.fully_qualified("gold_orders") == "`main`.`participant_01`.`gold_orders`"


def test_fully_qualified_handles_hyphens_and_reserved_words():
    # Hyphens, spaces, and reserved words are all legal Unity Catalog names.
    ctx = CheckContext(catalog="stryker-finance", schema="select")
    assert ctx.fully_qualified("my table") == "`stryker-finance`.`select`.`my table`"


def test_fully_qualified_escapes_embedded_backticks():
    ctx = CheckContext(catalog="a`b", schema="s")
    # An embedded backtick is escaped by doubling.
    assert ctx.fully_qualified("t") == "`a``b`.`s`.`t`"


def test_fully_qualified_requires_catalog_and_schema():
    with pytest.raises(RuntimeError):
        CheckContext(catalog="main").fully_qualified("t")  # schema missing
    with pytest.raises(RuntimeError):
        CheckContext(schema="s").fully_qualified("t")  # catalog missing


def test_require_spark_raises_without_session():
    with pytest.raises(RuntimeError, match="Databricks workspace"):
        CheckContext().require_spark()


def test_require_spark_returns_session_when_present():
    sentinel = object()
    assert CheckContext(spark=sentinel).require_spark() is sentinel
