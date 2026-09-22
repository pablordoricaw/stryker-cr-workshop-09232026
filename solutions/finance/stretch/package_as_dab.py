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
# MAGIC ├── foundation/      # schema + UC Volume            (platform lifecycle)
# MAGIC ├── pipeline/        # medallion Lakeflow Job         (data-engineering lifecycle)
# MAGIC └── app/             # Databricks App                 (product lifecycle)
# MAGIC ```
# MAGIC
# MAGIC The headline decision: **three independently-deployable bundles, not one
# MAGIC monolith.** A monolith couples resources with unrelated lifecycles under a
# MAGIC single `deploy`/`destroy`, so an app redeploy re-plans your schema and an
# MAGIC app teardown can drop it. The split groups by what changes together, who
# MAGIC owns it, and how often it deploys — see the bundle-set README for the full
# MAGIC reasoning and the cross-bundle reference model.

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
app_source_path = f"/Workspace/Users/{me}/stryker-cr-workshop/app"

print(f"Example bundle set : {bundle_root}")
print("Pass these to every bundle as --var:")
print(f"  catalog={config.catalog}   (existing — never created)")
print(f"  schema={config.schema}")
print(f"  volume={config.volume}")
print(f"  app_name={ns.app_name()}")
print(f"  notebooks_root={notebooks_root}")
print(f"  app_source_path={app_source_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Validate all three bundles offline
# MAGIC
# MAGIC Each bundle validates on its own. Run these in a terminal from the bundle
# MAGIC set directory (they pass offline with `--strict`):
# MAGIC
# MAGIC ```bash
# MAGIC cd solutions/finance/stretch/package_as_dab_bundle
# MAGIC for b in foundation pipeline app; do
# MAGIC   echo "== $b =="; (cd "$b" && databricks bundle validate --strict --profile <p>)
# MAGIC done
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Deploy in order (foundation → pipeline → app)
# MAGIC
# MAGIC Deploy order is the only cross-bundle dependency; there is no in-bundle
# MAGIC handle between the bundles — they agree by shared `--var catalog`/`schema`.
# MAGIC
# MAGIC ```bash
# MAGIC CATALOG=<your_existing_catalog>; SCHEMA=<workshop_you>; APPNAME=<your_app_name>; P=--profile <p>
# MAGIC
# MAGIC (cd foundation && databricks bundle deploy --var catalog=$CATALOG --var schema=$SCHEMA $P)
# MAGIC
# MAGIC (cd pipeline && databricks bundle deploy --var catalog=$CATALOG --var schema=$SCHEMA \
# MAGIC     --var notebooks_root=/Workspace/Users/<you>/stryker-cr-workshop/notebooks $P \
# MAGIC   && databricks bundle run medallion_build $P)
# MAGIC
# MAGIC # (create the Genie agent [06] and Lakebase synced table [07] out-of-band —
# MAGIC #  they are not DAB resources.)
# MAGIC
# MAGIC (cd app && databricks bundle deploy --var app_name=$APPNAME \
# MAGIC     --var app_source_path=/Workspace/Users/<you>/stryker-cr-workshop/app $P \
# MAGIC   && databricks apps start $APPNAME $P)
# MAGIC ```
# MAGIC
# MAGIC No `workshop.check` for this stretch — a clean `bundle validate --strict` on
# MAGIC all three bundles (and, if you deploy, a green pipeline run + a running app)
# MAGIC is the bar. The full rationale and runbook live in the bundle-set README.
