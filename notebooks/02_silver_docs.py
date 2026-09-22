# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver documents — parse, classify, extract
# MAGIC
# MAGIC The document-intelligence step. You'll turn the raw `bronze_docs` table
# MAGIC from module #5 into a governed **silver layer** using Databricks **AI
# MAGIC Functions** — no model endpoints, no API keys:
# MAGIC
# MAGIC 1. **parse** each document's raw bytes into text with `ai_parse_document`,
# MAGIC 2. **classify** each into one of your domain's document classes with
# MAGIC    `ai_classify`, landing a consolidated **`silver_docs`** table, and
# MAGIC 3. **extract** class-specific structured fields with `ai_extract` into one
# MAGIC    **`silver_<class>`** table per class.
# MAGIC
# MAGIC Run `01_bronze_docs` first — this notebook reads the `bronze_docs` table it
# MAGIC registers. Fill in each **`# TODO`** cell; open a **💡 Hint** if you get
# MAGIC stuck; then run the checkpoint at the bottom until it's green.
# MAGIC
# MAGIC ## ⚠️ Compute / preview requirements
# MAGIC
# MAGIC `ai_parse_document` requires **DBR 17.3+** (or **serverless environment
# MAGIC v3+**); all AI Functions require a **region that supports Foundation Model
# MAGIC APIs** and are **not available on a SQL Warehouse (Classic)**. Attach this
# MAGIC notebook to serverless or a DBR 17.3+ cluster. Each call is a billed LLM
# MAGIC inference, so materialize each stage to a Delta table once rather than
# MAGIC re-invoking the functions on every downstream read.

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
# MAGIC Same widgets as `00_setup`, so this notebook reads the bronze table in the
# MAGIC schema you already provisioned. This cell is done for you; just run it.

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

# The 02_silver_docs checkpoint expects the consolidated table `silver_docs` and
# one per-class extraction table named `silver_<class>`.
bronze_docs = workshop.fully_qualified(config.catalog, config.schema, "bronze_docs")
silver_docs = workshop.fully_qualified(config.catalog, config.schema, "silver_docs")

print("Your workshop environment:")
print(f"  domain : {config.domain}")
print(f"  catalog: {config.catalog}   (existing — not created)")
print(f"  schema : {config.schema}")
print(f"  bronze : {bronze_docs}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Parse the raw documents (`ai_parse_document`)
# MAGIC
# MAGIC Read the raw PDF bytes from `bronze_docs.content` and parse them into a
# MAGIC single `parsed_text` column. Carry `path`, `filename`, and `source_class`
# MAGIC (the ground-truth folder) through — you'll classify *without* looking at
# MAGIC `source_class`. Build a DataFrame named `parsed`.

# COMMAND ----------

from pyspark.sql import functions as F

# TODO: build `parsed` from `bronze_docs`:
#   - add `ai_parse_document(content, map('version','2.0'))` as a VARIANT column,
#   - flatten its per-page `elements` into one `parsed_text` string,
#   - keep `path`, `filename`, `source_class`, and drop any parse failures.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — parsing bytes into text</summary>
# MAGIC
# MAGIC `ai_parse_document` returns a VARIANT with `document.elements[]`; each
# MAGIC element has `content`. Concatenate them and filter parse errors:
# MAGIC
# MAGIC ```python
# MAGIC parsed = (
# MAGIC     spark.table(bronze_docs)
# MAGIC     .withColumn("parsed", F.expr("ai_parse_document(content, map('version','2.0'))"))
# MAGIC     .selectExpr(
# MAGIC         "path", "filename", "source_class",
# MAGIC         "concat_ws('\\n', transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'), e -> e:content::string)) AS parsed_text",
# MAGIC         "parsed:error_status AS parse_error",
# MAGIC     )
# MAGIC     .filter("parse_error::string IS NULL")  # clean parse => VARIANT JSON-null
# MAGIC     .drop("parse_error")
# MAGIC )
# MAGIC ```
# MAGIC
# MAGIC A clean parse leaves `error_status` a VARIANT JSON-null (not SQL `NULL`),
# MAGIC so cast it to string before the null test: `parse_error::string IS NULL`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Classify each document (`ai_classify`) → `silver_docs`
# MAGIC
# MAGIC `ai_classify` routes each document to exactly one of a **fixed label set**.
# MAGIC Derive that set from the ground-truth class folders already in bronze
# MAGIC (`SELECT DISTINCT source_class`) so it works for any domain, classify
# MAGIC `parsed_text`, and write a one-row-per-document `silver_docs` table with a
# MAGIC `doc_class` (predicted), `parsed_text`, and `processed_at` column.

# COMMAND ----------

import json

# TODO:
#   1. Collect the distinct `source_class` values from bronze into a JSON label list.
#   2. Add a `doc_class` column = ai_classify(parsed_text, <labels>, ...):response[0].
#   3. Write `silver_docs` (overwrite) with path, filename, source_class,
#      doc_class, parsed_text, processed_at.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — deriving labels and classifying</summary>
# MAGIC
# MAGIC ```python
# MAGIC class_labels = [r[0] for r in
# MAGIC     spark.table(bronze_docs).select("source_class").distinct().orderBy("source_class").collect()]
# MAGIC labels_json = json.dumps(class_labels)
# MAGIC
# MAGIC silver = (
# MAGIC     parsed.withColumn(
# MAGIC         "doc_class",
# MAGIC         F.expr(f"ai_classify(parsed_text, '{labels_json}', map('version','2.0')):response[0]::string"),
# MAGIC     )
# MAGIC     .select("path", "filename", "source_class", "doc_class", "parsed_text",
# MAGIC             F.current_timestamp().alias("processed_at"))
# MAGIC )
# MAGIC silver.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(silver_docs)
# MAGIC ```
# MAGIC
# MAGIC The label set is content, not code: `ai_classify` will only ever return one
# MAGIC of the labels you pass, so the ground-truth folder names are a perfect fit.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Extract structured fields (`ai_extract`) → `silver_<class>`
# MAGIC
# MAGIC Each class carries different fields, so route each class to its own
# MAGIC `ai_extract` schema and write one **`silver_<class>`** table per class
# MAGIC (e.g. `silver_vendor_invoice`). Create a table for **every** class — even
# MAGIC one with zero classified documents — so the silver schema is complete.
# MAGIC
# MAGIC Your domain's target fields per class are the **extraction-field contract**
# MAGIC in `data/<your-domain>/README.md`. Use ISO `YYYY-MM-DD` dates, numeric USD
# MAGIC amounts, and decimal rates; leave missing fields null. Also keep
# MAGIC `ai_extract`'s `error_message` as an **`extract_error`** column — the
# MAGIC checkpoint fails if any row has a non-null `extract_error`, so a failed
# MAGIC extraction can't slip through as "done".

# COMMAND ----------

# TODO:
#   1. Define an ai_extract JSON schema per class (see data/<domain>/README.md).
#   2. For each class: filter silver_docs to that predicted doc_class, add
#      ai_extract(parsed_text, <schema>, ...), select the fields out of
#      `extracted:response:<field>` PLUS `extracted:error_message::string AS
#      extract_error`, and write `silver_<class>` (overwrite).


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — the ai_extract pattern for one class</summary>
# MAGIC
# MAGIC Build a typed schema, run `ai_extract`, and read fields out of the returned
# MAGIC VARIANT with the `:` operator. Loop the same pattern over every class:
# MAGIC
# MAGIC ```python
# MAGIC schema = {
# MAGIC     "invoice_number": {"type": "string"},
# MAGIC     "total_amount":   {"type": "number"},
# MAGIC     "line_items": {"type": "array", "items": {"type": "object", "properties": {
# MAGIC         "description": {"type": "string"}, "line_amount": {"type": "number"}}}},
# MAGIC }
# MAGIC target = workshop.fully_qualified(config.catalog, config.schema, "silver_vendor_invoice")
# MAGIC (
# MAGIC     spark.table(silver_docs)
# MAGIC     .where(F.col("doc_class") == "vendor_invoice")
# MAGIC     .withColumn("extracted", F.expr(f"ai_extract(parsed_text, '{json.dumps(schema)}', map('version','2.0'))"))
# MAGIC     .selectExpr("path", "filename", "doc_class",
# MAGIC                 "extracted:error_message::string AS extract_error",  # null on success
# MAGIC                 "extracted:response:invoice_number::string AS invoice_number",
# MAGIC                 "extracted:response:total_amount::double AS total_amount",
# MAGIC                 "extracted:response:line_items AS line_items")  # nested stays VARIANT
# MAGIC     .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target)
# MAGIC )
# MAGIC ```
# MAGIC
# MAGIC The gated `solutions/finance/02_silver_docs.py` has all five Finance
# MAGIC schemas, an `instructions` option for the contract's formats, and a loop
# MAGIC that writes a table (with `extract_error`) for every class.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `02_silver_docs`
# MAGIC
# MAGIC Confirms — by looking at your catalog, not this notebook — that every
# MAGIC bronze document was parsed and classified into `silver_docs`, and that
# MAGIC `ai_extract` populated one `silver_<class>` table per class covering them
# MAGIC all. Green means you're ready for the gold layer (module #8).

# COMMAND ----------

result = workshop.check(
    "02_silver_docs",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    domain=config.domain,
)
print(result)
assert result.passed, result.message
