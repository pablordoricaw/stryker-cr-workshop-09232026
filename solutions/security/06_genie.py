# Databricks notebook source
# ruff: noqa: F821, I001
# MAGIC %md
# MAGIC # 06 · Genie agent over gold + metrics — SOLUTION (Security)
# MAGIC
# MAGIC This solution creates (or updates, idempotently) a **per-participant Genie
# MAGIC agent** in the participant's existing catalog, curated over the #8 gold
# MAGIC tables and #10 Metric Views. It attaches all four data assets, adds
# MAGIC pre-authored Security sample questions, short text instructions, and
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
dbutils.widgets.dropdown("domain", "security", ["security"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("warehouse_id", "", "SQL warehouse id (blank = auto-detect)")

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

gold_findings = f"{config.catalog}.{config.schema}.gold_findings"
gold_cve_exposure = f"{config.catalog}.{config.schema}.gold_cve_exposure"
findings_metrics = f"{config.catalog}.{config.schema}.security_findings_metrics"
cve_metrics = f"{config.catalog}.{config.schema}.security_cve_metrics"

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
# MAGIC Attach the two gold tables (finding/CVE detail) and the two Metric Views
# MAGIC (governed KPIs). All id-keyed arrays must be sorted by `id`, and data
# MAGIC sources by `identifier`.

# COMMAND ----------

import json, uuid


def _newid() -> str:
    return uuid.uuid4().hex


sample_questions = [
    "How many open findings are there by severity?",
    "How many open critical findings are there by asset type?",
    "Which CVEs have the highest weighted risk?",
    "What is the total value at risk by environment?",
    "Which vulnerability categories have the most open critical findings?",
]

# Benchmark questions with checked SQL over the governed Metric Views.
benchmarks = [
    (
        "How many open findings are there by severity?",
        f"SELECT `Severity`, MEASURE(`Open Findings`) AS open_findings FROM {findings_metrics} GROUP BY ALL ORDER BY open_findings DESC",
    ),
    (
        "Which CVEs have the highest weighted risk?",
        f"SELECT `CVE ID`, MEASURE(`Weighted Risk`) AS weighted_risk FROM {cve_metrics} GROUP BY ALL ORDER BY weighted_risk DESC LIMIT 10",
    ),
]

text_instructions = [
    "## PURPOSE",
    "- Answer Security questions about vulnerability-scan findings, CVE exposure, remediation effort, and value at risk.",
    "- Users are security analysts — assume fluency with CVEs, CVSS, severity bands, and remediation SLAs.",
    "",
    "## DISAMBIGUATION",
    "- 'Open' means status = 'Open'. 'Critical' means severity = 'Critical' (CVSS >= 9.0).",
    "- For exposure/remediation by dimension, prefer the security_findings_metrics Metric View over raw gold_findings.",
    "- For per-CVE exposure, use security_cve_metrics or gold_cve_exposure.",
    "",
    "## Instructions you must follow when providing summaries",
    "- State the grain (finding, asset, severity, category, or CVE) used in the answer.",
    "- Report value at risk as a currency amount and remediation as hours.",
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
                [{"identifier": gold_findings}, {"identifier": gold_cve_exposure}],
                key=lambda x: x["identifier"],
            ),
            "metric_views": sorted(
                [{"identifier": findings_metrics}, {"identifier": cve_metrics}],
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
# MAGIC ## 4. Ask a Security question

# COMMAND ----------

msg = w.genie.start_conversation_and_wait(
    space_id, "How many open findings are there by severity?"
)
print("status:", msg.status)
for attachment in msg.attachments or []:
    if attachment.query is not None:
        print("SQL:", attachment.query.query)
    if attachment.text is not None:
        print("TEXT:", attachment.text.content)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `06_genie`
# MAGIC
# MAGIC The domain-generic check validates the agent by observable Genie state
# MAGIC only. The Security expected sources and benchmark questions are passed
# MAGIC through so the generic checkpoint grades this domain's agent.

# COMMAND ----------

result = workshop.check(
    "06_genie",
    catalog=config.catalog,
    schema=config.schema,
    genie=w,
    namespace=ns,  # derives your agent title AND owner_path — one source of truth
    genie_space_id=space_id,
    expected_sources=[
        "gold_findings",
        "gold_cve_exposure",
        "security_findings_metrics",
        "security_cve_metrics",
    ],
    benchmark_questions=[
        "How many open findings are there by severity?",
        "Which CVEs have the highest weighted risk?",
    ],
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — tune the agent
# MAGIC
# MAGIC Add per-column synonyms/descriptions via `data_sources.tables[].column_configs`,
# MAGIC example SQL for a tricky question shape (e.g. SLA breaches by owner team),
# MAGIC or refine the text instructions, then re-run cell 3 and re-ask.
