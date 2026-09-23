# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze documents — land the raw PDFs
# MAGIC
# MAGIC Your first medallion step. You'll **land the committed source documents in
# MAGIC your UC Volume** and register a **bronze documents table** over the raw
# MAGIC files. Bronze means *raw and minimally processed*: one row per document,
# MAGIC the raw bytes, and light provenance (path, filename, class, size). No
# MAGIC parsing yet — a later module reads these bytes with AI functions.
# MAGIC
# MAGIC Run `notebooks/00_setup` first: this notebook writes into the schema and
# MAGIC UC Volume it created. Fill in each **`# TODO`** cell, then run the checkpoint
# MAGIC at the bottom until it's green.
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
# MAGIC Same widgets as `00_setup` — enter your **existing** catalog and keep the
# MAGIC domain you chose there. This cell is done for you; just run it.

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

print("Your workshop environment:")
print(f"  domain : {config.domain}")
print(f"  catalog: {config.catalog}   (existing — not created)")
print(f"  schema : {config.schema}")
print(f"  volume : {config.volume}   (files land in {config.volume_path})")

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
# MAGIC ## 2. Copy the committed source PDFs into your UC Volume
# MAGIC
# MAGIC The workshop ships the source PDFs in the repo at
# MAGIC `data/<domain>/documents/<class>/*.pdf`. Copy that whole tree into a
# MAGIC `documents/` folder inside your UC Volume. Two names are set up for you
# MAGIC below — fill in the copy.

# COMMAND ----------

repo_root = workshop.find_repo_root()
source_dir = f"file:{repo_root}/data/{config.domain}/documents"  # local repo tree
docs_path = f"{config.volume_path}/documents"                    # destination on your volume

# TODO: copy the source PDFs from `source_dir` into `docs_path`, recursively.
# Then list `docs_path` to confirm the per-class folders arrived.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — copying files into a UC Volume</summary>
# MAGIC
# MAGIC `dbutils.fs.cp(<from>, <to>, recurse=True)` copies a whole directory tree.
# MAGIC The source is a local repo path, so it needs the `file:` scheme (already in
# MAGIC `source_dir`); the destination is your `/Volumes/...` path (`docs_path`).
# MAGIC List the result with `dbutils.fs.ls(docs_path)`. Re-running is safe — it
# MAGIC overwrites the same files.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Register the bronze documents table
# MAGIC
# MAGIC Read the raw PDFs and write a Delta table named **`bronze_docs`** in your
# MAGIC schema, with **one row per document**. Keep it raw — the file bytes plus
# MAGIC light provenance:
# MAGIC
# MAGIC | column | what it holds |
# MAGIC | --- | --- |
# MAGIC | `path` | full `/Volumes/...` path to the file |
# MAGIC | `filename` | last path segment (e.g. `vendor_invoice_01.pdf`) |
# MAGIC | `source_class` | the parent folder — the document's ground-truth class |
# MAGIC | `size_bytes` | file size |
# MAGIC | `modification_time` | when the file was last modified |
# MAGIC | `content` | the raw file bytes (a later module parses these) |
# MAGIC | `ingested_at` | when you ran this cell |

# COMMAND ----------

from pyspark.sql import functions as F

bronze_table = workshop.fully_qualified(config.catalog, config.schema, "bronze_docs")

# TODO: read the PDFs under `docs_path` with Spark's `binaryFile` format
# (recursively, PDFs only), select the columns in the table above, and write the
# result to `bronze_table` as a Delta table with one row per file.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — reading files and deriving the columns</summary>
# MAGIC
# MAGIC Read with
# MAGIC `spark.read.format("binaryFile").option("recursiveFileLookup", "true").option("pathGlobFilter", "*.pdf").load(docs_path)`.
# MAGIC That gives you `path`, `length`, `modificationTime`, and `content`.
# MAGIC
# MAGIC Derive the rest from `path`:
# MAGIC `F.element_at(F.split(F.col("path"), "/"), -1)` is the filename and `-2` is
# MAGIC the `source_class` folder. Rename `length` → `size_bytes`,
# MAGIC `modificationTime` → `modification_time`, and add
# MAGIC `F.current_timestamp().alias("ingested_at")`.
# MAGIC
# MAGIC Write it with
# MAGIC `.write.mode("overwrite").saveAsTable(bronze_table)` so re-running replaces
# MAGIC the table cleanly.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ### Peek at your table (optional)
# MAGIC
# MAGIC Once the table exists, this shows the per-class counts — you should see an
# MAGIC even five documents in each class.

# COMMAND ----------

# display(spark.table(bronze_table).groupBy("source_class").count().orderBy("source_class"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `01_bronze_docs`
# MAGIC
# MAGIC Confirms — by looking at your volume and catalog, not this notebook — that
# MAGIC the PDFs landed and the bronze table registers all of them. Green means
# MAGIC you're done with this module.

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
