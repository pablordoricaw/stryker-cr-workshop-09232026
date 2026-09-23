# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold medallion layer — SOLUTION (Security)
# MAGIC
# MAGIC **Gated reference solution.** This notebook turns the upstream Security
# MAGIC tables into two analytics-ready, governed Delta tables:
# MAGIC
# MAGIC - **`gold_findings`** — one row per `finding_id`, enriched with its
# MAGIC   document-derived **CVE advisory**; and
# MAGIC - **`gold_cve_exposure`** — one row per `cve_id`, with additive exposure,
# MAGIC   remediation-effort, and value-at-risk measures for BI, Metric Views, and
# MAGIC   the app.
# MAGIC
# MAGIC The natural key shared by these sources is intentional:
# MAGIC `bronze_scan_findings.cve_id` joins the extracted
# MAGIC `silver_cve_advisory.cve_id`. Scan-summary, pentest, and cloud-posture
# MAGIC documents use different identifiers and do not falsely join to a CVE.
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

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "security", ["security"], "Domain")
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

bronze_findings = workshop.fully_qualified(
    config.catalog, config.schema, "bronze_scan_findings"
)
silver_advisories = workshop.fully_qualified(
    config.catalog, config.schema, "silver_cve_advisory"
)
gold_findings = workshop.fully_qualified(config.catalog, config.schema, "gold_findings")
gold_cve_exposure = workshop.fully_qualified(
    config.catalog, config.schema, "gold_cve_exposure"
)

print("Your workshop environment:")
print(f"  catalog : {config.catalog}   (existing — not created)")
print(f"  schema  : {config.schema}")
print(f"  detail  : {gold_findings}")
print(f"  mart    : {gold_cve_exposure}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build finding-grain `gold_findings`
# MAGIC
# MAGIC Project the extracted CVE-advisory fields into stable business names, then
# MAGIC left-join them to the scan findings on `cve_id`. A left join preserves
# MAGIC every finding even for CVEs that have no published advisory. The `03_gold`
# MAGIC checkpoint independently proves that the seeded join enriches exactly the
# MAGIC expected finding identities without changing grain.

# COMMAND ----------

from pyspark.sql import functions as F

advisories = spark.table(silver_advisories).select(
    F.col("cve_id").alias("advisory_cve_id"),
    F.col("path").alias("advisory_document_path"),
    F.col("filename").alias("advisory_document_filename"),
    F.col("title").alias("advisory_title"),
    F.to_date("published_date").alias("advisory_published_date"),
    F.col("severity").alias("advisory_severity"),
    F.col("cvss_score").alias("advisory_cvss_score"),
    F.col("recommended_remediation").alias("advisory_recommended_remediation"),
)

findings = spark.table(bronze_findings).alias("finding")
advisory_docs = advisories.alias("advisory")

gold_findings_df = (
    findings.join(
        advisory_docs,
        F.col("finding.cve_id") == F.col("advisory.advisory_cve_id"),
        "left",
    )
    .select(
        "finding.*",
        "advisory.advisory_cve_id",
        "advisory.advisory_document_path",
        "advisory.advisory_document_filename",
        "advisory.advisory_title",
        "advisory.advisory_published_date",
        "advisory.advisory_severity",
        "advisory.advisory_cvss_score",
        "advisory.advisory_recommended_remediation",
    )
)

(
    gold_findings_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(gold_findings)
)

spark.sql(
    f"COMMENT ON TABLE {gold_findings} IS "
    "'Gold findings fact: one row per vulnerability-scan finding, enriched from "
    "the governed CVE advisory document'"
)
print(f"Registered {gold_findings} ({spark.table(gold_findings).count():,} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Build CVE-grain `gold_cve_exposure`
# MAGIC
# MAGIC Aggregate additive exposure measures per CVE and retain the governed
# MAGIC advisory attributes. This is the compact serving mart for CVE-exposure
# MAGIC analysis; `gold_findings` remains the flexible detail table for asset,
# MAGIC environment, severity, and time dimensions.

# COMMAND ----------

gold_cve_exposure_df = (
    spark.table(gold_findings)
    .groupBy("cve_id")
    .agg(
        F.first("vulnerability_title", ignorenulls=True).alias("vulnerability_title"),
        F.first("vulnerability_category", ignorenulls=True).alias(
            "vulnerability_category"
        ),
        F.first("severity", ignorenulls=True).alias("severity"),
        F.first("cvss_score", ignorenulls=True).alias("cvss_score"),
        F.max("exploit_available").alias("exploit_available"),
        F.first("advisory_document_path", ignorenulls=True).alias(
            "advisory_document_path"
        ),
        F.first("advisory_document_filename", ignorenulls=True).alias(
            "advisory_document_filename"
        ),
        F.first("advisory_title", ignorenulls=True).alias("advisory_title"),
        F.first("advisory_published_date", ignorenulls=True).alias(
            "advisory_published_date"
        ),
        F.first("advisory_recommended_remediation", ignorenulls=True).alias(
            "advisory_recommended_remediation"
        ),
        F.min("scan_date").alias("first_scan_date"),
        F.max("scan_date").alias("last_scan_date"),
        F.count("finding_id").alias("finding_count"),
        F.countDistinct("scan_id").alias("scan_count"),
        F.countDistinct("asset_id").alias("affected_assets"),
        F.sum(F.when(F.col("status") == "Open", 1).otherwise(0)).alias("open_findings"),
        F.sum(F.when(F.col("severity") == "Critical", 1).otherwise(0)).alias(
            "critical_findings"
        ),
        F.sum("remediation_hours").alias("remediation_hours"),
        F.sum("asset_value_at_risk").alias("asset_value_at_risk"),
        F.sum("weighted_risk").alias("weighted_risk"),
        F.avg("cvss_score").alias("average_cvss"),
    )
)

(
    gold_cve_exposure_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(gold_cve_exposure)
)

spark.sql(
    f"COMMENT ON TABLE {gold_cve_exposure} IS "
    "'Gold CVE-exposure mart: one row per CVE with reconciled exposure, "
    "remediation-effort, and value-at-risk measures'"
)
print(
    f"Registered {gold_cve_exposure} "
    f"({spark.table(gold_cve_exposure).count():,} rows)"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Preview the exposure mart

# COMMAND ----------

display(
    spark.table(gold_cve_exposure)
    .select(
        "cve_id",
        "severity",
        "finding_count",
        "open_findings",
        "critical_findings",
        "asset_value_at_risk",
        "weighted_risk",
    )
    .orderBy(F.desc("weighted_risk"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `03_gold`
# MAGIC
# MAGIC The check reads only Unity Catalog state. It derives both expected grains
# MAGIC and the exact document-enriched finding set from the upstream bronze and
# MAGIC silver tables, then reconciles the mart's additive measures. The Security
# MAGIC table and column names are passed through the domain-generic checkpoint's
# MAGIC extras so nothing Finance-specific is assumed.

# COMMAND ----------

result = workshop.check(
    "03_gold",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    # Security table/column contract for the domain-generic gold checkpoint.
    source_table="bronze_scan_findings",
    document_table="silver_cve_advisory",
    detail_table="gold_findings",
    mart_table="gold_cve_exposure",
    source_key="finding_id",
    detail_key="finding_id",
    source_group_key="cve_id",
    document_key="cve_id",
    detail_document_key="advisory_cve_id",
    detail_document_match="advisory_document_path",
    mart_key="cve_id",
    # Additive measures present under the same name in the source and the mart.
    reconcile_measures=["remediation_hours", "asset_value_at_risk", "weighted_risk"],
)
print(result)
assert result.passed, result.message
