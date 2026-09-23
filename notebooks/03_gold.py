# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold medallion layer
# MAGIC
# MAGIC Turn document intelligence and transaction facts into business-ready gold
# MAGIC tables for Metric Views, Genie, and the app. Both table names and the
# MAGIC business key differ per domain (derived for you below):
# MAGIC
# MAGIC - a **detail** table — one row per transaction, enriched with its
# MAGIC   document-derived record (Finance `gold_sales`, Security `gold_findings`,
# MAGIC   ITSM `gold_incidents`); and
# MAGIC - a **mart** table — one row per business key, with additive measures
# MAGIC   (Finance `gold_contract_performance` per `contract_id`, Security
# MAGIC   `gold_cve_exposure` per `cve_id`, ITSM `gold_service_performance` per
# MAGIC   `incident_id`).
# MAGIC
# MAGIC Run `01_bronze_txn` and `02_silver_docs` first. Fill in each **`# TODO`**
# MAGIC cell, then run `03_gold`. This notebook uses the existing catalog from
# MAGIC `00_setup`; never create a catalog.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

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
# MAGIC Enter the same existing catalog and schema you used in `00_setup`, and keep
# MAGIC the same domain. This cell is done for you: it derives your domain's upstream
# MAGIC (bronze + silver) and gold (detail + mart) table names and the conformed
# MAGIC join key from the domain spec.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
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

# The single source of truth for this domain's transactional-track names/keys.
spec = workshop.domain_spec(config.domain)

bronze_source = workshop.fully_qualified(config.catalog, config.schema, spec.bronze_txn_table)
silver_document = workshop.fully_qualified(config.catalog, config.schema, spec.document_table)
gold_detail = workshop.fully_qualified(config.catalog, config.schema, spec.detail_table)
gold_mart = workshop.fully_qualified(config.catalog, config.schema, spec.mart_table)

print(f"Domain         : {config.domain}")
print(f"Bronze source  : {bronze_source}")
print(f"Silver document: {silver_document}")
print(f"Detail target  : {gold_detail}   (one row per {spec.transaction_key})")
print(f"Mart target    : {gold_mart}   (one row per {spec.group_key})")
print(f"Join key       : bronze.{spec.group_key} = silver.{spec.document_key}")

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
# MAGIC ## 2. Build the transaction-grain detail table
# MAGIC
# MAGIC The conformed business key is `bronze.<group_key> = silver.<document_key>`
# MAGIC (printed above for your domain). Project the extracted document columns with
# MAGIC clear names and **left-join** them to the transactions. Preserve every
# MAGIC transaction column and write a managed Delta table (`gold_detail`) in your
# MAGIC participant schema.

# COMMAND ----------

from pyspark.sql import functions as F

# TODO: Build and write the gold detail table (`gold_detail`).
#
# Requirements:
#   - one row per source transaction key (`spec.transaction_key`; use a left join),
#   - retain all bronze transaction columns,
#   - project the extracted document fields from `silver_document` under clear
#     names, including `spec.detail_document_key` (the document key) and
#     `spec.detail_document_match` (a non-null document column that proves
#     enrichment landed) — see your domain's data/<domain>/README.md and gated
#     solutions/<domain>/03_gold.py for the exact field list,
#   - overwrite the managed Delta target with schema overwrite enabled.

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — grain-safe document enrichment</summary>
# MAGIC
# MAGIC Alias the source DataFrames, project the document columns explicitly (so
# MAGIC their provenance stays obvious), and left-join on the conformed key:
# MAGIC
# MAGIC ```python
# MAGIC documents = spark.table(silver_document).select(
# MAGIC     F.col(spec.document_key).alias(spec.detail_document_key),
# MAGIC     F.col("path").alias(spec.detail_document_match),
# MAGIC     # TODO: project the remaining extracted document fields for your domain.
# MAGIC )
# MAGIC
# MAGIC gold_detail_df = (
# MAGIC     spark.table(bronze_source).alias("txn")
# MAGIC     .join(documents.alias("doc"),
# MAGIC           F.col(f"txn.{spec.group_key}") == F.col(f"doc.{spec.detail_document_key}"),
# MAGIC           "left")
# MAGIC     .select("txn.*", "doc.*")
# MAGIC )
# MAGIC gold_detail_df.write.format("delta").mode("overwrite") \
# MAGIC     .option("overwriteSchema", "true").saveAsTable(gold_detail)
# MAGIC ```
# MAGIC
# MAGIC Documents from other business processes deliberately use different
# MAGIC identifiers. Do not manufacture a string match to attach them — the
# MAGIC checkpoint proves the join enriches exactly the expected transactions. The
# MAGIC exact projected fields are in `data/<domain>/README.md` and the gated
# MAGIC `solutions/<domain>/03_gold.py`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Build the business-key-grain mart
# MAGIC
# MAGIC Starting from the persisted detail table, group by `spec.group_key`. Retain
# MAGIC one copy of the document attributes and calculate your domain's additive
# MAGIC measures (counts, sums, averages). The result must have exactly one row per
# MAGIC source business key.

# COMMAND ----------

# TODO: Build and write the mart (`gold_mart`) at one row per `spec.group_key`.
# Use countDistinct for distinct-entity counts and additive sums for the
# financial/exposure/effort measures. See solutions/<domain>/03_gold.py for the
# exact measure set your domain reconciles.

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — mart aggregation shape</summary>
# MAGIC
# MAGIC ```python
# MAGIC mart = (
# MAGIC     spark.table(gold_detail)
# MAGIC     .groupBy(spec.group_key)
# MAGIC     .agg(
# MAGIC         F.first(spec.detail_document_match, ignorenulls=True)
# MAGIC             .alias(spec.detail_document_match),
# MAGIC         F.count(spec.transaction_key).alias("transaction_count"),
# MAGIC         # TODO: add your domain's additive measures (sums / distinct counts).
# MAGIC     )
# MAGIC )
# MAGIC mart.write.format("delta").mode("overwrite") \
# MAGIC     .option("overwriteSchema", "true").saveAsTable(gold_mart)
# MAGIC ```
# MAGIC
# MAGIC The gated `solutions/<domain>/03_gold.py` lists the exact measures — and the
# MAGIC `03_gold` checkpoint reconciles the additive ones back to the transaction
# MAGIC source for your domain.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `03_gold`
# MAGIC
# MAGIC This check derives expected identities and grains from the upstream
# MAGIC tables. It catches missing tables, null/duplicate keys, a join that drops
# MAGIC or multiplies rows, incomplete document enrichment, and aggregates that
# MAGIC do not reconcile. Your domain's table and column names (and which additive
# MAGIC measures to reconcile) are passed to the shared checkpoint from the spec.

# COMMAND ----------

result = workshop.check(
    "03_gold",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    # Domain table/column contract for the domain-generic gold checkpoint.
    **spec.gold_extras(),
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Gold complete
# MAGIC
# MAGIC Both gold grains are ready for governed metadata, Metric Views, Genie,
# MAGIC and the app serving path.
