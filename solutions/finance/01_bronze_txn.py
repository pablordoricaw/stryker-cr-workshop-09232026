# Databricks notebook source
# MAGIC %md
# MAGIC # Solution · 01 Transactional ingestion to bronze — Finance
# MAGIC
# MAGIC This solution automatically ensures the `lb_sales_transactions_history`
# MAGIC CDF history table is available, then reconstructs the current state and
# MAGIC writes the bronze table.
# MAGIC
# MAGIC ## Automatic CDF source detection and provisioning
# MAGIC
# MAGIC The notebook uses a three-tier fallback to guarantee the history table:
# MAGIC
# MAGIC 1. **Detect** — if already present, use it.
# MAGIC 2. **Provision** — create a Lakebase Postgres project (if needed), seed it,
# MAGIC    and configure CDF→UC (requires workspace admin to enable CDF preview).
# MAGIC 3. **Synthesize** — on any failure, build the history table in UC from seed.

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

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.dropdown(
    "source_mode",
    "auto",
    ["auto", "delta_fallback", "lakebase_cdf"],
    "Transactional source",
)
dbutils.widgets.text(
    "lakebase_project",
    "",
    "Lakebase project (blank = auto-derive/create)",
)
dbutils.widgets.text(
    "lakebase_database",
    "",
    "Lakebase database resource path (blank = default)",
)
dbutils.widgets.text(
    "lakebase_cdf_table",
    "",
    "Lakebase CDF history table (blank = your domain's default)",
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
spec = workshop.domain_spec(config.domain)
source_mode = dbutils.widgets.get("source_mode")
bronze_table = f"{config.quoted_schema()}.`bronze_sales_transactions`"
lakebase_project = dbutils.widgets.get("lakebase_project") or None
lakebase_database = dbutils.widgets.get("lakebase_database") or None

# COMMAND ----------

# Ensure CDF source (done for you)
if source_mode == "delta_fallback":
    # Explicit delta_fallback: use the Delta seed directly.
    lakebase_cdf_table = None
    print(f"[Solution] Using delta_fallback (CDF skipped per source_mode)")
else:
    # source_mode is "auto" or "lakebase_cdf": provision/synthesize CDF.
    from databricks.sdk import WorkspaceClient

    try:
        w = WorkspaceClient()
    except Exception as e:
        w = None
        print(f"[Solution] Could not initialize WorkspaceClient: {e}")

    try:
        cdf_report = workshop.ensure_txn_cdf_source(
            config=config,
            spec=spec,
            spark=spark,
            lakebase_project=lakebase_project,
            lakebase_database=lakebase_database,
            w=w,
            timeout_s=120.0,
            logger=print,
        )
        lakebase_cdf_table = cdf_report.cdf_history_table
        print(f"[Solution] CDF source: {cdf_report.mode} ({cdf_report.cdf_history_table})")
    except Exception as e:
        if source_mode == "lakebase_cdf":
            raise RuntimeError(f"source_mode is lakebase_cdf but CDF failed: {e}") from e
        lakebase_cdf_table = None
        print(f"[Solution] CDF provisioning failed; using delta_fallback: {e}")

# COMMAND ----------

import shutil

from pyspark.sql import functions as F
from pyspark.sql.window import Window

TRANSACTION_COLUMNS = [
    "transaction_id",
    "order_id",
    "sale_date",
    "posting_timestamp",
    "customer_id",
    "customer_name",
    "customer_type",
    "facility_state",
    "sales_region",
    "sales_rep_id",
    "product_sku",
    "product_family",
    "procedure_category",
    "units",
    "unit_price",
    "gross_sales",
    "discount_pct",
    "discount_amount",
    "net_sales",
    "cost_of_goods",
    "gross_margin",
    "currency",
    "sales_channel",
    "contract_id",
    "purchase_order_number",
    "invoice_number",
    "payment_status",
    "source_updated_at",
]

if lakebase_cdf_table is not None:
    cdf_table = ".".join(
        [
            config.quoted_schema(),
            f"`{lakebase_cdf_table.split('.')[-1].replace('`', '``')}`",
        ]
    )
    cdf = spark.sql(f"SELECT * FROM {cdf_table}")
    required_metadata = {"_pg_change_type", "_sort_by"}
    missing_metadata = required_metadata.difference(cdf.columns)
    if missing_metadata:
        raise RuntimeError(
            "The CDF history table is missing required columns; missing "
            f"columns: {sorted(missing_metadata)}"
        )

    latest = Window.partitionBy("transaction_id").orderBy(F.col("_sort_by").desc())
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
        "finance",
        "transactional",
        "delta",
        "sales_transactions",
    )
    if not os.path.isdir(source_seed):
        raise RuntimeError(f"Committed Delta seed not found at {source_seed}")

    staged_seed = f"{config.volume_path}/finance/transactional/delta/sales_transactions"
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

missing_columns = set(TRANSACTION_COLUMNS).difference(transactions.columns)
if missing_columns:
    raise RuntimeError(
        f"Transactional source is missing expected columns: {sorted(missing_columns)}"
    )
transactions = transactions.select(*TRANSACTION_COLUMNS)

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
)
print(result)
assert result.passed, result.message
