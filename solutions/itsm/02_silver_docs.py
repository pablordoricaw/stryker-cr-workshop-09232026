# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver documents · SOLUTION (ITSM)
# MAGIC
# MAGIC **Gated reference solution.** The fully-worked version of the
# MAGIC `02_silver_docs` starter and the ground truth maintainer CI runs end to
# MAGIC end. Participants: try the starter (with its hints and the
# MAGIC `02_silver_docs` checkpoint) before peeking here.
# MAGIC
# MAGIC It builds the **document-intelligence silver layer** on top of the
# MAGIC `bronze_docs` table from module #5, using Databricks AI Functions, with no
# MAGIC model endpoints, no API keys:
# MAGIC
# MAGIC 1. **parse** each document's raw bytes with `ai_parse_document`,
# MAGIC 2. **classify** each into one of the five ITSM classes with
# MAGIC    `ai_classify`, landing a consolidated **`silver_docs`** table, and
# MAGIC 3. **extract** class-specific structured fields with `ai_extract` into one
# MAGIC    **`silver_<class>`** table per class.
# MAGIC
# MAGIC ## ⚠️ Compute / preview requirements
# MAGIC
# MAGIC `ai_parse_document` requires **DBR 17.3+** (or **serverless environment
# MAGIC v3+**); all AI Functions require a **region that supports Foundation Model
# MAGIC APIs** and are **not available on a SQL Warehouse (Classic)**. Attach this
# MAGIC notebook to serverless or a DBR 17.3+ cluster. Each call is a billed LLM
# MAGIC inference, so we materialize each stage to Delta once and never re-invoke
# MAGIC the functions on downstream reads.

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
# MAGIC schema you already provisioned. Module #5 (`01_bronze_docs`) must be green
# MAGIC first. It registers the `bronze_docs` table this notebook reads.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog, required)")
dbutils.widgets.dropdown("domain", "itsm", ["itsm"], "Domain")
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

# Table names. The 02_silver_docs checkpoint expects the consolidated table
# `silver_docs` and one per-class extraction table named `silver_<class>`.
bronze_docs = workshop.fully_qualified(config.catalog, config.schema, "bronze_docs")
silver_docs = workshop.fully_qualified(config.catalog, config.schema, "silver_docs")


def silver_class_table(cls: str) -> str:
    """Fully-qualified per-class extraction table, matching the checkpoint."""
    return workshop.fully_qualified(config.catalog, config.schema, f"silver_{cls}")


print("Your workshop environment:")
print(f"  domain : {config.domain}")
print(f"  catalog: {config.catalog}   (existing, not created)")
print(f"  schema : {config.schema}")
print(f"  bronze : {bronze_docs}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Parse the raw documents (`ai_parse_document`)
# MAGIC
# MAGIC Read the raw PDF bytes from `bronze_docs.content` and parse them into text
# MAGIC with `ai_parse_document`. It returns a VARIANT with per-page `elements`; we
# MAGIC concatenate the element text into a single `parsed_text` column and drop
# MAGIC any document whose `error_status` is set (none, for the clean synthetic
# MAGIC set). We carry `source_class` (the ground-truth folder from bronze) purely
# MAGIC for later comparison, though classification below does **not** look at it.

# COMMAND ----------

from pyspark.sql import functions as F

parsed = (
    spark.table(bronze_docs)
    .withColumn("parsed", F.expr("ai_parse_document(content, map('version', '2.0'))"))
    .selectExpr(
        "path",
        "filename",
        "source_class",
        "concat_ws('\\n', transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'), e -> e:content::string)) AS parsed_text",
        "parsed:error_status AS parse_error",
    )
    # A clean parse returns a VARIANT JSON-null for error_status (not SQL NULL),
    # so cast to string: that yields SQL NULL for a clean doc and the JSON error
    # payload for a failed one.
    .filter("parse_error::string IS NULL")
    .drop("parse_error")
)

# `parsed` is lazy, so we deliberately do NOT force it here. ai_parse_document is a
# billed LLM call, so we let parsing run exactly once, when silver_docs is
# written below, and read counts back from the persisted table afterward.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Classify each document (`ai_classify`) → `silver_docs`
# MAGIC
# MAGIC `ai_classify` routes each parsed document to exactly one of a fixed label
# MAGIC set. We derive that label set from the ground-truth class folders present
# MAGIC in bronze (`SELECT DISTINCT source_class`), so this stage stays
# MAGIC domain-generic, and the same code classifies Finance, Security, or ITSM. We
# MAGIC read the predicted label out of the returned VARIANT (`:response[0]`) and
# MAGIC write the consolidated one-row-per-document `silver_docs` table.

# COMMAND ----------

import json

# The fixed label set = the document classes shipped for this domain.
class_labels = [
    row[0]
    for row in spark.table(bronze_docs)
    .select("source_class")
    .distinct()
    .orderBy("source_class")
    .collect()
]
labels_json = json.dumps(class_labels)
print(f"Classifying into {len(class_labels)} classes: {class_labels}")

silver = (
    parsed.withColumn(
        "doc_class",
        F.expr(
            f"ai_classify(parsed_text, '{labels_json}', map('version', '2.0')):response[0]::string"
        ),
    )
    .select(
        "path",
        "filename",
        "source_class",
        "doc_class",
        "parsed_text",
        F.current_timestamp().alias("processed_at"),
    )
)

silver.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(silver_docs)
# Count the PERSISTED table (cheap Delta metadata), which does not re-run parse
# or classify, which already ran once during the write above.
print(f"Registered {silver_docs} ({spark.table(silver_docs).count()} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Peek: predicted vs. ground-truth class
# MAGIC
# MAGIC The `other` documents deliberately mention invoices, orders, pricing, and
# MAGIC quarters, so a keyword rule would misfire, but `ai_classify` handles them.

# COMMAND ----------

display(
    spark.table(silver_docs)
    .groupBy("source_class", "doc_class")
    .count()
    .orderBy("source_class", "doc_class")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Extract structured fields (`ai_extract`) → `silver_<class>`
# MAGIC
# MAGIC Each class carries different fields, so we route each class to its own
# MAGIC `ai_extract` schema (the extraction-field specification in
# MAGIC `data/itsm/README.md`) and write one `silver_<class>` table per class.
# MAGIC Every ITSM extraction field is scalar, so each is cast to its contract type
# MAGIC (the ITSM schemas define no nested arrays). An `instructions` option keeps
# MAGIC dates ISO `YYYY-MM-DD`, money numeric USD, and rates decimal. We create a table
# MAGIC for **every** class, even one with zero classified documents, so the
# MAGIC silver schema is complete and stable.
# MAGIC
# MAGIC We also persist `ai_extract`'s `error_message` as an **`extract_error`**
# MAGIC column (null on success). The `02_silver_docs` checkpoint fails if any row
# MAGIC carries a non-null `extract_error`, so a silently-failed extraction that
# MAGIC still wrote a row cannot pass as done.

# COMMAND ----------

# Per-class ai_extract schemas, the ITSM extraction-field specification.
EXTRACTION_SCHEMAS: dict[str, dict] = {
    "incident_report": {"incident_id": {"type": "string"}, "priority": {"type": "string"}, "service": {"type": "string"}, "configuration_item": {"type": "string"}, "opened_at": {"type": "string"}, "resolved_at": {"type": "string"}, "impact": {"type": "string"}},
    "post_incident_review": {"incident_id": {"type": "string"}, "root_cause": {"type": "string"}, "severity": {"type": "string"}, "corrective_action": {"type": "string"}, "owner_team": {"type": "string"}, "review_date": {"type": "string"}},
    "change_request": {"change_id": {"type": "string"}, "service": {"type": "string"}, "risk": {"type": "string"}, "implementation_window": {"type": "string"}, "rollback_plan": {"type": "string"}, "approval_status": {"type": "string"}},
    "kb_article_sop": {"kb_id": {"type": "string"}, "title": {"type": "string"}, "applies_to": {"type": "string"}, "procedure_steps": {"type": "string"}, "escalation_path": {"type": "string"}},
    "other": {"document_subtype": {"type": "string"}, "document_number": {"type": "string"}, "document_date": {"type": "string"}, "issuer_or_preparer": {"type": "string"}},
}

# VARIANT -> SQL cast for scalar fields; arrays/objects stay VARIANT.
_TYPE_TO_SQL = {
    "string": "string",
    "number": "double",
    "integer": "bigint",
    "boolean": "boolean",
    "enum": "string",
}


def extract_projection(schema: dict) -> list[str]:
    """Build `selectExpr` strings reading each field out of the ai_extract VARIANT."""
    exprs: list[str] = []
    for field, spec in schema.items():
        if spec["type"] in ("array", "object"):
            exprs.append(f"extracted:response:{field} AS {field}")  # keep nested VARIANT
        else:
            sql_type = _TYPE_TO_SQL[spec["type"]]
            exprs.append(f"extracted:response:{field}::{sql_type} AS {field}")
    return exprs

# COMMAND ----------

# Guide the model on the document formats, which is cheap, and it keeps dates ISO and
# money/rates numeric. Escaped for embedding in the SQL expression below.
EXTRACT_INSTRUCTIONS = (
    "Dates as ISO YYYY-MM-DD. Monetary amounts as numeric USD (no symbols or "
    "commas). Rates as decimals (0.18 for 18%). Leave a field null if absent; "
    "do not infer it from another document class."
).replace("'", "''")

for cls, schema in EXTRACTION_SCHEMAS.items():
    schema_json = json.dumps(schema)
    extracted = (
        spark.table(silver_docs)
        .where(F.col("doc_class") == cls)
        .withColumn(
            "extracted",
            F.expr(
                f"ai_extract(parsed_text, '{schema_json}', "
                f"map('version', '2.0', 'instructions', '{EXTRACT_INSTRUCTIONS}'))"
            ),
        )
        # Preserve ai_extract's error_message: a failed extraction is null on a
        # clean run and a JSON payload on failure. The 02_silver_docs checkpoint
        # fails if any row carries a non-null extract_error, so a silently-failed
        # (all-null) extraction cannot pass as "extracted".
        .selectExpr(
            "path",
            "filename",
            "doc_class",
            "extracted:error_message::string AS extract_error",
            *extract_projection(schema),
        )
    )
    target = silver_class_table(cls)
    extracted.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target)
    # Count the PERSISTED table so ai_extract runs exactly once (not again for a
    # separate .count() on the lazy DataFrame).
    print(f"Registered {target} ({spark.table(target).count()} row(s))")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Peek: extracted incident-report fields

# COMMAND ----------

display(
    spark.table(silver_class_table("incident_report")).select(
        "filename", "incident_id", "priority", "service", "configuration_item"
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `02_silver_docs`
# MAGIC
# MAGIC Confirms, by looking at your catalog, not this notebook, that every
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
