# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Genie agent over gold + metrics
# MAGIC
# MAGIC Build a curated **Genie agent** — a natural-language interface — over the
# MAGIC data you governed in the earlier modules for **your domain**. You will
# MAGIC attach the two gold tables and the two Metric Views, give the agent
# MAGIC pre-authored sample questions and instructions, and confirm it answers your
# MAGIC domain's questions sanely. Run `05_metric_views` first.
# MAGIC
# MAGIC The agent is created in **your existing workshop schema's** catalog — it
# MAGIC creates no catalog and no second schema. It only *reads* the gold tables
# MAGIC and Metric Views you already built.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

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
# MAGIC participant gets their own agent. This cell also derives your domain's gold
# MAGIC tables and Metric Views (the four data assets to attach).

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# COMMAND ----------

# Your identity resolves the SAME per-participant schema 00_setup created, and
# your namespace — the single source of truth for every unique name in the shared
# workspace (your schema, and here your Genie agent name).
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)

ns = workshop.namespace(me, domain=config.domain)

# The single source of truth for this domain's gold tables, Metric Views, and
# benchmark questions.
spec = workshop.domain_spec(config.domain)

gold_tables = [
    workshop.fully_qualified(config.catalog, config.schema, spec.detail_table),
    workshop.fully_qualified(config.catalog, config.schema, spec.mart_table),
]
metric_views = [
    workshop.fully_qualified(config.catalog, config.schema, name)
    for name in spec.metric_views
]
benchmark_questions = list(spec.genie_benchmark_questions)

# TODO: Name your agent from your namespace, so it never collides with a
# TODO: teammate's and the checkpoint resolves the exact same name:
# TODO:   agent_name = ns.genie_agent_name()
agent_name = None

print(f"Domain      : {config.domain}")
print(f"Gold tables : {gold_tables}")
print(f"Metric Views: {metric_views}")
print(f"Benchmarks  : {benchmark_questions}")

# COMMAND ----------

# MAGIC %md
# MAGIC <details>
# MAGIC <summary>💡 Hint — a unique, identity-derived agent name</summary>
# MAGIC
# MAGIC ```python
# MAGIC agent_name = ns.genie_agent_name()   # workshop_genie_<domain>_<you>
# MAGIC ```
# MAGIC
# MAGIC `ns = workshop.namespace(me, domain=config.domain)` (built above) is the one
# MAGIC source of truth: it derives your agent name from your identity, and the
# MAGIC checkpoint resolves that **same** name (pass `namespace=ns`) — so generation
# MAGIC and verification always agree. There is no shared default; two participants
# MAGIC in the same workspace each pass with their own agent.
# MAGIC </details>

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
# MAGIC ## 2. Create the Genie agent over gold + metrics
# MAGIC
# MAGIC You can build the agent two ways — both reach the same checkable state:
# MAGIC
# MAGIC - **UI:** New → Genie space, attach the two gold tables and two Metric
# MAGIC   Views, title it exactly your `agent_name`, and add the sample questions.
# MAGIC - **Code:** create it with the Databricks SDK (`WorkspaceClient().genie`)
# MAGIC   from a `serialized_space` JSON payload.
# MAGIC
# MAGIC Attach **all four** assets printed above (your two gold tables and two Metric
# MAGIC Views). The gold tables answer transaction-detail questions; the Metric
# MAGIC Views answer governed-KPI questions.

# COMMAND ----------

# TODO: Create (or update) a Genie agent titled exactly `agent_name`, attached to
# TODO: the `gold_tables` and `metric_views` derived above, with a few sample
# TODO: questions for your domain (`benchmark_questions` is a good start). Then
# TODO: capture its space id, e.g. `space_id = ...`.

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
# MAGIC     "tables": sorted([{"identifier": t} for t in gold_tables],
# MAGIC        key=lambda x: x["identifier"]),
# MAGIC     "metric_views": sorted([{"identifier": m} for m in metric_views],
# MAGIC        key=lambda x: x["identifier"]),
# MAGIC   },
# MAGIC   "config": {"sample_questions": sorted(
# MAGIC      [{"id": uuid.uuid4().hex, "question": [q]} for q in benchmark_questions],
# MAGIC      key=lambda x: x["id"])},
# MAGIC })
# MAGIC
# MAGIC parent = f"/Workspace/Users/{me}/genie_spaces"
# MAGIC w.workspace.mkdirs(parent)
# MAGIC space = w.genie.create_space(warehouse_id, serialized, title=agent_name, parent_path=parent)
# MAGIC space_id = space.space_id
# MAGIC ```
# MAGIC
# MAGIC The full solution (your domain's sample questions, instructions, and an
# MAGIC idempotent create-or-update) is in `solutions/<domain>/06_genie.py`.
# MAGIC </details>

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Ask your agent a question
# MAGIC
# MAGIC Confirm the pre-authored questions return sane answers before the
# MAGIC checkpoint does the same.

# COMMAND ----------

# TODO: Ask one of your `benchmark_questions` and inspect the generated SQL +
# TODO: answer, e.g.:
# TODO:   msg = w.genie.start_conversation_and_wait(space_id, benchmark_questions[0])
# TODO:   for a in (msg.attachments or []):
# TODO:       print(getattr(a.query, "query", None) or getattr(a.text, "content", None))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `06_genie`
# MAGIC
# MAGIC The check reads only observable Genie state: it finds **your** agent by
# MAGIC name, confirms it is attached to the expected gold tables and Metric Views,
# MAGIC and asks the benchmark questions — requiring each to return SQL grounded in
# MAGIC your curated data. It fails if the agent is missing, misconfigured, owned
# MAGIC by someone else (same title, different namespace), or answers with
# MAGIC no/irrelevant SQL.
# MAGIC
# MAGIC `namespace=ns` binds the check to **your** workspace namespace (deriving both
# MAGIC your agent name and owner_path) so a teammate's same-titled agent is never
# MAGIC adopted. Your domain's expected sources and benchmark questions are passed
# MAGIC from the spec. The agent must actually answer, so if the Conversation API is
# MAGIC gated the checkpoint stays **RED** — enable Partner-powered AI rather than
# MAGIC skipping the answer check.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

result = workshop.check(
    "06_genie",
    catalog=config.catalog,
    schema=config.schema,
    genie=WorkspaceClient(),
    namespace=ns,  # derives your agent name AND owner_path (one source of truth)
    genie_space_id=space_id,  # noqa: F821 — participant defines space_id above; optional, omit to resolve by name
    # Domain expected sources + benchmark questions for the shared checkpoint.
    expected_sources=list(spec.genie_expected_sources),
    benchmark_questions=benchmark_questions,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — tune your agent
# MAGIC
# MAGIC Add **text instructions** (e.g. default fiscal-year or SLA handling),
# MAGIC **example SQL** for a tricky question shape, or per-column **synonyms** so
# MAGIC Genie maps business language to your columns. Then re-ask a question and
# MAGIC watch the generated SQL improve. The `expected_sources` and
# MAGIC `benchmark_questions` above already validate your own domain's agent.
