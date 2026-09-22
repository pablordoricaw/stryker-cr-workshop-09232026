# solutions/

Gated reference solutions for all three domains — the top rung of the hint
ladder and the ground truth maintainer CI runs end-to-end.

**Participants:** reach for these only through Genie Code's graded hints. Peeking
here skips the learning; try the nudge → skeleton → checkpoint-solution ladder
first.

Layout (one subtree per domain; filled in as build-spine tickets land):

```
solutions/
├── finance/
│   ├── 01_bronze_docs.py   # #5 — land PDFs + register the bronze docs table
│   ├── 01_bronze_txn.py    # #7 — Lakebase CDF + Delta fallback to bronze txn
│   ├── 02_silver_docs.py   # #6 — ai_parse_document/classify/extract to silver
│   ├── 03_gold.py          # #8 — document-enriched sales + contract mart
│   ├── 04_metadata.py      # #9 — dbxmetagen comment/pi/domain on the gold tables
│   ├── 05_metric_views.py  # #10 — governed UC Metric Views over the gold tables
│   ├── 06_genie.py         # #11 — per-participant Genie agent over gold + metrics
│   ├── 07_app.py           # #12 — provided FastAPI app + Lakebase synced table
│   └── stretch/            # #16 — optional Tier-3 gated solutions
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
│   └── 07_app.py           # provided FastAPI app + Lakebase synced table
└── itsm/
```

The Finance solutions for `01_bronze_docs`, `01_bronze_txn`, and `02_silver_docs`
are authored. `01_bronze_txn` implements both the admin-enabled Lakebase CDF path
and the no-admin Delta fallback; `02_silver_docs` builds the document-intelligence
silver layer with AI Functions (`ai_parse_document` → `ai_classify` →
`ai_extract`), landing `silver_docs` plus one `silver_<class>` table per class.
`03_gold` joins sales to extracted commercial agreements without changing
transaction grain and builds a reconciled contract-performance mart. `04_metadata`
runs dbxmetagen (pinned `v0.10.68`) in `comment`, `pi`, and `domain` modes,
staging metadata with `apply_ddl=false` and then applying comments, PI
classification tags, and domain tags to the gold tables. Later solution notebooks
are authored alongside each build-spine ticket and validated by maintainer CI
(#17). This directory ships on both `dev` and the participant release.

`05_metric_views` defines the Finance sales revenue/margin and contract-
performance semantic layers as UC Metric Views in the participant's existing
resolved schema. It also demonstrates the `MEASURE()` query syntax and documents
the optional custom-metric stretch.

`06_genie` creates (idempotently, create-or-update) a per-participant Genie agent
over the two gold tables and two Metric Views, with an identity-derived name,
pre-authored sample questions, short text instructions, and benchmark Q&A. It
uses the Databricks SDK (`WorkspaceClient().genie`), asks a sample question to
show the generated SQL, and ends on the `06_genie` checkpoint, which validates
the agent by observable Genie state only.

`07_app` ships the provided FastAPI app (`app/`) wired to a per-participant
Lakebase synced table (created from `gold_contract_performance`) and the
participant's Genie agent. It shows the complete code for the two participant
gaps in `app/backend.py` (the Genie Conversation API call and the Lakebase read),
the Lakebase project/catalog/synced-table + app deploy/start commands, and the
`07_app` checkpoint, which validates the deployed slice by observable platform
state only (synced table serving the expected gold data + app deployed and
running).

`stretch/` holds the gated solutions for the optional Tier-3 modules (#16).
`package_as_dab_bundle/` is a **set of two independently-deployable DABs**
(`pipeline`, `app`) — deliberately not one monolith — that package the built work
and **target** the schema/volume `00_setup` provisioned (neither declares a
schema/volume resource, so a first deploy never collides with pre-existing UC
objects). Its README documents the division rationale, coupling/decoupling
tradeoffs, cross-bundle references, and deploy runbook; both pass
`databricks bundle validate --strict` offline. `add_your_own.py` adds a third
Metric View and two Genie benchmark questions, validated through the existing
`05_metrics` `metric_views=` and `06_genie` `expected_sources=`/
`benchmark_questions=` knobs (no framework change). These are additive and
ungraded; they ship on both `dev` and the participant release.

The **Security** solutions run the identical pipeline on the infrastructure-
security dataset (`data/security/`). The document classes are `vulnerability_scan`,
`cve_advisory`, `pentest_report`, `cloud_posture_finding`, and `other`; the
transactional grain is one row per vulnerability-scan finding
(`bronze_scan_findings`, 3,000 rows). `03_gold` joins findings to the extracted
CVE advisory on `cve_id`, building `gold_findings` (finding grain) and
`gold_cve_exposure` (per-CVE mart); `05_metric_views` defines
`security_findings_metrics` and `security_cve_metrics`; `06_genie` ships Security
sample/benchmark questions (open findings by severity, weighted risk by CVE); and
`07_app` syncs `gold_cve_exposure` on `cve_id`. Every domain-specific
expectation (table/column names, reconcile measures, metric-view contracts,
Genie sources, serving base) is passed to the shared, domain-generic checkpoints
through `workshop.check(...)` extras — no shared checkpoint or notebook is
modified. The domain-generic `01_bronze_txn` checkpoint takes the Security bronze
table name and expected row count as inputs, so it validates Security data
without any Finance-specific name baked in.
