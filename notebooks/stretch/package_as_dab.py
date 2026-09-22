# Databricks notebook source
# ruff: noqa: F821
# MAGIC %md
# MAGIC # 🚀 Stretch · Package your work as a DAB (Finance gap)
# MAGIC
# MAGIC **Optional Tier-3 module.** Your workshop is already complete without it.
# MAGIC
# MAGIC The Finance team ships pipelines and apps by hand. A **Databricks Asset
# MAGIC Bundle (DAB)** versions the provided infrastructure and app as
# MAGIC source-controlled YAML, so the whole thing is reviewable, re-runnable, and
# MAGIC promotable between workspaces. This module has you package the work you
# MAGIC already built — but **not as one monolithic bundle**.
# MAGIC
# MAGIC **Split it into three independently-deployable bundles**, grouped by
# MAGIC lifecycle / ownership / deploy cadence:
# MAGIC
# MAGIC | Bundle | Owns | Deploys |
# MAGIC | ------ | ---- | ------- |
# MAGIC | `foundation` | schema + UC Volume | once, up front (widest blast radius) |
# MAGIC | `pipeline` | the medallion Lakeflow Job (bronze→gold→metadata→metrics) | on the DE cadence |
# MAGIC | `app` | the Databricks App | many times a day (smallest blast radius) |
# MAGIC
# MAGIC The **why** (coupling/decoupling tradeoffs, cross-bundle references, deploy
# MAGIC order) is the point of this module — read
# MAGIC `solutions/finance/stretch/package_as_dab_bundle/README.md`.
# MAGIC
# MAGIC > This module uses the Databricks CLI (`databricks bundle …`), which needs a
# MAGIC > terminal or local machine — the one Tier-3 module that steps outside the
# MAGIC > pure Workspace-UI flow, because a DAB *is* a source-control/CLI artifact.

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ Two rules carry over from the core path
# MAGIC
# MAGIC - **Bring your own catalog.** No bundle here runs `CREATE CATALOG`; the
# MAGIC   `catalog` variable names your **existing** catalog and the bundles define
# MAGIC   only the schema, volume, job, and app inside it.
# MAGIC - **Per-participant names.** The `schema` and `app_name` variables default
# MAGIC   to placeholders; you pass your identity-derived names (printed below) as
# MAGIC   `--var`, so your bundle set never collides with a teammate's.

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
# MAGIC ## 1. Your per-participant bundle variables
# MAGIC
# MAGIC The same identity-derived names your other notebooks use. Pass these as
# MAGIC `--var` to every bundle so all three agree on where your objects live.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)
ns = workshop.namespace(me, domain=config.domain)

print("Pass these to every bundle as --var:")
print(f"  --var catalog={config.catalog}   (existing — never created)")
print(f"  --var schema={config.schema}")
print(f"  --var volume={config.volume}")
print(f"  --var app_name={ns.app_name()}")
print(f"  notebooks_root: /Workspace/Users/{me}/stryker-cr-workshop/notebooks")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Author the `foundation` bundle (schema + UC Volume)
# MAGIC
# MAGIC In your cloned Git folder, create `foundation/databricks.yml` (with a
# MAGIC `catalog`/`schema`/`volume` variable block and dev/prod targets) plus
# MAGIC `foundation/resources/schema.schema.yml` and
# MAGIC `foundation/resources/volume.volume.yml`. This is the substrate every other
# MAGIC bundle references **by name**.

# COMMAND ----------

# TODO: Create the foundation bundle files (databricks.yml + resources/). It must
# TODO: define ONLY a schema and volume inside ${var.catalog} — no catalogs:
# TODO: resource. Do NOT set `mode: development` (it prefixes names with illegal
# TODO: UC characters). Then, in a terminal:
# TODO:   cd foundation && databricks bundle validate --strict


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — foundation resource skeleton</summary>
# MAGIC
# MAGIC ```yaml
# MAGIC # resources/schema.schema.yml
# MAGIC resources:
# MAGIC   schemas:
# MAGIC     workshop_schema:
# MAGIC       catalog_name: ${var.catalog}   # EXISTING catalog — not created
# MAGIC       name: ${var.schema}
# MAGIC # resources/volume.volume.yml — schema_name references the schema RESOURCE
# MAGIC # (${resources.schemas.workshop_schema.name}) so the volume waits for it.
# MAGIC ```
# MAGIC
# MAGIC The complete, validated files are in
# MAGIC `solutions/finance/stretch/package_as_dab_bundle/foundation/`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Author the `pipeline` bundle (medallion Lakeflow Job)
# MAGIC
# MAGIC A serverless Lakeflow Job whose tasks run your build notebooks
# MAGIC (`01_bronze_*` → `02_silver_docs` → `03_gold` → `04_metadata` →
# MAGIC `05_metric_views`) by **workspace path** — so the bundle carries no copy of
# MAGIC them to drift. UC Metric Views are not a DAB resource type, so they ride
# MAGIC this job (the `metric_views` task) rather than a bundle of their own.

# COMMAND ----------

# TODO: Create pipeline/databricks.yml (catalog/schema/volume/domain/notebooks_root
# TODO: variables) and pipeline/resources/medallion.job.yml — one serverless
# TODO: notebook_task per build notebook, wired with depends_on to mirror the
# TODO: medallion DAG, each passing catalog/domain/schema/volume as base_parameters.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — one serverless notebook task</summary>
# MAGIC
# MAGIC ```yaml
# MAGIC tasks:
# MAGIC   - task_key: gold
# MAGIC     depends_on:
# MAGIC       - task_key: silver_docs
# MAGIC       - task_key: bronze_txn
# MAGIC     notebook_task:
# MAGIC       notebook_path: ${var.notebooks_root}/03_gold.py   # absolute workspace path
# MAGIC       base_parameters: {catalog: ${var.catalog}, domain: ${var.domain},
# MAGIC                         schema: ${var.schema}, volume: ${var.volume}}
# MAGIC ```
# MAGIC
# MAGIC No `new_cluster`/`job_cluster_key` → serverless. The complete job is in
# MAGIC `solutions/finance/stretch/package_as_dab_bundle/pipeline/`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Author the `app` bundle (Databricks App)
# MAGIC
# MAGIC The App deploys independently of the data. Its Genie agent (`06_genie`) and
# MAGIC Lakebase synced table (`07_app`) are **not** DAB resources — the app reaches
# MAGIC them through its `genie-space` and `postgres` app resources (added in the
# MAGIC Apps UI), referenced by key rather than owned by the bundle.

# COMMAND ----------

# TODO: Create app/databricks.yml (app_name + app_source_path variables) and
# TODO: app/resources/data_app.app.yml with name: ${var.app_name} and
# TODO: source_code_path: ${var.app_source_path}. No `mode: development` — the
# TODO: app name must match what the `07_app` checkpoint expects.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — app resource + deploy order</summary>
# MAGIC
# MAGIC ```yaml
# MAGIC # resources/data_app.app.yml
# MAGIC resources:
# MAGIC   apps:
# MAGIC     data_app:
# MAGIC       name: ${var.app_name}
# MAGIC       source_code_path: ${var.app_source_path}   # /Workspace/Users/<you>/.../app
# MAGIC ```
# MAGIC
# MAGIC Deploy order is the only cross-bundle "dependency": **foundation → pipeline
# MAGIC (→ run) → app**. There is no in-bundle handle between them — they agree by
# MAGIC shared `--var catalog`/`schema`. The full runbook + the *why* are in
# MAGIC `solutions/finance/stretch/package_as_dab_bundle/README.md`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Validate (and optionally deploy)
# MAGIC
# MAGIC From a terminal, validate each bundle on its own — all three should pass
# MAGIC offline:
# MAGIC
# MAGIC ```bash
# MAGIC for b in foundation pipeline app; do (cd $b && databricks bundle validate --strict); done
# MAGIC ```
# MAGIC
# MAGIC To deploy, follow the ordered runbook in the gated solution's README
# MAGIC (foundation → pipeline → run → app). There is **no `workshop.check` for this
# MAGIC stretch** — a clean `bundle validate --strict` on all three bundles is your
# MAGIC green.
