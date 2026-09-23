# solutions/

Gated reference solutions for all three domains: the top rung of the hint ladder and the ground truth that maintainer CI validates end-to-end.

> [!WARNING]
> **Participants:** reach for these only through Genie Code's graded hints. Peeking here skips the learning; try the nudge → skeleton → checkpoint-solution ladder first.

## Layout

```
solutions/
├── finance/
│   ├── 01_bronze_docs.py   # land PDFs + register the bronze docs table
│   ├── 01_bronze_txn.py    # Lakebase CDF + Delta fallback to bronze txn
│   ├── 02_silver_docs.py   # ai_parse_document/classify/extract to silver
│   ├── 03_gold.py          # document-enriched sales + contract mart
│   ├── 04_metadata.py      # dbxmetagen comment/pi/domain on the gold tables
│   ├── 05_metric_views.py  # governed UC Metric Views over the gold tables
│   ├── 06_genie.py         # per-participant Genie agent over gold + metrics
│   ├── 07_app.py           # provided Streamlit app + Lakebase synced table
│   └── stretch/            # optional Tier-3 gated solutions
│       ├── package_as_dab.py            # walkthrough of the bundle set below
│       ├── package_as_dab_bundle/       # 2 independently-deployable DABs + the "why"
│       └── add_your_own.py              # a 3rd Metric View + extra Genie questions
├── security/
│   ├── 01_bronze_docs.py   # land PDFs + register the bronze docs table
│   ├── 01_bronze_txn.py    # Lakebase CDF + Delta fallback to bronze scan findings
│   ├── 02_silver_docs.py   # ai_parse_document/classify/extract to silver
│   ├── 03_gold.py          # advisory-enriched findings + CVE-exposure mart
│   ├── 04_metadata.py      # dbxmetagen comment/pi/domain on the gold tables
│   ├── 05_metric_views.py  # governed UC Metric Views over the gold tables
│   ├── 06_genie.py         # per-participant Genie agent over gold + metrics
│   └── 07_app.py           # provided Streamlit app + Lakebase synced table
└── itsm/
```

## Domain Implementations

### Finance

The Finance solutions implement the full medallion pipeline with document enrichment:

**Bronze layer:**
- `01_bronze_docs.py` — land PDFs and register the bronze docs table.
- `01_bronze_txn.py` — implements both the admin-enabled **Lakebase CDF path** and the no-admin **Delta fallback**; both land `bronze_sales_transactions`.

**Silver layer:**
- `02_silver_docs.py` — builds the document-intelligence silver layer with AI Functions (`ai_parse_document` → `ai_classify` → `ai_extract`), landing `silver_docs` plus one `silver_<class>` table per class.

**Gold layer:**
- `03_gold.py` — joins sales to extracted commercial agreements without changing transaction grain, building `gold_sales` (transaction grain) and `gold_contract_performance` (contract-grain reconciled mart).

**Governance and semantics:**
- `04_metadata.py` — runs dbxmetagen (pinned `v0.10.68`) in `comment`, `pi`, and `domain` modes. Stages metadata with `apply_ddl=false` and then applies comments, PI classification tags, and domain tags to the gold tables.
- `05_metric_views.py` — defines Finance sales revenue/margin and contract-performance semantic layers as UC Metric Views in the participant's resolved schema. Demonstrates the `MEASURE()` query syntax and documents the optional custom-metric stretch.

**Agent and app:**
- `06_genie.py` — creates (idempotently) a per-participant Genie agent over the two gold tables and two Metric Views, with an identity-derived name, pre-authored sample questions, and benchmark Q&A. Uses the Databricks SDK (`WorkspaceClient().genie`) and demonstrates how the generated SQL queries the curated data.
- `07_app.py` — ships the provided Streamlit app (`app/`) wired to a per-participant Lakebase synced table (created from `gold_contract_performance`) and the participant's Genie agent. Shows the complete code for the two participant gaps in `app/backend.py` (the Genie Conversation API call and the Lakebase read), plus Lakebase project/catalog/synced-table + app deploy/start commands.

**Optional Tier-3 stretch:**
- `stretch/package_as_dab.py` — walkthrough for packaging your built work as independently-deployable Databricks Asset Bundles.
- `stretch/package_as_dab_bundle/` — a **set of two independently-deployable DABs** (`pipeline`, `app`), deliberately not one monolith. Packages the built work and targets the schema/volume `00_setup` provisioned (neither declares a schema/volume resource, so a first deploy never collides with pre-existing UC objects). The README documents the division rationale, coupling/decoupling tradeoffs, cross-bundle references, and deploy runbook; both pass `databricks bundle validate --strict` offline.
- `stretch/add_your_own.py` — adds a third Metric View and two Genie benchmark questions, validated through the existing `05_metrics` `metric_views=` and `06_genie` `expected_sources=`/`benchmark_questions=` knobs (no framework change).

All Finance solutions are authored and validated. The stretch modules are additive and ungraded; they ship on both `dev` and the participant release.

### Security

The Security solutions run the identical medallion pipeline on the infrastructure-security dataset (`data/security/`), with domain-specific refinements:

**Document classes:** `vulnerability_scan`, `cve_advisory`, `pentest_report`, `cloud_posture_finding`, `other`.

**Transactional grain:** one row per vulnerability-scan finding in `bronze_scan_findings` (3,000 rows).

**Pipeline adjustments:**
- `03_gold.py` — joins findings to the extracted CVE advisory on `cve_id`, building `gold_findings` (finding grain) and `gold_cve_exposure` (per-CVE mart).
- `05_metric_views.py` — defines `security_findings_metrics` and `security_cve_metrics`.
- `06_genie.py` — includes Security-specific sample/benchmark questions (e.g., open findings by severity, weighted risk by CVE).
- `07_app.py` — syncs `gold_cve_exposure` on `cve_id`.

**Domain abstraction:**
Every domain-specific expectation (table/column names, reconcile measures, metric-view contracts, Genie sources, serving base) is passed to the shared, domain-generic checkpoints through `workshop.check(...)` extras; no shared checkpoint or notebook is modified. The domain-generic `01_bronze_txn` checkpoint takes the Security bronze table name and expected row count as inputs, so it validates Security data without any Finance-specific name baked in.

### ITSM

ITSM solutions follow the same structure and conventions as Finance and Security but are tailored to IT-Ops use cases and datasets.
