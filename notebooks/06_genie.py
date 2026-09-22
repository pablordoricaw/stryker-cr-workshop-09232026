# Databricks notebook source
# ruff: noqa: F821
# MAGIC %md
# MAGIC # 06 · Genie agent over gold + metrics
# MAGIC
# MAGIC Build a curated **Genie agent** — a natural-language interface — over the
# MAGIC Finance data you governed in the earlier modules. You will attach the two
# MAGIC gold tables and the two Metric Views, give the agent pre-authored sample
# MAGIC questions and instructions, and confirm it answers Finance questions
# MAGIC sanely. Run `05_metric_views` first.
# MAGIC
# MAGIC The agent is created in **your existing workshop schema's** catalog — it
# MAGIC creates no catalog and no second schema. It only *reads* the gold tables
# MAGIC and Metric Views you already built.

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ Pre-check: Partner-powered AI must be enabled
# MAGIC
# MAGIC Genie is an AI feature. Before it will answer anything, your workspace must
# MAGIC have **Partner-powered AI features** (which enable the Databricks Assistant
# MAGIC that Genie is built on) turned **on**:
# MAGIC
# MAGIC - **Settings → Advanced → Partner-powered AI features** must be enabled at
# MAGIC   the account/workspace level (an admin toggle).
# MAGIC - You need **CAN USE** on a **Pro or Serverless SQL warehouse** (the same
# MAGIC   warehouse the agent runs its generated SQL on).
# MAGIC
# MAGIC If Genie is disabled, agent creation and the checkpoint below will fail with
# MAGIC a permissions/feature error — ask your workspace admin to enable it. Genie
# MAGIC agent APIs may be **Preview/entitlement-gated** on some workspaces.

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
# MAGIC ## 1. Use your existing workshop schema and name your agent
# MAGIC
# MAGIC A Genie agent is **workspace-scoped**, and your whole team shares one
# MAGIC workspace — so a fixed agent name would collide with your teammates'. Give
# MAGIC your agent a **per-participant name** derived from your identity, so every
# MAGIC participant gets their own agent.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = domain name)")
dbutils.widgets.text("volume", "landing", "UC Volume")

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
)

gold_sales = workshop.fully_qualified(config.catalog, config.schema, "gold_sales")
gold_contracts = workshop.fully_qualified(
    config.catalog, config.schema, "gold_contract_performance"
)
sales_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_sales_metrics"
)
contract_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "finance_contract_metrics"
)

# TODO: Build your per-participant agent name from your Databricks identity, so
# TODO: it never collides with a teammate's. Something like:
# TODO:   me = spark.sql("SELECT current_user()").collect()[0][0]
# TODO:   suffix = "".join(c if c.isalnum() else "_" for c in me.split("@")[0]).strip("_").lower()
# TODO:   agent_name = f"workshop_genie_{config.domain}_{suffix}"
agent_name = None

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — a unique, identity-derived agent name</summary>
# MAGIC
# MAGIC ```python
# MAGIC me = spark.sql("SELECT current_user()").collect()[0][0]        # you@company.com
# MAGIC suffix = "".join(c if c.isalnum() else "_" for c in me.split("@")[0]).strip("_").lower()
# MAGIC agent_name = f"workshop_genie_{config.domain}_{suffix}"
# MAGIC ```
# MAGIC
# MAGIC The checkpoint asserts **your own** agent by this exact name — there is no
# MAGIC shared default. Two participants in the same workspace each pass with their
# MAGIC own agent.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create the Genie agent over gold + metrics
# MAGIC
# MAGIC You can build the agent two ways — both reach the same checkable state:
# MAGIC
# MAGIC - **UI:** New → Genie space, attach the two gold tables and two Metric
# MAGIC   Views, title it exactly your `agent_name`, and add the sample questions.
# MAGIC - **Code:** create it with the Databricks SDK (`WorkspaceClient().genie`)
# MAGIC   from a `serialized_space` JSON payload.
# MAGIC
# MAGIC Attach **all four**: `gold_sales`, `gold_contract_performance`,
# MAGIC `finance_sales_metrics`, `finance_contract_metrics`. The gold tables answer
# MAGIC transaction-detail questions; the Metric Views answer governed-KPI
# MAGIC questions.

# COMMAND ----------

# TODO: Create (or update) a Genie agent titled exactly `agent_name`, attached to
# TODO: the two gold tables and the two Metric Views, with a few Finance sample
# TODO: questions. Then capture its space id, e.g. `space_id = ...`.


# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — create the agent with the SDK</summary>
# MAGIC
# MAGIC ```python
# MAGIC import json, uuid
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC
# MAGIC w = WorkspaceClient()
# MAGIC warehouse_id = next(wh.id for wh in w.warehouses.list())        # a Pro/Serverless warehouse
# MAGIC
# MAGIC serialized = json.dumps({
# MAGIC   "version": 2,
# MAGIC   "data_sources": {
# MAGIC     "tables": sorted([{"identifier": t} for t in (
# MAGIC        f"{config.catalog}.{config.schema}.gold_sales",
# MAGIC        f"{config.catalog}.{config.schema}.gold_contract_performance")],
# MAGIC        key=lambda x: x["identifier"]),
# MAGIC     "metric_views": sorted([{"identifier": m} for m in (
# MAGIC        f"{config.catalog}.{config.schema}.finance_sales_metrics",
# MAGIC        f"{config.catalog}.{config.schema}.finance_contract_metrics")],
# MAGIC        key=lambda x: x["identifier"]),
# MAGIC   },
# MAGIC   "config": {"sample_questions": sorted(
# MAGIC      [{"id": uuid.uuid4().hex, "question": [q]} for q in [
# MAGIC         "What were total net sales by product family?",
# MAGIC         "Which sales region had the highest gross margin?"]],
# MAGIC      key=lambda x: x["id"])},
# MAGIC })
# MAGIC
# MAGIC parent = f"/Workspace/Users/{me}/genie_spaces"
# MAGIC w.workspace.mkdirs(parent)
# MAGIC space = w.genie.create_space(warehouse_id, serialized, title=agent_name, parent_path=parent)
# MAGIC space_id = space.space_id
# MAGIC ```
# MAGIC
# MAGIC The full solution (sample questions, instructions, and an idempotent
# MAGIC create-or-update) is in `solutions/finance/06_genie.py`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Ask your agent a question
# MAGIC
# MAGIC Confirm the pre-authored questions return sane answers before the
# MAGIC checkpoint does the same.

# COMMAND ----------

# TODO: Ask a Finance question and inspect the generated SQL + answer, e.g.:
# TODO:   msg = w.genie.start_conversation_and_wait(space_id, "What were total net sales by product family?")
# TODO:   for a in (msg.attachments or []):
# TODO:       print(getattr(a.query, "query", None) or getattr(a.text, "content", None))


# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `06_genie`
# MAGIC
# MAGIC The check reads only observable Genie state: it finds **your** agent by
# MAGIC name, confirms it is attached to the expected gold tables and Metric Views,
# MAGIC and asks the benchmark questions — requiring each to return SQL grounded in
# MAGIC your curated data. It fails if the agent is missing, misconfigured, or
# MAGIC answers with no/irrelevant SQL.
# MAGIC
# MAGIC If the Conversation API is gated on your workspace, pass
# MAGIC `ask_benchmarks=False` to check structure only.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

result = workshop.check(
    "06_genie",
    catalog=config.catalog,
    schema=config.schema,
    genie=WorkspaceClient(),
    agent_name=agent_name,
    genie_space_id=space_id,  # optional; omit to resolve by name
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — tune your agent
# MAGIC
# MAGIC Add **text instructions** (e.g. default fiscal-year handling), **example
# MAGIC SQL** for a tricky question shape, or per-column **synonyms** so Genie maps
# MAGIC business language to your columns. Then re-ask a question and watch the
# MAGIC generated SQL improve. For a custom domain, pass `expected_sources=[...]`
# MAGIC and `benchmark_questions=[...]` to `workshop.check` to validate your own
# MAGIC agent.
