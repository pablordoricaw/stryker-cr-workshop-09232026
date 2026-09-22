# Databricks notebook source
# ruff: noqa: F821
# MAGIC %md
# MAGIC # 05 · Governed Metric Views
# MAGIC
# MAGIC Define Finance's reusable business metrics over the gold layer. You will
# MAGIC create two Unity Catalog Metric Views in your existing workshop schema:
# MAGIC
# MAGIC - `finance_sales_metrics` — revenue and margin by product, region,
# MAGIC   customer type, and sale date; and
# MAGIC - `finance_contract_metrics` — contract-performance KPIs.
# MAGIC
# MAGIC Metric Views are YAML semantic models, not copied tables. They keep one
# MAGIC governed definition of each KPI for SQL, AI/BI, and Genie. Run `03_gold`
# MAGIC first. This notebook never creates a catalog or a second schema.
# MAGIC
# MAGIC **Compute requirement:** `WITH METRICS ... version: 1.1` needs DBR 17.2+
# MAGIC and `DESCRIBE ... AS JSON` needs DBR 16.2+, so use DBR 17.2+ overall.

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

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

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
gold_sales = workshop.fully_qualified(config.catalog, config.schema, "gold_sales")
gold_contracts = workshop.fully_qualified(
    config.catalog, config.schema, "gold_contract_performance"
)
sales_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_sales_metrics"
)
contract_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_contract_metrics"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create the Sales Metric View
# MAGIC
# MAGIC `MEASURE()` makes these YAML measures queryable at any selected dimension
# MAGIC grain. Use a composed `Gross Margin Percent` rather than repeating the
# MAGIC ratio in every dashboard or Genie answer.

# COMMAND ----------

# TODO: Create `finance_sales_metrics` with `CREATE OR REPLACE VIEW ... WITH
# TODO: METRICS LANGUAGE YAML AS $$ ... $$`. Source it from `gold_sales` and
# TODO: include these dimensions: Sale Date, Product Family, Sales Region,
# TODO: Customer Type. Include Transaction Count, Order Count, Units Sold,
# TODO: Gross Sales, Net Sales, Gross Margin, and Gross Margin Percent measures.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — sales YAML skeleton</summary>
# MAGIC
# MAGIC ```sql
# MAGIC CREATE OR REPLACE VIEW <sales_metrics>
# MAGIC WITH METRICS
# MAGIC LANGUAGE YAML
# MAGIC AS $$
# MAGIC version: 1.1
# MAGIC source: "<gold_sales>"
# MAGIC dimensions:
# MAGIC   - name: Product Family
# MAGIC     expr: product_family
# MAGIC measures:
# MAGIC   - name: Net Sales
# MAGIC     expr: SUM(net_sales)
# MAGIC   - name: Gross Margin Percent
# MAGIC     expr: "MEASURE(`Gross Margin`) / NULLIF(MEASURE(`Net Sales`), 0)"
# MAGIC $$
# MAGIC ```
# MAGIC
# MAGIC Define the atomic `Gross Margin` and `Net Sales` measures before the
# MAGIC composed percentage. The full field set is in the gated solution.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create the Contract Metric View

# COMMAND ----------

# TODO: Create `finance_contract_metrics` over `gold_contract_performance`.
# TODO: Add Contract ID, Customer, and Currency dimensions; add the contract
# TODO: performance measures named in the checkpoint below.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — contract KPI pattern</summary>
# MAGIC
# MAGIC Use `SUM(...)` for additive totals, `SUM(transaction_count)` and
# MAGIC `SUM(order_count)` for pre-aggregated counts, and compose margin percent
# MAGIC from `Gross Margin` and `Net Sales` with `MEASURE()`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Query the governed metrics
# MAGIC
# MAGIC Dimensions are regular quoted columns; measures are available only through
# MAGIC `MEASURE()`. Use `GROUP BY ALL` when selecting dimensions.

# COMMAND ----------

# TODO: Run a query like:
# TODO: SELECT `Product Family`, MEASURE(`Net Sales`) AS net_sales,
# TODO:        MEASURE(`Gross Margin`) AS gross_margin
# TODO: FROM <sales_metrics> GROUP BY ALL ORDER BY net_sales DESC


# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `05_metrics`

# MAGIC The check reads the UC Metric View definitions and queries each view. It
# MAGIC fails if either view is absent, its required dimensions/measures or source
# MAGIC are wrong, or its aggregate result is empty/null.

# COMMAND ----------

result = workshop.check(
    "05_metrics",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — add your own governed metric
# MAGIC
# MAGIC Add a third Metric View in this same schema for a question Finance asks
# MAGIC often, such as net sales by `sales_channel` or average discount by
# MAGIC `procedure_category`. Choose dimensions with useful cardinality, define
# MAGIC atomic measures first, then compose a ratio with `MEASURE()` if needed.
# MAGIC Query it with `MEASURE()` and `GROUP BY ALL`. For a custom domain, pass a
# MAGIC `metric_views={...}` contract to `workshop.check` to validate it too.
