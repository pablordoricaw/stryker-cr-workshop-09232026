"""The ``01_bronze_docs`` checkpoint: raw documents landed and registered.

Green once the participant has (a) copied the committed source PDFs into their UC
Volume and (b) registered a bronze documents table over those raw files. It
asserts only externally-observable state — the count of PDFs in the volume and
the bronze table's existence and row count — never *how* the notebook did either,
so a participant can reach the same state with ``dbutils.fs.cp``, a Spark write,
``read_files``, or anything else.

Run it as::

    workshop.check("01_bronze_docs", spark=spark,
                   catalog=config.catalog, schema=config.schema,
                   volume=config.volume)

Two knobs are forwarded through ``ctx.extras`` and rarely need changing:
``volume`` (the UC Volume name, as in ``00_setup``) and ``table`` (the bronze
table name, default ``bronze_docs``).
"""

from __future__ import annotations

from typing import Any

from workshop.config import DEFAULT_VOLUME
from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

BRONZE_DOCS_CHECKPOINT_ID = "01_bronze_docs"

#: Default bronze table name the solution registers; overridable via the
#: ``table`` extra for maintainers who name it differently.
DEFAULT_BRONZE_TABLE = "bronze_docs"

#: The workshop ships 25 source PDFs (5 per class); ``>= 20`` tolerates a
#: participant who skips a class or two while still proving the ingestion ran.
MIN_DOCUMENTS = 20


def _count_pdfs_in_volume(spark: Any, volume_path: str) -> int:
    """Count ``*.pdf`` files anywhere under the UC Volume path.

    Uses the ``binaryFile`` reader with a recursive lookup so the count reflects
    the files actually present on the volume, independent of how they were
    copied there or how the bronze table was built.
    """
    df = (
        spark.read.format("binaryFile")
        .option("recursiveFileLookup", "true")
        .option("pathGlobFilter", "*.pdf")
        .load(volume_path)
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
    summary="Source PDFs are in your UC Volume and the bronze_docs table registers them.",
)
def check_bronze_docs(ctx: CheckContext) -> CheckResult:
    """Assert the PDFs landed in the volume and the bronze table matches them."""
    spark = ctx.require_spark()
    catalog = ctx.catalog
    schema = ctx.schema
    volume = ctx.extras.get("volume") or DEFAULT_VOLUME
    table = ctx.extras.get("table") or DEFAULT_BRONZE_TABLE

    if not catalog or not schema:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            "No catalog/schema to check. Call workshop.check('01_bronze_docs', "
            "spark=spark, catalog=config.catalog, schema=config.schema, "
            "volume=config.volume) — the notebook does this for you.",
            {"catalog": catalog, "schema": schema},
        )

    volume_path = f"/Volumes/{catalog}/{schema}/{volume}"
    fq_table = ctx.fully_qualified(table)

    # 1. Are the raw PDFs on the volume? A missing/empty volume raises here, which
    #    we turn into a targeted "run setup / the copy cell" message.
    try:
        pdf_count = _count_pdfs_in_volume(spark, volume_path)
    except Exception as exc:  # noqa: BLE001 - surface as a clean, targeted failure
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"Could not read PDFs from {volume_path} ({type(exc).__name__}). "
            f"Confirm the UC Volume exists (run notebooks/00_setup) and re-run the "
            f"cell that copies the source PDFs into it.",
            {
                "stage": "volume",
                "volume_path": volume_path,
                "error_type": type(exc).__name__,
            },
        )

    if pdf_count < MIN_DOCUMENTS:
        detail = (
            "No PDFs found" if pdf_count == 0 else f"Found only {pdf_count} PDF(s)"
        )
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"{detail} in {volume_path}; expected >= {MIN_DOCUMENTS}. Re-run the "
            f"cell that copies the committed source PDFs into your UC Volume.",
            {"stage": "volume", "volume_path": volume_path, "pdf_count": pdf_count},
        )

    # 2. Is the bronze table registered, and does it cover every landed PDF?
    row_count = _table_row_count(spark, fq_table)
    if row_count is None:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"{pdf_count} PDFs are in {volume_path}, but the bronze table "
            f"{fq_table} is missing or unreadable. Run the cell that creates the "
            f"bronze documents table over the raw files.",
            {
                "stage": "table",
                "volume_path": volume_path,
                "pdf_count": pdf_count,
                "table": fq_table,
            },
        )

    if row_count != pdf_count:
        return CheckResult(
            BRONZE_DOCS_CHECKPOINT_ID,
            False,
            f"Bronze table {fq_table} has {row_count} row(s) but {pdf_count} PDF(s) "
            f"are in {volume_path}. Re-create the bronze table so it registers "
            f"every landed document (one row per file).",
            {
                "stage": "table",
                "volume_path": volume_path,
                "pdf_count": pdf_count,
                "row_count": row_count,
                "table": fq_table,
            },
        )

    return CheckResult(
        BRONZE_DOCS_CHECKPOINT_ID,
        True,
        f"Bronze layer ready: {pdf_count} PDFs landed in {volume_path} and "
        f"{fq_table} registers all {row_count} of them.",
        {
            "stage": "done",
            "volume_path": volume_path,
            "pdf_count": pdf_count,
            "row_count": row_count,
            "table": fq_table,
        },
    )
