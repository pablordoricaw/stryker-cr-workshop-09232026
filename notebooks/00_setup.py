# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — provision your workshop environment
# MAGIC
# MAGIC This is the **first notebook you run**. It provisions everything the rest
# MAGIC of the workshop needs, entirely from the Databricks Workspace UI:
# MAGIC
# MAGIC 1. A **schema** and **UC Volume** inside your team's **existing catalog**.
# MAGIC 2. **Seed hooks** that load your domain's data (populated by later modules).
# MAGIC 3. The **`00_setup` checkpoint**, which confirms your environment is ready.
# MAGIC
# MAGIC **Bring your own catalog.** The workshop does **not** create a catalog —
# MAGIC your team already has one. You tell it the catalog name below, and it
# MAGIC creates a schema and a UC Volume *inside* that catalog. You only need
# MAGIC `USE CATALOG` + `CREATE SCHEMA` (and volume-create) on your own catalog.
# MAGIC
# MAGIC **No terminal. No admin toggle. Free-Edition-safe.** Every step is plain
# MAGIC Python/SQL you run here in the notebook. You can re-run this notebook
# MAGIC safely at any time; every step is idempotent.

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
# MAGIC ## 1. Enter your catalog and choose your domain
# MAGIC
# MAGIC **Catalog** — type your team's **existing** Unity Catalog catalog name.
# MAGIC This is required; the workshop creates a schema and volume inside it, but
# MAGIC does not create the catalog. If you're not sure of the name, open
# MAGIC **Catalog** in the sidebar and use the catalog your team was given.
# MAGIC
# MAGIC **Domain** — pick the dataset your team is working in. The workshop is the
# MAGIC same end-to-end project for all three; only the dataset differs:
# MAGIC
# MAGIC | Domain     | Dataset                                        |
# MAGIC | ---------- | ---------------------------------------------- |
# MAGIC | `finance`  | Orthopedics finance documents + transactions   |
# MAGIC | `security` | Infrastructure security documents + transactions |
# MAGIC | `itsm`     | IT-Ops incidents + transactions                |
# MAGIC
# MAGIC The schema defaults to the domain name and the volume to `landing` — leave
# MAGIC them as-is unless you have a reason to change them. Later notebooks read
# MAGIC this same config, so whatever you choose here is what the whole workshop uses.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = domain name)")
dbutils.widgets.text("volume", "landing", "UC Volume")

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
)

print("Your workshop environment:")
print(f"  domain : {config.domain}")
print(f"  catalog: {config.catalog}   (existing — not created)")
print(f"  schema : {config.schema}")
print(f"  volume : {config.volume}   (files land in {config.volume_path})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create your schema and UC Volume
# MAGIC
# MAGIC `workshop.provision(...)` runs `CREATE SCHEMA IF NOT EXISTS` and
# MAGIC `CREATE VOLUME IF NOT EXISTS` inside your existing catalog. It does not
# MAGIC touch the catalog itself. If this step fails with a permission error,
# MAGIC confirm the catalog name is correct and that you can create schemas in it.

# COMMAND ----------

report = workshop.provision(config, spark)

for statement in report.statements:
    print(f"ran: {statement}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Run the seed hooks
# MAGIC
# MAGIC Seed hooks load your domain's data into the environment you just created.
# MAGIC They are registered by later modules — today this reports that there is no
# MAGIC data to load yet, which is expected. Running it now confirms the seed
# MAGIC mechanism works end to end.

# COMMAND ----------

for result in workshop.run_seeds(config, spark=spark):
    print(result)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `00_setup`
# MAGIC
# MAGIC The single validation seam. It confirms — by looking at your catalog, not
# MAGIC at this notebook — that your catalog is accessible and that the schema and
# MAGIC UC Volume exist. Green means you're ready for the next module.

# COMMAND ----------

result = workshop.check(
    "00_setup",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    volume=config.volume,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Setup complete
# MAGIC
# MAGIC Your schema and UC Volume exist inside your catalog and `00_setup` is
# MAGIC green. Move on to the next module — it reuses the domain and names you
# MAGIC chose above.
