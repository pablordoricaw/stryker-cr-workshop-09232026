# Databricks notebook source
# MAGIC %md
# MAGIC # 99 · Teardown — remove the workshop hints from Genie Code
# MAGIC
# MAGIC `00_setup` injected the workshop's hint ladder into your personal
# MAGIC instructions file, `~/.assistant_instructions.md`, which **Genie Code**
# MAGIC auto-loads each session. Run this notebook when you're done with the
# MAGIC workshop to take it back out.
# MAGIC
# MAGIC It is **surgical**: it removes **only** the `STRYKER-WORKSHOP` block that
# MAGIC setup added and leaves any personal instructions of your own exactly as
# MAGIC they were. If there is no workshop block (or no personal file at all),
# MAGIC this is a safe no-op.

# COMMAND ----------

# --- Workshop bootstrap: run this first in every notebook ---
import os
import sys

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
# MAGIC ## Remove the workshop hint block
# MAGIC
# MAGIC Reads your personal instructions file, strips the `STRYKER-WORKSHOP`
# MAGIC block, and writes the rest back untouched.

# COMMAND ----------

me = spark.sql("SELECT current_user()").collect()[0][0]
personal_path = f"/Workspace/Users/{me}/.assistant_instructions.md"

import io

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.workspace import ExportFormat, ImportFormat

w = WorkspaceClient()
try:
    with w.workspace.download(personal_path, format=ExportFormat.RAW) as _stream:
        existing = _stream.read().decode("utf-8")
except NotFound:
    existing = ""

cleaned = workshop.strip_block(existing)

if cleaned == existing:
    print(f"No workshop hint block found in {personal_path}; nothing to remove.")
else:
    w.workspace.upload(
        personal_path,
        io.BytesIO(cleaned.encode("utf-8")),
        format=ImportFormat.RAW,
        overwrite=True,
    )
    print(f"Removed the workshop hint block from {personal_path}")
    print("  (your own personal instructions, if any, were preserved)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clean up Lakebase resources (if created by provisioning)
# MAGIC
# MAGIC If `01_bronze_txn` created a Lakebase project or CDF config, this cell
# MAGIC attempts to delete them. If you supplied your own project/database (bring-your-own),
# MAGIC nothing is deleted. This is guarded: only resources that match the known
# MAGIC naming scheme and domain are cleaned up.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

w = WorkspaceClient()

# Resolve config to know what domain/catalog/schema we're working with.
catalog = dbutils.widgets.get("catalog") if "catalog" in dir(dbutils.widgets) else ""
domain = dbutils.widgets.get("domain") if "domain" in dir(dbutils.widgets) else "finance"
schema = dbutils.widgets.get("schema") if "schema" in dir(dbutils.widgets) else ""
volume = dbutils.widgets.get("volume") if "volume" in dir(dbutils.widgets) else "landing"

if catalog:
    try:
        config = workshop.resolve_config(
            catalog=catalog,
            domain=domain,
            schema=schema or None,
            volume=volume,
            identity=me,
        )

        metadata_path = os.path.join(
            config.volume_path,
            ".stryker_workshop_cdf_metadata.json"
        )

        import json
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)

            # Check if this was a provisioned (not BYO) resource that was created by the workshop.
            if metadata.get("mode") == "provisioned" and metadata.get("lakebase_project_created"):
                lakebase_project = metadata.get("lakebase_project")
                if lakebase_project:
                    try:
                        print(f"[99_teardown] Attempting to delete Lakebase project: {lakebase_project}")
                        # Attempt to delete; SDK support varies.
                        try:
                            w.postgres.delete_project(name=lakebase_project)
                            print(f"[99_teardown] Deleted Lakebase project {lakebase_project}")
                        except (AttributeError, NotFound) as del_err:
                            print(f"[99_teardown] Could not delete project via SDK: {del_err}; manual cleanup may be needed.")
                    except Exception as e:
                        print(f"[99_teardown] Error during Lakebase cleanup: {e}")
            else:
                mode = metadata.get('mode', 'unknown')
                was_created = metadata.get('lakebase_project_created', False)
                if mode == "provisioned" and not was_created:
                    lakebase_project = metadata.get("lakebase_project")
                    print(f"[99_teardown] CDF source was provisioned with a bring-your-own project ({lakebase_project}); preserving for reuse by 07_app.")
                else:
                    print(f"[99_teardown] CDF source mode is {mode}; skipping Lakebase cleanup.")
        except FileNotFoundError:
            print(f"[99_teardown] No provisioning metadata found; nothing to clean up.")
        except Exception as e:
            print(f"[99_teardown] Could not read/process provisioning metadata: {e}")
    except Exception as e:
        print(f"[99_teardown] Could not resolve config for cleanup: {e}")
else:
    print(f"[99_teardown] No catalog configured; skipping Lakebase cleanup.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Teardown complete
# MAGIC
# MAGIC Your personal instructions no longer carry the workshop hint block. Any
# MAGIC instructions of your own are exactly as you left them. Lakebase resources
# MAGIC created by provisioning (if any) have been removed (or noted for manual cleanup).
