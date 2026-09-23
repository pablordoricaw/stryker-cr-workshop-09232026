# Databricks notebook source
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
# MAGIC # Solution · 01 Transactional ingestion to bronze — Security
# MAGIC
# MAGIC Both source paths are implemented below and overwrite the same
# MAGIC `bronze_scan_findings` table — the Security transactional grain is one row
# MAGIC per **vulnerability-scan finding** (3,000 rows), each carrying the `cve_id`
# MAGIC that later joins the extracted CVE advisory in `03_gold`.
# MAGIC
# MAGIC ## ⚠️ Lakebase CDF admin/preview dependency
# MAGIC
# MAGIC `lakebase_cdf` requires a workspace admin to enable the **Lakebase
# MAGIC Lakehouse Sync / CDF Beta/Preview** under workspace **Previews**, a
# MAGIC Lakebase Autoscaling Postgres 17 project seeded from the committed
# MAGIC `security_seed` SQL/CSV, and an ONLINE CDF config targeting the selected
# MAGIC Unity Catalog schema. Without all three, use `delta_fallback`; it has no
# MAGIC admin or preview dependency.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "security", ["security"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.dropdown(
    "source_mode",
    "delta_fallback",
    ["delta_fallback", "lakebase_cdf"],
    "Transactional source",
)
dbutils.widgets.text(
    "lakebase_cdf_table",
    "lb_scan_findings_history",
    "Lakebase CDF history table",
)

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
source_mode = dbutils.widgets.get("source_mode")

# The Security bronze transactional table name and grain key. These are
# domain-specific; the domain-generic `01_bronze_txn` checkpoint takes them (and
# the expected row count) as inputs so the same shared checkpoint validates every
# domain — Finance's `bronze_sales_transactions`/`transaction_id`, Security's
# `bronze_scan_findings`/`finding_id`.
BRONZE_TXN_TABLE = "bronze_scan_findings"
TRANSACTION_KEY = "finding_id"
EXPECTED_TXN_ROWS = 3_000
bronze_table = f"{config.quoted_schema()}.`{BRONZE_TXN_TABLE}`"

# COMMAND ----------

import shutil

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# The Security scan-findings schema (mirrors data/security/transactional). Every
# finding carries a non-null `cve_id` — the join key to the CVE advisory in gold.
FINDING_COLUMNS = [
    "finding_id",
    "scan_id",
    "scan_date",
    "detected_timestamp",
    "asset_id",
    "asset_name",
    "asset_type",
    "environment",
    "business_unit",
    "owner_team",
    "cve_id",
    "vulnerability_title",
    "vulnerability_category",
    "severity",
    "cvss_score",
    "cvss_vector",
    "status",
    "first_detected_date",
    "age_days",
    "remediation_hours",
    "asset_value_at_risk",
    "weighted_risk",
    "remediation_sla_days",
    "exploit_available",
    "detection_source",
    "source_updated_at",
]

if source_mode == "lakebase_cdf":
    cdf_table = ".".join(
        [
            config.quoted_schema(),
            f"`{dbutils.widgets.get('lakebase_cdf_table').replace('`', '``')}`",
        ]
    )
    cdf = spark.sql(f"SELECT * FROM {cdf_table}")
    required_metadata = {"_pg_change_type", "_sort_by"}
    missing_metadata = required_metadata.difference(cdf.columns)
    if missing_metadata:
        raise RuntimeError(
            "The selected table is not a Lakebase CDF history table; missing "
            f"columns: {sorted(missing_metadata)}"
        )

    latest = Window.partitionBy("finding_id").orderBy(F.col("_sort_by").desc())
    findings = (
        cdf.withColumn("_bronze_rank", F.row_number().over(latest))
        .where(F.col("_bronze_rank") == 1)
        .where(F.col("_pg_change_type") != "delete")
    )
    print(f"Read current state from Lakebase CDF table {cdf_table}")
else:
    source_seed = os.path.join(
        _root,
        "data",
        "security",
        "transactional",
        "delta",
        "scan_findings",
    )
    if not os.path.isdir(source_seed):
        raise RuntimeError(f"Committed Delta seed not found at {source_seed}")

    staged_seed = f"{config.volume_path}/security/transactional/delta/scan_findings"
    for source_dir, _, filenames in os.walk(source_seed):
        relative_dir = os.path.relpath(source_dir, source_seed)
        destination_dir = (
            staged_seed
            if relative_dir == "."
            else os.path.join(staged_seed, relative_dir)
        )
        os.makedirs(destination_dir, exist_ok=True)
        for filename in filenames:
            source_file = os.path.join(source_dir, filename)
            destination_file = os.path.join(destination_dir, filename)
            with open(source_file, "rb") as source_handle, open(
                destination_file, "wb"
            ) as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle)
    findings = spark.read.format("delta").load(staged_seed)
    print(f"Read committed Delta fallback staged at {staged_seed}")

missing_columns = set(FINDING_COLUMNS).difference(findings.columns)
if missing_columns:
    raise RuntimeError(
        f"Transactional source is missing expected columns: {sorted(missing_columns)}"
    )
findings = findings.select(*FINDING_COLUMNS)

# COMMAND ----------

(
    findings.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(bronze_table)
)

print(f"Wrote {spark.table(bronze_table).count():,} rows to {bronze_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Checkpoint: `01_bronze_txn`
# MAGIC
# MAGIC The domain-generic checkpoint asserts the bronze transactional table exists
# MAGIC with the seeded row count. Security's table name (`bronze_scan_findings`)
# MAGIC and expected count (3,000) are passed through so the shared checkpoint
# MAGIC validates Security data without any Finance-specific name baked in.

# COMMAND ----------

result = workshop.check(
    "01_bronze_txn",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    # Domain expectations for the shared, domain-generic bronze_txn checkpoint.
    bronze_txn_table=BRONZE_TXN_TABLE,
    expected_txn_rows=EXPECTED_TXN_ROWS,
    transaction_key=TRANSACTION_KEY,
)
print(result)
assert result.passed, result.message
