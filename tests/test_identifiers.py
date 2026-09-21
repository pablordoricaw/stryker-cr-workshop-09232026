"""Identifier quoting, and a drift guard against CheckContext's own quoting."""

from __future__ import annotations

import pytest

from workshop import CheckContext
from workshop.identifiers import fully_qualified, quote_identifier


def test_quote_identifier_wraps_in_backticks():
    assert quote_identifier("landing") == "`landing`"


def test_quote_identifier_allows_hyphens_and_reserved_words():
    assert quote_identifier("stryker-finance") == "`stryker-finance`"
    assert quote_identifier("select") == "`select`"


def test_quote_identifier_escapes_embedded_backticks():
    assert quote_identifier("a`b") == "`a``b`"


def test_fully_qualified_quotes_each_part():
    assert fully_qualified("main", "finance", "landing") == "`main`.`finance`.`landing`"


def test_fully_qualified_requires_a_part():
    with pytest.raises(ValueError):
        fully_qualified()


def test_matches_check_context_quoting():
    # The framework foundation (CheckContext.fully_qualified) and this module must
    # produce byte-identical output, or SQL built in different places would drift.
    ctx = CheckContext(catalog="stryker-finance", schema="select")
    assert fully_qualified("stryker-finance", "select", "my table") == ctx.fully_qualified(
        "my table"
    )
