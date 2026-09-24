"""The ``01_bronze_docs`` checkpoint: raw documents landed and registered.

Green once the participant has (a) copied the committed source PDFs into their UC
Volume and (b) registered a bronze documents table over those raw files. It
asserts only externally-observable state, the count of PDFs under the volume's
``documents/`` folder and the bronze table's existence and row count, never
*how* the notebook did either, so a participant can reach the same state with
``dbutils.fs.cp``, a Spark write, ``read_files``, or anything else.

**Domain-generic expected count.** The bar is not a hardcoded number: the
checkpoint counts the ``*.pdf`` files the workshop *ships* for the run's domain
(``data/<domain>/documents/`` in the cloned Git folder, located via the same repo
anchor as the notebook bootstrap) and requires the volume's ``documents/`` folder
and the bronze table to each hold exactly that many. Finance ships 25; Security
(#13) and ITSM (#14) reuse this checkpoint with their own counts, no edits.

Run it as::

    workshop.check("01_bronze_docs", spark=spark,
                   catalog=config.catalog, schema=config.schema,
                   volume=config.volume, domain=config.domain)

Extras forwarded through ``ctx.extras``: ``volume`` (UC Volume name, as in
``00_setup``), ``domain`` (which shipped dataset sets the expected count),
``table`` (bronze table name, default ``bronze_docs``), and ``expected_docs`` (an
explicit expected count that overrides source-count derivation, a documented
fallback for contexts where the committed source tree is not on disk).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workshop.bootstrap import find_repo_root
from workshop.config import DEFAULT_VOLUME
from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

BRONZE_DOCS_CHECKPOINT_ID = "01_bronze_docs"

#: Default bronze table name the solution registers; overridable via the
#: ``table`` extra for maintainers who name it differently.
DEFAULT_BRONZE_TABLE = "bronze_docs"

#: Sub-folder of the UC Volume the documents are copied into (matches the
#: notebook/solution, which land ``data/<domain>/documents`` there). The probe is
#: scoped to this folder so unrelated PDFs elsewhere in the volume can neither
#: fail a valid bronze table nor mask a missing one.
DOCS_SUBDIR = "documents"


def _count_source_pdfs(domain: str) -> int | None:
    """Count committed ``*.pdf`` files under ``data/<domain>/documents``.

    Resolves the repo root with the same anchor the notebook bootstrap uses, so
    it works from a Databricks Git folder at check time. Returns ``None`` when
    the repo root or the domain's source tree cannot be located (a distinct,
    reportable condition from "found zero files").
    """
    root = find_repo_root()
    if root is None:
        return None
    source = Path(root) / "data" / domain / DOCS_SUBDIR
    if not source.is_dir():
        return None
    return sum(1 for _ in source.rglob("*.pdf"))


def _count_pdfs(spark: Any, path: str) -> int:
    """Count ``*.pdf`` files under ``path`` via the recursive ``binaryFile`` reader.

    Scoped to whatever ``path`` is passed (the volume's ``documents/`` folder),
    independent of how the files were copied or how the bronze table was built.
    """
    df = (
        spark.read.format("binaryFile")
        .option("recursiveFileLookup", "true")
        .option("pathGlobFilter", "*.pdf")
        .load(path)
    )
    return df.count()


def _table_row_count(spark: Any, fq_table: str) -> int | None:
    """Row count of ``fq_table``, or ``None`` if it does not exist / is unreadable."""
    try:
        return spark.sql(f"SELECT count(*) FROM {fq_table}").collect()[0][0]
    except Exception:  # noqa: BLE001 - "missing/unreadable" is a normal not-yet-done state
        return None


@checkpoint(
    BRONZE_DOCS_CHECKPOINT_ID,
    summary="Every shipped source PDF is in your UC Volume and the bronze_docs table registers them.",
)
def check_bronze_docs(ctx: CheckContext) -> CheckResult:
    """Assert the volume's ``documents/`` folder and the bronze table each hold
    exactly the number of PDFs the workshop ships for this domain."""
    spark = ctx.require_spark()
    catalog = ctx.catalog
    schema = ctx.schema
    volume = ctx.extras.get("volume") or DEFAULT_VOLUME
    table = ctx.extras.get("table") or DEFAULT_BRONZE_TABLE
    domain = ctx.extras.get("domain")
    expected = ctx.extras.get("expected_docs")

    if not catalog or not schema:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            "No catalog/schema to check. Call workshop.check('01_bronze_docs', "
            "spark=spark, catalog=config.catalog, schema=config.schema, "
            "volume=config.volume, domain=config.domain). The notebook does this "
            "for you.",
            {"catalog": catalog, "schema": schema},
        )

    # How many documents SHOULD be here: the count the workshop ships for this
    # domain (derived from the committed source), unless an explicit override is
    # passed. This keeps the bar domain-generic, with no hardcoded number.
    if expected is None:
        if not domain:
            return CheckResult(
                BRONZE_DOCS_CHECKPOINT_ID,
                False,
                "Cannot determine the expected document count: pass "
                "domain=config.domain to workshop.check('01_bronze_docs', ...) "
                "(or expected_docs=<n>).",
                {"stage": "expected", "domain": domain},
            )
        expected = _count_source_pdfs(domain)
        if expected is None:
            return CheckResult(
                BRONZE_DOCS_CHECKPOINT_ID,
                False,
                f"Could not locate the committed source documents for domain "
                f"'{domain}' (expected data/{domain}/{DOCS_SUBDIR}/ in the cloned "
                f"workshop Git folder). Open this notebook from inside the repo, or "
                f"pass expected_docs=<n>.",
                {"stage": "expected", "domain": domain},
            )
    if expected <= 0:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"No committed source PDFs found for domain '{domain}'; nothing to "
            f"validate against. Confirm data/{domain}/{DOCS_SUBDIR}/ contains the "
            f"shipped documents.",
            {"stage": "expected", "domain": domain, "expected": expected},
        )

    docs_path = f"/Volumes/{catalog}/{schema}/{volume}/{DOCS_SUBDIR}"
    fq_table = ctx.fully_qualified(table)

    # 1. Are the raw PDFs in the volume's documents/ folder? A missing/empty path
    #    raises here, which we turn into a targeted "run setup / the copy cell".
    try:
        pdf_count = _count_pdfs(spark, docs_path)
    except Exception as exc:  # noqa: BLE001 - surface as a clean, targeted failure
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"Could not read PDFs from {docs_path} ({type(exc).__name__}). Confirm "
            f"the UC Volume exists (run notebooks/00_setup) and re-run the cell "
            f"that copies the source PDFs into it.",
            {
                "stage": "volume",
                "docs_path": docs_path,
                "expected": expected,
                "error_type": type(exc).__name__,
            },
        )

    if pdf_count == 0:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"No PDFs found in {docs_path}; expected {expected}. Re-run the cell "
            f"that copies the committed source PDFs into your UC Volume.",
            {"stage": "volume", "docs_path": docs_path, "pdf_count": 0, "expected": expected},
        )

    if pdf_count != expected:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"Landed {pdf_count} PDF(s) in {docs_path} but the workshop ships "
            f"{expected} for domain '{domain}'. Re-run the copy cell so every "
            f"document lands.",
            {
                "stage": "volume",
                "docs_path": docs_path,
                "pdf_count": pdf_count,
                "expected": expected,
            },
        )

    # 2. Is the bronze table registered, and does it cover every shipped PDF?
    row_count = _table_row_count(spark, fq_table)
    if row_count is None:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"{pdf_count} PDFs are in {docs_path}, but the bronze table {fq_table} "
            f"is missing or unreadable. Run the cell that creates the bronze "
            f"documents table over the raw files.",
            {
                "stage": "table",
                "docs_path": docs_path,
                "pdf_count": pdf_count,
                "expected": expected,
                "table": fq_table,
            },
        )

    if row_count != expected:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"Bronze table {fq_table} has {row_count} row(s); expected {expected} "
            f"(one per committed document, matching the {pdf_count} in {docs_path}). "
            f"Re-create the bronze table so it registers every landed document.",
            {
                "stage": "table",
                "docs_path": docs_path,
                "pdf_count": pdf_count,
                "expected": expected,
                "row_count": row_count,
                "table": fq_table,
            },
        )

    return CheckResult(
        BRONZE_DOCS_CHECKPOINT_ID,
        True,
        f"Bronze layer ready: all {expected} shipped PDFs landed in {docs_path} "
        f"and {fq_table} registers all {row_count} of them.",
        {
            "stage": "done",
            "docs_path": docs_path,
            "pdf_count": pdf_count,
            "expected": expected,
            "row_count": row_count,
            "table": fq_table,
        },
    )
