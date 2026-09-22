# Databricks notebook source
# ruff: noqa: F821, I001
# MAGIC %md
# MAGIC # 07 · Data app over a Lakebase synced table — SOLUTION (Finance)
# MAGIC
# MAGIC **Gated reference solution.** Ships the provided FastAPI app (`app/`) wired
# MAGIC to a per-participant **Genie agent** (#11) and a **Lakebase synced table**
# MAGIC created from `gold_contract_performance` (#8). It shows the complete code for
# MAGIC the two participant gaps in `app/backend.py`, the Lakebase + app lifecycle
# MAGIC commands, and the `07_app` checkpoint. No catalog and no second schema are
# MAGIC created; the Lakebase project + synced table + app are all per-participant.
# MAGIC
# MAGIC **Prerequisite:** Lakebase (Autoscaling Postgres) enabled; `03_gold` and
# MAGIC `06_genie` complete. On Free Edition, sync **one** denormalized serving table.

# COMMAND ----------

# --- Workshop bootstrap: run this first in every notebook ---
import os, sys
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

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = domain name)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("genie_space_id", "", "Genie space id (from 06_genie)")

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Per-participant names (identity-derived)
# MAGIC
# MAGIC The app, Lakebase project, and synced table are workspace-scoped, so each
# MAGIC name carries an identity suffix — like the `06_genie` agent name.

# COMMAND ----------

me = spark.sql("SELECT current_user()").collect()[0][0]
suffix = "".join(c if c.isalnum() else "-" for c in me.split("@")[0]).strip("-").lower()
usuffix = suffix.replace("-", "_")

app_name = f"stryker-{config.domain}-{suffix}"[:30].rstrip("-")
project_id = f"lb-{config.domain}-{suffix}"[:63].rstrip("-")
branch = f"projects/{project_id}/branches/production"
gold_serving = f"{config.catalog}.{config.schema}.gold_contract_performance"

# The synced table lands in YOUR existing catalog + schema — no catalog is
# created, and none is registered. The synced-table id `<catalog>.<schema>.<table>`
# doubles as a Unity Catalog virtual table AND a Postgres table `<table>` in
# schema `<schema>`, so the app reads `<schema>.<table>` from Postgres directly.
target_table = f"gold_contract_performance_served_{usuffix}"
synced_table = f"{config.catalog}.{config.schema}.{target_table}"
serving_table = f"{config.schema}.{target_table}"  # the app's SERVING_TABLE (Postgres name)

print(f"me             : {me}")
print(f"app_name       : {app_name}")
print(f"project_id     : {project_id}")
print(f"synced_table   : {synced_table}")
print(f"serving_table  : {serving_table}")
print(f"gold_serving   : {gold_serving}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create the Lakebase project and synced table (CLI)
# MAGIC
# MAGIC Run these in a terminal with your `--profile`. The project auto-creates a
# MAGIC `production` branch + `primary` endpoint (scale-to-zero). Then create the
# MAGIC synced table straight into your **existing** catalog/schema — there is **no
# MAGIC catalog to create or register** (`create-catalog` is not used). Snapshot
# MAGIC mode is simplest on Free Edition; Triggered/Continuous need Change Data Feed
# MAGIC on the gold table.

# COMMAND ----------

print(f"""# 2a. Create the per-participant Lakebase project (waits until ready)
databricks postgres create-project {project_id} \\
  --json '{{"spec": {{"display_name": "Stryker workshop — {me}"}}}}' --profile <p>

# 2b. Create the synced table from the gold serving table (Snapshot mode). The id
#     is a UC name in YOUR existing catalog/schema — there is NO create-catalog.
databricks postgres create-synced-table {synced_table} \\
  --json '{{"spec": {{
    "source_table_full_name": "{gold_serving}",
    "primary_key_columns": ["contract_id"],
    "scheduling_policy": "SNAPSHOT",
    "branch": "{branch}",
    "postgres_database": "databricks_postgres",
    "create_database_objects_if_missing": true,
    "new_pipeline_spec": {{"storage_catalog": "{config.catalog}", "storage_schema": "{config.schema}"}}
  }}}}' --profile <p>

# 2c. Wait for the sync to be ONLINE
databricks postgres get-synced-table "synced_tables/{synced_table}" --profile <p>
""")

# COMMAND ----------

# MAGIC %md
# MAGIC The same via the SDK, in-notebook (equivalent to the CLI above):

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import (
    NewPipelineSpec,
    SyncedTable,
    SyncedTableSyncedTableSpec,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
)

import time

w = WorkspaceClient()

# Assumes the project (2a) already exists. The synced-table id is a UC name in
# your existing catalog — there is NO Lakebase catalog. NOTE: `.wait()` returns
# once the resource is provisioned, which can still be SYNCED_TABLE_PROVISIONING
# — it does NOT block until the initial snapshot finishes. So poll below until
# the sync is ONLINE before deploying the app / expecting served rows. The
# `07_app` checkpoint correctly stays RED until the table is online and serving.
synced = w.postgres.create_synced_table(
    synced_table_id=synced_table,
    synced_table=SyncedTable(
        spec=SyncedTableSyncedTableSpec(
            source_table_full_name=gold_serving,
            primary_key_columns=["contract_id"],
            scheduling_policy=SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy.SNAPSHOT,
            branch=branch,
            postgres_database="databricks_postgres",
            create_database_objects_if_missing=True,
            new_pipeline_spec=NewPipelineSpec(
                storage_catalog=config.catalog,
                storage_schema=config.schema,
            ),
        ),
    ),
).wait()
print("synced table created:", synced.name)

# Poll until the sync reaches an ONLINE detailed_state (e.g.
# SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE). A still-provisioning table serves no
# rows yet, so wait here before deploying / running the checkpoint.
for _ in range(40):  # ~10 min ceiling at 15s
    t = w.postgres.get_synced_table(name=f"synced_tables/{synced_table}")
    detailed = getattr(getattr(t.status, "detailed_state", None), "value", "") or ""
    print("  detailed_state:", detailed)
    if detailed.startswith("SYNCED_TABLE_ONLINE") and "FAILED" not in detailed:
        break
    if "FAILED" in detailed:
        raise RuntimeError(f"sync failed: {getattr(t.status, 'message', None)}")
    time.sleep(15)
else:
    raise TimeoutError("synced table did not reach an ONLINE state in time")
print("synced table ONLINE")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Fill the two gaps in `app/backend.py`
# MAGIC
# MAGIC The complete code for each `PARTICIPANT GAP`. Paste these bodies over the
# MAGIC `raise NotImplementedError(...)` lines in `app/backend.py`, then redeploy.

# COMMAND ----------

# MAGIC %md
# MAGIC **GAP 1 of 2 — Genie Conversation API connection** (`Backend.ask_genie`):
# MAGIC ```python
# MAGIC def ask_genie(self, question: str) -> dict:
# MAGIC     msg = self._ws().genie.start_conversation_and_wait(GENIE_SPACE_ID, question)
# MAGIC     status = getattr(getattr(msg, "status", None), "value", None) or str(msg.status)
# MAGIC     answer_text, sql = None, None
# MAGIC     for a in (msg.attachments or []):
# MAGIC         if getattr(a, "query", None) and getattr(a.query, "query", None):
# MAGIC             sql = a.query.query
# MAGIC         if getattr(a, "text", None) and getattr(a.text, "content", None):
# MAGIC             answer_text = a.text.content
# MAGIC     return {"status": str(status).lower(), "answer": answer_text, "sql": sql}
# MAGIC ```
# MAGIC
# MAGIC **GAP 2 of 2 — Lakebase read** (`Backend.fetch_serving_rows`):
# MAGIC ```python
# MAGIC def fetch_serving_rows(self, limit: int = SERVING_LIMIT) -> list[dict]:
# MAGIC     schema, table = SERVING_TABLE.split(".", 1)
# MAGIC     with self._lakebase_connection() as conn, conn.cursor() as cur:
# MAGIC         cur.execute(f'SELECT * FROM "{schema}"."{table}" LIMIT %s', (limit,))
# MAGIC         cols = [c.name for c in cur.description]
# MAGIC         return [dict(zip(cols, row)) for row in cur.fetchall()]
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Deploy, wire resources, and START the app (CLI)
# MAGIC
# MAGIC Deploying can leave the app **stopped** — start it explicitly. Add a Genie
# MAGIC space resource (`genie-space`, Can run) and your Lakebase database
# MAGIC (`postgres`, Can connect and create). After the sync is online, grant the
# MAGIC app's service principal SELECT on the synced table.

# COMMAND ----------

print(f"""# 4a. Create + sync code + deploy + START
databricks apps create {app_name} --profile <p>
databricks sync ./app "/Workspace/Users/{me}/{app_name}" --profile <p>
databricks apps deploy {app_name} --source-code-path "/Workspace/Users/{me}/{app_name}" --profile <p>
databricks apps start {app_name} --profile <p>

# 4b. Wire resources (Apps UI → Edit → Resources, or `databricks apps create-update`):
#   genie-space  (Can run)                 → GENIE_SPACE_ID  ({dbutils.widgets.get("genie_space_id") or "your 06_genie space id"})
#   postgres     (Can connect and create)  → PGHOST/... + LAKEBASE_ENDPOINT
#   env SERVING_TABLE = {serving_table}

# 4c. Grant the app SP SELECT on the synced table (run as project owner). The
#     synced table lands in the Postgres schema "{config.schema}" (= your UC schema):
#   GRANT USAGE ON SCHEMA "{config.schema}" TO "<app_sp_client_id>";
#   GRANT SELECT ON ALL TABLES IN SCHEMA "{config.schema}" TO "<app_sp_client_id>";
# app_sp_client_id: databricks apps get {app_name} --profile <p>  (service_principal_client_id)
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `07_app`
# MAGIC
# MAGIC Reads only observable state: your synced table exists, syncs from **your**
# MAGIC `gold_contract_performance` on `contract_id`, is **owned by you**, is online,
# MAGIC and **serves rows** (verified fail-closed via a live row count); and your app
# MAGIC is deployed, **owned by you**, and running. Pass the Lakebase connection
# MAGIC hints so the served-row count can be read.

# COMMAND ----------

lakebase_endpoint = f"{branch}/endpoints/primary"
lakebase_host = w.postgres.get_endpoint(name=lakebase_endpoint).status.hosts.host

result = workshop.check(
    "07_app",
    spark=spark,  # enables source-count parity
    catalog=config.catalog,
    schema=config.schema,
    apps=w,
    app_name=app_name,
    synced_table=synced_table,
    owner=me,  # required — binds the app AND synced table to YOU
    lakebase_endpoint=lakebase_endpoint,  # so served rows are verified (fail-closed)
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
# MAGIC - Switch the sync to **Triggered** (enable Change Data Feed on the gold table)
# MAGIC   so the app sees scheduled fresh data.
# MAGIC - Add a second serving screen over `gold_sales`.
# MAGIC - For another domain, sync that gold serving table and pass `source_table=`,
# MAGIC   `primary_key_columns=`, `synced_table=`, and `app_name=` to `workshop.check`.
