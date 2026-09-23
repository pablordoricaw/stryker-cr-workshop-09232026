# notebooks/

Participant-facing starter notebooks: one per workshop module, each with `# TODO` cells, collapsible hints, and "build from scratch" stretch toggles. Each module ends with a `workshop.check("<checkpoint_id>")` validation cell.

## Overview

Every graded **build** stage (`01_bronze_docs` through `07_app`) includes an identical **"🚀 From-scratch mode (optional stretch)"** markdown cell right after its config cell. This uniform, default-off convention lets you flip any stage from guided (with `# TODO`s and hints) to build-it-yourself mode. The cell is markdown only (no widget, no code), so it does not change what the checkpoint asserts. `00_setup` is excluded because it provisions rather than teaches a build. The convention is documented in [`../docs/stretch/README.md`](../docs/stretch/README.md).

The curriculum is **one shared spine** across all three domains (Finance, Security, ITSM); only the dataset and pre-authored semantic content differ. Notebooks are domain-agnostic and read your selected domain from the setup notebook's config.

## Setup

### `00_setup.py`

The participant setup notebook that starts every workshop:

- Creates a schema and UC Volume inside your team's **existing catalog** (no catalog-creation privilege needed).
- Runs seed hooks.
- Ends on the `00_setup` checkpoint.

After your domain is chosen, it also **installs the Genie Code hint ladder**:

- Reads [`../docs/genie/.assistant_instructions.md`](../docs/genie/.assistant_instructions.md), fills in your repo root and domain.
- Injects the result (wrapped in `STRYKER-WORKSHOP` sentinels) into your personal `~/.assistant_instructions.md`, which Genie Code auto-loads each session.
- Preserves any personal instructions of your own and is idempotent on re-run.
- The injection/merge/strip logic is the pure-Python `workshop.genie_instructions` module (unit-tested in [`../tests/test_genie_instructions.py`](../tests/test_genie_instructions.py)).

## Core Pipeline

### `01_bronze_docs.py`

The first medallion step:

- Copy the committed source PDFs from `data/<domain>/` into your UC Volume.
- Register a **bronze documents table** over the raw files.
- Ends on the `01_bronze_docs` checkpoint.

### `01_bronze_txn.py`

The transactional-ingestion starter for your domain:

- Offers a primary **Lakebase CDF path** (admin-enabled, marked Beta/Preview) and a no-admin **Delta fallback**.
- Both paths land your domain's transactional table (e.g., `bronze_sales_transactions` for Finance).
- Finishes at checkpoint `01_bronze_txn`.

### `02_silver_docs.py`

The document-intelligence silver step:

- Uses **Databricks AI Functions** to parse each bronze document (`ai_parse_document`).
- Classifies each document into one of your domain's classes (`ai_classify`) into a consolidated `silver_docs` table.
- Extracts class-specific fields (`ai_extract`) into one `silver_<class>` table per class.
- Ends on the `02_silver_docs` checkpoint.

**Requirement:** `ai_parse_document` requires DBR 17.3+, serverless environment v3+, and a region that supports AI Functions (not SQL Warehouse Classic). See the notebook callout for details.

### `03_gold.py`

The gold medallion step for your domain:

- Joins the transactional fact to extracted domain-specific documents on the domain-appropriate key.
- Produces transaction-grain and reconciled mart tables (e.g., `gold_sales` and `gold_contract_performance` for Finance).
- Ends on the `03_gold` checkpoint, which derives expected grains, identities, enrichment coverage, and aggregate measures from the upstream tables (no hardcoded seed counts).

### `04_metadata.py`

Governance metadata with [dbxmetagen](https://github.com/databricks-industry-solutions/dbxmetagen):

- Pinned to `v0.10.68` (notebook-only install).
- Runs `comment`, `pi`, and `domain` modes with `apply_ddl=false` to stage metadata for review.
- Re-runs with `apply_ddl=true` to apply table/column comments, PI classification tags on sensitive columns, and business-domain tags on each table.
- Uses a model endpoint (defaults to `databricks-claude-sonnet-4-6`; notebook prompts you to confirm it exists in **Serving → Foundation Models** or pick another).
- The `02_silver_docs` AI Functions use the built-in system model (you select only the endpoint for this step).
- Ends on the `04_metadata` checkpoint, which reads `information_schema` comments and tags and derives expected columns from live tables.

### `05_metric_views.py`

Creates two governed UC Metric Views in your resolved participant schema:

- **Sales and contract metrics** over the gold tables (e.g., `gold_sales` revenue/margin and `gold_contract_performance` metrics for Finance).
- Includes a documented "add your own metric" stretch.
- Ends at the `05_metrics` checkpoint, which validates deployed metric-model definitions and non-null aggregate query results.

### `06_genie.py`

Builds a curated **Genie agent** as a natural-language interface:

- Attaches your gold tables and Metric Views (all four Finance data assets, for example: `gold_sales`, `gold_contract_performance`, `finance_sales_metrics`, `finance_contract_metrics`).
- Gives the agent a **per-participant, identity-derived name** so teammates in the same workspace do not collide.
- Adds pre-authored sample questions.
- Ends on `06_genie`. The checkpoint finds your own agent by name, confirms the expected sources are attached (binding to your own workspace namespace), and asks benchmark questions. Each must return SQL that genuinely queries the curated data (mentioning a source name in a string, comment, alias, or CTE name does not count).
- If the Genie Conversation API is gated, the checkpoint stays RED (enable Partner-powered AI in workspace settings).

### `07_app.py`

Ships the **provided Streamlit data app** (`app/`) wired to your built pipeline:

- Create a per-participant **Lakebase synced table** from your gold domain table (e.g., `gold_contract_performance`).
- Deploy and explicitly **start** the app (deploying can leave it stopped).
- Fill the app's **two gaps** in `app/backend.py`: the Genie Conversation API call and the Lakebase read.
- Ends on `07_app`. The checkpoint asserts observable platform state only: your own synced table exists, syncs from the expected gold table on the expected key, is online and serving rows, and your app is deployed and running.
- On Databricks Free Edition, one denormalized serving table is synced.
- The app name, Lakebase project, and synced table are all namespaced per participant.

## Optional Stretch Modules

The **Tier-3 stretch** starters live in [`stretch/`](stretch/):

- **`package_as_dab.py`**: Package your built infrastructure and app as a set of independently-deployable Databricks Asset Bundles.
- **`add_your_own.py`**: Add your own Metric View and Genie benchmark questions, validated through the existing checkpoint knobs.

Both are additive and ungraded. Their gated solutions are under `solutions/<domain>/stretch/`.

## Cleanup

### `99_teardown.py`

Optional end-of-workshop cleanup:

- Strips the `STRYKER-WORKSHOP` block that `00_setup` injected from your personal `~/.assistant_instructions.md`, leaving any instructions of your own untouched.
- Safe no-op if there's no block.
- Does **not** touch your catalog data; drop the workshop schema separately if you want to reclaim that.
