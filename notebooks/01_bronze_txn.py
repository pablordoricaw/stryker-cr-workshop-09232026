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
# MAGIC # 01 · Transactional ingestion to bronze — Finance
# MAGIC
# MAGIC Land the 3,000 synthetic sales transactions in one Delta table:
# MAGIC `bronze_sales_transactions`. Choose one source; both paths produce the
# MAGIC same current-state bronze table and finish at the same checkpoint.
# MAGIC
# MAGIC ## ⚠️ Lakebase CDF is an admin-enabled Beta/Preview
# MAGIC
# MAGIC The **primary Lakebase CDF path does not work until a workspace admin**:
# MAGIC
# MAGIC 1. enables the **Lakebase Lakehouse Sync / CDF Beta/Preview** in the
# MAGIC    workspace **Previews** settings;
# MAGIC 2. provides a Lakebase Autoscaling Postgres 17 project seeded from
# MAGIC    `data/finance/transactional/lakebase/`; and
# MAGIC 3. configures CDF for Postgres schema `finance_seed` into the Unity
# MAGIC    Catalog catalog/schema entered below, then waits for
# MAGIC    `lb_sales_transactions_history` to be online.
# MAGIC
# MAGIC **No admin or preview access? Choose `delta_fallback`.** It reads the
# MAGIC committed, pre-seeded Delta snapshot and is the supported workshop path
# MAGIC for every participant. This notebook never creates a catalog.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Reuse your setup configuration
# MAGIC
# MAGIC Enter the same existing catalog, schema, and volume you used in
# MAGIC `00_setup`. The schema defaults to `finance` and the volume to `landing`.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
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
    "lb_sales_transactions_history",
    "Lakebase CDF history table",
)

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
source_mode = dbutils.widgets.get("source_mode")
bronze_table = f"{config.quoted_schema()}.`bronze_sales_transactions`"
print(f"Source: {source_mode}")
print(f"Target: {bronze_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🚀 From-scratch mode (optional stretch)
# MAGIC
# MAGIC This stage ships in **guided** mode — the `# TODO` cells and collapsible
# MAGIC **💡 Hint**s below. Strong engineers can flip it to **from-scratch** mode:
# MAGIC treat every `# TODO` as **blank**, keep each **💡 Hint** collapsed, and build
# MAGIC to the **`workshop.check(...)` cell at the end** — it is identical in both
# MAGIC modes and is the only thing that grades you. Re-open a hint to drop back to
# MAGIC guided mode anytime; the checkpoint is unchanged. This is a **convention,
# MAGIC not a setting** — see [`docs/stretch/README.md`](../docs/stretch/README.md).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Read one transactional source
# MAGIC
# MAGIC Complete the branch you selected. Leave the other branch alone.
# MAGIC
# MAGIC <details>
# MAGIC <summary>Hint: Lakebase CDF (nudge)</summary>
# MAGIC
# MAGIC Read `lb_sales_transactions_history`, rank events within each
# MAGIC `transaction_id` by descending `_sort_by`, keep rank 1 unless its
# MAGIC `_pg_change_type` is `delete`, then drop the CDF metadata columns.
# MAGIC </details>
# MAGIC
# MAGIC <details>
# MAGIC <summary>Hint: Delta fallback (nudge)</summary>
# MAGIC
# MAGIC Spark executors need a workspace-accessible path. Copy the committed
# MAGIC `data/finance/transactional/delta/sales_transactions` directory into a
# MAGIC subdirectory of `config.volume_path`, then read that destination with
# MAGIC `spark.read.format("delta")`.
# MAGIC </details>

# COMMAND ----------

# TODO: Build a DataFrame named `transactions` from the selected source.
#
# if source_mode == "lakebase_cdf":
#     # TODO: reconstruct current state from the Lakebase CDF history table.
#     ...
# else:
#     # TODO: copy the committed Delta seed to the UC Volume and read it.
#     ...

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Write the shared bronze table
# MAGIC
# MAGIC Overwrite the target as Delta so rerunning either path is deterministic.
# MAGIC
# MAGIC <details>
# MAGIC <summary>Hint: write shape (nudge)</summary>
# MAGIC
# MAGIC Use `transactions.write.format("delta").mode("overwrite")`, allow schema
# MAGIC overwrite, and save to the fully qualified `bronze_table`.
# MAGIC </details>

# COMMAND ----------

# TODO: Write `transactions` to `bronze_table` in overwrite mode.
# ...

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `01_bronze_txn`
# MAGIC
# MAGIC The check observes only Unity Catalog state. It passes whether the rows
# MAGIC came from Lakebase CDF or from the Delta fallback.

# COMMAND ----------

result = workshop.check(
    "01_bronze_txn",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
)
print(result)
assert result.passed, result.message
