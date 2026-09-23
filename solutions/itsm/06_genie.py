# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Genie agent over gold + metrics — SOLUTION (ITSM)
# MAGIC
# MAGIC This solution creates (or updates, idempotently) a **per-participant Genie
# MAGIC agent** in the participant's existing catalog, curated over the #8 gold
# MAGIC tables and #10 Metric Views. It attaches all four data assets, adds
# MAGIC pre-authored ITSM sample questions, short text instructions, and
# MAGIC benchmark Q&A, then verifies observable state with the `06_genie`
# MAGIC checkpoint. No catalog or additional schema is created.
# MAGIC
# MAGIC **Prerequisite:** Partner-powered AI features (Databricks Assistant) must be
# MAGIC enabled and you need CAN USE on a Pro/Serverless SQL warehouse. Genie agent
# MAGIC APIs may be Preview/entitlement-gated on some workspaces.

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
dbutils.widgets.dropdown("domain", "itsm", ["itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("warehouse_id", "", "SQL warehouse id (blank = auto-detect)")

# COMMAND ----------

# Your identity resolves the SAME per-participant workshop_<you> schema 00_setup
# created, and your namespace — the one source of truth for every unique name in
# the shared workspace (here, your Genie agent title).
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)

ns = workshop.namespace(me, domain=config.domain)

gold_incidents = f"{config.catalog}.{config.schema}.gold_incidents"
gold_performances = f"{config.catalog}.{config.schema}.gold_service_performance"
incident_metrics = f"{config.catalog}.{config.schema}.itsm_incident_metrics"
performance_metrics = f"{config.catalog}.{config.schema}.itsm_service_metrics"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Per-participant agent name (identity-derived)
# MAGIC
# MAGIC A Genie agent is workspace-scoped and the team shares one workspace, so the
# MAGIC name must be unique per participant. Derive it from `current_user()`.

# COMMAND ----------

# The agent title comes from your namespace, so it is unique per participant and
# the checkpoint (below, via namespace=ns) resolves the exact same name.
agent_name = ns.genie_agent_name()
print(f"Agent name: {agent_name}")
print(f"Signed in as: {me}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build the serialized space payload
# MAGIC
# MAGIC Attach the two gold tables (transaction/performance detail) and the two Metric
# MAGIC Views (governed KPIs). All id-keyed arrays must be sorted by `id`, and data
# MAGIC sources by `identifier`.

# COMMAND ----------

import json, uuid


def _newid() -> str:
    return uuid.uuid4().hex


sample_questions = [
    "What is MTTR by service?",
    "Show incident volume by priority.",
    "Which assignment group has the most SLA breaches?",
    "Which service has the highest P1 incident volume?",
    "Show affected configuration-item counts by service.",
]

# Benchmark questions with checked SQL over the governed Metric Views.
benchmarks = [
    (
        "Show incident volume by priority.",
        f"SELECT `Priority`, MEASURE(`Incident Volume`) AS incident_volume FROM {incident_metrics} GROUP BY ALL ORDER BY incident_volume DESC",
    ),
    (
        "What is MTTR by service?",
        f"SELECT `Service`, MEASURE(`MTTR Hours`) AS mttr_hours FROM {incident_metrics} GROUP BY ALL ORDER BY mttr_hours DESC",
    ),
]

text_instructions = [
    "## PURPOSE",
    "- Answer ITSM questions about incident volume, MTTR, SLA breaches, services, and configuration items.",
    "- Users are IT operations analysts — use governed ITSM Metric Views for aggregates.",
    "",
    "## DISAMBIGUATION",
    "- MTTR means the average resolution_hours for resolved incidents.",
    "- Prefer itsm_incident_metrics for priority/service/group questions.",
    "- Use itsm_service_metrics for the compact service performance mart.",
    "",
    "## Instructions you must follow when providing summaries",
    "- State whether the answer is ticket or service/priority grain.",
    "- Round MTTR hours to two decimal places.",
]

serialized_space = json.dumps(
    {
        "version": 2,
        "config": {
            "sample_questions": sorted(
                [{"id": _newid(), "question": [q]} for q in sample_questions],
                key=lambda x: x["id"],
            )
        },
        "data_sources": {
            "tables": sorted(
                [{"identifier": gold_incidents}, {"identifier": gold_performances}],
                key=lambda x: x["identifier"],
            ),
            "metric_views": sorted(
                [{"identifier": incident_metrics}, {"identifier": performance_metrics}],
                key=lambda x: x["identifier"],
            ),
        },
        "instructions": {
            "text_instructions": [{"id": _newid(), "content": text_instructions}],
        },
        "benchmarks": {
            "questions": sorted(
                [
                    {
                        "id": _newid(),
                        "question": [q],
                        "answer": [{"format": "SQL", "content": [sql]}],
                    }
                    for q, sql in benchmarks
                ],
                key=lambda x: x["id"],
            )
        },
    }
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create or update the agent (idempotent)
# MAGIC
# MAGIC Look up an existing agent by title; update it if present, else create it.
# MAGIC Re-running this cell is safe.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Resolve a SQL warehouse (widget override, else the first available).
warehouse_id = dbutils.widgets.get("warehouse_id") or None
if not warehouse_id:
    warehouse_id = next((wh.id for wh in w.warehouses.list()), None)
if not warehouse_id:
    raise RuntimeError(
        "No SQL warehouse available. Create a Pro/Serverless warehouse or set the "
        "warehouse_id widget."
    )

home = ns.owner_path()  # your own workspace namespace (/Workspace/Users/<me>)
parent_path = f"{home}/genie_spaces"
w.workspace.mkdirs(parent_path)


def _pages():
    token = None
    while True:
        resp = w.genie.list_spaces(page_token=token)
        yield from (resp.spaces or [])
        token = resp.next_page_token
        if not token:
            return


def _canon(path):
    # Genie returns parent_path without the /Workspace prefix, so normalize both.
    p = (path or "").rstrip("/")
    return p[len("/Workspace"):] if p.startswith("/Workspace/") else p


def _under_home(path):
    p, h = _canon(path), _canon(home)
    return bool(h) and (p == h or p.startswith(h + "/"))


# Only ever update an agent that is demonstrably YOURS (same title AND living
# under your own workspace path). A same-title agent owned by a teammate is left
# untouched — we create our own instead — so we never overwrite someone else's.
owned = None
for s in _pages():
    if (s.title or "").strip() != agent_name:
        continue
    full = w.genie.get_space(s.space_id, include_serialized_space=True)
    if _under_home(full.parent_path):
        owned = full
        break

if owned is not None:
    space = w.genie.update_space(
        owned.space_id,
        serialized_space=serialized_space,
        title=agent_name,
        warehouse_id=warehouse_id,
        etag=owned.etag,
    )
    print(f"Updated your agent: {space.space_id}")
else:
    space = w.genie.create_space(
        warehouse_id,
        serialized_space,
        title=agent_name,
        parent_path=parent_path,
    )
    print(f"Created your agent: {space.space_id}")

space_id = space.space_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Ask a ITSM question

# COMMAND ----------

msg = w.genie.start_conversation_and_wait(space_id, "What is MTTR by service?")
print("status:", msg.status)
for attachment in msg.attachments or []:
    if attachment.query is not None:
        print("SQL:", attachment.query.query)
    if attachment.text is not None:
        print("TEXT:", attachment.text.content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `06_genie`

# COMMAND ----------

result = workshop.check(
    "06_genie",
    catalog=config.catalog,
    schema=config.schema,
    genie=w,
    namespace=ns,  # derives your agent title AND owner_path — one source of truth
    genie_space_id=space_id,
    expected_sources=["gold_incidents", "gold_service_performance", "itsm_incident_metrics", "itsm_service_metrics"],
    benchmark_questions=["Show incident volume by priority.", "What is MTTR by service?"],
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — tune the agent
# MAGIC
# MAGIC Add per-column synonyms/descriptions via `data_sources.tables[].column_configs`,
# MAGIC example SQL for a tricky question shape, or refine the text instructions,
# MAGIC then re-run cell 3 and re-ask. For another domain, attach that domain's gold
# MAGIC tables and Metric Views and pass matching `expected_sources` and
# MAGIC `benchmark_questions` to `workshop.check`.
