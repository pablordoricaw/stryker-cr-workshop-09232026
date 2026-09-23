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

# MAGIC %md
# MAGIC ## Install dependencies for Lakebase provisioning
# MAGIC
# MAGIC This cell installs `psycopg[binary]` (Postgres client) and upgrades
# MAGIC `databricks-sdk` (for the `databricks.sdk.service.postgres` Lakebase CDF module) —
# MAGIC needed only if Lakebase provisioning is attempted. Installing does not restart the
# MAGIC kernel on its own, so the next cell calls `dbutils.library.restartPython()` to make
# MAGIC the packages importable; the bootstrap cell then runs fresh and rebuilds state.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "psycopg[binary]" "databricks-sdk>=0.135"

# COMMAND ----------

# On serverless / recent runtimes, %pip does not auto-restart Python, so the freshly
# installed package is not importable until the kernel restarts. Restart explicitly
# here — before any state is built — so the bootstrap cell below runs in the fresh kernel.
dbutils.library.restartPython()

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
# MAGIC ## Configuration widgets
# MAGIC
# MAGIC Configure your notebook using the widgets below. The `catalog` and `domain` are required; the Lakebase widgets are optional (leave blank for automatic setup).
# MAGIC
# MAGIC ### Widget reference
# MAGIC
# MAGIC | Widget | What to enter | Leave blank? |
# MAGIC |--------|---------------|--------------|
# MAGIC | **catalog** | Your existing workshop catalog — **required** | No — must always provide |
# MAGIC | **domain** | Finance (locked to this solution) | Never — selects the Finance transactional schema |
# MAGIC | **schema** | Leave blank to use your personal `workshop_<you>` schema (recommended); only override to target a specific schema | Yes — blank is the recommended default |
# MAGIC | **volume** | Leave as `landing` unless you used a different UC volume name | Yes — if you used the default, leave blank or keep as `landing` |
# MAGIC | **source_mode** | Choose your Lakebase CDF approach: `auto` (recommended) = try real CDF, else Delta seed; `lakebase_cdf` = require real CDF (fails if unavailable); `delta_fallback` = skip Lakebase, use committed Delta seed only (fastest) | No — `auto` is the recommended default |
# MAGIC | **lakebase_project** | (Advanced / optional) Leave blank to auto-derive/create; fill only if reusing an existing Lakebase project | Yes — blank is the recommended default |
# MAGIC | **lakebase_database** | (Advanced / optional) Leave blank to use default; fill only if you are bringing your own Lakebase database resource path | Yes — blank is the recommended default |
# MAGIC | **lakebase_cdf_table** | (Advanced / optional) Leave blank to use the Finance default history table; fill only if bringing your own CDF table | Yes — blank is the recommended default |
# MAGIC
# MAGIC **Setup:** enter your **catalog**, leave the **domain** as Finance, and leave everything else blank or as-is.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (required — enter your existing workshop catalog)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain (Finance — locked to this solution)")
dbutils.widgets.text("schema", "", "Schema (leave blank for workshop_<you> — recommended)")
dbutils.widgets.text("volume", "landing", "UC Volume (leave as landing unless you used a different name)")
dbutils.widgets.dropdown(
    "source_mode",
    "auto",
    ["auto", "delta_fallback", "lakebase_cdf"],
    "Transactional source (auto recommended)",
)
dbutils.widgets.text(
    "lakebase_project",
    "",
    "(Advanced) Lakebase project — leave blank for auto",
)
dbutils.widgets.text(
    "lakebase_database",
    "",
    "(Advanced) Lakebase database — leave blank for default",
)
dbutils.widgets.text(
    "lakebase_cdf_table",
    "",
    "(Advanced) Lakebase CDF table — leave blank for Finance default",
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
            repo_root=_root,
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
