# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Transactional ingestion to bronze
# MAGIC
# MAGIC Land the 3,000 synthetic transactions for **your domain** in one Delta
# MAGIC table. The table name and grain key differ per domain — Finance's
# MAGIC `bronze_sales_transactions` / `transaction_id`, Security's
# MAGIC `bronze_scan_findings` / `finding_id`, ITSM's `bronze_service_tickets` /
# MAGIC `ticket_id` — and are derived for you below from the domain you pick.
# MAGIC
# MAGIC ## 📦 Automatic CDF source detection and provisioning
# MAGIC
# MAGIC This notebook automatically ensures your domain's CDF history table is
# MAGIC available via a **three-tier fallback**:
# MAGIC
# MAGIC 1. **Detect** — if the history table already exists in your catalog/schema,
# MAGIC    it is used as-is.
# MAGIC 2. **Provision** — if you supply a Lakebase project/database (via widgets,
# MAGIC    optional) or a derived one can be created, the notebook seeds Postgres
# MAGIC    and configures CDF→UC automatically. Requires workspace admin to enable
# MAGIC    the **Lakebase Lakehouse Sync / CDF Beta/Preview** under workspace
# MAGIC    **Previews**.
# MAGIC 3. **Synthesize** — if provisioning is unavailable or fails (e.g.,
# MAGIC    default-storage catalogs are unsupported), the history table is built
# MAGIC    in UC from the committed seed, and the participant's `# TODO` cells run
# MAGIC    as if synced.
# MAGIC
# MAGIC Both paths produce the same current-state bronze table and finish at the
# MAGIC same checkpoint. Leave the Lakebase widgets blank for automatic detection;
# MAGIC fill them only to reuse an existing project.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

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
# MAGIC ## 1. Reuse your setup configuration and pick your domain
# MAGIC
# MAGIC Enter the same existing catalog, schema, and volume you used in
# MAGIC `00_setup`, and keep the **same domain** you chose there. This cell is done
# MAGIC for you: it resolves your config and derives your domain's bronze table
# MAGIC name, grain key, seeded row count, and committed Delta seed path.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
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

# The single source of truth for this domain's transactional-track names/keys.
spec = workshop.domain_spec(config.domain)

source_mode = dbutils.widgets.get("source_mode")
bronze_table = f"{config.quoted_schema()}.`{spec.bronze_txn_table}`"
# The committed Delta snapshot for your domain, and the Lakebase CDF history
# table (widget override wins; else the domain default).
delta_seed_path = os.path.join(
    _root, "data", config.domain, "transactional", "delta", spec.txn_seed_dir
)
widget_lakebase_cdf_table = dbutils.widgets.get("lakebase_cdf_table")

# Lakebase provisioning will be triggered in the next cell if source_mode is "auto"
# or "lakebase_cdf". The helper will resolve lakebase_cdf_table.
lakebase_project = dbutils.widgets.get("lakebase_project") or None
lakebase_database = dbutils.widgets.get("lakebase_database") or None

print(f"Domain          : {config.domain}   ({spec.txn_entity_label})")
print(f"Source mode     : {source_mode}")
print(f"Target          : {bronze_table}")
print(f"Grain key       : {spec.transaction_key}")
print(f"Expected rows   : {spec.expected_txn_rows:,}")
print(f"Delta seed      : {delta_seed_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ensure CDF history table (done for you)
# MAGIC
# MAGIC This cell automatically resolves your domain's CDF history table via:
# MAGIC detect (preexisting) → provision (Lakebase Postgres + CDF) → synthesize (UC).
# MAGIC
# MAGIC When `source_mode` is `auto` or `lakebase_cdf`, the helper handles it; when
# MAGIC `delta_fallback` is explicit, the Delta snapshot is used instead.

# COMMAND ----------

# %pip install psycopg[binary] --quiet
# (psycopg is only needed if Lakebase provisioning is attempted; keep it quiet
#  so the UI is not cluttered)

# Resolve what CDF source to use based on source_mode widget.
if source_mode == "delta_fallback":
    # Explicit delta_fallback: use the Delta seed directly.
    lakebase_cdf_table = None  # Signal that CDF is not being used
    print(f"[01_bronze_txn] Using delta_fallback (CDF skipped per source_mode)")
else:
    # source_mode is "auto" (default) or "lakebase_cdf": try to provision CDF.
    from databricks.sdk import WorkspaceClient

    try:
        w = WorkspaceClient()
    except Exception as e:
        w = None
        print(f"[01_bronze_txn] Could not initialize WorkspaceClient: {e}. "
              f"Provisioning will be skipped; synthesis will be attempted.")

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
        print(f"[01_bronze_txn] CDF source report:")
        print(f"  Mode:             {cdf_report.mode}")
        print(f"  History table:    {cdf_report.cdf_history_table}")
        print(f"  Lakebase project: {cdf_report.lakebase_project or 'none'}")
        print(f"  Notes:            {cdf_report.notes}")
    except Exception as e:
        if source_mode == "lakebase_cdf":
            # Explicit lakebase_cdf: fail hard if even synthesis fails.
            raise RuntimeError(
                f"source_mode is lakebase_cdf but could not ensure CDF source: {e}"
            ) from e
        else:
            # auto mode: silently fall back to delta_fallback
            lakebase_cdf_table = None
            print(f"[01_bronze_txn] CDF provisioning/synthesis failed; "
                  f"falling back to delta_fallback: {e}")

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
# MAGIC Complete the branch you selected. Leave the other branch alone. Both derive
# MAGIC from the names printed above, so the same cell works for every domain.

# COMMAND ----------

# TODO: Build a DataFrame named `transactions` from the selected source.
#
# if lakebase_cdf_table is not None:
#     # TODO: reconstruct current state from `lakebase_cdf_table`, keeping only the
#     #       latest non-deleted row per `spec.transaction_key`.
#     ...
# else:
#     # TODO: copy `delta_seed_path` to a subdir of config.volume_path and read it.
#     ...

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint — Lakebase CDF (nudge)

# COMMAND ----------

# MAGIC %md
# MAGIC Read `lakebase_cdf_table`, rank events within each `spec.transaction_key`
# MAGIC (your domain's grain key) by descending `_sort_by`, keep rank 1 unless its
# MAGIC `_pg_change_type` is `delete`, then drop the CDF metadata columns.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint — Delta fallback (nudge)

# COMMAND ----------

# MAGIC %md
# MAGIC Spark executors need a workspace-accessible path. Copy the committed
# MAGIC `delta_seed_path` (printed above — `data/<domain>/transactional/delta/...`)
# MAGIC into a subdirectory of `config.volume_path`, then read that destination with
# MAGIC `spark.read.format("delta")`. Your domain's gated
# MAGIC `solutions/<domain>/01_bronze_txn.py` has the full staging loop.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Write the shared bronze table
# MAGIC
# MAGIC Overwrite the target as Delta so rerunning either path is deterministic.

# COMMAND ----------

# TODO: Write `transactions` to `bronze_table` in overwrite mode.
# ...

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint — write shape (nudge)

# COMMAND ----------

# MAGIC %md
# MAGIC Use `transactions.write.format("delta").mode("overwrite")`, allow schema
# MAGIC overwrite, and save to the fully qualified `bronze_table` (derived above for
# MAGIC your domain).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `01_bronze_txn`
# MAGIC
# MAGIC The check observes only Unity Catalog state. It passes whether the rows
# MAGIC came from Lakebase CDF or from the Delta fallback. Your domain's table name,
# MAGIC grain key, and seeded row count are passed to the shared, domain-generic
# MAGIC checkpoint from the domain spec — nothing Finance-specific is assumed.

# COMMAND ----------

result = workshop.check(
    "01_bronze_txn",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    # Domain expectations for the shared, domain-generic bronze_txn checkpoint.
    bronze_txn_table=spec.bronze_txn_table,
    expected_txn_rows=spec.expected_txn_rows,
    transaction_key=spec.transaction_key,
)
print(result)
assert result.passed, result.message
