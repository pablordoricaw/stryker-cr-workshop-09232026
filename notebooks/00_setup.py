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
# MAGIC Your **whole team shares one catalog**, so the schema is derived from
# MAGIC **your identity** — every participant gets their own `workshop_<you>`
# MAGIC schema, so two teammates never collide and all workshop schemas sort
# MAGIC together in Catalog Explorer. Leave the schema blank to use it (recommended);
# MAGIC the volume defaults to `landing`. Later notebooks derive the **same** schema
# MAGIC from your identity, so what you set here is what the whole workshop uses.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# Your Databricks identity. It makes your schema (and, later, your Genie agent,
# app, and Lakebase objects) unique in the shared team catalog/workspace.
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,  # blank schema -> your per-participant workshop_<you> schema
)

print("Your workshop environment:")
print(f"  identity: {me}")
print(f"  domain  : {config.domain}")
print(f"  catalog : {config.catalog}   (existing — not created)")
print(f"  schema  : {config.schema}   (per-participant — unique to you)")
print(f"  volume  : {config.volume}   (files land in {config.volume_path})")

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
# MAGIC ## 5. Give Genie Code your workshop hints
# MAGIC
# MAGIC **Genie Code** — the in-workspace coding assistant — helps you through the
# MAGIC workshop *one rung at a time*. It doesn't read this repo's files on its own;
# MAGIC what it *does* read is your personal instructions file,
# MAGIC `~/.assistant_instructions.md`, at the start of every session. This cell
# MAGIC injects the workshop's hint ladder (with **your** repo root and domain
# MAGIC filled in) into that file so Genie Code knows how to help.
# MAGIC
# MAGIC It is **surgical and safe**: the workshop's content is wrapped in
# MAGIC `STRYKER-WORKSHOP` sentinels, so any personal instructions you already have
# MAGIC are preserved untouched. Re-running it just refreshes the workshop block
# MAGIC (e.g. if you change your domain above). Remove it any time with the teardown
# MAGIC notebook, `notebooks/99_teardown.py`.

# COMMAND ----------

import io

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.workspace import ExportFormat, ImportFormat

# The workshop clone's root (anchored on workshop/__init__.py) and the shipped
# hint-ladder source. `config.domain` is the domain you chose above.
repo_root = workshop.find_repo_root() or _root
with open(
    os.path.join(repo_root, "docs", "genie", ".assistant_instructions.md"),
    encoding="utf-8",
) as _handle:
    hint_source = _handle.read()

block = workshop.build_injection_block(hint_source, repo_root, config.domain)

# Your personal instructions file. Genie Code auto-loads it each session.
personal_path = f"/Workspace/Users/{me}/.assistant_instructions.md"

w = WorkspaceClient()
try:
    with w.workspace.download(personal_path, format=ExportFormat.RAW) as _stream:
        existing = _stream.read().decode("utf-8")
except NotFound:
    # No personal file yet (most common) — start from empty and only add ours.
    existing = ""

merged = workshop.merge_block(existing, block)
w.workspace.upload(
    personal_path,
    io.BytesIO(merged.encode("utf-8")),
    format=ImportFormat.RAW,
    overwrite=True,
)

print(f"Injected the workshop hint block into {personal_path}")
print(f"  repo root: {repo_root}")
print(f"  domain   : {config.domain}")
print("  (your existing personal instructions, if any, were preserved)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Setup complete
# MAGIC
# MAGIC Your schema and UC Volume exist inside your catalog, `00_setup` is green,
# MAGIC and Genie Code has your workshop hints. Move on to the next module — it
# MAGIC reuses the domain and names you chose above. When you're done with the
# MAGIC workshop, run `notebooks/99_teardown.py` to remove the hint block from your
# MAGIC personal instructions.
