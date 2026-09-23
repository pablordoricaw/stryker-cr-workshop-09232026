"""Tests for workshop.cdf_source — pure logic, off-platform.

Unit tests for mode selection and CDC row shaping logic, which are pure Python
and unit-testable without Spark or live workspace access.

Key semantic: provisioning_succeeded means "provisioned AND verified readable".
When provisioning reaches ONLINE but the UC history table is not readable within
the grace timeout, provisioning fails (raises) and mode resolves to "synthesized".
"""

from __future__ import annotations

from workshop.cdf_source import _as_fq_table, _resolve_mode, shape_seed_to_cdc


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


def test_resolve_mode_provisioned_and_readable():
    """Provisioning succeeds only when BOTH ONLINE AND table is readable.

    This test documents the fixed contract: provisioning_succeeded=True means
    the CDF config reached ONLINE AND post-provision verification confirmed
    the UC history table is readable. If the table becomes unreadable after ONLINE,
    provisioning is treated as failed and mode resolves to 'synthesized'.
    """
    # Provisioning succeeded: ONLINE + table readable -> provisioned mode
    mode = _resolve_mode(history_table_exists=False, provisioning_succeeded=True)
    assert mode == "provisioned"

    # Provisioning failed: ONLINE but table unreadable -> synthesized mode
    # (This is handled by the provision function raising, so provisioning_succeeded=False)
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


def test_as_fq_table_bare_name():
    """Bare table name gets qualified with catalog, schema, and backticks."""
    result = _as_fq_table("my_table", "my_catalog", "my_schema")
    assert result == "my_catalog.my_schema.`my_table`"


def test_as_fq_table_already_qualified():
    """Already-qualified table name is returned unchanged."""
    result = _as_fq_table("cat.sch.table", "other_catalog", "other_schema")
    # Should return the input as-is, ignoring the catalog/schema params
    assert result == "cat.sch.table"


def test_as_fq_table_cdf_discovered_format():
    """CdfStatus.uc_table (already fully-qualified) is returned unchanged."""
    # Simulate what CDF discovery returns
    discovered = "stryker_workshop.default.lb_scan_findings_history"
    result = _as_fq_table(discovered, "my_catalog", "my_schema")
    assert result == "stryker_workshop.default.lb_scan_findings_history"
