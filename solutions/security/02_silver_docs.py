# Databricks notebook source
# ruff: noqa: F821, I001
# MAGIC %md
# MAGIC # 02 · Silver documents — SOLUTION (Security)
# MAGIC
# MAGIC **Gated reference solution.** The fully-worked version of the
# MAGIC `02_silver_docs` starter and the ground truth maintainer CI runs end to
# MAGIC end. Participants: try the starter (with its hints and the
# MAGIC `02_silver_docs` checkpoint) before peeking here.
# MAGIC
# MAGIC It builds the **document-intelligence silver layer** on top of the
# MAGIC `bronze_docs` table from module #5, using Databricks AI Functions — no
# MAGIC model endpoints, no API keys:
# MAGIC
# MAGIC 1. **parse** each document's raw bytes with `ai_parse_document`,
# MAGIC 2. **classify** each into one of the five Security classes with
# MAGIC    `ai_classify`, landing a consolidated **`silver_docs`** table, and
# MAGIC 3. **extract** class-specific structured fields with `ai_extract` into one
# MAGIC    **`silver_<class>`** table per class.
# MAGIC
# MAGIC The `cve_advisory` extraction schema pulls a single `cve_id` from each
# MAGIC advisory — the join key `03_gold` uses to enrich scan findings.
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
# MAGIC first — it registers the `bronze_docs` table this notebook reads.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "security", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

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
print(f"  catalog: {config.catalog}   (existing — not created)")
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
# MAGIC for later comparison — classification below does **not** look at it.

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

# `parsed` is lazy — we deliberately do NOT force it here. ai_parse_document is a
# billed LLM call, so we let parsing run exactly once, when silver_docs is
# written below, and read counts back from the persisted table afterward.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Classify each document (`ai_classify`) → `silver_docs`
# MAGIC
# MAGIC `ai_classify` routes each parsed document to exactly one of a fixed label
# MAGIC set. We derive that label set from the ground-truth class folders present
# MAGIC in bronze (`SELECT DISTINCT source_class`), so this stage stays
# MAGIC domain-generic — the same code classifies Finance, Security, or ITSM. We
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
# Count the PERSISTED table (cheap Delta metadata) — this does not re-run parse
# or classify, which already ran once during the write above.
print(f"Registered {silver_docs} ({spark.table(silver_docs).count()} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Peek: predicted vs. ground-truth class
# MAGIC
# MAGIC The `other` documents (policies, runbooks, risk memos) deliberately mention
# MAGIC CVEs, scans, and remediation, so a keyword rule would misfire —
# MAGIC `ai_classify` handles them.

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
# MAGIC `ai_extract` schema (the extraction-field contract in
# MAGIC `data/security/README.md`) and write one `silver_<class>` table per class.
# MAGIC Scalar fields are cast to their contract types; nested arrays stay VARIANT.
# MAGIC An `instructions` option keeps dates ISO `YYYY-MM-DD` and CVSS scores
# MAGIC numeric. We create a table for **every** class — even one with zero
# MAGIC classified documents — so the silver schema is complete and stable.
# MAGIC
# MAGIC We also persist `ai_extract`'s `error_message` as an **`extract_error`**
# MAGIC column (null on success). The `02_silver_docs` checkpoint fails if any row
# MAGIC carries a non-null `extract_error`, so a silently-failed extraction that
# MAGIC still wrote a row cannot pass as done.
# MAGIC
# MAGIC The `cve_advisory` schema's `cve_id` is the **join key** `03_gold` uses to
# MAGIC enrich scan findings, so it must extract cleanly and uniquely per advisory.

# COMMAND ----------

# Per-class ai_extract schemas — the Security extraction-field contract.
EXTRACTION_SCHEMAS: dict[str, dict] = {
    "vulnerability_scan": {
        "scan_id": {"type": "string"},
        "scanner_name": {"type": "string"},
        "scan_date": {"type": "string"},
        "target_scope": {"type": "string"},
        "authenticated": {"type": "string"},
        "total_findings": {"type": "number"},
        "critical_count": {"type": "number"},
        "high_count": {"type": "number"},
        "medium_count": {"type": "number"},
        "low_count": {"type": "number"},
        "highest_cvss": {"type": "number"},
        "top_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cve_id": {"type": "string"},
                    "asset": {"type": "string"},
                    "category": {"type": "string"},
                    "cvss": {"type": "number"},
                    "status": {"type": "string"},
                },
            },
        },
    },
    "cve_advisory": {
        "cve_id": {"type": "string"},
        "title": {"type": "string"},
        "published_date": {"type": "string"},
        "last_updated": {"type": "string"},
        "severity": {"type": "string"},
        "cvss_score": {"type": "number"},
        "cvss_vector": {"type": "string"},
        "exploit_observed": {"type": "string"},
        "affected_products": {"type": "string"},
        "recommended_remediation": {"type": "string"},
        "references": {"type": "array", "items": {"type": "string"}},
    },
    "pentest_report": {
        "engagement_id": {"type": "string"},
        "test_type": {"type": "string"},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
        "tester_name": {"type": "string"},
        "overall_risk": {"type": "string"},
        "findings_count": {"type": "number"},
        "exploited_paths": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "attack_path": {"type": "string"},
                    "impact": {"type": "string"},
                    "related_cve": {"type": "string"},
                },
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "cloud_posture_finding": {
        "finding_id": {"type": "string"},
        "cloud_provider": {"type": "string"},
        "service": {"type": "string"},
        "control_id": {"type": "string"},
        "benchmark": {"type": "string"},
        "severity": {"type": "string"},
        "region": {"type": "string"},
        "status": {"type": "string"},
        "resource_id": {"type": "string"},
        "first_detected_date": {"type": "string"},
        "remediation_guidance": {"type": "string"},
    },
    "other": {
        "document_subtype": {"type": "string"},
        "document_number": {"type": "string"},
        "document_date": {"type": "string"},
        "owner_or_preparer": {"type": "string"},
        "subject": {"type": "string"},
        "classification": {"type": "string"},
        "referenced_documents": {"type": "array", "items": {"type": "string"}},
    },
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

# Guide the model on the contract's formats — cheap, and it keeps dates ISO and
# CVSS numeric. Escaped for embedding in the SQL expression below.
EXTRACT_INSTRUCTIONS = (
    "Dates as ISO YYYY-MM-DD. CVSS scores as numeric 0-10 (no text). Copy CVE "
    "identifiers verbatim in the form CVE-YYYY-NNNNN. Leave a field null if "
    "absent; do not infer it from another document class."
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
# MAGIC ### Peek: extracted CVE-advisory fields
# MAGIC
# MAGIC `cve_id` is the join key module #8 uses to enrich scan findings.

# COMMAND ----------

display(
    spark.table(silver_class_table("cve_advisory")).select(
        "filename", "cve_id", "severity", "cvss_score", "published_date"
    )
)

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
