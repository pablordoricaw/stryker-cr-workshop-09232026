# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Data app over a Lakebase synced table
# MAGIC
# MAGIC Ship the **provided FastAPI app** (`app/`) wired to two things you already
# MAGIC built: your **Genie agent** (`06_genie`) and a **Lakebase synced table**
# MAGIC created from one of your gold tables (`03_gold`). The app is complete except
# MAGIC for **two gaps** you fill in `app/backend.py` — the Genie connection and the
# MAGIC Lakebase read.
# MAGIC
# MAGIC The gold serving table and its primary key differ per domain (Finance
# MAGIC `gold_contract_performance` on `contract_id`, Security `gold_cve_exposure` on
# MAGIC `cve_id`, ITSM `gold_service_performance` on `incident_id`) and are derived
# MAGIC for you below.
# MAGIC
# MAGIC Everything lands in **your existing catalog / schema** and a **per-participant
# MAGIC Lakebase project** — no catalog is created, and no second schema.
# MAGIC
# MAGIC You will:
# MAGIC 1. create a per-participant **Lakebase project**;
# MAGIC 2. create a **synced table** from your gold serving table into your existing catalog/schema;
# MAGIC 3. **deploy and start** the app (Apps UI or CLI) with its Genie + Lakebase resources;
# MAGIC 4. fill the **two gaps** in `app/backend.py`; and
# MAGIC 5. pass the **`07_app`** checkpoint.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

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
# MAGIC This cell derives your domain's gold serving table, primary key, and
# MAGIC serving-table base from the domain spec.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# Your identity resolves the SAME per-participant schema 00_setup created, and
# your namespace — the one source of truth for every unique name in the shared
# workspace (schema, Genie agent, app, Lakebase project, synced table).
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)

ns = workshop.namespace(me, domain=config.domain)

# The single source of truth for this domain's gold serving table + primary key.
spec = workshop.domain_spec(config.domain)
serving_base = spec.app_serving_base
primary_key = list(spec.app_primary_key)

# The gold serving table synced into Lakebase (one denormalized table).
gold_serving = workshop.fully_qualified(
    config.catalog, config.schema, spec.app_source_table
)

# Per-participant identifiers, all derived from your namespace so the checkpoint
# resolves the SAME names (pass namespace=ns). App names allow [a-z0-9-] (<=30);
# Lakebase project ids are RFC 1123 (<=63); the digest is always kept, so
# uniqueness survives the length limits.
app_name = ns.app_name()
project_id = ns.lakebase_project()
branch = f"projects/{project_id}/branches/production"

# The synced table lands in YOUR existing catalog + schema — no catalog is
# created. Its Unity Catalog id (`<catalog>.<schema>.<table>`) doubles as a
# Postgres table `<table>` in schema `<schema>`, so the app reads
# `<schema>.<table>` from Postgres directly — no Lakebase catalog to register.
# The serving-table base is domain-specific (from the spec).
synced_table = ns.synced_table_fqn(config.catalog, config.schema, base=serving_base)
target_table = ns.synced_table_name(base=serving_base)
serving_table = f"{config.schema}.{target_table}"  # the app's SERVING_TABLE (Postgres name)

print(f"Domain          : {config.domain}")
print(f"Signed in as    : {me}")
print(f"App name        : {app_name}")
print(f"Lakebase project: {project_id}")
print(f"Synced table    : {synced_table}")
print(f"App SERVING_TABLE: {serving_table}")
print(f"Gold source     : {gold_serving}   (primary key: {', '.join(primary_key)})")

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
# MAGIC ## 🚀 From-scratch mode (optional stretch)
# MAGIC
# MAGIC This stage ships in **guided** mode — the `# TODO` cells and collapsible
# MAGIC **💡 Hint**s below. Strong engineers can flip it to **from-scratch** mode:
# MAGIC treat every `# TODO` as **blank**, keep each **💡 Hint** collapsed, and build
# MAGIC to the **`workshop.check(...)` cell at the end** — it is identical in both
# MAGIC modes and is the only thing that grades you. Re-open a hint to drop back to
# MAGIC guided mode anytime; the checkpoint is unchanged. This is a **convention,
# MAGIC not a setting** — see [`docs/stretch/README.md`](../docs/stretch/README.md).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create your Lakebase synced table from the gold serving table
# MAGIC
# MAGIC Sync your gold serving table (one denormalized row per business key) into
# MAGIC Lakebase so the app reads it at low latency. Two steps: create a Lakebase
# MAGIC **project**, then create the **synced table** straight into your existing
# MAGIC catalog/schema. There is **no catalog to create or register** — the
# MAGIC synced-table id is a Unity Catalog name in *your own* catalog, and Lakebase
# MAGIC creates the matching Postgres table for you.
# MAGIC
# MAGIC <details>
# MAGIC <summary>Hint: create the project (CLI, run in a terminal)</summary>
# MAGIC
# MAGIC ```bash
# MAGIC databricks postgres create-project <project_id> \
# MAGIC   --json '{"spec": {"display_name": "<project_id>"}}' --profile <p>
# MAGIC ```
# MAGIC The project auto-creates a `production` branch + `primary` endpoint
# MAGIC (scale-to-zero). You do **not** run `databricks postgres create-catalog`.
# MAGIC </details>

# COMMAND ----------

# TODO: Create the Lakebase synced table from `gold_serving` into `synced_table`
# TODO: (your existing catalog/schema, already derived above), primary key
# TODO: `primary_key` (your domain's key). Snapshot mode is simplest on Free
# TODO: Edition. You can use the CLI or the SDK; the synced-table id is a UC name
# TODO: in YOUR catalog — there is no Lakebase catalog to create.
#
# SDK sketch (see solutions/<domain>/07_app.py for the complete, waited version):
#   from databricks.sdk import WorkspaceClient
#   from databricks.sdk.service.postgres import (
#       SyncedTable, SyncedTableSyncedTableSpec, NewPipelineSpec,
#       SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy as Policy,
#   )
#   w = WorkspaceClient()
#   w.postgres.create_synced_table(
#       synced_table_id=synced_table,
#       synced_table=SyncedTable(spec=SyncedTableSyncedTableSpec(
#           source_table_full_name=gold_serving,
#           primary_key_columns=primary_key, scheduling_policy=Policy.SNAPSHOT,
#           branch=branch, postgres_database="databricks_postgres",
#           create_database_objects_if_missing=True,
#           new_pipeline_spec=NewPipelineSpec(
#               storage_catalog=config.catalog, storage_schema=config.schema))),
#   ).wait()

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>Hint: create the synced table (CLI)</summary>
# MAGIC
# MAGIC ```bash
# MAGIC databricks postgres create-synced-table <catalog>.<schema>.<serving_base>_<suffix> \
# MAGIC   --json '{"spec": {
# MAGIC     "source_table_full_name": "<catalog>.<schema>.<gold_serving_table>",
# MAGIC     "primary_key_columns": ["<your_primary_key>"],
# MAGIC     "scheduling_policy": "SNAPSHOT",
# MAGIC     "branch": "projects/<project_id>/branches/production",
# MAGIC     "postgres_database": "databricks_postgres",
# MAGIC     "create_database_objects_if_missing": true,
# MAGIC     "new_pipeline_spec": {"storage_catalog": "<your_catalog>", "storage_schema": "<your_schema>"}
# MAGIC   }}' --profile <p>
# MAGIC ```
# MAGIC The synced-table id is a UC name **in your own catalog** — there is no
# MAGIC `create-catalog`. `storage_catalog` / `storage_schema` (DLT pipeline
# MAGIC metadata) are a **regular UC catalog/schema** — your existing ones are fine.
# MAGIC Use the concrete names printed in cell 1. Check status with
# MAGIC `databricks postgres get-synced-table "synced_tables/<synced_table>"` and
# MAGIC wait for it to be **online** before deploying.
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
# MAGIC *Can connect and create*). Set `SERVING_TABLE` to your synced table's
# MAGIC Postgres name — `<schema>.<table>`, the `serving_table` printed above
# MAGIC (e.g. `<your_schema>.<serving_base>_<suffix>`).
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
# MAGIC it (see solutions/<domain>/07_app.py).
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
# MAGIC The app is domain-agnostic — it selects from whatever `SERVING_TABLE` names,
# MAGIC so your domain's serving table works unchanged. Redeploy after editing. The
# MAGIC complete code is in `solutions/<domain>/07_app.py`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `07_app`
# MAGIC
# MAGIC The check reads only observable platform state: your **synced table** exists,
# MAGIC syncs from **your** gold serving table on your domain's primary key, is
# MAGIC **owned by you**, is **online**, and **serves rows**; and your **app** is
# MAGIC deployed, **owned by you**, and **running**. It fails (RED) if the synced
# MAGIC table is missing/someone else's/stale/empty or the app is
# MAGIC missing/someone else's/stopped.
# MAGIC
# MAGIC `namespace=ns` binds both resources to you — it derives your app name,
# MAGIC synced-table name, and owner from your identity (no adopting a teammate's).
# MAGIC Your domain's serving base, source table, and primary key are passed to the
# MAGIC shared checkpoint from the spec. The Lakebase connection hints let the check
# MAGIC read the served-row count — serving is verified fail-closed, so an
# MAGIC unverifiable/empty synced table stays RED.

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
    namespace=ns,  # derives your app name, synced-table name, and owner (one source)
    # Domain serving contract for the shared checkpoint.
    serving_base=serving_base,
    source_table=spec.app_source_table,
    primary_key_columns=primary_key,
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
# MAGIC - Add an `/api/ask` history panel, or a second serving screen over your
# MAGIC   domain's other gold table.
# MAGIC - Switch the sync to **Triggered** (enable Change Data Feed on the gold
# MAGIC   table first) so the app sees fresh data on a schedule.
# MAGIC - The `serving_base`, `source_table`, and `primary_key_columns` above already
# MAGIC   bind the checkpoint to your domain's serving table.
