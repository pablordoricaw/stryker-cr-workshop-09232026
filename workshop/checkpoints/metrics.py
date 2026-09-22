"""The ``05_metrics`` checkpoint: observable Unity Catalog Metric View state.

The check deliberately validates the deployed semantic layer, rather than a
notebook or a particular deployment mechanism.  Each required metric view must
exist, describe the expected source, dimensions, and measures, and return a
non-empty row whose requested measures are non-null when queried with
``MEASURE()``.  Thus a regular view, a view with a truncated YAML model, or an
empty/null-only metric view cannot accidentally pass.

The Finance defaults cover the two gold facts built in ``03_gold``.  Other
domains supply a ``metric_views`` mapping through ``workshop.check``; no
Finance-specific column or object name is baked into the validation logic.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from numbers import Number
from typing import Any

from workshop.context import CheckContext
from workshop.identifiers import quote_identifier
from workshop.registry import checkpoint
from workshop.results import CheckResult

METRICS_CHECKPOINT_ID = "05_metrics"


@dataclass(frozen=True)
class MetricViewContract:
    """Observable contract for one metric view in the participant schema."""

    source_table: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]


DEFAULT_METRIC_VIEWS: dict[str, MetricViewContract] = {
    "finance_sales_metrics": MetricViewContract(
        source_table="gold_sales",
        dimensions=("Sale Date", "Product Family", "Sales Region", "Customer Type"),
        measures=(
            "Transaction Count",
            "Order Count",
            "Units Sold",
            "Gross Sales",
            "Net Sales",
            "Gross Margin",
            "Gross Margin Percent",
        ),
    ),
    "finance_contract_metrics": MetricViewContract(
        source_table="gold_contract_performance",
        dimensions=("Contract ID", "Customer", "Currency"),
        measures=(
            "Transaction Count",
            "Order Count",
            "Total Units",
            "Gross Sales",
            "Net Sales",
            "Gross Margin",
            "Gross Margin Percent",
        ),
    ),
}


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(METRICS_CHECKPOINT_ID, False, message, details)


def _nonempty_names(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise TypeError(f"{field} must be a name or a list of names")
    if not values or any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{field} entries must be non-empty names")
    return tuple(dict.fromkeys(values))


def _metric_view_contracts(value: Any) -> dict[str, MetricViewContract]:
    """Resolve default or caller-supplied view contracts from checkpoint extras."""
    if value is None:
        return DEFAULT_METRIC_VIEWS
    if not isinstance(value, Mapping) or not value:
        raise TypeError("metric_views must be a non-empty mapping of view contracts")

    contracts: dict[str, MetricViewContract] = {}
    for view_name, raw_contract in value.items():
        if not isinstance(view_name, str) or not view_name.strip():
            raise ValueError("metric_views keys must be non-empty view names")
        if not isinstance(raw_contract, Mapping):
            raise TypeError(f"metric_views[{view_name!r}] must be a mapping")
        source_table = raw_contract.get("source_table")
        if not isinstance(source_table, str) or not source_table.strip():
            raise ValueError(
                f"metric_views[{view_name!r}].source_table must be a non-empty name"
            )
        contracts[view_name] = MetricViewContract(
            source_table=source_table,
            dimensions=_nonempty_names(raw_contract.get("dimensions"), "dimensions"),
            measures=_nonempty_names(raw_contract.get("measures"), "measures"),
        )
    return contracts


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _walk_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _walk_strings(item)]
    return []


def _normalize_reference(value: str) -> str:
    """Compare UC references independent of SQL quoting/case/whitespace."""
    return value.replace("`", "").replace('"', "").replace(" ", "").lower()


def _expected_source(ctx: CheckContext, source_table: str) -> str:
    # Domain contracts normally supply a local object name.  Permit an explicit
    # three-part source too, which is useful for generic cross-schema exercises.
    return (
        _normalize_reference(source_table)
        if "." in source_table
        else _normalize_reference(ctx.fully_qualified(source_table))
    )


def _column_contract(description: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    columns = description.get("columns")
    if not isinstance(columns, list):
        raise TypeError("DESCRIBE TABLE EXTENDED AS JSON returned no columns list")
    dimensions: set[str] = set()
    measures: set[str] = set()
    for column in columns:
        if not isinstance(column, Mapping) or not isinstance(column.get("name"), str):
            continue
        name = column["name"]
        if column.get("is_measure") is True:
            measures.add(name)
        else:
            dimensions.add(name)
    return dimensions, measures


def _source_from_description(description: Mapping[str, Any]) -> str | None:
    # UC returns the YAML metric model in the extended JSON description.  The
    # exact enclosing property is platform-owned, so inspect its string values
    # and extract the declarative YAML ``source:`` entry rather than depending
    # on a non-contractual property name.
    candidates: list[tuple[int, str]] = []
    for text in _walk_strings(description):
        for match in re.finditer(
            r"(?m)^(?P<indent>[ \t]*)source:\s*[\"']?([^\n\"']+)", text
        ):
            candidates.append((len(match.group("indent")), match.group(2).strip()))
    if not candidates:
        return None
    # Joined models have nested ``joins[].source`` entries. YAML allows ``joins``
    # to appear before the top-level source, so document order is not reliable.
    # The least-indented source is the metric view's own source declaration.
    return _normalize_reference(min(candidates, key=lambda item: item[0])[1])


def _sane(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return not isinstance(value, Number) or isfinite(float(value))


@checkpoint(
    METRICS_CHECKPOINT_ID,
    summary=(
        "The required Unity Catalog Metric Views expose their declared source, "
        "dimensions, and measures and return non-null aggregate values."
    ),
)
def check_metrics(ctx: CheckContext) -> CheckResult:
    """Validate deployed UC Metric Views using only externally visible state."""
    spark = ctx.require_spark()
    if not ctx.catalog or not ctx.schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('05_metrics', "
            "spark=spark, catalog=config.catalog, schema=config.schema).",
            {"catalog": ctx.catalog, "schema": ctx.schema},
        )
    try:
        contracts = _metric_view_contracts(ctx.extras.get("metric_views"))
    except (TypeError, ValueError) as exc:
        return _fail(
            f"Invalid metric-view configuration: {exc}.",
            {"stage": "configuration", "error_type": type(exc).__name__},
        )

    checked: dict[str, dict[str, Any]] = {}
    for view_name, contract in contracts.items():
        view = ctx.fully_qualified(view_name)
        try:
            raw_description = spark.sql(
                f"/* metrics:describe:{view_name} */ DESCRIBE TABLE EXTENDED {view} AS JSON"
            ).collect()
            if len(raw_description) != 1:
                raise ValueError("expected one JSON description row")
            description = json.loads(raw_description[0][0])
            if not isinstance(description, Mapping):
                raise TypeError("expected a JSON object")
            dimensions, measures = _column_contract(description)
        except Exception as exc:  # noqa: BLE001 - participant-facing RED state
            return _fail(
                f"Metric view {view} is missing or unreadable "
                f"({type(exc).__name__}). Create the required metric view first.",
                {"stage": "describe", "view": view_name, "error_type": type(exc).__name__},
            )

        missing_dimensions = sorted(set(contract.dimensions) - dimensions)
        missing_measures = sorted(set(contract.measures) - measures)
        if missing_dimensions or missing_measures:
            return _fail(
                f"Metric view {view} is missing required dimensions or measures.",
                {
                    "stage": "definition",
                    "view": view_name,
                    "missing_dimensions": missing_dimensions,
                    "missing_measures": missing_measures,
                },
            )

        observed_source = _source_from_description(description)
        expected_source = _expected_source(ctx, contract.source_table)
        if observed_source != expected_source:
            return _fail(
                f"Metric view {view} does not declare the required source table.",
                {
                    "stage": "source",
                    "view": view_name,
                    "expected_source": expected_source,
                    "observed_source": observed_source,
                },
            )

        selected_measures = ", ".join(
            f"MEASURE({quote_identifier(measure)}) AS {quote_identifier(f'metric_{index}')}"
            for index, measure in enumerate(contract.measures)
        )
        try:
            rows = spark.sql(
                f"/* metrics:aggregate:{view_name} */ SELECT {selected_measures} FROM {view}"
            ).collect()
        except Exception as exc:  # noqa: BLE001
            return _fail(
                f"Metric view {view} could not be queried with MEASURE() "
                f"({type(exc).__name__}).",
                {"stage": "query", "view": view_name, "error_type": type(exc).__name__},
            )
        if not rows or not all(_sane(rows[0][index]) for index in range(len(contract.measures))):
            return _fail(
                f"Metric view {view} returned an empty or null aggregate result.",
                {
                    "stage": "aggregate",
                    "view": view_name,
                    "row_count": len(rows),
                    "measures": list(contract.measures),
                },
            )
        checked[view_name] = {
            "source_table": contract.source_table,
            "dimensions": list(contract.dimensions),
            "measures": list(contract.measures),
        }

    return CheckResult(
        METRICS_CHECKPOINT_ID,
        True,
        "Metric Views expose the required semantic definitions and sane aggregates.",
        {"stage": "done", "metric_views": checked},
    )
