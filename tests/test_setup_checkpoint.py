"""Tests for the 00_setup checkpoint, off-platform via a fake Spark session.

The checkpoint asserts the catalog is accessible and the schema + UC Volume
exist, never that a catalog was created (participants bring their own).
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.setup import SETUP_CHECKPOINT_ID


class _Row:
    def __init__(self, d: dict) -> None:
        self._d = d

    def asDict(self) -> dict:
        return dict(self._d)


class _DF:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def collect(self) -> list[_Row]:
        return self._rows


class FakeSpark:
    """Answers the SHOW SCHEMAS / SHOW VOLUMES the checkpoint issues.

    Test names carry no backticks or dots, so stripping backticks and splitting
    on '.' recovers the catalog/schema being queried.
    """

    def __init__(
        self,
        *,
        schemas_by_catalog: dict[str, list[str]] | None = None,
        volumes_by_schema: dict[tuple[str, str], list[str]] | None = None,
        inaccessible: set[str] | None = None,
        volumes_inaccessible: set[tuple[str, str]] | None = None,
    ) -> None:
        self.schemas_by_catalog = schemas_by_catalog or {}
        self.volumes_by_schema = volumes_by_schema or {}
        self.inaccessible = inaccessible or set()
        self.volumes_inaccessible = volumes_inaccessible or set()

    def sql(self, query: str) -> _DF:
        q = query.replace("`", "").strip()
        if q.startswith("SHOW SCHEMAS IN "):
            catalog = q[len("SHOW SCHEMAS IN ") :].strip()
            if catalog in self.inaccessible:
                raise RuntimeError(f"Catalog '{catalog}' does not exist or no access")
            return _DF(
                [_Row({"databaseName": s}) for s in self.schemas_by_catalog.get(catalog, [])]
            )
        if q.startswith("SHOW VOLUMES IN "):
            catalog, schema = q[len("SHOW VOLUMES IN ") :].strip().split(".", 1)
            if (catalog, schema) in self.volumes_inaccessible:
                raise RuntimeError(f"No USE SCHEMA on '{catalog}.{schema}'")
            vols = self.volumes_by_schema.get((catalog, schema), [])
            # The real SHOW VOLUMES shape: a `database` (schema) column and a
            # `volume_name` column. The checkpoint must read only `volume_name`.
            return _DF([_Row({"database": schema, "volume_name": v}) for v in vols])
        raise AssertionError(f"unexpected SQL: {query!r}")


def _check(spark, **kwargs):
    return workshop.check(SETUP_CHECKPOINT_ID, spark=spark, **kwargs)


def test_registered():
    assert SETUP_CHECKPOINT_ID in workshop.registry


def test_requires_a_workspace():
    result = workshop.check(SETUP_CHECKPOINT_ID)  # no spark
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_missing_catalog_or_schema_args():
    spark = FakeSpark()
    result = _check(spark, catalog=None, schema=None)
    assert result.passed is False
    assert "No catalog/schema to check" in result.message


def test_inaccessible_catalog():
    spark = FakeSpark(inaccessible={"c"})
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["missing"] == "catalog"
    assert "not accessible" in result.message


def test_missing_schema():
    spark = FakeSpark(schemas_by_catalog={"c": ["other"]})
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["missing"] == "schema"


def test_missing_volume():
    spark = FakeSpark(
        schemas_by_catalog={"c": ["finance"]},
        volumes_by_schema={("c", "finance"): []},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["missing"] == "volume"


def test_green_when_everything_exists():
    spark = FakeSpark(
        schemas_by_catalog={"c": ["finance"]},
        volumes_by_schema={("c", "finance"): ["landing"]},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is True
    assert result.details["volume_path"] == "/Volumes/c/finance/landing"


def test_volume_defaults_to_landing_when_extra_omitted():
    spark = FakeSpark(
        schemas_by_catalog={"c": ["finance"]},
        volumes_by_schema={("c", "finance"): ["landing"]},
    )
    result = _check(spark, catalog="c", schema="finance")  # no volume= extra
    assert result.passed is True
    assert result.details["volume"] == "landing"


def test_volume_name_equal_to_schema_name_does_not_false_pass():
    # Regression: SHOW VOLUMES also returns the schema (`database`) name. If we
    # scanned every string column, requesting a volume named like the schema
    # would false-pass whenever *any* volume exists. Only `volume_name` counts.
    spark = FakeSpark(
        schemas_by_catalog={"c": ["finance"]},
        volumes_by_schema={("c", "finance"): ["other"]},  # a volume exists, not "finance"
    )
    result = _check(spark, catalog="c", schema="finance", volume="finance")
    assert result.passed is False
    assert result.details["missing"] == "volume"


def test_volume_named_like_schema_that_actually_exists_passes():
    spark = FakeSpark(
        schemas_by_catalog={"c": ["finance"]},
        volumes_by_schema={("c", "finance"): ["finance"]},  # really is named "finance"
    )
    result = _check(spark, catalog="c", schema="finance", volume="finance")
    assert result.passed is True


def test_volume_listing_failure_is_targeted():
    spark = FakeSpark(
        schemas_by_catalog={"c": ["finance"]},
        volumes_inaccessible={("c", "finance")},
    )
    result = _check(spark, catalog="c", schema="finance", volume="landing")
    assert result.passed is False
    assert result.details["missing"] == "volume"
    assert "error_type" in result.details
    assert "USE SCHEMA" in result.message
