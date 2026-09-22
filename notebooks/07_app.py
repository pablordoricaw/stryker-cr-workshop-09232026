# Databricks notebook source
# ruff: noqa: F821
# MAGIC %md
# MAGIC # 07 · Data app over a Lakebase synced table
# MAGIC
# MAGIC Ship the **provided FastAPI app** (`app/`) wired to two things you already
# MAGIC built: your **Genie agent** (`06_genie`) and a **Lakebase synced table**
# MAGIC created from one of your gold tables (`03_gold`). The app is complete except
# MAGIC for **two gaps** you fill in `app/backend.py` — the Genie connection and the
# MAGIC Lakebase read.
# MAGIC
# MAGIC Everything lands in **your existing catalog / schema** and a **per-participant
# MAGIC Lakebase project** — no catalog is created, and no second schema.
# MAGIC
# MAGIC You will:
# MAGIC 1. create a **Lakebase project** and register it as a UC catalog (per participant);
# MAGIC 2. create a **synced table** from `gold_contract_performance`;
# MAGIC 3. **deploy and start** the app (Apps UI or CLI) with its Genie + Lakebase resources;
# MAGIC 4. fill the **two gaps** in `app/backend.py`; and
# MAGIC 5. pass the **`07_app`** checkpoint.

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ Pre-check: Lakebase must be enabled
# MAGIC
# MAGIC Lakebase (Autoscaling Postgres) must be available in your workspace. On
# MAGIC **Free Edition** you sync **one denormalized serving table** into a
# MAGIC scale-to-zero project. If `databricks postgres` / project creation is gated,
# MAGIC ask your facilitator — the fallback is a **shared project with a
# MAGIC per-participant database**.

# COMMAND ----------

# --- Workshop bootstrap: run this first in every notebook ---
import os
import sys

_root = os.path.abspath(os.getcwd())
while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        raise RuntimeError("workshop repo root not found; open this notebook inside the cloned workshop Git folder.")
    _root = _parent
if _root not in sys.path:
    sys.path.insert(0, _root)

import workshop

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Config and your per-participant names
# MAGIC
# MAGIC The app, the Lakebase project, and the synced table are all
# MAGIC **workspace-scoped**, and your team shares one workspace — so each carries a
# MAGIC **per-participant identity suffix**, exactly like your `06_genie` agent name.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = domain name)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("lakebase_catalog", "", "Lakebase UC catalog (blank = derive)")

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
)

# The gold serving table synced into Lakebase (one denormalized table).
gold_serving = workshop.fully_qualified(
    config.catalog, config.schema, "gold_contract_performance"
)

me = spark.sql("SELECT current_user()").collect()[0][0]
suffix = "".join(c if c.isalnum() else "-" for c in me.split("@")[0]).strip("-").lower()

# Per-participant identifiers (App names allow [a-z0-9-]; Lakebase ids are RFC 1123).
app_name = f"stryker-{config.domain}-{suffix}"[:30].rstrip("-")
project_id = f"lb-{config.domain}-{suffix}"[:63].rstrip("-")
lakebase_catalog = dbutils.widgets.get("lakebase_catalog") or f"lb_{config.domain}_{suffix.replace('-', '_')}"
synced_table = f"{lakebase_catalog}.public.gold_contract_performance"

print(f"Signed in as   : {me}")
print(f"App name       : {app_name}")
print(f"Lakebase project: {project_id}")
print(f"Synced table   : {synced_table}")
print(f"Gold source    : {gold_serving}")

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — why per-participant names</summary>
# MAGIC
# MAGIC The `07_app` checkpoint asserts **your own** app and synced table by these
# MAGIC exact names — there is no shared/fixed name. Two participants in the same
# MAGIC workspace each pass with their own app + synced table.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create your Lakebase synced table from the gold serving table
# MAGIC
# MAGIC Sync `gold_contract_performance` (one denormalized row per contract) into
# MAGIC Lakebase so the app reads it at low latency. Two steps: create a Lakebase
# MAGIC project + register it as a UC catalog, then create the synced table.
# MAGIC
# MAGIC <details>
# MAGIC <summary>Hint: create the project + catalog (CLI, run in a terminal)</summary>
# MAGIC
# MAGIC ```bash
# MAGIC databricks postgres create-project <project_id> \
# MAGIC   --json '{"spec": {"display_name": "<project_id>"}}' --profile <p>
# MAGIC # register the Lakebase DB as a UC catalog (one-time per project):
# MAGIC databricks postgres create-catalog <lakebase_catalog> \
# MAGIC   --json '{"spec": {"postgres_database": "databricks_postgres",
# MAGIC     "branch": "projects/<project_id>/branches/production"}}' --profile <p>
# MAGIC ```
# MAGIC </details>

# COMMAND ----------

# TODO: Create the Lakebase synced table from `gold_serving` into your Lakebase
# TODO: catalog's `public` schema, primary key `contract_id`. Snapshot mode is
# TODO: simplest on Free Edition. You can use the CLI or the SDK; capture the
# TODO: synced-table UC name in `synced_table` (already derived above).
#
# SDK sketch (see solutions/finance/07_app.py for the complete, waited version):
#   from databricks.sdk import WorkspaceClient
#   w = WorkspaceClient()
#   w.database.create_synced_database_table(... source_table_full_name=...,
#       primary_key_columns=["contract_id"], scheduling_policy="SNAPSHOT", ...)

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>Hint: create the synced table (CLI)</summary>
# MAGIC
# MAGIC ```bash
# MAGIC databricks postgres create-synced-table <lakebase_catalog>.public.gold_contract_performance \
# MAGIC   --json '{"spec": {
# MAGIC     "source_table_full_name": "<catalog>.<schema>.gold_contract_performance",
# MAGIC     "primary_key_columns": ["contract_id"],
# MAGIC     "scheduling_policy": "SNAPSHOT",
# MAGIC     "branch": "projects/<project_id>/branches/production",
# MAGIC     "postgres_database": "databricks_postgres",
# MAGIC     "create_database_objects_if_missing": true,
# MAGIC     "new_pipeline_spec": {"storage_catalog": "<your_catalog>", "storage_schema": "<your_schema>"}
# MAGIC   }}' --profile <p>
# MAGIC ```
# MAGIC `storage_catalog` must be a **regular UC catalog** (your existing one), not
# MAGIC the Lakebase catalog. Wait for the sync to be **online** before deploying.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Deploy and **start** the app
# MAGIC
# MAGIC Deploy `app/` as a Databricks App named `app_name`, add its resources, and
# MAGIC **start it** — deploying can leave the app stopped, and a stopped app answers
# MAGIC nothing.
# MAGIC
# MAGIC Add resources (Apps UI → Edit → Resources, or CLI): a **Genie space** (key
# MAGIC `genie-space`, *Can run*) and your **Lakebase database** (key `postgres`,
# MAGIC *Can connect and create*). Set `SERVING_TABLE=public.gold_contract_performance`.
# MAGIC
# MAGIC <details>
# MAGIC <summary>Hint: deploy + start (CLI)</summary>
# MAGIC
# MAGIC ```bash
# MAGIC databricks apps create <app_name> --profile <p>            # once
# MAGIC databricks sync ./app "/Workspace/Users/<me>/<app_name>" --profile <p>
# MAGIC databricks apps deploy <app_name> \
# MAGIC   --source-code-path "/Workspace/Users/<me>/<app_name>" --profile <p>
# MAGIC databricks apps start <app_name> --profile <p>             # explicit start!
# MAGIC ```
# MAGIC After the synced table is online, grant the app's service principal SELECT on
# MAGIC it (see solutions/finance/07_app.py).
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Fill the two gaps in `app/backend.py`
# MAGIC
# MAGIC Open `app/backend.py` and complete the two `PARTICIPANT GAP` functions:
# MAGIC
# MAGIC 1. **Genie connection** — `ask_genie` calls the Genie Conversation API.
# MAGIC 2. **Lakebase read** — `fetch_serving_rows` reads your synced serving table.
# MAGIC
# MAGIC Redeploy after editing. The complete code is in `solutions/finance/07_app.py`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `07_app`
# MAGIC
# MAGIC The check reads only observable platform state: your **synced table** exists,
# MAGIC syncs from **your** `gold_contract_performance` on `contract_id`, is **owned
# MAGIC by you**, is **online**, and **serves rows**; and your **app** is deployed,
# MAGIC **owned by you**, and **running**. It fails (RED) if the synced table is
# MAGIC missing/someone else's/stale/empty or the app is missing/someone else's/stopped.
# MAGIC
# MAGIC `owner=me` binds both resources to you (no adopting a teammate's). The Lakebase
# MAGIC connection hints let the check read the served-row count — serving is verified
# MAGIC fail-closed, so an unverifiable/empty synced table stays RED.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
lakebase_endpoint = f"projects/{project_id}/branches/production/endpoints/primary"
lakebase_host = w.postgres.get_endpoint(name=lakebase_endpoint).status.hosts.host

result = workshop.check(
    "07_app",
    spark=spark,  # enables source-count parity for the synced table
    catalog=config.catalog,
    schema=config.schema,
    apps=w,
    app_name=app_name,
    synced_table=synced_table,
    owner=me,  # required — binds the app AND synced table to YOU
    lakebase_endpoint=lakebase_endpoint,  # so served rows can be verified
    lakebase_host=lakebase_host,
    lakebase_user=me,
    lakebase_database="databricks_postgres",
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch
# MAGIC
# MAGIC - Add an `/api/ask` history panel, or a second serving screen over
# MAGIC   `gold_sales`.
# MAGIC - Switch the sync to **Triggered** (enable Change Data Feed on the gold
# MAGIC   table first) so the app sees fresh data on a schedule.
# MAGIC - For another domain, sync that domain's gold serving table and pass
# MAGIC   `source_table=`, `primary_key_columns=`, `synced_table=`, and `app_name=`
# MAGIC   to `workshop.check`.
