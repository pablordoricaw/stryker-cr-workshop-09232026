"""Repo invariants for the shared domain spec + generalized starter notebooks (#25).

Dependency-free structural checks (no Spark, no SDK, no network) that lock the
generalization so it cannot silently regress:

1. **Finance behaviour is unchanged.** Every value the ``finance`` :class:`DomainSpec`
   feeds a checkpoint equals that checkpoint's built-in default, so a Finance
   participant sees byte-identical grading to before the spec existed.
2. **The spec matches each domain's gated solution.** For every domain, the
   table/entity names, keys, measures, Metric View contracts, benchmark
   questions, and app serving contract the spec exposes appear in the matching
   ``solutions/<domain>/`` notebook — the reference "filled" notebook — so
   generation (participant) and verification (checkpoint) agree.
3. **The six starter notebooks are single, shared, parameterised scaffolds.**
   Each offers the 3-domain dropdown, derives its names from ``config.domain``
   via ``workshop.domain_spec``, passes the spec-derived extras to
   ``workshop.check``, and hardcodes **no** domain's transactional-track object
   names in a shared cell.
"""

from __future__ import annotations

import os

import workshop
from workshop.checkpoints import app as app_cp
from workshop.checkpoints import bronze_txn as bronze_txn_cp
from workshop.checkpoints import genie as genie_cp
from workshop.checkpoints import gold as gold_cp
from workshop.checkpoints import metadata as metadata_cp
from workshop.checkpoints import metrics as metrics_cp
from workshop.namespace import DEFAULT_SERVING_BASE

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(workshop.__file__)))

DOMAINS = ("finance", "security", "itsm")

# The six starter notebooks generalized by #25 (the transactional track).
STARTER_NOTEBOOKS = (
    "01_bronze_txn.py",
    "03_gold.py",
    "04_metadata.py",
    "05_metric_views.py",
    "06_genie.py",
    "07_app.py",
)

# The 3-domain dropdown line the already-generalized doc notebooks use verbatim.
DOMAIN_DROPDOWN = 'dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")'

# Every domain's transactional-track object names. A shared starter cell must
# reference NONE of these as a literal — it derives them from the spec instead.
# (Finance's are the sharpest guard: they used to be hardcoded here.)
DOMAIN_OBJECT_LITERALS = {
    "finance": (
        "bronze_sales_transactions",
        "silver_sales_contract_pricing_agreement",
        "gold_sales",
        "gold_contract_performance",
        "finance_sales_metrics",
        "finance_contract_metrics",
        "contract_agreement_id",
        "Product Family",
    ),
    "security": (
        "bronze_scan_findings",
        "silver_cve_advisory",
        "gold_findings",
        "gold_cve_exposure",
        "security_findings_metrics",
        "security_cve_metrics",
        "advisory_cve_id",
    ),
    "itsm": (
        "bronze_service_tickets",
        "silver_incident_report",
        "gold_incidents",
        "gold_service_performance",
        "itsm_incident_metrics",
        "itsm_service_metrics",
        "report_incident_id",
    ),
}


def _read(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _shared_code(text: str) -> str:
    """The executed Python of a notebook: drop ``# MAGIC`` markdown and the
    per-line ``#`` comments/TODOs, so a name only counts if it is real code."""
    lines = []
    for line in text.splitlines():
        # Every `# MAGIC` markdown line also starts with `#`, so one test covers
        # both markdown hints and ordinary comments/TODOs.
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 1. Finance behaviour is unchanged (spec values == checkpoint defaults).
# --------------------------------------------------------------------------- #
def test_finance_spec_equals_bronze_txn_defaults() -> None:
    spec = workshop.domain_spec("finance")
    assert spec.bronze_txn_table == bronze_txn_cp.BRONZE_TXN_TABLE
    assert spec.transaction_key == bronze_txn_cp.DEFAULT_TRANSACTION_KEY
    assert spec.expected_txn_rows == bronze_txn_cp.EXPECTED_ROW_COUNT


def test_finance_spec_equals_gold_defaults() -> None:
    extras = workshop.domain_spec("finance").gold_extras()
    assert extras["source_table"] == gold_cp.DEFAULT_SOURCE_TABLE
    assert extras["document_table"] == gold_cp.DEFAULT_DOCUMENT_TABLE
    assert extras["detail_table"] == gold_cp.DEFAULT_DETAIL_TABLE
    assert extras["mart_table"] == gold_cp.DEFAULT_MART_TABLE
    assert extras["source_key"] == gold_cp.DEFAULT_SOURCE_KEY
    assert extras["detail_key"] == gold_cp.DEFAULT_DETAIL_KEY
    assert extras["source_group_key"] == gold_cp.DEFAULT_SOURCE_GROUP_KEY
    assert extras["document_key"] == gold_cp.DEFAULT_DOCUMENT_KEY
    assert extras["detail_document_key"] == gold_cp.DEFAULT_DETAIL_DOCUMENT_KEY
    assert extras["detail_document_match"] == gold_cp.DEFAULT_DETAIL_DOCUMENT_MATCH
    assert extras["mart_key"] == gold_cp.DEFAULT_MART_KEY
    # ``True`` makes the gold check use its built-in additive-measure defaults —
    # identical to Finance passing no reconcile_measures at all.
    assert extras["reconcile_measures"] is True


def test_finance_spec_equals_metadata_defaults() -> None:
    assert workshop.domain_spec("finance").metadata_tables == metadata_cp.DEFAULT_TABLES


def test_finance_spec_equals_metric_view_defaults() -> None:
    contracts = workshop.domain_spec("finance").metric_view_contracts()
    defaults = metrics_cp.DEFAULT_METRIC_VIEWS
    assert set(contracts) == set(defaults)
    for name, contract in contracts.items():
        default = defaults[name]
        assert contract["source_table"] == default.source_table
        assert tuple(contract["dimensions"]) == default.dimensions
        assert tuple(contract["measures"]) == default.measures


def test_finance_spec_equals_genie_defaults() -> None:
    spec = workshop.domain_spec("finance")
    assert spec.genie_expected_sources == genie_cp.DEFAULT_EXPECTED_SOURCES
    assert spec.genie_benchmark_questions == genie_cp.DEFAULT_BENCHMARK_QUESTIONS


def test_finance_spec_equals_app_defaults() -> None:
    spec = workshop.domain_spec("finance")
    assert spec.app_source_table == app_cp.DEFAULT_SOURCE_TABLE
    assert spec.app_primary_key == app_cp.DEFAULT_PRIMARY_KEY
    # The 07_app checkpoint derives the synced-table name from the namespace's
    # default serving base when none is passed — Finance's spec must match it.
    assert spec.app_serving_base == DEFAULT_SERVING_BASE


# --------------------------------------------------------------------------- #
# 2. Every domain's spec matches its gated solution's literals.
# --------------------------------------------------------------------------- #
def test_spec_names_appear_in_each_domain_solution() -> None:
    for domain in DOMAINS:
        spec = workshop.domain_spec(domain)

        bronze = _read("solutions", domain, "01_bronze_txn.py")
        assert spec.bronze_txn_table in bronze
        assert spec.transaction_key in bronze

        gold = _read("solutions", domain, "03_gold.py")
        for name in (
            spec.document_table,
            spec.detail_table,
            spec.mart_table,
            spec.group_key,
            spec.document_key,
            spec.detail_document_key,
            spec.detail_document_match,
        ):
            assert name in gold, f"{domain}: {name!r} missing from 03_gold solution"

        metadata = _read("solutions", domain, "04_metadata.py")
        for table in spec.metadata_tables:
            assert table in metadata, f"{domain}: {table!r} missing from 04_metadata solution"

        metrics = _read("solutions", domain, "05_metric_views.py")
        for view_name, view in spec.metric_views.items():
            assert view_name in metrics, f"{domain}: {view_name!r} missing from 05 solution"
            assert view.source_table in metrics
            for dimension in view.dimensions:
                assert dimension in metrics, f"{domain}: dim {dimension!r} missing"
            for measure in view.measures:
                assert measure in metrics, f"{domain}: measure {measure!r} missing"

        genie = _read("solutions", domain, "06_genie.py")
        for source in spec.genie_expected_sources:
            assert source in genie, f"{domain}: source {source!r} missing from 06 solution"
        for question in spec.genie_benchmark_questions:
            assert question in genie, f"{domain}: benchmark {question!r} missing"

        app = _read("solutions", domain, "07_app.py")
        assert spec.app_source_table in app
        # A domain that overrides the namespace's default serving base names it
        # explicitly in its solution; Finance uses the default base implicitly
        # (its equality to DEFAULT_SERVING_BASE is asserted separately).
        if spec.app_serving_base != DEFAULT_SERVING_BASE:
            assert spec.app_serving_base in app, (
                f"{domain}: serving base {spec.app_serving_base!r} missing from 07 solution"
            )
        for key in spec.app_primary_key:
            assert key in app, f"{domain}: primary key {key!r} missing from 07 solution"


def test_gold_reconcile_measures_are_present_in_solutions() -> None:
    # Security reconciles a concrete additive-measure list; those columns must be
    # real columns the Security gold solution aggregates.
    security = workshop.domain_spec("security")
    assert isinstance(security.reconcile_measures, tuple) and security.reconcile_measures
    gold = _read("solutions", "security", "03_gold.py")
    for measure in security.reconcile_measures:
        assert measure in gold, f"security reconcile measure {measure!r} missing"
    # ITSM disables measure reconciliation (its mart measures are not same-named
    # additive source columns) — the solution passes reconcile_measures=False.
    assert workshop.domain_spec("itsm").reconcile_measures is False
    assert "reconcile_measures=False" in _read("solutions", "itsm", "03_gold.py")


# --------------------------------------------------------------------------- #
# 3. The six starter notebooks are shared, parameterised scaffolds.
# --------------------------------------------------------------------------- #
def test_every_starter_notebook_offers_three_domains() -> None:
    for notebook in STARTER_NOTEBOOKS:
        text = _read("notebooks", notebook)
        assert DOMAIN_DROPDOWN in text, f"{notebook} lacks the 3-domain dropdown"


def test_every_starter_notebook_derives_from_the_domain_spec() -> None:
    for notebook in STARTER_NOTEBOOKS:
        text = _read("notebooks", notebook)
        assert "workshop.domain_spec(config.domain)" in text, (
            f"{notebook} must derive its names from workshop.domain_spec(config.domain)"
        )


def test_starter_notebooks_have_no_hardcoded_domain_object_names() -> None:
    # A shared, parameterised cell derives every object name from the spec — so no
    # domain's transactional-track literal (Finance, Security, or ITSM) may appear
    # in executed code. This is the release-blocking guarantee: a Security/ITSM
    # participant is never sent to a Finance table, and vice versa.
    for notebook in STARTER_NOTEBOOKS:
        code = _shared_code(_read("notebooks", notebook))
        for domain, literals in DOMAIN_OBJECT_LITERALS.items():
            for literal in literals:
                assert literal not in code, (
                    f"{notebook}: hardcoded {domain} literal {literal!r} in a shared "
                    "cell — derive it from workshop.domain_spec instead"
                )


def test_every_starter_notebook_passes_spec_derived_extras_to_check() -> None:
    # The checkpoint call must forward spec-derived values (not bare literals), so
    # generation and the domain-generic checkpoint agree for every domain.
    for notebook in STARTER_NOTEBOOKS:
        text = _read("notebooks", notebook)
        assert "spec." in text, f"{notebook} never references the resolved spec"
