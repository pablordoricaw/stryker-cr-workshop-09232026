# Databricks notebook source
# MAGIC %md
# MAGIC # 🚀 Stretch · Add your own metrics + Genie questions
# MAGIC
# MAGIC **Optional Tier-3 module.** Your workshop is already complete without it.
# MAGIC
# MAGIC You built two Metric Views (`05_metric_views`) and a Genie agent
# MAGIC (`06_genie`). This module extends **both**, on top of what you already have,
# MAGIC **without touching the framework** — the `05_metrics` and `06_genie`
# MAGIC checkpoints already accept your *own* contract through `workshop.check`
# MAGIC extras. It is the same override pattern the Security (#13) and ITSM (#14)
# MAGIC domains use to reuse the generic checkpoints.
# MAGIC
# MAGIC Everything lands in **your existing catalog / `workshop_<you>` schema** — no
# MAGIC catalog is created, no second schema. Run `05_metric_views` and `06_genie`
# MAGIC first.

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
# MAGIC ## 1. Use your existing workshop schema and namespace

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
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

gold_sales = workshop.fully_qualified(config.catalog, config.schema, "gold_sales")
gold_contracts = workshop.fully_qualified(
    config.catalog, config.schema, "gold_contract_performance"
)
sales_metrics = workshop.fully_qualified(config.catalog, config.schema, "finance_sales_metrics")
contract_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_contract_metrics"
)
# Your new Metric View (rename it to your own question):
my_metrics = workshop.fully_qualified(config.catalog, config.schema, "finance_discount_metrics")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Add your own Metric View
# MAGIC
# MAGIC Author a third governed Metric View in your schema for a question Finance
# MAGIC asks often — e.g. discounting by product family and sales channel. Keep the
# MAGIC YAML `source:` pointed at a gold table, define atomic measures first, then
# MAGIC compose a ratio with `MEASURE()`. Confirmed `gold_sales` columns you can use:
# MAGIC `product_family`, `sales_region`, `customer_type`, `sales_channel`,
# MAGIC `procedure_category`, `gross_sales`, `discount_amount`, `net_sales`.

# COMMAND ----------

# TODO: CREATE OR REPLACE VIEW <my_metrics> WITH METRICS LANGUAGE YAML AS $$ ... $$
# TODO: source: "<gold_sales>"; pick dimensions with useful cardinality and
# TODO: define atomic measures (SUM(...)) plus one composed MEASURE()-ratio.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — a discount Metric View skeleton</summary>
# MAGIC
# MAGIC ```sql
# MAGIC CREATE OR REPLACE VIEW <my_metrics>
# MAGIC WITH METRICS LANGUAGE YAML AS $$
# MAGIC version: 1.1
# MAGIC source: "<gold_sales>"
# MAGIC dimensions:
# MAGIC   - name: Product Family
# MAGIC     expr: product_family
# MAGIC   - name: Sales Channel
# MAGIC     expr: sales_channel
# MAGIC measures:
# MAGIC   - name: Gross Sales
# MAGIC     expr: SUM(gross_sales)
# MAGIC   - name: Discount Amount
# MAGIC     expr: SUM(discount_amount)
# MAGIC   - name: Discount Rate
# MAGIC     expr: "MEASURE(`Discount Amount`) / NULLIF(MEASURE(`Gross Sales`), 0)"
# MAGIC $$
# MAGIC ```
# MAGIC
# MAGIC The complete solution is in `solutions/finance/stretch/add_your_own.py`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Validate your Metric View with a `metric_views` contract
# MAGIC
# MAGIC The generic `05_metrics` check validates any view you describe: pass a
# MAGIC `metric_views={view_name: {source_table, dimensions, measures}}` contract.
# MAGIC It is a **per-call** contract — validating your own view here does not change
# MAGIC how the default `05_metrics` grade works.

# COMMAND ----------

# TODO: result = workshop.check(
# TODO:     "05_metrics", spark=spark, catalog=config.catalog, schema=config.schema,
# TODO:     metric_views={"finance_discount_metrics": {
# TODO:         "source_table": "gold_sales",
# TODO:         "dimensions": ["Product Family", "Sales Channel"],
# TODO:         "measures": ["Gross Sales", "Discount Amount", "Discount Rate"]}})
# TODO: print(result); assert result.passed, result.message


# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Add your own Genie sources + benchmark questions
# MAGIC
# MAGIC Attach your new Metric View to your Genie agent (Genie UI → your space →
# MAGIC add data), then validate the agent against **your** sources and questions.
# MAGIC `expected_sources` is a **superset** check, so adding assets never breaks the
# MAGIC default `06_genie` grade; each `benchmark_questions` entry must return SQL
# MAGIC grounded in a curated source.

# COMMAND ----------

# TODO: from databricks.sdk import WorkspaceClient
# TODO: result = workshop.check(
# TODO:     "06_genie", catalog=config.catalog, schema=config.schema,
# TODO:     genie=WorkspaceClient(), namespace=ns,
# TODO:     expected_sources=[gold_sales, gold_contracts, sales_metrics,
# TODO:                       contract_metrics, my_metrics],
# TODO:     benchmark_questions=[
# TODO:         "What is the discount rate by sales channel?",
# TODO:         "Which product family gives the deepest discounts?"])
# TODO: print(result); assert result.passed, result.message


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — why the superset check is safe</summary>
# MAGIC
# MAGIC The `06_genie` check asserts your agent is attached to **at least** the
# MAGIC `expected_sources` (a superset test) and that each benchmark question
# MAGIC returns SQL touching a curated source. Adding `my_metrics` and two questions
# MAGIC extends coverage; it never removes the default assets, so your agent still
# MAGIC passes the plain `06_genie` grade too. Full example:
# MAGIC `solutions/finance/stretch/add_your_own.py`.
# MAGIC </details>
