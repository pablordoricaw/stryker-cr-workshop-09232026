# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold medallion layer — SOLUTION (Finance)
# MAGIC
# MAGIC **Gated reference solution.** This notebook turns the upstream Finance
# MAGIC tables into two analytics-ready, governed Delta tables:
# MAGIC
# MAGIC - **`gold_sales`** — one row per `transaction_id`, enriched with its
# MAGIC   document-derived commercial agreement; and
# MAGIC - **`gold_contract_performance`** — one row per `contract_id`, with
# MAGIC   additive sales and margin measures for BI, Metric Views, and the app.
# MAGIC
# MAGIC The natural key shared by these sources is intentional:
# MAGIC `bronze_sales_transactions.contract_id` joins
# MAGIC `silver_sales_contract_pricing_agreement.agreement_id`. Supplier invoice
# MAGIC and purchase-order documents use different business processes and do not
# MAGIC falsely join to customer sales identifiers.
# MAGIC
# MAGIC Run `01_bronze_txn` and `02_silver_docs` first. This notebook creates no
# MAGIC catalog: every object lands in the participant schema selected in
# MAGIC `00_setup`.

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
# MAGIC Use the same existing catalog and schema as `00_setup`. Only managed
# MAGIC tables inside that schema are created.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
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

print("Your workshop environment:")
print(f"  catalog : {config.catalog}   (existing — not created)")
print(f"  schema  : {config.schema}")
print(f"  detail  : {gold_sales}")
print(f"  mart    : {gold_contract_performance}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build transaction-grain `gold_sales`
# MAGIC
# MAGIC Project the extracted contract fields into stable business names, then
# MAGIC left-join them to sales. A left join preserves every transaction even if
# MAGIC a participant later adds sales outside the current agreement set. The
# MAGIC `03_gold` checkpoint independently proves that the current seeded join
# MAGIC enriches exactly the expected transaction identities without changing
# MAGIC grain.

# COMMAND ----------

from pyspark.sql import functions as F

contracts = spark.table(silver_contracts).select(
    F.col("agreement_id").alias("contract_agreement_id"),
    F.col("path").alias("contract_document_path"),
    F.col("filename").alias("contract_document_filename"),
    F.col("customer_name").alias("contract_customer_name"),
    F.to_date("effective_date").alias("contract_effective_date"),
    F.to_date("expiration_date").alias("contract_expiration_date"),
    F.col("currency").alias("contract_currency"),
    F.col("minimum_procedure_commitment").alias(
        "contract_minimum_procedure_commitment"
    ),
    F.col("rebate_terms").alias("contract_rebate_terms"),
    F.col("governing_law").alias("contract_governing_law"),
    F.col("covered_products").alias("contract_covered_products"),
)

sales = spark.table(bronze_sales).alias("sales")
contract_docs = contracts.alias("contract")

gold_sales_df = (
    sales.join(
        contract_docs,
        F.col("sales.contract_id") == F.col("contract.contract_agreement_id"),
        "left",
    )
    .select(
        "sales.*",
        "contract.contract_agreement_id",
        "contract.contract_document_path",
        "contract.contract_document_filename",
        "contract.contract_customer_name",
        "contract.contract_effective_date",
        "contract.contract_expiration_date",
        "contract.contract_currency",
        "contract.contract_minimum_procedure_commitment",
        "contract.contract_rebate_terms",
        "contract.contract_governing_law",
        "contract.contract_covered_products",
    )
)

(
    gold_sales_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(gold_sales)
)

spark.sql(
    f"COMMENT ON TABLE {gold_sales} IS "
    "'Gold sales fact: one row per transaction, enriched from the governed "
    "commercial-agreement document'"
)
print(f"Registered {gold_sales} ({spark.table(gold_sales).count():,} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Build contract-grain `gold_contract_performance`
# MAGIC
# MAGIC Aggregate only additive measures and retain the governed agreement
# MAGIC attributes. This is the compact serving mart for contract-performance
# MAGIC analysis; `gold_sales` remains the flexible detail table for product,
# MAGIC customer, geography, and time dimensions.

# COMMAND ----------

gold_contract_performance_df = (
    spark.table(gold_sales)
    .groupBy("contract_id")
    .agg(
        F.first("contract_document_path", ignorenulls=True).alias(
            "contract_document_path"
        ),
        F.first("contract_document_filename", ignorenulls=True).alias(
            "contract_document_filename"
        ),
        F.first("contract_customer_name", ignorenulls=True).alias(
            "contract_customer_name"
        ),
        F.first("contract_effective_date", ignorenulls=True).alias(
            "contract_effective_date"
        ),
        F.first("contract_expiration_date", ignorenulls=True).alias(
            "contract_expiration_date"
        ),
        F.first("contract_currency", ignorenulls=True).alias("contract_currency"),
        F.first("contract_minimum_procedure_commitment", ignorenulls=True).alias(
            "contract_minimum_procedure_commitment"
        ),
        F.first("contract_rebate_terms", ignorenulls=True).alias(
            "contract_rebate_terms"
        ),
        F.first("contract_governing_law", ignorenulls=True).alias(
            "contract_governing_law"
        ),
        F.min("sale_date").alias("first_sale_date"),
        F.max("sale_date").alias("last_sale_date"),
        F.count("transaction_id").alias("transaction_count"),
        F.countDistinct("order_id").alias("order_count"),
        F.sum("units").alias("total_units"),
        F.sum("gross_sales").alias("gross_sales"),
        F.sum("discount_amount").alias("discount_amount"),
        F.sum("net_sales").alias("net_sales"),
        F.sum("cost_of_goods").alias("cost_of_goods"),
        F.sum("gross_margin").alias("gross_margin"),
        F.avg("discount_pct").alias("average_discount_pct"),
    )
)

(
    gold_contract_performance_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(gold_contract_performance)
)

spark.sql(
    f"COMMENT ON TABLE {gold_contract_performance} IS "
    "'Gold contract-performance mart: one row per commercial agreement with "
    "reconciled sales and margin measures'"
)
print(
    f"Registered {gold_contract_performance} "
    f"({spark.table(gold_contract_performance).count():,} rows)"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Preview the business mart

# COMMAND ----------

display(
    spark.table(gold_contract_performance)
    .select(
        "contract_id",
        "contract_customer_name",
        "transaction_count",
        "net_sales",
        "gross_margin",
        "average_discount_pct",
    )
    .orderBy(F.desc("net_sales"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `03_gold`
# MAGIC
# MAGIC The check reads only Unity Catalog state. It derives both expected grains
# MAGIC and the exact document-enriched transaction set from the upstream bronze
# MAGIC and silver tables, then reconciles the mart's additive measures.

# COMMAND ----------

result = workshop.check(
    "03_gold",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
)
print(result)
assert result.passed, result.message
