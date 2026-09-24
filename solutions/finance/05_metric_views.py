# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Governed Metric Views · SOLUTION (Finance)
# MAGIC
# MAGIC This solution creates two Unity Catalog Metric Views in the participant's
# MAGIC existing resolved schema. They are semantic definitions over the #8 gold
# MAGIC tables, not copies of data: `finance_sales_metrics` provides revenue and
# MAGIC margin slices by product, geography, customer type, and date; and
# MAGIC `finance_contract_metrics` provides contract-performance KPIs. No catalog
# MAGIC or additional schema is created.
# MAGIC
# MAGIC **Compute requirement:** `WITH METRICS ... version: 1.1` needs DBR 17.2+
# MAGIC and `DESCRIBE ... AS JSON` needs DBR 16.2+, so use DBR 17.2+ overall.

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

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog, required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# COMMAND ----------

# Your identity resolves the SAME per-participant workshop_<you> schema 00_setup
# created in the shared team catalog. Leave the schema blank to use it.
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

print(f"Catalog (existing): {config.catalog}")
print(f"Schema: {config.schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Sales revenue and margin metrics

# COMMAND ----------

spark.sql(
    f'''CREATE OR REPLACE VIEW {sales_metrics}
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: "{gold_sales}"
comment: "Governed Finance sales revenue and margin metrics"
dimensions:
  - name: Sale Date
    expr: sale_date
  - name: Product Family
    expr: product_family
  - name: Sales Region
    expr: sales_region
  - name: Customer Type
    expr: customer_type
measures:
  - name: Transaction Count
    expr: COUNT(1)
  - name: Order Count
    expr: COUNT(DISTINCT order_id)
  - name: Units Sold
    expr: SUM(units)
  - name: Gross Sales
    expr: SUM(gross_sales)
  - name: Net Sales
    expr: SUM(net_sales)
  - name: Gross Margin
    expr: SUM(gross_margin)
  - name: Gross Margin Percent
    expr: "MEASURE(`Gross Margin`) / NULLIF(MEASURE(`Net Sales`), 0)"
$$'''
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Contract-performance metrics

# COMMAND ----------

spark.sql(
    f'''CREATE OR REPLACE VIEW {contract_metrics}
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: "{gold_contracts}"
comment: "Governed Finance commercial-agreement performance metrics"
dimensions:
  - name: Contract ID
    expr: contract_id
  - name: Customer
    expr: contract_customer_name
  - name: Currency
    expr: contract_currency
measures:
  - name: Transaction Count
    expr: SUM(transaction_count)
  - name: Order Count
    expr: SUM(order_count)
  - name: Total Units
    expr: SUM(total_units)
  - name: Gross Sales
    expr: SUM(gross_sales)
  - name: Net Sales
    expr: SUM(net_sales)
  - name: Gross Margin
    expr: SUM(gross_margin)
  - name: Gross Margin Percent
    expr: "MEASURE(`Gross Margin`) / NULLIF(MEASURE(`Net Sales`), 0)"
$$'''
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Query the metric layer

# COMMAND ----------

display(
    spark.sql(
        f'''SELECT
              `Product Family`,
              MEASURE(`Net Sales`) AS net_sales,
              MEASURE(`Gross Margin`) AS gross_margin,
              MEASURE(`Gross Margin Percent`) AS gross_margin_percent
            FROM {sales_metrics}
            GROUP BY ALL
            ORDER BY net_sales DESC'''
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `05_metrics`

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
# MAGIC ## Add your own governed metric (stretch)
# MAGIC
# MAGIC Create another Metric View in this same schema, for example a sales-channel
# MAGIC or procedure-category metric. Keep the YAML source pointed at a gold table,
# MAGIC choose useful dimensions, and use `MEASURE()` for composed ratios. Query it
# MAGIC with `GROUP BY ALL`; if you want the generic checkpoint to validate it, pass
# MAGIC a matching `metric_views` contract (view name, source table, dimensions, and
# MAGIC measures) to `workshop.check`.
