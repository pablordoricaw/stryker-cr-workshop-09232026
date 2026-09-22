"""Behavioral tests for the observable-state ``05_metrics`` checkpoint."""

from __future__ import annotations

import json

import workshop
from workshop.checkpoints.metrics import (
    DEFAULT_METRIC_VIEWS,
    METRICS_CHECKPOINT_ID,
    MetricViewContract,
)


class _Row:
    def __init__(self, values):
        self.values = values if isinstance(values, list) else [values]

    def __getitem__(self, index: int):
        return self.values[index]


class _DF:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    def collect(self) -> list[_Row]:
        return self.rows


class FakeSpark:
    """Serve metric-view descriptions and MEASURE results from observable state."""

    def __init__(
        self,
        *,
        contracts=DEFAULT_METRIC_VIEWS,
        missing_view: str | None = None,
        missing_dimension: tuple[str, str] | None = None,
        missing_measure: tuple[str, str] | None = None,
        source_override: tuple[str, str] | None = None,
        empty_aggregate: str | None = None,
        null_aggregate: str | None = None,
    ) -> None:
        self.contracts = contracts
        self.missing_view = missing_view
        self.empty_aggregate = empty_aggregate
        self.null_aggregate = null_aggregate
        self.queries: list[str] = []
        self.descriptions: dict[str, dict] = {}
        for name, contract in self.contracts.items():
            dimensions = list(contract.dimensions)
            measures = list(contract.measures)
            if missing_dimension and missing_dimension[0] == name:
                dimensions.remove(missing_dimension[1])
            if missing_measure and missing_measure[0] == name:
                measures.remove(missing_measure[1])
            source = f"`catalog`.`schema`.`{contract.source_table}`"
            if source_override and source_override[0] == name:
                source = source_override[1]
            self.descriptions[name] = {
                "columns": [
                    *[{"name": dimension, "is_measure": False} for dimension in dimensions],
                    *[{"name": measure, "is_measure": True} for measure in measures],
                ],
                "view_definition": f"version: 1.1\nsource: \"{source}\"\n",
            }

    def sql(self, query: str) -> _DF:
        self.queries.append(query)
        for name, contract in self.contracts.items():
            if f"metrics:describe:{name}" in query:
                if self.missing_view == name:
                    raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")
                return _DF([_Row(json.dumps(self.descriptions[name]))])
            if f"metrics:aggregate:{name}" in query:
                if self.empty_aggregate == name:
                    return _DF([])
                values = [10] * len(contract.measures)
                if self.null_aggregate == name:
                    values[0] = None
                return _DF([_Row(values)])
        raise AssertionError(f"unexpected SQL: {query!r}")


def _check(spark, **kwargs):
    return workshop.check(
        METRICS_CHECKPOINT_ID, spark=spark, catalog="catalog", schema="schema", **kwargs
    )


def test_registered():
    assert METRICS_CHECKPOINT_ID in workshop.registry


def test_requires_workspace():
    result = workshop.check(METRICS_CHECKPOINT_ID)
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message


def test_requires_catalog_and_schema():
    result = workshop.check(METRICS_CHECKPOINT_ID, spark=FakeSpark())
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_missing_metric_view_is_red():
    result = _check(FakeSpark(missing_view="finance_sales_metrics"))
    assert result.passed is False
    assert result.details["stage"] == "describe"


def test_missing_required_dimension_is_red():
    result = _check(FakeSpark(missing_dimension=("finance_sales_metrics", "Product Family")))
    assert result.passed is False
    assert result.details["stage"] == "definition"
    assert result.details["missing_dimensions"] == ["Product Family"]


def test_missing_required_measure_is_red():
    result = _check(FakeSpark(missing_measure=("finance_sales_metrics", "Net Sales")))
    assert result.passed is False
    assert result.details["stage"] == "definition"
    assert result.details["missing_measures"] == ["Net Sales"]


def test_wrong_source_is_red():
    result = _check(
        FakeSpark(source_override=("finance_sales_metrics", "`catalog`.`schema`.`other_gold`"))
    )
    assert result.passed is False
    assert result.details["stage"] == "source"


def test_empty_aggregate_is_red():
    result = _check(FakeSpark(empty_aggregate="finance_contract_metrics"))
    assert result.passed is False
    assert result.details["stage"] == "aggregate"


def test_null_aggregate_is_red():
    result = _check(FakeSpark(null_aggregate="finance_contract_metrics"))
    assert result.passed is False
    assert result.details["stage"] == "aggregate"


def test_green_and_quotes_identifiers():
    spark = FakeSpark()
    for name, contract in DEFAULT_METRIC_VIEWS.items():
        spark.descriptions[name]["view_definition"] = (
            "version: 1.1\n"
            f'source: "`team-catalog`.`finance data`.`{contract.source_table}`"\n'
        )
    result = workshop.check(
        METRICS_CHECKPOINT_ID,
        spark=spark,
        catalog="team-catalog",
        schema="finance data",
    )
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert all("`team-catalog`.`finance data`." in query for query in spark.queries)
    aggregate = next(query for query in spark.queries if "metrics:aggregate:finance_sales_metrics" in query)
    assert "MEASURE(`Net Sales`)" in aggregate


def test_custom_metric_view_contract_is_honored():
    contracts = {
        "service metrics": {
            "source_table": "gold service",
            "dimensions": ["Service"],
            "measures": ["Request Count"],
        }
    }
    expected = {
        "service metrics": MetricViewContract(
            source_table="gold service",
            dimensions=("Service",),
            measures=("Request Count",),
        )
    }
    result = _check(FakeSpark(contracts=expected), metric_views=contracts)
    assert result.passed is True
    assert result.details["metric_views"]["service metrics"]["source_table"] == "gold service"
