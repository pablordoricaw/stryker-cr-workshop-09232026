# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze documents · SOLUTION (Finance)
# MAGIC
# MAGIC **Gated reference solution.** This is the fully-worked version of the
# MAGIC `01_bronze_docs` starter notebook and the ground truth maintainer CI runs
# MAGIC end to end. Participants: try the starter (with its hints and the
# MAGIC `01_bronze_docs` checkpoint) before peeking here.
# MAGIC
# MAGIC It lands the committed Finance source PDFs into your UC Volume and
# MAGIC registers a **bronze documents table** over the raw files. This is a faithful
# MAGIC bronze layer: one row per document, raw bytes plus lightweight provenance
# MAGIC (path, filename, ground-truth class from the folder, size, modified time),
# MAGIC no parsing yet. Module #6 parses and classifies from here.

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
# MAGIC Same widgets as `00_setup`, so this notebook lands documents in the schema
# MAGIC and UC Volume you already provisioned. Enter your **existing** catalog and
# MAGIC keep the domain you chose in setup.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog, required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
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

print("Your workshop environment:")
print(f"  domain : {config.domain}")
print(f"  catalog: {config.catalog}   (existing, not created)")
print(f"  schema : {config.schema}")
print(f"  volume : {config.volume}   (files land in {config.volume_path})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Copy the committed source PDFs into your UC Volume
# MAGIC
# MAGIC The workshop ships the source PDFs in the repo at
# MAGIC `data/<domain>/documents/<class>/*.pdf`. We copy that tree, recursively,
# MAGIC into a `documents/` folder inside your UC Volume with `dbutils.fs.cp`. The
# MAGIC repo path is local to the Git folder, so it needs a `file:` scheme; the
# MAGIC destination is the `/Volumes/...` path from your config. Re-running is safe
# MAGIC because it overwrites the same files.

# COMMAND ----------

repo_root = workshop.find_repo_root()
source_dir = f"file:{repo_root}/data/{config.domain}/documents"
docs_path = f"{config.volume_path}/documents"

dbutils.fs.cp(source_dir, docs_path, recurse=True)

print(f"Copied source documents into {docs_path}:")
for entry in dbutils.fs.ls(docs_path):
    print(f"  {entry.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Register the bronze documents table
# MAGIC
# MAGIC Read the raw PDFs with Spark's `binaryFile` format (recursively, PDFs
# MAGIC only) and write a Delta table with **one row per document**. We keep it a
# MAGIC true bronze layer with the raw `content` bytes plus lightweight provenance:
# MAGIC
# MAGIC | column | source |
# MAGIC | --- | --- |
# MAGIC | `path` | full `/Volumes/...` path (from `binaryFile`) |
# MAGIC | `filename` | last path segment |
# MAGIC | `source_class` | parent folder (the ground-truth class) |
# MAGIC | `size_bytes` | `binaryFile.length` |
# MAGIC | `modification_time` | `binaryFile.modificationTime` |
# MAGIC | `content` | raw file bytes (module #6 parses these) |
# MAGIC | `ingested_at` | when this cell ran |

# COMMAND ----------

from pyspark.sql import functions as F

bronze_table = workshop.fully_qualified(config.catalog, config.schema, "bronze_docs")

raw = (
    spark.read.format("binaryFile")
    .option("recursiveFileLookup", "true")
    .option("pathGlobFilter", "*.pdf")
    .load(docs_path)
)

bronze = raw.select(
    F.col("path"),
    F.element_at(F.split(F.col("path"), "/"), -1).alias("filename"),
    F.element_at(F.split(F.col("path"), "/"), -2).alias("source_class"),
    F.col("length").alias("size_bytes"),
    F.col("modificationTime").alias("modification_time"),
    F.col("content"),
    F.current_timestamp().alias("ingested_at"),
)

bronze.write.mode("overwrite").saveAsTable(bronze_table)
print(f"Registered {bronze_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Peek at the bronze table
# MAGIC
# MAGIC One row per PDF, and an even five per ground-truth class.

# COMMAND ----------

display(
    spark.table(bronze_table)
    .groupBy("source_class")
    .count()
    .orderBy("source_class")
)

# COMMAND ----------

display(
    spark.table(bronze_table).select(
        "filename", "source_class", "size_bytes", "modification_time"
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `01_bronze_docs`
# MAGIC
# MAGIC Confirms, by looking at your volume and catalog rather than this notebook, that
# MAGIC the PDFs landed and the bronze table registers all of them. Green means
# MAGIC you're ready for module #6 (parse + classify).

# COMMAND ----------

result = workshop.check(
    "01_bronze_docs",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    volume=config.volume,
    domain=config.domain,
)
print(result)
assert result.passed, result.message
