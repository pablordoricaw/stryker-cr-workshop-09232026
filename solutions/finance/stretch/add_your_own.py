# Databricks notebook source
# ruff: noqa: F821, I001
# MAGIC %md
# MAGIC # 🚀 Stretch · Add your own metrics + Genie questions — SOLUTION (Finance)
# MAGIC
# MAGIC One concrete extension of the semantic + Genie layers you built, end to end:
# MAGIC a third Metric View (`finance_discount_metrics` over `gold_sales`) and two
# MAGIC extra Genie benchmark questions — each validated by the **existing** generic
# MAGIC checkpoints through `workshop.check` extras, with no framework change. Run
# MAGIC `05_metric_views` and `06_genie` first.

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

gold_sales = workshop.fully_qualified(config.catalog, config.schema, "gold_sales")
gold_contracts = workshop.fully_qualified(
    config.catalog, config.schema, "gold_contract_performance"
)
sales_metrics = workshop.fully_qualified(config.catalog, config.schema, "finance_sales_metrics")
contract_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_contract_metrics"
)
discount_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_discount_metrics"
)

print(f"Schema: {config.schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. A third Metric View — discounting by product family and channel

# COMMAND ----------

spark.sql(
    f'''CREATE OR REPLACE VIEW {discount_metrics}
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: "{gold_sales}"
comment: "Governed Finance discount metrics by product family and sales channel"
dimensions:
  - name: Product Family
    expr: product_family
  - name: Sales Channel
    expr: sales_channel
  - name: Customer Type
    expr: customer_type
measures:
  - name: Gross Sales
    expr: SUM(gross_sales)
  - name: Discount Amount
    expr: SUM(discount_amount)
  - name: Net Sales
    expr: SUM(net_sales)
  - name: Discount Rate
    expr: "MEASURE(`Discount Amount`) / NULLIF(MEASURE(`Gross Sales`), 0)"
$$'''
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Query it with `MEASURE()` and `GROUP BY ALL`

# COMMAND ----------

display(
    spark.sql(
        f'''SELECT
              `Sales Channel`,
              MEASURE(`Gross Sales`) AS gross_sales,
              MEASURE(`Discount Amount`) AS discount_amount,
              MEASURE(`Discount Rate`) AS discount_rate
            FROM {discount_metrics}
            GROUP BY ALL
            ORDER BY discount_amount DESC'''
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Validate the new Metric View via a `metric_views` contract
# MAGIC
# MAGIC The generic `05_metrics` check validates any view you describe. This is a
# MAGIC per-call contract — it does not change how the default `05_metrics` grade
# MAGIC (the two required views) works.

# COMMAND ----------

result = workshop.check(
    "05_metrics",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    metric_views={
        "finance_discount_metrics": {
            "source_table": "gold_sales",
            "dimensions": ["Product Family", "Sales Channel", "Customer Type"],
            "measures": ["Gross Sales", "Discount Amount", "Net Sales", "Discount Rate"],
        }
    },
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Add the new source + benchmark questions to your Genie agent
# MAGIC
# MAGIC Attach `finance_discount_metrics` to your agent (Genie UI → your space → add
# MAGIC data, or re-run your `06_genie` create-or-update with the extra source), then
# MAGIC validate against your own sources and questions. `expected_sources` is a
# MAGIC superset check, so adding assets never breaks the default `06_genie` grade.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

result = workshop.check(
    "06_genie",
    catalog=config.catalog,
    schema=config.schema,
    genie=WorkspaceClient(),
    namespace=ns,  # derives your agent name AND owner_path (one source of truth)
    expected_sources=[
        gold_sales,
        gold_contracts,
        sales_metrics,
        contract_metrics,
        discount_metrics,
    ],
    benchmark_questions=[
        "What is the discount rate by sales channel?",
        "Which product family gives the deepest discounts?",
    ],
)
print(result)
assert result.passed, result.message
