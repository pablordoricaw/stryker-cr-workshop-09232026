"""Tests for workshop.cdf_source — pure logic, off-platform.

Unit tests for mode selection and CDC row shaping logic, which are pure Python
and unit-testable without Spark or live workspace access.
"""

from __future__ import annotations

from workshop.cdf_source import _resolve_mode, shape_seed_to_cdc


def test_resolve_mode_preexisting():
    """If history table exists, mode is preexisting."""
    mode = _resolve_mode(history_table_exists=True, provisioning_succeeded=False)
    assert mode == "preexisting"


def test_resolve_mode_preexisting_ignores_provision():
    """Preexisting wins even if provisioning succeeded."""
    mode = _resolve_mode(history_table_exists=True, provisioning_succeeded=True)
    assert mode == "preexisting"


def test_resolve_mode_provisioned():
    """If provisioning succeeded and history doesn't exist, mode is provisioned."""
    mode = _resolve_mode(history_table_exists=False, provisioning_succeeded=True)
    assert mode == "provisioned"


def test_resolve_mode_synthesized():
    """If both detect and provision fail, mode is synthesized."""
    mode = _resolve_mode(history_table_exists=False, provisioning_succeeded=False)
    assert mode == "synthesized"


def test_shape_seed_to_cdc_adds_cdc_columns():
    """Shape seed rows by adding CDC metadata columns."""
    seed_rows = [
        {
            "transaction_id": "TXN-001",
            "order_id": "SO-100",
            "customer_id": "CUS-001",
            "amount": "100.00",
        },
        {
            "transaction_id": "TXN-002",
            "order_id": "SO-101",
            "customer_id": "CUS-002",
            "amount": "200.00",
        },
    ]
    columns = ["transaction_id", "order_id", "customer_id", "amount"]

    shaped = shape_seed_to_cdc(seed_rows, include_cols=columns)

    assert len(shaped) == 2
    # Check first row.
    row = shaped[0]
    assert row["transaction_id"] == "TXN-001"
    assert row["order_id"] == "SO-100"
    assert row["customer_id"] == "CUS-001"
    assert row["amount"] == "100.00"
    # CDC columns added.
    assert row["_pg_change_type"] == "insert"
    assert row["_pg_lsn"] is None  # Caller fills via monotonically_increasing_id
    assert row["_sort_by"] is None
    assert row["_pg_xid"] is None
    assert row["_timestamp"] is None


def test_shape_seed_to_cdc_filters_to_include_cols():
    """Only include specified columns in the shaped row."""
    seed_rows = [
        {
            "transaction_id": "TXN-001",
            "order_id": "SO-100",
            "secret_field": "SHOULD_NOT_APPEAR",
        }
    ]
    columns = ["transaction_id", "order_id"]

    shaped = shape_seed_to_cdc(seed_rows, include_cols=columns)

    row = shaped[0]
    assert "transaction_id" in row
    assert "order_id" in row
    # Filtered out columns don't appear (not even as None).
    assert set(row.keys()) == {
        "transaction_id",
        "order_id",
        "_pg_change_type",
        "_pg_lsn",
        "_sort_by",
        "_pg_xid",
        "_timestamp",
    }


def test_shape_seed_to_cdc_empty():
    """Shaping an empty seed produces an empty result."""
    shaped = shape_seed_to_cdc([], include_cols=["transaction_id"])
    assert shaped == []
