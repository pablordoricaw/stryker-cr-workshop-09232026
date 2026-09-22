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
# MAGIC # Solution · 01 Transactional ingestion to bronze — ITSM
# MAGIC
# MAGIC Both source paths are implemented below and overwrite the same
# MAGIC `bronze_service_tickets` table.
# MAGIC
# MAGIC ## ⚠️ Lakebase CDF admin/preview dependency
# MAGIC
# MAGIC `lakebase_cdf` requires a workspace admin to enable the **Lakebase
# MAGIC Lakehouse Sync / CDF Beta/Preview** under workspace **Previews**, a
# MAGIC Lakebase Autoscaling Postgres 17 project seeded from the committed
# MAGIC `itsm_seed` SQL/CSV, and an ONLINE CDF config targeting the selected
# MAGIC Unity Catalog schema. Without all three, use `delta_fallback`; it has no
# MAGIC admin or preview dependency.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "itsm", ["itsm"], "Domain")
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
    "lb_service_tickets_history",
    "Lakebase CDF history table",
)

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
bronze_table = f"{config.quoted_schema()}.`bronze_service_tickets`"

# COMMAND ----------

import shutil

from pyspark.sql import functions as F
from pyspark.sql.window import Window

TICKET_COLUMNS = [
    "ticket_id",
    "opened_at",
    "resolved_at",
    "priority",
    "status",
    "assignment_group",
    "service",
    "configuration_item",
    "category",
    "resolution_hours",
    "sla_breached",
    "root_cause_code",
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

    latest = Window.partitionBy("ticket_id").orderBy(F.col("_sort_by").desc())
    transactions = (
        cdf.withColumn("_bronze_rank", F.row_number().over(latest))
        .where(F.col("_bronze_rank") == 1)
        .where(F.col("_pg_change_type") != "delete")
    )
    print(f"Read current state from Lakebase CDF table {cdf_table}")
else:
    source_seed = os.path.join(
        _root,
        "data",
        "itsm",
        "transactional",
        "delta",
        "service_tickets",
    )
    if not os.path.isdir(source_seed):
        raise RuntimeError(f"Committed Delta seed not found at {source_seed}")

    staged_seed = f"{config.volume_path}/itsm/transactional/delta/service_tickets"
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
    transactions = spark.read.format("delta").load(staged_seed)
    print(f"Read committed Delta fallback staged at {staged_seed}")

missing_columns = set(TICKET_COLUMNS).difference(transactions.columns)
if missing_columns:
    raise RuntimeError(
        f"Transactional source is missing expected columns: {sorted(missing_columns)}"
    )
transactions = transactions.select(*TICKET_COLUMNS)

# COMMAND ----------

(
    transactions.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(bronze_table)
)

print(f"Wrote {spark.table(bronze_table).count():,} rows to {bronze_table}")

# COMMAND ----------

result = workshop.check(
    "01_bronze_txn",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    bronze_txn_table="bronze_service_tickets",
    expected_txn_rows=3_000,
    transaction_key="ticket_id",
)
print(result)
assert result.passed, result.message
