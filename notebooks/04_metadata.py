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
# MAGIC - **`domain_tag_name`** / **`pi_classification_tag_name`** are the UC tag
# MAGIC   keys dbxmetagen writes (defaults `domain` / `data_classification`). Change
# MAGIC   them here if your metastore enforces a tag policy on the defaults (see §4).
# MAGIC   The same values flow to dbxmetagen *and* the checkpoint, so they stay in
# MAGIC   sync.
# MAGIC
# MAGIC dbxmetagen writes its review/log tables into your **resolved schema** — the
# MAGIC single schema `00_setup` provisioned. No second schema is created.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("model_endpoint", "databricks-claude-sonnet-4-6", "FM endpoint")
dbutils.widgets.text("domain_tag_name", "domain", "Domain tag key")
dbutils.widgets.text("pi_classification_tag_name", "data_classification", "PI tag key")

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
model_endpoint = dbutils.widgets.get("model_endpoint") or "databricks-claude-sonnet-4-6"
domain_tag_name = dbutils.widgets.get("domain_tag_name") or "domain"
pi_classification_tag_name = (
    dbutils.widgets.get("pi_classification_tag_name") or "data_classification"
)

# The gold tables to document (built by 03_gold). dbxmetagen takes a
# comma-separated list of fully-qualified table names.
target_tables = ["gold_sales", "gold_contract_performance"]
table_names = ",".join(
    f"{config.catalog}.{config.schema}.{table}" for table in target_tables
)

print(f"Documenting: {table_names}")
print(f"Model endpoint: {model_endpoint}   (confirm it exists in Serving)")
print(f"dbxmetagen output schema: {config.catalog}.{config.schema}")
print(f"Tag keys: domain={domain_tag_name}, pi={pi_classification_tag_name}")

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
#   - catalog_name                = config.catalog   (the catalog being documented)
#   - schema_name                 = config.schema    (your ONE resolved schema)
#   - table_names                 = table_names      (gold tables, comma-separated)
#   - table_names_source          = "parameter"
#   - model                       = model_endpoint
#   - mode                        = the mode
#   - apply_ddl                   = False            (stage only — do not apply yet)
#   - domain_tag_name             = domain_tag_name          (keep keys in sync)
#   - pi_classification_tag_name  = pi_classification_tag_name


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — stage the three modes</summary>
# MAGIC
# MAGIC ```python
# MAGIC for mode in ("comment", "pi", "domain"):
# MAGIC     main({
# MAGIC         "catalog_name": config.catalog,
# MAGIC         "schema_name": config.schema,
# MAGIC         "table_names": table_names,
# MAGIC         "table_names_source": "parameter",
# MAGIC         "model": model_endpoint,
# MAGIC         "mode": mode,
# MAGIC         "apply_ddl": False,
# MAGIC         "domain_tag_name": domain_tag_name,
# MAGIC         "pi_classification_tag_name": pi_classification_tag_name,
# MAGIC     })
# MAGIC ```
# MAGIC
# MAGIC dbxmetagen generates one mode at a time. `comment` first is a good habit —
# MAGIC the other modes reuse its context. `schema_name` is your single resolved
# MAGIC schema, so the review tables land beside the gold tables.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Review the staged metadata
# MAGIC
# MAGIC dbxmetagen wrote the generated comments, PI classifications, and domain
# MAGIC tags to review/log tables in your resolved schema `<catalog>.<schema>`
# MAGIC (e.g. `metadata_generation_log`, `column_knowledge_base`), beside the gold
# MAGIC tables. Inspect them and confirm the output looks right before applying.

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {config.catalog}.{config.schema}"))

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
# MAGIC > `UC_TAG_POLICY_VALUE_NOT_ALLOWED`. The fix is executable here: set the
# MAGIC > **`domain_tag_name`** / **`pi_classification_tag_name`** widgets in §1 to a
# MAGIC > key your metastore permits (e.g. `business_domain`) and re-run. Those
# MAGIC > values flow to both dbxmetagen and the checkpoint, so they stay in sync.

# COMMAND ----------

# TODO: Apply all three modes with apply_ddl=true and apply_tags=true.
# Same main() calls as the staging step (still passing schema_name=config.schema
# and the two *_tag_name options), but with apply_ddl=True and apply_tags=True.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — apply the reviewed metadata</summary>
# MAGIC
# MAGIC ```python
# MAGIC for mode in ("comment", "pi", "domain"):
# MAGIC     main({
# MAGIC         "catalog_name": config.catalog,
# MAGIC         "schema_name": config.schema,
# MAGIC         "table_names": table_names,
# MAGIC         "table_names_source": "parameter",
# MAGIC         "model": model_endpoint,
# MAGIC         "mode": mode,
# MAGIC         "apply_ddl": True,
# MAGIC         "apply_tags": True,
# MAGIC         "domain_tag_name": domain_tag_name,
# MAGIC         "pi_classification_tag_name": pi_classification_tag_name,
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
    # Verify the same tag keys you generated with, so the two never drift.
    domain_tag_name=domain_tag_name,
    pi_tag_name=pi_classification_tag_name,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Metadata complete
# MAGIC
# MAGIC The gold tables are governed: documented, PI-classified, and
# MAGIC domain-tagged — ready for Metric Views, Genie, and the app.
