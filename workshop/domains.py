"""Per-domain scaffold spec — the one place that names each domain's transactional-track objects.

The workshop is one shared curriculum across three domains (Finance, Security,
ITSM); only the dataset and pre-authored semantic content differ. The
document-intelligence track (``00_setup`` / ``01_bronze_docs`` /
``02_silver_docs``) is already domain-parameterised through
:class:`~workshop.config.WorkshopConfig` and generic table names (``bronze_docs``
/ ``silver_docs``). The **transactional** track — bronze transactions, the gold
medallion, governed metadata, Metric Views, the Genie agent, and the app — names
different tables, keys, and measures per domain.

The domain-generic checkpoints already take every one of those names as a
``workshop.check`` extra, defaulting to Finance. This module is the single source
of truth those extras come from, so the **shared** participant STARTER notebooks
derive domain-correct names from ``config.domain`` instead of hardcoding Finance
literals — a Security or ITSM participant runs the exact same notebooks and
reaches green on their domain.

Every value here mirrors exactly what the matching ``solutions/<domain>/``
notebook builds and what its ``workshop.check(...)`` call passes, so *generation*
(the participant's filled notebook) and *verification* (the checkpoint) agree by
construction. Finance's values equal the checkpoints' built-in defaults, so a
Finance participant sees byte-identical behaviour to before this spec existed.

Pure Python — no Spark, no SDK, no network — so it is unit-testable off-platform
and safe to import from the connection-free framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import DOMAINS


@dataclass(frozen=True)
class MetricViewSpec:
    """One Metric View's observable contract (its name is the mapping key).

    Matches the shape the ``05_metrics`` checkpoint's ``metric_views`` extra
    expects (:meth:`as_contract`) and the YAML the ``05_metric_views`` solution
    creates.
    """

    source_table: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]

    def as_contract(self) -> dict[str, Any]:
        """The plain mapping the ``05_metrics`` checkpoint's ``metric_views`` extra wants."""
        return {
            "source_table": self.source_table,
            "dimensions": list(self.dimensions),
            "measures": list(self.measures),
        }


@dataclass(frozen=True)
class DomainSpec:
    """Resolved names/keys/measures for one domain's transactional track.

    The starter notebooks read these and pass the derived values to
    ``workshop.check(...)``; the helper methods bundle the exact extras each
    checkpoint accepts so a notebook never re-lists them.
    """

    domain: str

    # --- 01_bronze_txn -------------------------------------------------------
    #: The transactional bronze table the participant lands (one row per event).
    bronze_txn_table: str
    #: The event grain key (the ``transaction_key`` the bronze/gold checks take).
    transaction_key: str
    #: The exact seeded row count the bronze checkpoint asserts.
    expected_txn_rows: int
    #: The committed Delta seed directory under ``data/<domain>/transactional/delta/``.
    txn_seed_dir: str
    #: The Lakebase CDF history table for the admin-gated ``lakebase_cdf`` path.
    lakebase_cdf_table: str
    #: A human noun for prose (e.g. ``"sales transactions"``).
    txn_entity_label: str

    # --- 03_gold -------------------------------------------------------------
    #: The silver document table joined into the gold detail table.
    document_table: str
    #: The gold detail table (one row per transaction, enriched from the document).
    detail_table: str
    #: The gold mart table (one row per business key, with additive measures).
    mart_table: str
    #: The business key — the mart grain, and the transaction column that joins the document.
    group_key: str
    #: The unique key in the silver document table (its join side).
    document_key: str
    #: The projected document key carried into the gold detail table.
    detail_document_key: str
    #: A non-null gold-detail column that proves document enrichment landed.
    detail_document_match: str
    #: ``reconcile_measures`` for the gold check: ``True`` = the checkpoint's
    #: additive-measure defaults; a tuple of same-named source/mart columns; or
    #: ``False`` to skip measure reconciliation (grain/identity checks stay on).
    reconcile_measures: Any

    # --- 04_metadata ---------------------------------------------------------
    #: Sensitive (PII/PHI-ish) columns per gold table, tagged with the PI
    #: classification key by the ``04_metadata`` no-PyPI manual fallback. Keyed by
    #: gold table name; a table with no direct PII maps to an empty tuple (the
    #: domain's ``min_pi_columns=1`` requirement is met by its other gold table).
    #: Mirrors the columns dbxmetagen's ``pi`` mode classifies.
    pii_columns: dict[str, tuple[str, ...]]

    # --- 05_metric_views -----------------------------------------------------
    #: The Metric Views this domain builds, keyed by view name (insertion-ordered:
    #: detail-grain view first, mart-grain view second).
    metric_views: dict[str, MetricViewSpec]

    # --- 06_genie ------------------------------------------------------------
    #: The two benchmark questions the Genie checkpoint asks this domain's agent.
    genie_benchmark_questions: tuple[str, ...]

    # --- 07_app --------------------------------------------------------------
    #: The gold serving table synced into Lakebase (a denormalised mart).
    app_source_table: str
    #: The synced table's primary key.
    app_primary_key: tuple[str, ...]
    #: The namespace serving-table base (``<base>_<suffix>`` → the synced-table name).
    app_serving_base: str

    # --- derived convenience -------------------------------------------------
    @property
    def source_table(self) -> str:
        """The gold check's ``source_table`` — the transactional bronze table."""
        return self.bronze_txn_table

    @property
    def metadata_tables(self) -> tuple[str, ...]:
        """The gold tables the ``04_metadata`` check documents (detail, then mart)."""
        return (self.detail_table, self.mart_table)

    @property
    def genie_expected_sources(self) -> tuple[str, ...]:
        """The data assets the Genie agent must attach: gold tables + Metric Views."""
        return (self.detail_table, self.mart_table, *self.metric_views.keys())

    def gold_extras(self) -> dict[str, Any]:
        """The full ``03_gold`` checkpoint extras for this domain."""
        return {
            "source_table": self.source_table,
            "document_table": self.document_table,
            "detail_table": self.detail_table,
            "mart_table": self.mart_table,
            "source_key": self.transaction_key,
            "detail_key": self.transaction_key,
            "source_group_key": self.group_key,
            "document_key": self.document_key,
            "detail_document_key": self.detail_document_key,
            "detail_document_match": self.detail_document_match,
            "mart_key": self.group_key,
            "reconcile_measures": self.reconcile_measures,
        }

    def metric_view_contracts(self) -> dict[str, dict[str, Any]]:
        """The ``metric_views`` extra for the ``05_metrics`` checkpoint."""
        return {name: view.as_contract() for name, view in self.metric_views.items()}


#: Every domain's transactional-track spec. Values mirror ``solutions/<domain>/``
#: and each domain's ``workshop.check(...)`` extras exactly; Finance equals the
#: checkpoints' built-in defaults.
DOMAIN_SPECS: dict[str, DomainSpec] = {
    "finance": DomainSpec(
        domain="finance",
        bronze_txn_table="bronze_sales_transactions",
        transaction_key="transaction_id",
        expected_txn_rows=3_000,
        txn_seed_dir="sales_transactions",
        lakebase_cdf_table="lb_sales_transactions_history",
        txn_entity_label="sales transactions",
        document_table="silver_sales_contract_pricing_agreement",
        detail_table="gold_sales",
        mart_table="gold_contract_performance",
        group_key="contract_id",
        document_key="agreement_id",
        detail_document_key="contract_agreement_id",
        detail_document_match="contract_document_path",
        # Finance uses the gold checkpoint's built-in additive-measure defaults.
        reconcile_measures=True,
        pii_columns={
            "gold_sales": ("customer_id", "customer_name", "contract_customer_name"),
            "gold_contract_performance": ("contract_customer_name",),
        },
        metric_views={
            "finance_sales_metrics": MetricViewSpec(
                source_table="gold_sales",
                dimensions=(
                    "Sale Date",
                    "Product Family",
                    "Sales Region",
                    "Customer Type",
                ),
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
            "finance_contract_metrics": MetricViewSpec(
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
        },
        genie_benchmark_questions=(
            "What were total net sales by product family?",
            "Which sales region had the highest gross margin?",
        ),
        app_source_table="gold_contract_performance",
        app_primary_key=("contract_id",),
        app_serving_base="gold_contract_performance_served",
    ),
    "security": DomainSpec(
        domain="security",
        bronze_txn_table="bronze_scan_findings",
        transaction_key="finding_id",
        expected_txn_rows=3_000,
        txn_seed_dir="scan_findings",
        lakebase_cdf_table="lb_scan_findings_history",
        txn_entity_label="vulnerability-scan findings",
        document_table="silver_cve_advisory",
        detail_table="gold_findings",
        mart_table="gold_cve_exposure",
        group_key="cve_id",
        document_key="cve_id",
        detail_document_key="advisory_cve_id",
        detail_document_match="advisory_document_path",
        reconcile_measures=(
            "remediation_hours",
            "asset_value_at_risk",
            "weighted_risk",
        ),
        pii_columns={
            "gold_findings": ("asset_id", "asset_name", "business_unit", "owner_team"),
            # Aggregated CVE mart with no direct PII; the domain's PI requirement
            # is met by gold_findings above.
            "gold_cve_exposure": (),
        },
        metric_views={
            "security_findings_metrics": MetricViewSpec(
                source_table="gold_findings",
                dimensions=(
                    "Scan Date",
                    "Asset Type",
                    "Environment",
                    "Severity",
                    "Vulnerability Category",
                ),
                measures=(
                    "Finding Count",
                    "Scan Count",
                    "Affected Assets",
                    "Open Findings",
                    "Critical Findings",
                    "Remediation Hours",
                    "Value at Risk",
                    "Average CVSS",
                ),
            ),
            "security_cve_metrics": MetricViewSpec(
                source_table="gold_cve_exposure",
                dimensions=("CVE ID", "Severity", "Vulnerability Category"),
                measures=(
                    "Finding Count",
                    "Open Findings",
                    "Critical Findings",
                    "Affected Assets",
                    "Remediation Hours",
                    "Value at Risk",
                    "Weighted Risk",
                ),
            ),
        },
        genie_benchmark_questions=(
            "How many open findings are there by severity?",
            "Which CVEs have the highest weighted risk?",
        ),
        app_source_table="gold_cve_exposure",
        app_primary_key=("cve_id",),
        app_serving_base="gold_cve_exposure_served",
    ),
    "itsm": DomainSpec(
        domain="itsm",
        bronze_txn_table="bronze_service_tickets",
        transaction_key="ticket_id",
        expected_txn_rows=3_000,
        txn_seed_dir="service_tickets",
        lakebase_cdf_table="lb_service_tickets_history",
        txn_entity_label="service tickets",
        document_table="silver_incident_report",
        detail_table="gold_incidents",
        mart_table="gold_service_performance",
        group_key="incident_id",
        document_key="incident_id",
        detail_document_key="report_incident_id",
        detail_document_match="incident_document_path",
        # ITSM's mart measures are not same-named additive source columns, so the
        # grain/identity checks run but measure reconciliation is disabled.
        reconcile_measures=False,
        pii_columns={
            "gold_incidents": ("assignment_group", "configuration_item"),
            "gold_service_performance": ("assignment_group", "configuration_item"),
        },
        metric_views={
            "itsm_incident_metrics": MetricViewSpec(
                source_table="gold_incidents",
                dimensions=("Priority", "Service", "Assignment Group"),
                measures=("Incident Volume", "MTTR Hours", "SLA Breach Count"),
            ),
            "itsm_service_metrics": MetricViewSpec(
                source_table="gold_service_performance",
                dimensions=("Service", "Priority"),
                measures=("Incident Volume", "MTTR Hours", "SLA Breach Count"),
            ),
        },
        genie_benchmark_questions=(
            "Show incident volume by priority.",
            "What is MTTR by service?",
        ),
        app_source_table="gold_service_performance",
        app_primary_key=("incident_id",),
        app_serving_base="gold_service_performance_served",
    ),
}


def domain_spec(domain: str | None) -> DomainSpec:
    """Return the :class:`DomainSpec` for ``domain`` (case/space-insensitive).

    Raises:
        ValueError: If ``domain`` is not one of :data:`~workshop.config.DOMAINS`.
    """
    key = (domain or "").strip().lower()
    try:
        return DOMAIN_SPECS[key]
    except KeyError:
        raise ValueError(
            f"Unknown domain {key!r}. Choose one of: {', '.join(DOMAINS)}."
        ) from None
