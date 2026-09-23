# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Governed Metric Views
# MAGIC
# MAGIC Define your domain's reusable business metrics over the gold layer. You will
# MAGIC create two Unity Catalog Metric Views in your existing workshop schema — one
# MAGIC over the transaction-grain detail table and one over the business-key mart.
# MAGIC Their names differ per domain (Finance `finance_sales_metrics` /
# MAGIC `finance_contract_metrics`, Security `security_findings_metrics` /
# MAGIC `security_cve_metrics`, ITSM `itsm_incident_metrics` /
# MAGIC `itsm_service_metrics`) and are derived for you below.
# MAGIC
# MAGIC Metric Views are YAML semantic models, not copied tables. They keep one
# MAGIC governed definition of each KPI for SQL, AI/BI, and Genie. Run `03_gold`
# MAGIC first. This notebook never creates a catalog or a second schema.
# MAGIC
# MAGIC **Compute requirement:** `WITH METRICS ... version: 1.1` needs DBR 17.2+
# MAGIC and `DESCRIBE ... AS JSON` needs DBR 16.2+, so use DBR 17.2+ overall.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

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
# MAGIC ## 1. Use your existing workshop schema
# MAGIC
# MAGIC This cell is done for you: it derives your domain's two gold source tables
# MAGIC and the two Metric View names, and prints the exact dimensions and measures
# MAGIC each view must expose (the `05_metrics` checkpoint asserts them).

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# COMMAND ----------

# Your identity gives you a unique schema in the shared team catalog
# (workshop_<you>) — the same one 00_setup created. Leave the schema blank to use it.
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)

# The single source of truth for this domain's metric-view names and contracts.
spec = workshop.domain_spec(config.domain)

# Resolve each view's fully-qualified name and its gold source table.
metric_view_fqns = {
    name: workshop.fully_qualified(config.catalog, config.schema, name)
    for name in spec.metric_views
}
source_fqns = {
    name: workshop.fully_qualified(config.catalog, config.schema, view.source_table)
    for name, view in spec.metric_views.items()
}

print(f"Domain: {config.domain}")
for name, view in spec.metric_views.items():
    print(f"\nMetric View: {metric_view_fqns[name]}")
    print(f"  source    : {source_fqns[name]}")
    print(f"  dimensions: {', '.join(view.dimensions)}")
    print(f"  measures  : {', '.join(view.measures)}")

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
# MAGIC ## 2. Create the detail-grain Metric View
# MAGIC
# MAGIC `MEASURE()` makes these YAML measures queryable at any selected dimension
# MAGIC grain. Build the **first** view above (over the gold detail table) with the
# MAGIC printed dimensions and measures. Compose a ratio measure (e.g. a margin or
# MAGIC average) with `MEASURE()` rather than repeating it in every dashboard.

# COMMAND ----------

# TODO: Create the first Metric View with `CREATE OR REPLACE VIEW ... WITH
# TODO: METRICS LANGUAGE YAML AS $$ ... $$`, sourced from its gold detail table
# TODO: and exposing exactly the dimensions and measures printed above. The exact
# TODO: YAML for your domain is in solutions/<domain>/05_metric_views.py.

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — metric-view YAML skeleton</summary>
# MAGIC
# MAGIC ```sql
# MAGIC CREATE OR REPLACE VIEW <metric_view_fqn>
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS $$
# MAGIC version: 1.1
# MAGIC source: "<gold_source_fqn>"
# MAGIC dimensions:
# MAGIC   - name: <Dimension Name>
# MAGIC     expr: <source_column>
# MAGIC measures:
# MAGIC   - name: <Measure Name>
# MAGIC     expr: SUM(<source_column>)
# MAGIC   # a composed ratio references atomic measures with MEASURE():
# MAGIC   # - name: <Ratio> ; expr: "MEASURE(`A`) / NULLIF(MEASURE(`B`), 0)"
# MAGIC $$
# MAGIC ```
# MAGIC
# MAGIC Use the fully-qualified names and the exact `name:` labels printed in cell 1
# MAGIC (the checkpoint matches on them). Define atomic measures before any composed
# MAGIC ratio. The full field set and expressions for your domain are in the gated
# MAGIC `solutions/<domain>/05_metric_views.py`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create the mart-grain Metric View

# COMMAND ----------

# TODO: Create the second Metric View over your domain's gold mart table, with
# TODO: the dimensions and measures printed above. Mart measures are usually
# TODO: SUM(...) over pre-aggregated columns; see solutions/<domain>/05_metric_views.py.

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — mart KPI pattern</summary>
# MAGIC
# MAGIC Source the second view from your gold **mart** table. Use `SUM(...)` for
# MAGIC additive totals (including pre-aggregated counts like a per-key
# MAGIC transaction/finding/incident count) and compose any ratio from atomic
# MAGIC measures with `MEASURE()`. Exact expressions are in the gated solution.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Query the governed metrics
# MAGIC
# MAGIC Dimensions are regular quoted columns; measures are available only through
# MAGIC `MEASURE()`. Use `GROUP BY ALL` when selecting dimensions.

# COMMAND ----------

# TODO: Run a query against one of your views, e.g.:
# TODO: SELECT `<Dimension>`, MEASURE(`<Measure>`) AS m
# TODO: FROM <metric_view_fqn> GROUP BY ALL ORDER BY m DESC
# TODO: (use a real dimension/measure from the list printed in cell 1)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `05_metrics`

# MAGIC The check reads the UC Metric View definitions and queries each view. It
# MAGIC fails if either view is absent, its required dimensions/measures or source
# MAGIC are wrong, or its aggregate result is empty/null. Your domain's view
# MAGIC contracts (name, source, dimensions, measures) are passed to the shared
# MAGIC checkpoint from the spec.

# COMMAND ----------

result = workshop.check(
    "05_metrics",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    metric_views=spec.metric_view_contracts(),
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — add your own governed metric
# MAGIC
# MAGIC Add a third Metric View in this same schema for a question your domain asks
# MAGIC often. Choose dimensions with useful cardinality, define atomic measures
# MAGIC first, then compose a ratio with `MEASURE()` if needed. Query it with
# MAGIC `MEASURE()` and `GROUP BY ALL`. To validate it too, pass an extended
# MAGIC `metric_views={...}` contract to `workshop.check`.
