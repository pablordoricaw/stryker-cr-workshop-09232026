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
# MAGIC ## ✅ Teardown complete
# MAGIC
# MAGIC Your personal instructions no longer carry the workshop hint block. Any
# MAGIC instructions of your own are exactly as you left them.
