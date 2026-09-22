# Databricks notebook source
# ruff: noqa: F401, F821, I001
# MAGIC %md
# MAGIC # 04 · Governed metadata with dbxmetagen — Finance
# MAGIC
# MAGIC Turn the gold tables into *governed* tables by generating and applying
# MAGIC metadata with [**dbxmetagen**](https://github.com/databricks-industry-solutions/dbxmetagen)
# MAGIC in its three modes:
# MAGIC
# MAGIC - **`comment`** — AI-generated table and column descriptions;
# MAGIC - **`pi`** — PII/PHI/PCI classification tags on sensitive columns; and
# MAGIC - **`domain`** — a business-domain tag on each table.
# MAGIC
# MAGIC The governance model is **stage → review → apply**: every run defaults to
# MAGIC `apply_ddl=false`, so metadata is staged into review tables and *nothing*
# MAGIC touches Unity Catalog until you approve it. You review, then re-run with
# MAGIC `apply_ddl=true` to apply.
# MAGIC
# MAGIC Run `03_gold` first. Fill in each **`# TODO`** cell, open the collapsible
# MAGIC hints if needed, then run the checkpoint. This notebook uses the existing
# MAGIC catalog from `00_setup`; it never creates a catalog.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install dbxmetagen (pinned)
# MAGIC
# MAGIC dbxmetagen is installed notebook-only and **pinned to a known version**
# MAGIC (`v0.10.68`) — not `@main`/latest — so the workshop is reproducible. This
# MAGIC must be the first cell you run; `restartPython()` restarts the interpreter
# MAGIC so the freshly-installed library is importable in the cells below.

# COMMAND ----------

# MAGIC %pip install -qqq git+https://github.com/databricks-industry-solutions/dbxmetagen.git@v0.10.68
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# --- Workshop bootstrap: run this after the pip restart ---
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
# MAGIC
# MAGIC - **`model_endpoint`** is the Foundation Model endpoint dbxmetagen calls.
# MAGIC   It defaults to `databricks-claude-sonnet-4-6`. **Confirm that endpoint
# MAGIC   exists** under **Serving → Foundation Models** in your workspace (its
# MAGIC   availability is region-dependent), or set this widget to another endpoint
# MAGIC   you can access. This is the *only* place you pick an endpoint — the AI
# MAGIC   Functions in `02_silver_docs` (`ai_parse_document` / `ai_classify` /
# MAGIC   `ai_extract`) use Databricks' built-in system model with no endpoint to
# MAGIC   select.
# MAGIC - **`metadata_schema`** is where dbxmetagen writes its own review/log
# MAGIC   tables (created if absent), inside your existing catalog.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = domain name)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("model_endpoint", "databricks-claude-sonnet-4-6", "FM endpoint")
dbutils.widgets.text("metadata_schema", "dbxmetagen_meta", "dbxmetagen review schema")

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
)
model_endpoint = dbutils.widgets.get("model_endpoint") or "databricks-claude-sonnet-4-6"
metadata_schema = dbutils.widgets.get("metadata_schema") or "dbxmetagen_meta"

# The gold tables to document (built by 03_gold). dbxmetagen takes a
# comma-separated list of fully-qualified table names.
target_tables = ["gold_sales", "gold_contract_performance"]
table_names = ",".join(
    f"{config.catalog}.{config.schema}.{table}" for table in target_tables
)

print(f"Documenting: {table_names}")
print(f"Model endpoint: {model_endpoint}   (confirm it exists in Serving)")
print(f"dbxmetagen review schema: {config.catalog}.{metadata_schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Stage metadata for review (`apply_ddl=false`)
# MAGIC
# MAGIC Run dbxmetagen once per mode with `apply_ddl=false`. Each run sends the
# MAGIC gold tables' schema (and, by default, a small row sample) to your model
# MAGIC endpoint, generates metadata, and **stages** it in the review tables —
# MAGIC nothing is written to Unity Catalog yet.

# COMMAND ----------

from dbxmetagen.main import main

# TODO: Stage all three modes with apply_ddl=false.
#
# For each mode in ("comment", "pi", "domain"), call dbxmetagen's main() with:
#   - catalog_name        = config.catalog        (the catalog being documented)
#   - schema_name         = metadata_schema       (where review tables are written)
#   - table_names         = table_names           (the gold tables, comma-separated)
#   - table_names_source  = "parameter"
#   - model               = model_endpoint
#   - mode                = the mode
#   - apply_ddl           = False                 (stage only — do not apply yet)


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — stage the three modes</summary>
# MAGIC
# MAGIC ```python
# MAGIC for mode in ("comment", "pi", "domain"):
# MAGIC     main({
# MAGIC         "catalog_name": config.catalog,
# MAGIC         "schema_name": metadata_schema,
# MAGIC         "table_names": table_names,
# MAGIC         "table_names_source": "parameter",
# MAGIC         "model": model_endpoint,
# MAGIC         "mode": mode,
# MAGIC         "apply_ddl": False,
# MAGIC     })
# MAGIC ```
# MAGIC
# MAGIC dbxmetagen generates one mode at a time. `comment` first is a good habit —
# MAGIC the other modes reuse its context.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Review the staged metadata
# MAGIC
# MAGIC dbxmetagen wrote the generated comments, PI classifications, and domain
# MAGIC tags to review/log tables in `<catalog>.<metadata_schema>` (e.g.
# MAGIC `metadata_generation_log`, `column_knowledge_base`). Inspect them and
# MAGIC confirm the descriptions and classifications look right before applying.

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {config.catalog}.{metadata_schema}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Apply the approved metadata (`apply_ddl=true`)
# MAGIC
# MAGIC Once the staged metadata looks right, apply it. Re-run each mode with
# MAGIC `apply_ddl=true` (and `apply_tags=true` so the PI and domain tags are
# MAGIC written as UC-native tags). This issues the `COMMENT ON …` and
# MAGIC `ALTER … SET TAGS` statements against your gold tables.
# MAGIC
# MAGIC > **If your metastore enforces a UC tag policy** on the `domain` or
# MAGIC > `data_classification` tag keys, `SET TAGS` fails with
# MAGIC > `UC_TAG_POLICY_VALUE_NOT_ALLOWED` unless the generated value is in the
# MAGIC > policy's allowed list. Ask a governance admin to allow the values, or
# MAGIC > point dbxmetagen at permitted tag keys (`pi_classification_tag_name` /
# MAGIC > `domain_tag_name`) — the checkpoint accepts matching `pi_tag_name` /
# MAGIC > `domain_tag_name` overrides so it observes the keys you actually used.

# COMMAND ----------

# TODO: Apply all three modes with apply_ddl=true and apply_tags=true.
# Same calls as the staging step, but with apply_ddl=True and apply_tags=True.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — apply the reviewed metadata</summary>
# MAGIC
# MAGIC ```python
# MAGIC for mode in ("comment", "pi", "domain"):
# MAGIC     main({
# MAGIC         "catalog_name": config.catalog,
# MAGIC         "schema_name": metadata_schema,
# MAGIC         "table_names": table_names,
# MAGIC         "table_names_source": "parameter",
# MAGIC         "model": model_endpoint,
# MAGIC         "mode": mode,
# MAGIC         "apply_ddl": True,
# MAGIC         "apply_tags": True,
# MAGIC     })
# MAGIC ```
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `04_metadata`
# MAGIC
# MAGIC This check reads only Unity Catalog state — `information_schema` comments
# MAGIC and tags. It fails if any target table or column is uncommented, if no
# MAGIC column carries the PI classification tag, or if any table is missing its
# MAGIC business-domain tag. It never inspects this notebook.

# COMMAND ----------

result = workshop.check(
    "04_metadata",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Metadata complete
# MAGIC
# MAGIC The gold tables are governed: documented, PI-classified, and
# MAGIC domain-tagged — ready for Metric Views, Genie, and the app.
