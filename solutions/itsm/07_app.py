# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Data app over a Lakebase synced table — SOLUTION (ITSM)
# MAGIC
# MAGIC **Gated reference solution.** Ships the provided Streamlit app (`app/`) wired
# MAGIC to a per-participant **Genie agent** (#11) and a **Lakebase synced table**
# MAGIC created from `gold_service_performance` (#8). It shows the complete code for
# MAGIC the two participant gaps in `app/backend.py`, the Lakebase + app lifecycle
# MAGIC commands, and the `07_app` checkpoint. No catalog and no second schema are
# MAGIC created; the Lakebase project + synced table + app are all per-participant.
# MAGIC
# MAGIC **Prerequisite:** Lakebase (Autoscaling Postgres) enabled; `03_gold` and
# MAGIC `06_genie` complete. On Free Edition, sync **one** denormalized serving table.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install dependencies
# MAGIC
# MAGIC This cell upgrades `databricks-sdk` (for the `databricks.sdk.service.postgres`
# MAGIC Lakebase module used to create the synced table) and installs `psycopg` (the
# MAGIC Postgres driver the `07_app` checkpoint uses to verify served rows) — the
# MAGIC serverless-default kernel has neither. Installing does not restart the kernel
# MAGIC on its own, so the next cell calls `dbutils.library.restartPython()` to make
# MAGIC the packages importable; the bootstrap cell then runs fresh.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "psycopg[binary]" "databricks-sdk>=0.135"

# COMMAND ----------

# On serverless / recent runtimes, %pip does not auto-restart Python, so the freshly
# installed packages are not importable until the kernel restarts. Restart explicitly
# here — before any state is built — so the bootstrap cell below runs in the fresh kernel.
dbutils.library.restartPython()

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
dbutils.widgets.dropdown("domain", "itsm", ["itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("genie_space_id", "", "Genie space id (from 06_genie)")
dbutils.widgets.text("lakebase_project", "", "Lakebase project — reuse the one from 01_bronze_txn (required)")

# COMMAND ----------

# Your identity resolves the SAME per-participant workshop_<you> schema 00_setup
# created, and your namespace — the one source of truth for every unique name in
# the shared workspace (app, Lakebase project, synced table).
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)

ns = workshop.namespace(me, domain=config.domain)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Per-participant names (identity-derived)
# MAGIC
# MAGIC The app, Lakebase project, and synced table are workspace-scoped, so each
# MAGIC name carries an identity suffix — like the `06_genie` agent name.

# COMMAND ----------

# The app and synced-table names come from your namespace, so the checkpoint
# (below, via namespace=ns) resolves the SAME names. App names allow [a-z0-9-]
# (<=30); the digest is always kept, so uniqueness survives the length limit. The
# Lakebase project is bring-your-own (below), not namespace-derived.
app_name = ns.app_name()

# Bring-your-own Lakebase project: reuse the SAME project you created for
# 01_bronze_txn (supplied via the widget). 07_app does NOT create a project — its
# synced serving table lands there as a DISTINCT table, alongside (not colliding
# with) 01_bronze_txn's CDF history table (different table, different Postgres schema).
project_id = dbutils.widgets.get("lakebase_project") or None
if not project_id:
    raise RuntimeError(
        "Set the 'lakebase_project' widget to the Lakebase project you created in "
        "01_bronze_txn (Compute -> Lakebase). 07_app reuses that project; it does not "
        "create one. If you used 01_bronze_txn's synthesized path and have no project, "
        "create one first (Compute -> Lakebase, or 'databricks postgres create-project')."
    )
branch = f"projects/{project_id}/branches/production"
gold_serving = f"{config.catalog}.{config.schema}.gold_service_performance"

# The synced table lands in YOUR existing catalog + schema — no catalog is
# created, and none is registered. The synced-table id `<catalog>.<schema>.<table>`
# doubles as a Unity Catalog virtual table AND a Postgres table `<table>` in
# schema `<schema>`, so the app reads `<schema>.<table>` from Postgres directly.
synced_table = ns.synced_table_fqn(config.catalog, config.schema, base="gold_service_performance_served")
target_table = ns.synced_table_name(base="gold_service_performance_served")
serving_table = f"{config.schema}.{target_table}"  # the app's SERVING_TABLE (Postgres name)

print(f"me             : {me}")
print(f"app_name       : {app_name}")
print(f"project_id     : {project_id}")
print(f"synced_table   : {synced_table}")
print(f"serving_table  : {serving_table}")
print(f"gold_serving   : {gold_serving}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Add your synced serving table to your 01_bronze_txn Lakebase project
# MAGIC
# MAGIC Everything here stays in the Databricks workspace — no terminal needed.
# MAGIC **Reuse the Lakebase project you created for `01_bronze_txn`** — 07_app does
# MAGIC not create one. Need a refresher on creating the project? Go back to
# MAGIC `01_bronze_txn`, which walks through it in the UI (Compute → Lakebase). Then
# MAGIC run the cell below to create the **synced table** in-notebook with the SDK. It
# MAGIC lands straight into your **existing** catalog/schema — there is **no catalog to
# MAGIC create or register** — as a **distinct table** in that same project, alongside
# MAGIC 01_bronze_txn's CDF history table (they don't collide — different table, and a
# MAGIC different Postgres schema). Snapshot mode is simplest on Free Edition;
# MAGIC Triggered/Continuous need Change Data Feed on the gold table.

# COMMAND ----------

# MAGIC %md
# MAGIC Create the synced table in-notebook via the SDK, then poll until it is ONLINE:

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
            primary_key_columns=["incident_id"],
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
# MAGIC ## 4. Deploy the app and wire its resources (Databricks UI)
# MAGIC
# MAGIC Do all of this in the workspace — no terminal. **Deploying an app starts it
# MAGIC automatically**, so there is no separate start step. The `app/` folder already
# MAGIC lives in your cloned workshop repo, so you deploy straight from it.
# MAGIC
# MAGIC 1. **Create** — app switcher (top-left grid) → **Databricks Apps** →
# MAGIC    **+ Create app** → **Create a custom app**. Name it the `app_name` printed
# MAGIC    below (the name is immutable), then **Create app**.
# MAGIC 2. **Add resources** (in the Configure step, or later via **Edit → App
# MAGIC    resources**):
# MAGIC    - **+ Add resource → Genie Agent** → pick your `06_genie` space →
# MAGIC      permission **Can run** (resource key `genie-space`; this fills the app's
# MAGIC      `GENIE_SPACE_ID`).
# MAGIC    - **+ Add resource → Database** → pick your `01_bronze_txn` Lakebase
# MAGIC      project, its `production` branch, and `databricks_postgres` → permission
# MAGIC      **Can connect and create** (key `postgres`; injects
# MAGIC      `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` + `LAKEBASE_ENDPOINT`).
# MAGIC    - Set the env var **`SERVING_TABLE`** to your synced table's Postgres name
# MAGIC      (the `serving_table` printed below) — edit `app/app.yaml` or set it in
# MAGIC      the app's config.
# MAGIC 3. **Deploy** — on the app page click **Deploy**, choose the **`app/` folder in
# MAGIC    your cloned workshop repo** in the folder picker, then **Deploy**. The app
# MAGIC    builds, starts on its own, and its URL becomes clickable.
# MAGIC 4. **Grant read access** — wiring the database resource gives the app's service
# MAGIC    principal a Postgres role with connect/create, but **not** read access, so
# MAGIC    you grant `SELECT` yourself (next cell). Do this **after** the first deploy,
# MAGIC    which is what creates the service principal's Postgres role.

# COMMAND ----------

print(f"""# Plug these per-participant values into the Apps UI:
#   App name         : {app_name}                 (Create a custom app → this name)
#   Genie space id   : {dbutils.widgets.get("genie_space_id") or "your 06_genie space id"}   (resource: Genie Agent, Can run)
#   Lakebase project : {project_id}                (resource: Database, Can connect and create)
#   SERVING_TABLE    : {serving_table}
#   Deploy source    : the app/ folder in your cloned workshop repo

# After the first deploy, grant the app's service principal read access to the
# synced table. Do it in the UI: app switcher → Lakebase Postgres → your project →
# SQL Editor (as a Lakebase superuser). The synced table lands in Postgres schema
# "{config.schema}" (= your UC schema):
#   GRANT USAGE ON SCHEMA "{config.schema}" TO "<app_sp_client_id>";
#   GRANT SELECT ON ALL TABLES IN SCHEMA "{config.schema}" TO "<app_sp_client_id>";
# Find <app_sp_client_id> on the app's Authorization tab (it is also the app's PGUSER).
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `07_app`
# MAGIC
# MAGIC Reads only observable state: your synced table exists, syncs from **your**
# MAGIC `gold_service_performance` on `service`, is **owned by you**, is online,
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
    namespace=ns,  # derives your app name, synced-table name, and owner (one source)
    lakebase_endpoint=lakebase_endpoint,  # so served rows are verified (fail-closed)
    lakebase_host=lakebase_host,
    lakebase_user=me,
    lakebase_database="databricks_postgres",
    serving_base="gold_service_performance_served",
    source_table="gold_service_performance",
    primary_key_columns=("incident_id",),
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch
# MAGIC
# MAGIC - Switch the sync to **Triggered** (enable Change Data Feed on the gold table)
# MAGIC   so the app sees scheduled fresh data.
# MAGIC - Add a second serving screen over `gold_incidents`.
# MAGIC - For another domain, sync that gold serving table and pass `source_table=`,
# MAGIC   `primary_key_columns=`, `synced_table=`, and `app_name=` to `workshop.check`.
