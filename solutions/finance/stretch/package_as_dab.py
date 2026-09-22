# Databricks notebook source
# ruff: noqa: F821
# MAGIC %md
# MAGIC # 🚀 Stretch · Package your work as a DAB — SOLUTION (Finance)
# MAGIC
# MAGIC The gated solution for the "package your work as a DAB" stretch. The
# MAGIC complete, validated artifact is the **bundle set** next to this notebook:
# MAGIC
# MAGIC ```
# MAGIC solutions/finance/stretch/package_as_dab_bundle/
# MAGIC ├── README.md        # the WHY: division rationale, tradeoffs, deploy runbook
# MAGIC ├── pipeline/        # medallion Lakeflow Job         (data-engineering lifecycle)
# MAGIC └── app/             # Databricks App, bundle-local source (product lifecycle)
# MAGIC ```
# MAGIC
# MAGIC Two headline decisions:
# MAGIC
# MAGIC 1. **Two independently-deployable bundles, not one monolith.** A monolith
# MAGIC    couples resources with unrelated lifecycles under a single
# MAGIC    `deploy`/`destroy`, so an app teardown can drop the pipeline job. The
# MAGIC    split groups by what changes together, who owns it, and how often it
# MAGIC    deploys.
# MAGIC 2. **Package the built work, not the provisioning.** Your schema + UC Volume
# MAGIC    were created by `00_setup` (the notebook path), so neither bundle declares
# MAGIC    a schema/volume resource — they **target** the existing `catalog.schema`
# MAGIC    by variable. That is what makes the runbook deployable without colliding
# MAGIC    with pre-existing UC objects. Never `CREATE CATALOG`.
# MAGIC
# MAGIC See the bundle-set README for the full reasoning and the cross-bundle
# MAGIC reference model.

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

bundle_root = os.path.join(_root, "solutions", "finance", "stretch", "package_as_dab_bundle")
notebooks_root = f"/Workspace/Users/{me}/stryker-cr-workshop/notebooks"

print(f"Example bundle set : {bundle_root}")
print("pipeline --var:")
print(f"  catalog={config.catalog}   (existing — provisioned by 00_setup, never created)")
print(f"  schema={config.schema}     (provisioned by 00_setup)")
print(f"  volume={config.volume}")
print(f"  notebooks_root={notebooks_root}")
print("app --var:")
print(f"  app_name={ns.app_name()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Validate both bundles offline
# MAGIC
# MAGIC Each bundle validates on its own. Run these in a terminal from the bundle
# MAGIC set directory (they pass offline with `--strict`):
# MAGIC
# MAGIC ```bash
# MAGIC cd solutions/finance/stretch/package_as_dab_bundle
# MAGIC for b in pipeline app; do
# MAGIC   echo "== $b =="; (cd "$b" && databricks bundle validate --strict --profile "$PROFILE")
# MAGIC done
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Deploy in order (pipeline → run → app)
# MAGIC
# MAGIC Deploy order is the only cross-bundle dependency; there is no in-bundle
# MAGIC handle between the bundles — they agree by shared `--var catalog`/`schema`
# MAGIC and by the gold table name. Neither bundle creates the schema/volume
# MAGIC `00_setup` provisioned, so nothing collides.
# MAGIC
# MAGIC ```bash
# MAGIC CATALOG=your_existing_catalog; SCHEMA=workshop_you; APPNAME=your_app_name; PROFILE=your-profile
# MAGIC
# MAGIC (cd pipeline && databricks bundle deploy --var catalog="$CATALOG" --var schema="$SCHEMA" \
# MAGIC     --var notebooks_root=/Workspace/Users/you/stryker-cr-workshop/notebooks --profile "$PROFILE" \
# MAGIC   && databricks bundle run medallion_build --profile "$PROFILE")
# MAGIC
# MAGIC # (create the Genie agent [06] and Lakebase synced table [07] out-of-band —
# MAGIC #  they are not DAB resources.)
# MAGIC
# MAGIC (cd app && databricks bundle deploy --var app_name="$APPNAME" --profile "$PROFILE" \
# MAGIC   && databricks apps start "$APPNAME" --profile "$PROFILE")
# MAGIC ```
# MAGIC
# MAGIC No `workshop.check` for this stretch — a clean `bundle validate --strict` on
# MAGIC both bundles (and, if you deploy, a green pipeline run + a running app) is
# MAGIC the bar. The full rationale and runbook live in the bundle-set README.
