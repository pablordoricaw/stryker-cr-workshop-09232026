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

> The remaining notebooks are added by later tickets: the rest of the medallion
> + AI-functions build spine (metadata #9), metric views (#10), the
> Genie agent (#11), and the app wiring (#12).
