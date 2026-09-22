"""The ``02_silver_docs`` checkpoint: documents parsed, classified, extracted.

Green once the participant has built the silver document-intelligence layer on
top of the ``01_bronze_docs`` bronze table:

1. **parse** every bronze document with ``ai_parse_document`` into text,
2. **classify** each into one of the domain's document classes with
   ``ai_classify``, landing a consolidated ``silver_docs`` table, and
3. **extract** class-specific structured fields with ``ai_extract`` into one
   per-class ``silver_<class>`` table.

Like ``01_bronze_docs``, it asserts only externally-observable Unity Catalog
state — table existence and row/class counts — never *how* the notebook parsed,
classified, or extracted. A participant can reach the same state with SQL AI
functions, PySpark ``expr``, a Declarative Pipeline, or anything else.

**Domain-generic expected shape.** No finance-only number is hardcoded: the
checkpoint reads the per-class document folders the workshop *ships* for the
run's domain (``data/<domain>/documents/<class>/*.pdf`` in the cloned Git folder,
located via the same repo anchor as the notebook bootstrap) and derives both the
expected document count and the expected class set from them. Finance ships 25
documents across 5 classes; Security (#13) and ITSM (#14) reuse this checkpoint
with their own folders, no edits.

Run it as::

    workshop.check("02_silver_docs", spark=spark,
                   catalog=config.catalog, schema=config.schema,
                   domain=config.domain)

Extras forwarded through ``ctx.extras``:

* ``domain`` — which shipped dataset determines the expected count/classes.
* ``docs_table`` — consolidated parsed+classified table (default ``silver_docs``).
* ``class_column`` — the predicted-class column in ``docs_table`` (default
  ``doc_class``).
* ``text_column`` — the parsed-text column in ``docs_table`` (default
  ``parsed_text``).
* ``class_table_prefix`` — prefix for the per-class extraction tables (default
  ``silver_``, so class ``vendor_invoice`` -> ``silver_vendor_invoice``).
* ``expected_classes`` + ``expected_docs`` — explicit overrides that bypass
  source derivation (both required together; a documented fallback for contexts
  where the committed source tree is not on disk).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workshop.bootstrap import find_repo_root
from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

SILVER_DOCS_CHECKPOINT_ID = "02_silver_docs"

#: Default consolidated parsed+classified table the solution registers; one row
#: per bronze document. Overridable via the ``docs_table`` extra.
DEFAULT_SILVER_DOCS_TABLE = "silver_docs"

#: Default columns the consolidated table carries. ``class_column`` holds the
#: ``ai_classify`` prediction; ``text_column`` the ``ai_parse_document`` output.
DEFAULT_CLASS_COLUMN = "doc_class"
DEFAULT_TEXT_COLUMN = "parsed_text"

#: Per-class ``ai_extract`` tables are ``<prefix><class>`` (e.g. class
#: ``vendor_invoice`` -> ``silver_vendor_invoice``). Overridable via the
#: ``class_table_prefix`` extra so maintainers who prefix differently still line
#: up with this checkpoint.
DEFAULT_CLASS_TABLE_PREFIX = "silver_"

#: Sub-folder of ``data/<domain>/`` whose per-class child folders define the
#: expected document classes and counts (matches the ``01_bronze_docs`` source).
DOCS_SUBDIR = "documents"


def silver_class_table(cls: str, prefix: str = DEFAULT_CLASS_TABLE_PREFIX) -> str:
    """Per-class extraction table name for a class (``silver_<class>``).

    The solution and this checkpoint agree on this single naming rule so the
    check can find the tables ``ai_extract`` wrote without inspecting the
    notebook.
    """
    return f"{prefix}{cls}"


def _source_class_counts(domain: str) -> dict[str, int] | None:
    """Map each shipped document class to its committed ``*.pdf`` count.

    Reads the per-class child folders of ``data/<domain>/documents`` (the same
    tree ``01_bronze_docs`` lands), resolving the repo root with the notebook
    bootstrap's anchor so it works from a Databricks Git folder at check time.
    Returns ``None`` when the repo root or the domain's source tree cannot be
    located (distinct from "found zero classes", which is an empty dict).
    """
    root = find_repo_root()
    if root is None:
        return None
    source = Path(root) / "data" / domain / DOCS_SUBDIR
    if not source.is_dir():
        return None
    counts: dict[str, int] = {}
    for child in sorted(source.iterdir()):
        if child.is_dir():
            counts[child.name] = sum(1 for _ in child.rglob("*.pdf"))
    return counts


def _row_count(spark: Any, fq_table: str) -> int | None:
    """Row count of ``fq_table``, or ``None`` if it does not exist / is unreadable."""
    try:
        return int(spark.sql(f"SELECT count(*) FROM {fq_table}").collect()[0][0])
    except Exception:  # noqa: BLE001 - "missing/unreadable" is a normal not-yet-done state
        return None


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(SILVER_DOCS_CHECKPOINT_ID, False, message, details)


@checkpoint(
    SILVER_DOCS_CHECKPOINT_ID,
    summary=(
        "Every bronze document is parsed and classified into silver_docs, and "
        "ai_extract populates one silver_<class> table per class."
    ),
)
def check_silver_docs(ctx: CheckContext) -> CheckResult:
    """Assert the silver layer parsed, classified, and extracted every document."""
    spark = ctx.require_spark()
    catalog = ctx.catalog
    schema = ctx.schema
    domain = ctx.extras.get("domain")
    docs_table = ctx.extras.get("docs_table") or DEFAULT_SILVER_DOCS_TABLE
    class_column = ctx.extras.get("class_column") or DEFAULT_CLASS_COLUMN
    text_column = ctx.extras.get("text_column") or DEFAULT_TEXT_COLUMN
    class_prefix = ctx.extras.get("class_table_prefix") or DEFAULT_CLASS_TABLE_PREFIX
    override_classes = ctx.extras.get("expected_classes")
    override_docs = ctx.extras.get("expected_docs")

    if not catalog or not schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('02_silver_docs', "
            "spark=spark, catalog=config.catalog, schema=config.schema, "
            "domain=config.domain) — the notebook does this for you.",
            {"catalog": catalog, "schema": schema},
        )

    # What the silver layer SHOULD contain: the classes and document count the
    # workshop ships for this domain, unless both are explicitly overridden.
    # Kept domain-generic — no hardcoded number.
    if override_classes is not None and override_docs is not None:
        expected_classes = set(override_classes)
        expected_docs = int(override_docs)
    else:
        if not domain:
            return _fail(
                "Cannot determine the expected classes/count: pass "
                "domain=config.domain to workshop.check('02_silver_docs', ...) "
                "(or expected_classes=[...] and expected_docs=<n> together).",
                {"stage": "expected", "domain": domain},
            )
        counts = _source_class_counts(domain)
        if counts is None:
            return _fail(
                f"Could not locate the committed source documents for domain "
                f"'{domain}' (expected data/{domain}/{DOCS_SUBDIR}/ in the cloned "
                f"workshop Git folder). Open this notebook from inside the repo, "
                f"or pass expected_classes=[...] and expected_docs=<n>.",
                {"stage": "expected", "domain": domain},
            )
        expected_classes = {cls for cls, n in counts.items() if n > 0}
        expected_docs = sum(counts.values())

    if expected_docs <= 0 or not expected_classes:
        return _fail(
            f"No committed source PDFs found for domain '{domain}'; nothing to "
            f"validate against. Confirm data/{domain}/{DOCS_SUBDIR}/ contains the "
            f"shipped per-class document folders.",
            {"stage": "expected", "domain": domain, "expected_docs": expected_docs},
        )

    fq_docs = ctx.fully_qualified(docs_table)

    # 1. The consolidated parsed+classified table: does it exist, cover every
    #    bronze document, have parsed text and a valid predicted class for each?
    try:
        integrity = spark.sql(
            f"SELECT count(*) AS total, "
            f"count_if(`{text_column}` IS NULL OR `{text_column}` = '') AS blank_text, "
            f"count_if(`{class_column}` IS NULL) AS null_class "
            f"FROM {fq_docs}"
        ).collect()[0]
    except Exception as exc:  # noqa: BLE001 - surface as a clean, targeted failure
        return _fail(
            f"Silver table {fq_docs} is missing or unreadable "
            f"({type(exc).__name__}). Run notebooks/02_silver_docs to parse the "
            f"bronze documents with ai_parse_document and classify them with "
            f"ai_classify into {docs_table}.",
            {"stage": "silver_docs", "table": fq_docs, "error_type": type(exc).__name__},
        )

    total = int(integrity[0])
    blank_text = int(integrity[1])
    null_class = int(integrity[2])

    if total != expected_docs:
        return _fail(
            f"{fq_docs} has {total} row(s); expected {expected_docs} (one per "
            f"bronze document). Parse and classify every document from the "
            f"bronze_docs table into {docs_table}.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "row_count": total,
                "expected_docs": expected_docs,
            },
        )

    if blank_text > 0:
        return _fail(
            f"{blank_text} of {total} row(s) in {fq_docs} have no parsed text "
            f"(`{text_column}` null/empty). ai_parse_document must produce text "
            f"for every document before classification and extraction.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "blank_text": blank_text,
                "text_column": text_column,
            },
        )

    if null_class > 0:
        return _fail(
            f"{null_class} of {total} row(s) in {fq_docs} have no predicted class "
            f"(`{class_column}` is null). ai_classify must assign every document "
            f"one of the {len(expected_classes)} classes.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "null_class": null_class,
                "class_column": class_column,
            },
        )

    # Every predicted class must be one the workshop ships — a stray/hallucinated
    # label means classification drifted off the fixed label set.
    predicted = {
        row[0]
        for row in spark.sql(
            f"SELECT DISTINCT `{class_column}` FROM {fq_docs} "
            f"WHERE `{class_column}` IS NOT NULL"
        ).collect()
    }
    unexpected = predicted - expected_classes
    if unexpected:
        return _fail(
            f"{fq_docs} contains class label(s) {sorted(unexpected)} that are not "
            f"among the domain's classes {sorted(expected_classes)}. ai_classify "
            f"must route each document to one of the shipped classes.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "unexpected_classes": sorted(unexpected),
                "expected_classes": sorted(expected_classes),
            },
        )

    # 2. Per-class ai_extract tables: one per shipped class, and together they
    #    must cover every document (each classified doc extracted exactly once).
    missing_tables: list[str] = []
    per_class_counts: dict[str, int] = {}
    for cls in sorted(expected_classes):
        fq_cls = ctx.fully_qualified(silver_class_table(cls, class_prefix))
        n = _row_count(spark, fq_cls)
        if n is None:
            missing_tables.append(silver_class_table(cls, class_prefix))
        else:
            per_class_counts[cls] = n

    if missing_tables:
        return _fail(
            f"Missing per-class silver extraction table(s): {missing_tables}. "
            f"ai_extract must write a `{class_prefix}<class>` table for every "
            f"class in {docs_table}.",
            {
                "stage": "extract",
                "missing_tables": missing_tables,
                "expected_classes": sorted(expected_classes),
            },
        )

    per_class_total = sum(per_class_counts.values())
    if per_class_total != expected_docs:
        return _fail(
            f"Per-class silver extraction tables hold {per_class_total} row(s) "
            f"in total; expected {expected_docs} (one extracted row per "
            f"document). Extract every classified document into its "
            f"`{class_prefix}<class>` table. Per-class counts: {per_class_counts}.",
            {
                "stage": "extract",
                "per_class_counts": per_class_counts,
                "per_class_total": per_class_total,
                "expected_docs": expected_docs,
            },
        )

    return CheckResult(
        SILVER_DOCS_CHECKPOINT_ID,
        True,
        f"Silver layer ready: {fq_docs} parsed and classified all {total} "
        f"documents across {len(expected_classes)} classes, and ai_extract "
        f"populated {len(per_class_counts)} `{class_prefix}<class>` tables "
        f"holding all {per_class_total} of them.",
        {
            "stage": "done",
            "table": fq_docs,
            "row_count": total,
            "expected_docs": expected_docs,
            "expected_classes": sorted(expected_classes),
            "per_class_counts": per_class_counts,
        },
    )
