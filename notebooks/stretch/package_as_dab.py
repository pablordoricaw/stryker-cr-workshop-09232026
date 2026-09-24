# Databricks notebook source
# MAGIC %md
# MAGIC # 🚀 Stretch · Package your work as a DAB
# MAGIC
# MAGIC **Optional Tier-3 module.** Your workshop is already complete without it.
# MAGIC
# MAGIC Your team (Finance, Security, or ITSM) ships pipelines and apps by hand.
# MAGIC A **Databricks Asset Bundle (DAB)** versions your **built work** as
# MAGIC source-controlled YAML, so it is reviewable, re-runnable, and promotable
# MAGIC between workspaces. This module has you package what you built, **not as one
# MAGIC monolithic bundle**.
# MAGIC
# MAGIC **Package the built work as two independently-deployable bundles**, grouped
# MAGIC by lifecycle / ownership / deploy cadence:
# MAGIC
# MAGIC | Bundle | Owns | Deploys |
# MAGIC | ------ | ---- | ------- |
# MAGIC | `pipeline` | the medallion Lakeflow Job (bronze→gold→metadata→metrics) | on the DE cadence |
# MAGIC | `app` | the Databricks App | many times a day (smallest blast radius) |
# MAGIC
# MAGIC **What you do NOT package: your schema + UC Volume.** `00_setup` already
# MAGIC provisioned those (the notebook path). Both bundles **target** that existing
# MAGIC `catalog.schema` by variable and declare **no** schema/volume resource, so a
# MAGIC `bundle deploy` never collides with what `00_setup` created. Never
# MAGIC `CREATE CATALOG`.
# MAGIC
# MAGIC The **why** (coupling/decoupling tradeoffs, cross-bundle references, deploy
# MAGIC order) is the point of this module. Read
# MAGIC `solutions/finance/stretch/package_as_dab_bundle/README.md`.
# MAGIC
# MAGIC > This module uses the Databricks CLI (`databricks bundle …`), which needs a
# MAGIC > terminal or local machine, the one Tier-3 module that steps outside the
# MAGIC > pure Workspace-UI flow, because a DAB *is* a source-control/CLI artifact.

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
# MAGIC The same identity-derived names your other notebooks use. Pass `catalog` and
# MAGIC `schema` (the ones `00_setup` provisioned) to the pipeline, and `app_name`
# MAGIC to the app.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog, required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# COMMAND ----------

me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)
ns = workshop.namespace(me, domain=config.domain)

print("pipeline bundle --var:")
print(f"  --var catalog={config.catalog}   (existing, provisioned by 00_setup, never created)")
print(f"  --var schema={config.schema}     (provisioned by 00_setup)")
print(f"  --var volume={config.volume}")
print(f"  --var notebooks_root=/Workspace/Users/{me}/stryker-cr-workshop/notebooks")
print("app bundle --var:")
print(f"  --var app_name={ns.app_name()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Author the `pipeline` bundle (medallion Lakeflow Job)
# MAGIC
# MAGIC A serverless Lakeflow Job whose tasks run your build notebooks
# MAGIC (`01_bronze_*` → `02_silver_docs` → `03_gold` → `04_metadata` →
# MAGIC `05_metric_views`) by **workspace path**, so the bundle carries no copy of
# MAGIC them to drift. It **targets** your existing `catalog.schema` (declare no
# MAGIC schema/volume resource). UC Metric Views are not a DAB resource type, so
# MAGIC they ride this job (the `metric_views` task) rather than a bundle of their
# MAGIC own.

# COMMAND ----------

# TODO: Create pipeline/databricks.yml (catalog/schema/volume/domain/notebooks_root
# TODO: variables) and pipeline/resources/medallion.job.yml, one serverless
# TODO: notebook_task per build notebook, wired with depends_on to mirror the
# TODO: medallion DAG, each passing catalog/domain/schema/volume as base_parameters.
# TODO: Declare NO schemas:/volumes: resources, because 00_setup already made those.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint: one serverless notebook task

# COMMAND ----------

# MAGIC %md
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

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Author the `app` bundle (self-contained Databricks App)
# MAGIC
# MAGIC The App deploys independently of the data, and must ship its **own source**
# MAGIC (`bundle deploy` uploads it), not point at a pre-existing Workspace path.
# MAGIC Use `sync.paths` to scope the bundle's sync root to your repo's `app/`, then
# MAGIC point `source_code_path` at it. The app's Genie agent (`06_genie`) and
# MAGIC Lakebase synced table (`07_app`) are **not** DAB resources. The app reaches
# MAGIC them through its `genie-space` and `postgres` app resources (added in the
# MAGIC Apps UI), referenced by key rather than owned by the bundle.

# COMMAND ----------

# TODO: Create app/databricks.yml with an `app_name` variable, a `sync: {paths: [app]}`
# TODO: block scoping the sync root to your repo's app/, and no schema/volume
# TODO: resource. In app/resources/data_app.app.yml set name: ${var.app_name} and
# TODO: source_code_path to that bundle-local app source. No `mode: development`, since
# TODO: the app name must match what the `07_app` checkpoint expects.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint: bundle-local app source + deploy order

# COMMAND ----------

# MAGIC %md
# MAGIC ```yaml
# MAGIC # app/databricks.yml (at your repo root)
# MAGIC sync:
# MAGIC   paths: [app]            # ship the repo's app/ as this bundle's source
# MAGIC # app/resources/data_app.app.yml
# MAGIC resources:
# MAGIC   apps:
# MAGIC     data_app:
# MAGIC       name: ${var.app_name}
# MAGIC       source_code_path: app   # LOCAL path uploaded on deploy, not /Workspace/...
# MAGIC ```
# MAGIC
# MAGIC Deploy order is the only cross-bundle "dependency": **pipeline (→ run) →
# MAGIC app**. There is no in-bundle handle between them, so they agree by shared
# MAGIC `--var catalog`/`schema` and by the gold table name. The full runbook + the
# MAGIC *why* are in `solutions/finance/stretch/package_as_dab_bundle/README.md`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Validate (and optionally deploy)
# MAGIC
# MAGIC From a terminal, validate each bundle on its own, and both should pass offline:
# MAGIC
# MAGIC ```bash
# MAGIC for b in pipeline app; do (cd $b && databricks bundle validate --strict); done
# MAGIC ```
# MAGIC
# MAGIC To deploy, follow the ordered runbook in the gated solution's README
# MAGIC (pipeline → run → app). There is **no `workshop.check` for this stretch**. A
# MAGIC clean `bundle validate --strict` on both bundles is your green.
