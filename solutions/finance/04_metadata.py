# Databricks notebook source
# ruff: noqa: F821, I001
# MAGIC %md
# MAGIC # 04 · Governed metadata with dbxmetagen — SOLUTION (Finance)
# MAGIC
# MAGIC **Gated reference solution.** Generates and applies governed metadata to
# MAGIC the gold tables with [**dbxmetagen**](https://github.com/databricks-industry-solutions/dbxmetagen)
# MAGIC in all three modes:
# MAGIC
# MAGIC - **`comment`** — table + column descriptions;
# MAGIC - **`pi`** — a `data_classification` tag on sensitive columns; and
# MAGIC - **`domain`** — a `domain` tag on each table.
# MAGIC
# MAGIC The flow is **stage → review → apply**: run each mode with
# MAGIC `apply_ddl=false` first (metadata staged in review tables, nothing touches
# MAGIC Unity Catalog), then re-run with `apply_ddl=true` to apply the approved
# MAGIC comments and tags.
# MAGIC
# MAGIC Run `03_gold` first. This notebook creates no catalog; every object lands
# MAGIC in the participant schema selected in `00_setup`, and dbxmetagen's own
# MAGIC review tables land in a metadata schema inside that same catalog.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install dbxmetagen (pinned)
# MAGIC
# MAGIC Pinned to `v0.10.68` (not `@main`/latest) for reproducibility.
# MAGIC `restartPython()` makes the freshly-installed library importable below.

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
# MAGIC Use the same existing catalog and schema as `00_setup`. dbxmetagen writes
# MAGIC its own review/log tables into that **same resolved schema** — the workshop
# MAGIC provisions exactly one schema, and we do not create a second one.
# MAGIC
# MAGIC - **`model_endpoint`** defaults to `databricks-claude-sonnet-4-6`; confirm it
# MAGIC   exists under **Serving → Foundation Models** (region-dependent) or override.
# MAGIC - **`domain_tag_name`** / **`pi_classification_tag_name`** are the UC tag keys
# MAGIC   dbxmetagen writes. Change them here if your metastore enforces a tag policy
# MAGIC   on the defaults (see the callout in §4). Both generation *and* the
# MAGIC   checkpoint read these same values, so they never desync.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = domain name)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("model_endpoint", "databricks-claude-sonnet-4-6", "FM endpoint")
dbutils.widgets.text("domain_tag_name", "domain", "Domain tag key")
dbutils.widgets.text("pi_classification_tag_name", "data_classification", "PI tag key")

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
)
model_endpoint = dbutils.widgets.get("model_endpoint") or "databricks-claude-sonnet-4-6"
domain_tag_name = dbutils.widgets.get("domain_tag_name") or "domain"
pi_classification_tag_name = (
    dbutils.widgets.get("pi_classification_tag_name") or "data_classification"
)

target_tables = ["gold_sales", "gold_contract_performance"]
table_names = ",".join(
    f"{config.catalog}.{config.schema}.{table}" for table in target_tables
)

print("Your workshop environment:")
print(f"  catalog       : {config.catalog}   (existing — not created)")
print(f"  schema        : {config.schema}   (dbxmetagen output lands here too)")
print(f"  documenting   : {table_names}")
print(f"  model endpoint: {model_endpoint}")
print(f"  domain tag key: {domain_tag_name}")
print(f"  PI tag key    : {pi_classification_tag_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Stage metadata for review (`apply_ddl=false`)
# MAGIC
# MAGIC One dbxmetagen run per mode. With `apply_ddl=false` the generated metadata
# MAGIC is written to review/log tables in your resolved schema
# MAGIC (`<catalog>.<schema>`) and nothing reaches the gold tables yet.

# COMMAND ----------

from dbxmetagen.main import main

MODES = ("comment", "pi", "domain")


def run_dbxmetagen(mode: str, *, apply_ddl: bool) -> None:
    """Invoke dbxmetagen for one mode against the gold tables.

    ``schema_name`` is the participant's resolved schema, so dbxmetagen's review
    tables live alongside the gold tables in the single provisioned schema. The
    tag-key options are forwarded so generation writes the same keys the
    checkpoint verifies.
    """
    main(
        {
            "catalog_name": config.catalog,
            "schema_name": config.schema,
            "table_names": table_names,
            "table_names_source": "parameter",
            "model": model_endpoint,
            "mode": mode,
            "apply_ddl": apply_ddl,
            # apply_tags follows apply_ddl by default; set it explicitly so PI and
            # domain tags are written as UC-native tags when we apply.
            "apply_tags": apply_ddl,
            "domain_tag_name": domain_tag_name,
            "pi_classification_tag_name": pi_classification_tag_name,
        }
    )


for mode in MODES:
    print(f"Staging '{mode}' (apply_ddl=False) …")
    run_dbxmetagen(mode, apply_ddl=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Review the staged metadata
# MAGIC
# MAGIC dbxmetagen's review/log tables (e.g. `metadata_generation_log`,
# MAGIC `column_knowledge_base`) are in your resolved schema, next to the gold
# MAGIC tables. Inspect them and edit anything off before applying.

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {config.catalog}.{config.schema}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Apply the approved metadata (`apply_ddl=true`)
# MAGIC
# MAGIC Re-run each mode with `apply_ddl=true` (and `apply_tags=true`) to issue the
# MAGIC `COMMENT ON …` and `ALTER … SET TAGS` statements against the gold tables.
# MAGIC
# MAGIC > **UC tag policies:** if the metastore governs the `domain` or
# MAGIC > `data_classification` tag keys, `SET TAGS` fails with
# MAGIC > `UC_TAG_POLICY_VALUE_NOT_ALLOWED` unless the value is allowed. The fix is
# MAGIC > executable here: set the **`domain_tag_name`** / **`pi_classification_tag_name`**
# MAGIC > widgets in §1 to a tag key your metastore permits (e.g. `business_domain`).
# MAGIC > Because those same values are forwarded to dbxmetagen *and* to the
# MAGIC > checkpoint below, generation and verification stay in sync.

# COMMAND ----------

for mode in MODES:
    print(f"Applying '{mode}' (apply_ddl=True) …")
    run_dbxmetagen(mode, apply_ddl=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Preview the applied governance
# MAGIC
# MAGIC The comments and tags are now on the gold tables and observable in
# MAGIC `information_schema`.

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT table_name, column_name, tag_name, tag_value
        FROM `{config.catalog}`.information_schema.column_tags
        WHERE schema_name = '{config.schema}'
          AND table_name IN ('gold_sales', 'gold_contract_performance')
        ORDER BY table_name, column_name
        """
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `04_metadata`
# MAGIC
# MAGIC The check reads only Unity Catalog state: every target table and column is
# MAGIC commented, the sensitive columns carry the PI classification tag, and each
# MAGIC table carries a business-domain tag.

# COMMAND ----------

result = workshop.check(
    "04_metadata",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    # Verify the same tag keys generation wrote — never the defaults if overridden.
    domain_tag_name=domain_tag_name,
    pi_tag_name=pi_classification_tag_name,
)
print(result)
assert result.passed, result.message
