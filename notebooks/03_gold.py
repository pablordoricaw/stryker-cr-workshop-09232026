# Databricks notebook source
# ruff: noqa: F401, F821, I001
# MAGIC %md
# MAGIC # 03 · Gold medallion layer — Finance
# MAGIC
# MAGIC Turn document intelligence and transaction facts into business-ready
# MAGIC gold tables for Metric Views, Genie, and the app:
# MAGIC
# MAGIC - **`gold_sales`** — one row per `transaction_id`, enriched with its
# MAGIC   extracted commercial agreement; and
# MAGIC - **`gold_contract_performance`** — one row per `contract_id`, with
# MAGIC   additive sales and margin measures.
# MAGIC
# MAGIC Run `01_bronze_txn` and `02_silver_docs` first. Fill in each **`# TODO`**
# MAGIC cell, open the collapsible hints if needed, then run `03_gold`. This
# MAGIC notebook uses the existing catalog from `00_setup`; never create a catalog.

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

# MAGIC %md
# MAGIC ## 1. Read your workshop config
# MAGIC
# MAGIC Enter the same existing catalog and schema you used in `00_setup`.

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

bronze_sales = workshop.fully_qualified(
    config.catalog, config.schema, "bronze_sales_transactions"
)
silver_contracts = workshop.fully_qualified(
    config.catalog, config.schema, "silver_sales_contract_pricing_agreement"
)
gold_sales = workshop.fully_qualified(config.catalog, config.schema, "gold_sales")
gold_contract_performance = workshop.fully_qualified(
    config.catalog, config.schema, "gold_contract_performance"
)

print(f"Detail target: {gold_sales}")
print(f"Mart target:   {gold_contract_performance}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build transaction-grain `gold_sales`
# MAGIC
# MAGIC The conformed business key is
# MAGIC `bronze_sales_transactions.contract_id =
# MAGIC silver_sales_contract_pricing_agreement.agreement_id`. Project the
# MAGIC extracted agreement columns with clear `contract_...` names and left-join
# MAGIC them to sales. Preserve every transaction column and write a managed Delta
# MAGIC table in your participant schema.

# COMMAND ----------

from pyspark.sql import functions as F

# TODO: Build and write `gold_sales`.
#
# Requirements:
#   - one row per source `transaction_id` (use a left join),
#   - retain all bronze transaction columns,
#   - add `contract_agreement_id`, `contract_document_path`,
#     `contract_document_filename`, `contract_customer_name`, effective and
#     expiration dates, currency, commitment, rebate, governing-law, and
#     covered-products fields from the silver contract table,
#   - overwrite the managed Delta target with schema overwrite enabled.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — grain-safe document enrichment</summary>
# MAGIC
# MAGIC Alias the source DataFrames, join on the conformed key, and explicitly
# MAGIC project document columns so their provenance remains obvious:
# MAGIC
# MAGIC ```python
# MAGIC contracts = spark.table(silver_contracts).select(
# MAGIC     F.col("agreement_id").alias("contract_agreement_id"),
# MAGIC     F.col("path").alias("contract_document_path"),
# MAGIC     F.col("filename").alias("contract_document_filename"),
# MAGIC     F.col("customer_name").alias("contract_customer_name"),
# MAGIC     F.to_date("effective_date").alias("contract_effective_date"),
# MAGIC     F.to_date("expiration_date").alias("contract_expiration_date"),
# MAGIC     # TODO: project the remaining extracted agreement fields.
# MAGIC )
# MAGIC
# MAGIC gold_sales_df = (
# MAGIC     spark.table(bronze_sales).alias("sales")
# MAGIC     .join(contracts.alias("contract"),
# MAGIC           F.col("sales.contract_id") == F.col("contract.contract_agreement_id"),
# MAGIC           "left")
# MAGIC     .select("sales.*", "contract.*")
# MAGIC )
# MAGIC gold_sales_df.write.format("delta").mode("overwrite") \
# MAGIC     .option("overwriteSchema", "true").saveAsTable(gold_sales)
# MAGIC ```
# MAGIC
# MAGIC The supplier invoices and purchase orders deliberately use a different
# MAGIC business process. Do not manufacture a string match to attach them to
# MAGIC customer sales.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Build contract-grain `gold_contract_performance`
# MAGIC
# MAGIC Starting from persisted `gold_sales`, group by `contract_id`. Retain one
# MAGIC copy of the agreement attributes and calculate transaction/order counts,
# MAGIC units, gross sales, discounts, net sales, cost, margin, and average
# MAGIC discount. The result must have exactly one row per source contract.

# COMMAND ----------

# TODO: Build and write `gold_contract_performance` at one row per contract_id.
# Use countDistinct for order_count and additive sums for financial measures.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — contract performance aggregation</summary>
# MAGIC
# MAGIC ```python
# MAGIC mart = (
# MAGIC     spark.table(gold_sales)
# MAGIC     .groupBy("contract_id")
# MAGIC     .agg(
# MAGIC         F.first("contract_document_path", ignorenulls=True)
# MAGIC             .alias("contract_document_path"),
# MAGIC         F.count("transaction_id").alias("transaction_count"),
# MAGIC         F.countDistinct("order_id").alias("order_count"),
# MAGIC         F.sum("units").alias("total_units"),
# MAGIC         F.sum("gross_sales").alias("gross_sales"),
# MAGIC         F.sum("net_sales").alias("net_sales"),
# MAGIC         F.sum("gross_margin").alias("gross_margin"),
# MAGIC         # TODO: add the remaining agreement attributes and measures.
# MAGIC     )
# MAGIC )
# MAGIC mart.write.format("delta").mode("overwrite") \
# MAGIC     .option("overwriteSchema", "true").saveAsTable(gold_contract_performance)
# MAGIC ```
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `03_gold`
# MAGIC
# MAGIC This check derives expected identities and grains from the upstream
# MAGIC tables. It catches missing tables, null/duplicate keys, a join that drops
# MAGIC or multiplies rows, incomplete document enrichment, and aggregates that
# MAGIC do not reconcile.

# COMMAND ----------

result = workshop.check(
    "03_gold",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Gold complete
# MAGIC
# MAGIC Both gold grains are ready for governed metadata, Metric Views, Genie,
# MAGIC and the app serving path.
