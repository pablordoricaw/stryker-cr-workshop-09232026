"""The ``02_silver_docs`` checkpoint: documents parsed, classified, extracted.

Green once the participant has built the silver document-intelligence layer on
top of the ``01_bronze_docs`` bronze table:

1. **parse** every bronze document with ``ai_parse_document`` into text,
2. **classify** each into one of the domain's document classes with
   ``ai_classify``, landing a consolidated ``silver_docs`` table, and
3. **extract** class-specific structured fields with ``ai_extract`` into one
   per-class ``silver_<class>`` table.

Like ``01_bronze_docs``, it asserts only externally-observable Unity Catalog
state, table existence, per-document identity, and extraction success, never
*how* the notebook parsed, classified, or extracted. A participant can reach the
same state with SQL AI functions, PySpark ``expr``, a Declarative Pipeline, or
anything else.

**Per-document identity, not just a count.** The check derives the *set* of
shipped documents (``<class>/<filename>`` for each direct ``<class>/*.pdf`` the
workshop ships for the run's domain, located via the notebook bootstrap's repo
anchor) and requires the observed ``source_class``/``filename`` set in
``silver_docs`` to equal it exactly, so a missing document, a duplicate, or an
unexpected one all fail, where an aggregate count would not.

**Extraction must succeed, not merely produce a row.** ``ai_extract`` returns a
VARIANT with an ``error_message``; the solution persists it as an
``extract_error`` column. The check fails if *any* per-class row carries a
non-null ``extract_error``, so an all-null failed extraction cannot silently
satisfy the checkpoint.

**Domain-generic.** No finance-only number is hardcoded: Finance ships 25
documents across 5 classes; Security (#13) and ITSM (#14) reuse this checkpoint
with their own folders, no edits.

Run it as::

    workshop.check("02_silver_docs", spark=spark,
                   catalog=config.catalog, schema=config.schema,
                   domain=config.domain)

Extras forwarded through ``ctx.extras``:

* ``domain`` selects which shipped dataset determines the expected documents.
* ``docs_table`` is the consolidated parsed+classified table (default ``silver_docs``).
* ``class_column`` is the predicted-class column in ``docs_table`` (default
  ``doc_class``).
* ``text_column`` is the parsed-text column in ``docs_table`` (default
  ``parsed_text``).
* ``extract_error_column`` is the ``ai_extract`` error column in each per-class
  table (default ``extract_error``).
* ``class_table_prefix`` is the prefix for the per-class extraction tables (default
  ``silver_``, so class ``vendor_invoice`` -> ``silver_vendor_invoice``).
* ``expected_doc_keys`` is an explicit ``{"<class>/<filename>", ...}`` override
  that bypasses source derivation (a documented fallback for contexts where the
  committed source tree is not on disk).

``docs_table`` must carry ``source_class`` and ``filename`` columns (the bronze
layer provides both) so the check can reconstruct each document's identity;
per-class tables must carry ``path`` and the ``extract_error`` column.
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

#: Default per-class column that carries ``ai_extract``'s ``error_message`` (null
#: on success). A non-null value in any row fails the checkpoint.
DEFAULT_EXTRACT_ERROR_COLUMN = "extract_error"

#: Per-class ``ai_extract`` tables are ``<prefix><class>`` (e.g. class
#: ``vendor_invoice`` -> ``silver_vendor_invoice``). Overridable via the
#: ``class_table_prefix`` extra.
DEFAULT_CLASS_TABLE_PREFIX = "silver_"

#: Fixed identity columns. A document's identity is ``source_class/filename``
#: (its shipped ``<class>/<filename>``); ``path`` uniquely keys per-class rows.
ID_CLASS_COLUMN = "source_class"
ID_NAME_COLUMN = "filename"
ID_PATH_COLUMN = "path"

#: Sub-folder of ``data/<domain>/`` whose per-class child folders define the
#: shipped documents (matches the ``01_bronze_docs`` source layout).
DOCS_SUBDIR = "documents"


def silver_class_table(cls: str, prefix: str = DEFAULT_CLASS_TABLE_PREFIX) -> str:
    """Per-class extraction table name for a class (``silver_<class>``).

    The solution and this checkpoint agree on this single naming rule so the
    check can find the tables ``ai_extract`` wrote without inspecting the
    notebook.
    """
    return f"{prefix}{cls}"


def _source_doc_keys(domain: str) -> set[str] | None:
    """The set of shipped document identities ``{"<class>/<filename>", ...}``.

    Enumerates the *direct* ``<class>/*.pdf`` files under
    ``data/<domain>/documents`` (non-recursive within each class folder, so a
    nested/auxiliary PDF cannot inflate the expectation), resolving the repo root
    with the notebook bootstrap's anchor so it works from a Databricks Git folder
    at check time. Returns ``None`` when the repo root or the domain's source
    tree cannot be located (distinct from "found zero documents", an empty set).
    """
    root = find_repo_root()
    if root is None:
        return None
    source = Path(root) / "data" / domain / DOCS_SUBDIR
    if not source.is_dir():
        return None
    keys: set[str] = set()
    for child in sorted(source.iterdir()):
        if child.is_dir():
            for pdf in child.glob("*.pdf"):  # direct children only, not rglob
                keys.add(f"{child.name}/{pdf.name}")
    return keys


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(SILVER_DOCS_CHECKPOINT_ID, False, message, details)


@checkpoint(
    SILVER_DOCS_CHECKPOINT_ID,
    summary=(
        "Every shipped document is parsed and classified into silver_docs "
        "(one row each, valid class, non-blank text), and ai_extract populates "
        "one silver_<class> table per class with no extraction errors."
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
    err_column = ctx.extras.get("extract_error_column") or DEFAULT_EXTRACT_ERROR_COLUMN
    class_prefix = ctx.extras.get("class_table_prefix") or DEFAULT_CLASS_TABLE_PREFIX
    override_keys = ctx.extras.get("expected_doc_keys")

    if not catalog or not schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('02_silver_docs', "
            "spark=spark, catalog=config.catalog, schema=config.schema, "
            "domain=config.domain). The notebook does this for you.",
            {"catalog": catalog, "schema": schema},
        )

    # Which documents SHOULD be here: the exact set the workshop ships for this
    # domain (identity = "<class>/<filename>"), unless explicitly overridden.
    if override_keys is not None:
        expected_keys = set(override_keys)
    else:
        if not domain:
            return _fail(
                "Cannot determine the expected documents: pass "
                "domain=config.domain to workshop.check('02_silver_docs', ...) "
                "(or expected_doc_keys={...}).",
                {"stage": "expected", "domain": domain},
            )
        keys = _source_doc_keys(domain)
        if keys is None:
            return _fail(
                f"Could not locate the committed source documents for domain "
                f"'{domain}' (expected data/{domain}/{DOCS_SUBDIR}/ in the cloned "
                f"workshop Git folder). Open this notebook from inside the repo, "
                f"or pass expected_doc_keys={{...}}.",
                {"stage": "expected", "domain": domain},
            )
        expected_keys = keys

    if not expected_keys:
        return _fail(
            f"No committed source PDFs found for domain '{domain}'; nothing to "
            f"validate against. Confirm data/{domain}/{DOCS_SUBDIR}/ contains the "
            f"shipped per-class document folders.",
            {"stage": "expected", "domain": domain, "expected_docs": 0},
        )

    expected_classes = {key.split("/", 1)[0] for key in expected_keys}
    expected_docs = len(expected_keys)
    fq_docs = ctx.fully_qualified(docs_table)

    # 1. The consolidated table: exists, one row per shipped document (identity,
    #    not just a count), non-blank parsed text, a non-null predicted class.
    try:
        integrity = spark.sql(
            f"SELECT count(*) AS total, "
            f"count_if(`{text_column}` IS NULL OR trim(`{text_column}`) = '') AS blank_text, "
            f"count_if(`{class_column}` IS NULL) AS null_class, "
            f"count(DISTINCT concat_ws('/', `{ID_CLASS_COLUMN}`, `{ID_NAME_COLUMN}`)) AS distinct_keys "
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
    distinct_keys = int(integrity[3])

    if blank_text > 0:
        return _fail(
            f"{blank_text} of {total} row(s) in {fq_docs} have blank parsed text "
            f"(`{text_column}` null/empty/whitespace). ai_parse_document must "
            f"produce real text for every document before classification.",
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

    if distinct_keys != total:
        return _fail(
            f"{fq_docs} has {total} row(s) but only {distinct_keys} distinct "
            f"documents ({ID_CLASS_COLUMN}/{ID_NAME_COLUMN}), {total - distinct_keys} "
            f"duplicate row(s). Parse and classify each document exactly once.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "row_count": total,
                "distinct_keys": distinct_keys,
            },
        )

    # The observed document identities must equal the shipped set exactly:
    # catches missing, duplicate (already above), and unexpected documents.
    observed_keys = {
        row[0]
        for row in spark.sql(
            f"SELECT DISTINCT concat_ws('/', `{ID_CLASS_COLUMN}`, `{ID_NAME_COLUMN}`) "
            f"AS doc_key FROM {fq_docs}"
        ).collect()
    }
    missing = expected_keys - observed_keys
    unexpected = observed_keys - expected_keys
    if missing or unexpected:
        return _fail(
            f"{fq_docs} does not cover the shipped documents exactly: "
            f"{len(missing)} missing, {len(unexpected)} unexpected "
            f"(expected {expected_docs}). Parse and classify every shipped "
            f"document, and only those.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "missing": sorted(missing)[:10],
                "unexpected": sorted(unexpected)[:10],
                "expected_docs": expected_docs,
            },
        )

    # Every predicted class must be one the workshop ships, so a stray/hallucinated
    # label means classification drifted off the fixed label set.
    predicted = {
        row[0]
        for row in spark.sql(
            f"SELECT DISTINCT `{class_column}` FROM {fq_docs} "
            f"WHERE `{class_column}` IS NOT NULL"
        ).collect()
    }
    unexpected_classes = predicted - expected_classes
    if unexpected_classes:
        return _fail(
            f"{fq_docs} contains class label(s) {sorted(unexpected_classes)} that "
            f"are not among the domain's classes {sorted(expected_classes)}. "
            f"ai_classify must route each document to one of the shipped classes.",
            {
                "stage": "silver_docs",
                "table": fq_docs,
                "unexpected_classes": sorted(unexpected_classes),
                "expected_classes": sorted(expected_classes),
            },
        )

    # 2. Per-class ai_extract tables: one per shipped class, no extraction errors,
    #    and together they extract every document exactly once.
    missing_tables: list[str] = []
    per_class_counts: dict[str, int] = {}
    per_class_errors = 0
    per_class_distinct_total = 0
    for cls in sorted(expected_classes):
        fq_cls = ctx.fully_qualified(silver_class_table(cls, class_prefix))
        try:
            row = spark.sql(
                f"SELECT count(*) AS n, "
                f"count_if(`{err_column}` IS NOT NULL) AS errs, "
                f"count(DISTINCT `{ID_PATH_COLUMN}`) AS distinct_paths "
                f"FROM {fq_cls}"
            ).collect()[0]
        except Exception:  # noqa: BLE001 - missing/unreadable is a normal not-done state
            missing_tables.append(silver_class_table(cls, class_prefix))
            continue
        per_class_counts[cls] = int(row[0])
        per_class_errors += int(row[1])
        per_class_distinct_total += int(row[2])

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

    if per_class_errors > 0:
        return _fail(
            f"{per_class_errors} extracted row(s) across the "
            f"`{class_prefix}<class>` tables carry a non-null `{err_column}`, "
            f"ai_extract failed for them. A row with an extraction error does not "
            f"count as extracted; fix the inputs/schema so every extraction "
            f"succeeds.",
            {
                "stage": "extract",
                "extract_errors": per_class_errors,
                "extract_error_column": err_column,
            },
        )

    per_class_total = sum(per_class_counts.values())
    if per_class_distinct_total != per_class_total:
        return _fail(
            f"Per-class silver tables contain duplicate documents "
            f"({per_class_total} rows vs {per_class_distinct_total} distinct "
            f"paths). Extract each classified document exactly once.",
            {
                "stage": "extract",
                "per_class_total": per_class_total,
                "distinct_paths": per_class_distinct_total,
            },
        )

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
        f"Silver layer ready: {fq_docs} parsed and classified all {expected_docs} "
        f"shipped documents (one row each) across {len(expected_classes)} classes, "
        f"and ai_extract populated {len(per_class_counts)} `{class_prefix}<class>` "
        f"tables holding all {per_class_total} of them with no extraction errors.",
        {
            "stage": "done",
            "table": fq_docs,
            "row_count": total,
            "expected_docs": expected_docs,
            "expected_classes": sorted(expected_classes),
            "per_class_counts": per_class_counts,
        },
    )
