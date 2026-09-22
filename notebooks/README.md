# notebooks/

Participant-facing starter notebooks — one per workshop module — with `# TODO`
cells, collapsible hints, and "build from scratch" stretch toggles. Each module
ends with a `workshop.check("<checkpoint_id>")` validation cell.

The curriculum is **one shared spine** across all three domains (Finance,
Security, ITSM); only the dataset and pre-authored semantic content differ, so
notebooks are domain-agnostic and read your selected domain from the setup
notebook's config.

`00_setup.py` (added by #3) is the participant setup notebook: it creates a
schema and UC Volume inside your team's **existing catalog**, runs seed hooks,
and ends on the `00_setup` checkpoint. Start there.

`01_bronze_docs.py` (added by #5) is the first medallion step: copy the committed
source PDFs into your UC Volume and register a bronze documents table over the
raw files. It ends on the `01_bronze_docs` checkpoint.

`01_bronze_txn.py` (added by #7) is the Finance transactional-ingestion starter.
It offers a primary Lakebase CDF path (clearly marked as an admin-enabled
Beta/Preview) and a no-admin Delta fallback; both land
`bronze_sales_transactions` and finish at checkpoint `01_bronze_txn`.

`02_silver_docs.py` (added by #6) is the document-intelligence silver step. Using
Databricks AI Functions, it parses each bronze document (`ai_parse_document`),
classifies it into one of your domain's classes (`ai_classify`) in a consolidated
`silver_docs` table, and extracts class-specific fields (`ai_extract`) into one
`silver_<class>` table per class. It ends on the `02_silver_docs` checkpoint.
`ai_parse_document` needs DBR 17.3+ / serverless env v3+ and a region that
supports AI Functions (not SQL Warehouse Classic) — see the notebook callout.

`03_gold.py` (added by #8) is the Finance gold medallion step. It joins the
transaction fact to extracted commercial-agreement documents on the conformed
`contract_id = agreement_id` key, producing transaction-grain `gold_sales` and
contract-grain `gold_contract_performance`. It ends on `03_gold`, which derives
the expected grains, identities, enrichment coverage, and aggregate measures
from the upstream tables rather than hardcoding seed counts.

`04_metadata.py` (added by #9) governs the gold tables with
[dbxmetagen](https://github.com/databricks-industry-solutions/dbxmetagen)
(notebook-only install, pinned to `v0.10.68`). It runs the `comment`, `pi`, and
`domain` modes with `apply_ddl=false` to stage metadata for review, then re-runs
with `apply_ddl=true` to apply table/column comments, a PI classification tag on
sensitive columns, and a business-domain tag on each table. dbxmetagen's model
endpoint defaults to `databricks-claude-sonnet-4-6`; the notebook has you confirm
that endpoint exists in **Serving → Foundation Models** or pick another (the only
endpoint you select — the `02_silver_docs` AI Functions use the built-in system
model). It ends on the `04_metadata` checkpoint, which reads only
`information_schema` comments and tags and derives the expected columns from the
live tables rather than hardcoding column names.

`05_metric_views.py` (added by #10) creates two governed Unity Catalog Metric
Views in the same resolved participant schema: Finance sales revenue/margin
metrics over `gold_sales`, and contract-performance metrics over
`gold_contract_performance`. It includes a documented "add your own metric"
stretch and ends at `05_metrics`, which validates the deployed metric-model
definitions and their non-null aggregate query results.

`06_genie.py` (added by #11) builds a curated **Genie agent** — a natural-language
interface — over the gold tables and Metric Views. It attaches all four Finance
data assets (`gold_sales`, `gold_contract_performance`, `finance_sales_metrics`,
`finance_contract_metrics`), gives the agent a **per-participant, identity-derived
name** so teammates sharing the workspace do not collide, and adds pre-authored
sample questions. It opens with a Partner-powered AI (Databricks Assistant)
pre-check and ends on `06_genie`, which finds the caller's own agent by name,
confirms the expected sources are attached (binding to the caller's own
workspace namespace so a teammate's same-titled agent is never adopted), and
asks benchmark questions — requiring each to return SQL that genuinely queries
the curated data (a source name in a string, comment, alias, or CTE name does
not count). The agent must actually answer, so if the Conversation API is gated
the checkpoint stays RED (enable Partner-powered AI) rather than passing.

`07_app.py` (added by #12) ships the **provided FastAPI data app** (`app/`) wired
to a **Lakebase synced table** created from the `gold_contract_performance` gold
table (#8) and the participant's **Genie agent** (#11). It has the participant
create a per-participant Lakebase project + synced table, deploy and explicitly
**start** the app (deploying can leave it stopped), and fill the app's **two
gaps** (the Genie Conversation API call and the Lakebase read) in
`app/backend.py`. It ends on `07_app`, which asserts observable platform state
only: the caller's own synced table exists, syncs from the expected gold table on
the expected key, is online and serving rows, and the caller's own app is
deployed and running. On Free Edition, one denormalized serving table is synced.
The app name, Lakebase project, and synced table are all namespaced per
participant.
