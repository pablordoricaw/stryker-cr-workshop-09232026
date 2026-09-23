# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Governed metadata with dbxmetagen
# MAGIC
# MAGIC Turn the gold tables into *governed* tables by generating and applying
# MAGIC metadata with [**dbxmetagen**](https://github.com/databricks-industry-solutions/dbxmetagen)
# MAGIC in its three modes:
# MAGIC
# MAGIC - **`comment`** — AI-generated table and column descriptions;
# MAGIC - **`pi`** — PII/PHI/PCI classification tags on sensitive columns; and
# MAGIC - **`domain`** — a business-domain tag on each table.
# MAGIC
# MAGIC It documents whichever two gold tables your domain built in `03_gold`
# MAGIC (derived for you below). The governance model is **stage → review →
# MAGIC apply**: every run defaults to `apply_ddl=false`, so metadata is staged into
# MAGIC review tables and *nothing* touches Unity Catalog until you approve it. You
# MAGIC review, then re-run with `apply_ddl=true` to apply.
# MAGIC
# MAGIC Run `03_gold` first. Fill in each **`# TODO`** cell, then run the checkpoint.
# MAGIC This notebook uses the existing catalog from `00_setup`; it never creates a
# MAGIC catalog.
# MAGIC
# MAGIC **Getting unstuck.** Ask **Genie Code** in the workspace for a graded hint —
# MAGIC a nudge, then an API shape, then the gated `solutions/<domain>/` file for
# MAGIC this checkpoint, one rung at a time — or open a collapsible **💡 Hint**
# MAGIC below. If Genie Code is unavailable (e.g. Free Edition), open that solution
# MAGIC file for your domain and this checkpoint directly.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install dbxmetagen (pinned, vendored wheel)
# MAGIC
# MAGIC dbxmetagen is installed notebook-only and **pinned to `v0.10.68`** for
# MAGIC reproducibility. Instead of `%pip install git+…` — which clones *and builds*
# MAGIC dbxmetagen from GitHub at runtime and **hangs on workspaces without
# MAGIC github.com egress** — we install a **prebuilt wheel vendored in the repo**
# MAGIC under [`libs/`](../libs/README.md). The install still resolves dbxmetagen's
# MAGIC dependency tree (`mlflow`, `openai`, …) from **PyPI**, so it needs PyPI egress.
# MAGIC
# MAGIC **No PyPI access?** The precheck below stops in seconds with instructions:
# MAGIC skip the install and every dbxmetagen cell, and run the **🛟 No-PyPI
# MAGIC fallback** section to document the tables by hand.
# MAGIC
# MAGIC Run these first; `restartPython()` restarts the interpreter so the freshly
# MAGIC installed library is importable in the cells below.

# COMMAND ----------

# Egress precheck: dbxmetagen's install resolves its dependency tree from PyPI.
# Fail fast (seconds) with instructions instead of hanging if PyPI is unreachable.
import urllib.request

try:
    urllib.request.urlopen("https://pypi.org/simple/", timeout=5)
    print("✅ PyPI reachable — run the %pip cell below, then continue.")
except Exception as exc:  # any failure ⇒ treat PyPI as unreachable
    raise RuntimeError(
        f"No PyPI egress from this workspace ({type(exc).__name__}). dbxmetagen's "
        "dependencies cannot be installed here. Skip the %pip cell and every "
        "dbxmetagen cell below, and run the '🛟 No-PyPI fallback' section to "
        "document the tables by hand."
    ) from exc

# COMMAND ----------

# MAGIC %pip install -qqq ../libs/dbxmetagen-0.10.68-py3-none-any.whl
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# --- Workshop bootstrap: run this after the pip restart ---
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
# MAGIC ## 1. Read your workshop config
# MAGIC
# MAGIC Enter the same existing catalog and schema you used in `00_setup`, and keep
# MAGIC the same domain. Your domain's two gold tables are derived below.
# MAGIC
# MAGIC - **`model_endpoint`** is the Foundation Model endpoint dbxmetagen calls.
# MAGIC   It defaults to `databricks-claude-sonnet-4-6`. **Confirm that endpoint
# MAGIC   exists** under **Serving → Foundation Models** in your workspace (its
# MAGIC   availability is region-dependent), or set this widget to another endpoint
# MAGIC   you can access. This is the *only* place you pick an endpoint — the AI
# MAGIC   Functions in `02_silver_docs` (`ai_parse_document` / `ai_classify` /
# MAGIC   `ai_extract`) use Databricks' built-in system model with no endpoint to
# MAGIC   select.
# MAGIC - **`domain_tag_name`** / **`pi_classification_tag_name`** are the UC tag
# MAGIC   keys dbxmetagen writes (defaults `domain` / `data_classification`). Change
# MAGIC   them here if your metastore enforces a tag policy on the defaults (see §4).
# MAGIC   The same values flow to dbxmetagen *and* the checkpoint, so they stay in
# MAGIC   sync.
# MAGIC
# MAGIC dbxmetagen writes its review/log tables into your **resolved schema** — the
# MAGIC single schema `00_setup` provisioned. No second schema is created.

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "finance", ["finance", "security", "itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")
dbutils.widgets.text("model_endpoint", "databricks-claude-sonnet-4-6", "FM endpoint")
dbutils.widgets.text("domain_tag_name", "domain", "Domain tag key")
dbutils.widgets.text("pi_classification_tag_name", "data_classification", "PI tag key")

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
model_endpoint = dbutils.widgets.get("model_endpoint") or "databricks-claude-sonnet-4-6"
domain_tag_name = dbutils.widgets.get("domain_tag_name") or "domain"
pi_classification_tag_name = (
    dbutils.widgets.get("pi_classification_tag_name") or "data_classification"
)

# The single source of truth for this domain's transactional-track names. The
# gold tables to document (built by 03_gold) are your domain's detail + mart.
spec = workshop.domain_spec(config.domain)
target_tables = list(spec.metadata_tables)
table_names = ",".join(
    f"{config.catalog}.{config.schema}.{table}" for table in target_tables
)

print(f"Domain        : {config.domain}")
print(f"Documenting   : {table_names}")
print(f"Model endpoint: {model_endpoint}   (confirm it exists in Serving)")
print(f"dbxmetagen output schema: {config.catalog}.{config.schema}")
print(f"Tag keys: domain={domain_tag_name}, pi={pi_classification_tag_name}")

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
# MAGIC > ⏳ **Heads up — this is slow.**
# MAGIC >
# MAGIC > Each mode re-invokes the foundation-model endpoint once per target table. A single staging or apply pass takes several minutes (longer on cold/scale-to-zero endpoints). This is expected — let it run.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Stage metadata for review (`apply_ddl=false`)
# MAGIC
# MAGIC Run dbxmetagen once per mode with `apply_ddl=false`. Each run sends the
# MAGIC gold tables' schema (and, by default, a small row sample) to your model
# MAGIC endpoint, generates metadata, and **stages** it in the review tables —
# MAGIC nothing is written to Unity Catalog yet.

# COMMAND ----------

from dbxmetagen.main import main

# TODO: Stage all three modes with apply_ddl=false.
#
# For each mode in ("comment", "pi", "domain"), call dbxmetagen's main() with:
#   - catalog_name                = config.catalog   (the catalog being documented)
#   - schema_name                 = config.schema    (your ONE resolved schema)
#   - table_names                 = table_names      (gold tables, comma-separated)
#   - table_names_source          = "parameter"
#   - model                       = model_endpoint
#   - mode                        = the mode
#   - apply_ddl                   = False            (stage only — do not apply yet)
#   - include_deterministic_pi    = False            (LLM-based PI only — no spaCy/Presidio)
#   - domain_tag_name             = domain_tag_name          (keep keys in sync)
#   - pi_classification_tag_name  = pi_classification_tag_name

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint — stage the three modes

# COMMAND ----------

# MAGIC %md
# MAGIC ```python
# MAGIC for mode in ("comment", "pi", "domain"):
# MAGIC     main({
# MAGIC         "catalog_name": config.catalog,
# MAGIC         "schema_name": config.schema,
# MAGIC         "table_names": table_names,
# MAGIC         "table_names_source": "parameter",
# MAGIC         "model": model_endpoint,
# MAGIC         "mode": mode,
# MAGIC         "apply_ddl": False,
# MAGIC         "include_deterministic_pi": False,  # LLM-based PI only (no spaCy/Presidio)
# MAGIC         "domain_tag_name": domain_tag_name,
# MAGIC         "pi_classification_tag_name": pi_classification_tag_name,
# MAGIC     })
# MAGIC ```
# MAGIC
# MAGIC dbxmetagen generates one mode at a time. `comment` first is a good habit —
# MAGIC the other modes reuse its context. `schema_name` is your single resolved
# MAGIC schema, so the review tables land beside the gold tables.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Review the staged metadata
# MAGIC
# MAGIC dbxmetagen wrote the generated comments, PI classifications, and domain
# MAGIC tags to review/log tables in your resolved schema `<catalog>.<schema>`
# MAGIC (e.g. `metadata_generation_log`, `column_knowledge_base`), beside the gold
# MAGIC tables. Inspect them and confirm the output looks right before applying.

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {config.catalog}.{config.schema}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Apply the approved metadata (`apply_ddl=true`)
# MAGIC
# MAGIC Once the staged metadata looks right, apply it. Re-run each mode with
# MAGIC `apply_ddl=true` (and `apply_tags=true` so the PI and domain tags are
# MAGIC written as UC-native tags). This issues the `COMMENT ON …` and
# MAGIC `ALTER … SET TAGS` statements against your gold tables.
# MAGIC
# MAGIC > **If your metastore enforces a UC tag policy** on the `domain` or
# MAGIC > `data_classification` tag keys, `SET TAGS` fails with
# MAGIC > `UC_TAG_POLICY_VALUE_NOT_ALLOWED`. The fix is executable here: set the
# MAGIC > **`domain_tag_name`** / **`pi_classification_tag_name`** widgets in §1 to a
# MAGIC > key your metastore permits (e.g. `business_domain`) and re-run. Those
# MAGIC > values flow to both dbxmetagen and the checkpoint, so they stay in sync.

# COMMAND ----------

# TODO: Apply all three modes with apply_ddl=true and apply_tags=true.
# Same main() calls as the staging step (still passing schema_name=config.schema,
# include_deterministic_pi=False, and the two *_tag_name options), but with
# apply_ddl=True and apply_tags=True.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 💡 Hint — apply the reviewed metadata

# COMMAND ----------

# MAGIC %md
# MAGIC ```python
# MAGIC for mode in ("comment", "pi", "domain"):
# MAGIC     main({
# MAGIC         "catalog_name": config.catalog,
# MAGIC         "schema_name": config.schema,
# MAGIC         "table_names": table_names,
# MAGIC         "table_names_source": "parameter",
# MAGIC         "model": model_endpoint,
# MAGIC         "mode": mode,
# MAGIC         "apply_ddl": True,
# MAGIC         "apply_tags": True,
# MAGIC         "include_deterministic_pi": False,  # LLM-based PI only (no spaCy/Presidio)
# MAGIC         "domain_tag_name": domain_tag_name,
# MAGIC         "pi_classification_tag_name": pi_classification_tag_name,
# MAGIC     })
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 🛟 No-PyPI fallback — document the tables without dbxmetagen
# MAGIC
# MAGIC **Run this section only if the §0 egress precheck stopped you.** First run
# MAGIC the §0 *workshop bootstrap* cell (`import workshop`) and the §1 *config* cell
# MAGIC — neither needs dbxmetagen — then run the cell below. It reaches the *same*
# MAGIC Unity Catalog state the checkpoint verifies: a comment on every table and
# MAGIC column, a PI tag on the sensitive columns, and a business-domain tag on each
# MAGIC table, using hand-written DDL instead of dbxmetagen. Column comments are
# MAGIC derived from the column names (not AI-authored) — enough to document the
# MAGIC tables and pass the checkpoint.
# MAGIC
# MAGIC Comments always apply. The `SET TAGS` calls are **best-effort**: if your
# MAGIC metastore governs the `domain` / `data_classification` tag keys, they are
# MAGIC skipped with a warning — set the tag-key widgets in §1 to a permitted key
# MAGIC (as in §4) and re-run this cell.

# COMMAND ----------

# The sensitive columns to PI-classify come from the domain spec (resolved in §1),
# so this shared cell names no domain-specific table or column literal — your
# domain's participant tags their own columns, never another domain's.
def _bq(*parts):
    """Backtick-quote each identifier part and join with dots."""
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)


def apply_manual_metadata():
    """Comment every table/column and best-effort-tag PI + domain, from plain DDL."""
    for table in target_tables:
        fq = _bq(config.catalog, config.schema, table)
        desc = (
            f"{config.domain.capitalize()} gold table {table}, documented via the "
            "workshop no-PyPI fallback."
        ).replace("'", "''")
        spark.sql(f"COMMENT ON TABLE {fq} IS '{desc}'")

        cols = [
            row[0]
            for row in spark.sql(
                f"SELECT column_name FROM {_bq(config.catalog)}.information_schema.columns "
                f"WHERE table_schema = '{config.schema}' AND table_name = '{table}'"
            ).collect()
        ]
        for col in cols:
            col_desc = col.replace("_", " ").strip().capitalize().replace("'", "''")
            spark.sql(f"COMMENT ON COLUMN {fq}.{_bq(col)} IS '{col_desc}'")

        try:
            spark.sql(
                f"ALTER TABLE {fq} SET TAGS ('{domain_tag_name}' = '{config.domain}')"
            )
        except Exception as exc:  # governed tag policy may reject the value
            print(f"⚠️  domain tag not set on {table} ({type(exc).__name__}): {exc}")

        for col in spec.pii_columns.get(table, ()):
            if col in cols:
                try:
                    spark.sql(
                        f"ALTER TABLE {fq} ALTER COLUMN {_bq(col)} "
                        f"SET TAGS ('{pi_classification_tag_name}' = 'pii')"
                    )
                except Exception as exc:
                    print(f"⚠️  PI tag not set on {table}.{col} ({type(exc).__name__}): {exc}")

    print("Manual metadata applied. Re-run §5 checkpoint to verify.")


apply_manual_metadata()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Checkpoint: `04_metadata`
# MAGIC
# MAGIC This check reads only Unity Catalog state — `information_schema` comments
# MAGIC and tags. It fails if any target table or column is uncommented, if no
# MAGIC column carries the PI classification tag, or if any table is missing its
# MAGIC business-domain tag. It never inspects this notebook. Your domain's gold
# MAGIC tables are passed to the shared checkpoint from the spec.

# COMMAND ----------

result = workshop.check(
    "04_metadata",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    tables=target_tables,
    # Verify the same tag keys you generated with, so the two never drift.
    domain_tag_name=domain_tag_name,
    pi_tag_name=pi_classification_tag_name,
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Metadata complete
# MAGIC
# MAGIC The gold tables are governed: documented, PI-classified, and
# MAGIC domain-tagged — ready for Metric Views, Genie, and the app.
