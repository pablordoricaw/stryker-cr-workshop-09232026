"""The ``04_metadata`` checkpoint: governed metadata applied to the gold tables.

Ticket #9 runs `dbxmetagen <https://github.com/databricks-industry-solutions/dbxmetagen>`_
against the gold tables in its three modes — ``comment``, ``pi``, and
``domain`` — staging the generated metadata for review (``apply_ddl=false``)
and then applying it. This checkpoint proves the *applied* result, reading
**only externally-observable Unity Catalog state** — table/column comments and
UC tags — never how the notebook generated them. A participant can reach the
same state with dbxmetagen, hand-written ``COMMENT ON`` / ``ALTER … SET TAGS``
DDL, or anything else, and it passes identically.

What the three modes leave behind, and what this check observes:

* **comment** → a non-blank ``COMMENT`` on each target table *and on every one
  of its columns*. The full column set is read from
  ``information_schema.columns`` at check time, so coverage is derived from the
  actual table, never a hardcoded column list. A blank/whitespace comment fails
  (an empty string is not documentation).
* **pi** → a column-level classification tag (dbxmetagen's
  ``data_classification`` by default) on the sensitive columns. The check
  requires the tag to be present with a non-blank value on at least
  ``min_pi_columns`` column(s); a missing tag key or a blank tag value fails, so
  a stripped or emptied PI tag cannot pass.
* **domain** → a table-level business-domain tag (dbxmetagen's ``domain`` by
  default) on each target table, with a non-blank value.

**Domain-generic.** No Finance-only column name is hardcoded. The target
*tables* default to the gold tables built by #8 (``gold_sales`` and
``gold_contract_performance``) and are overridable, exactly like the ``03_gold``
check; the *columns*, the PI-tagged set, and the domain values are all read from
live catalog state. Security (#13) and ITSM (#14) reuse this module with their
own gold tables and, if they diverge from dbxmetagen's defaults, their own tag
keys — no edits.

Run it as::

    workshop.check("04_metadata", spark=spark,
                   catalog=config.catalog, schema=config.schema)

Extras forwarded through ``ctx.extras``:

* ``tables`` — target table names (default the two gold tables above).
* ``pi_tag_name`` — the column PI classification tag key (default
  ``data_classification``, dbxmetagen's default).
* ``domain_tag_name`` — the table domain tag key (default ``domain``).
* ``min_pi_columns`` — minimum distinct columns that must carry a non-blank PI
  tag across the target tables (default ``1``). Guards against ``pi`` mode never
  having run.
* ``expected_pi_columns`` — an explicit ``{"<table>.<column>", ...}`` set the
  PI-tagged columns must equal *exactly* (a documented pin for a domain that
  wants to assert the precise sensitive-column set). Overrides
  ``min_pi_columns`` when given.
"""

from __future__ import annotations

from typing import Any

from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

METADATA_CHECKPOINT_ID = "04_metadata"

#: Default target tables — the gold marts built by ``03_gold`` (#8). Overridable
#: via the ``tables`` extra so Security/ITSM point at their own gold tables.
DEFAULT_TABLES: tuple[str, ...] = ("gold_sales", "gold_contract_performance")

#: dbxmetagen's default tag keys (``pi_classification_tag_name`` /
#: ``domain_tag_name``). Overridable for a domain that reconfigures dbxmetagen.
DEFAULT_PI_TAG_NAME = "data_classification"
DEFAULT_DOMAIN_TAG_NAME = "domain"

#: A run must tag at least this many columns as PI unless ``expected_pi_columns``
#: pins the exact set. One is enough to prove ``pi`` mode ran and applied.
DEFAULT_MIN_PI_COLUMNS = 1

# Cap for the example lists surfaced in failure details, matching 03_gold.
_MAX_EXAMPLES = 20


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(METADATA_CHECKPOINT_ID, False, message, details)


def _literal(value: str) -> str:
    """Single-quote a value for a SQL string comparison, escaping embedded quotes.

    ``information_schema`` is filtered by *value* on schema/table/tag names (they
    are data in these views, not identifiers), so those go in as escaped string
    literals; the catalog, which prefixes the view, is backtick-quoted instead.
    """
    return "'" + value.replace("'", "''") + "'"


def _is_blank(value: Any) -> bool:
    """True for NULL/empty/whitespace-only — an empty comment or tag is not set."""
    return value is None or str(value).strip() == ""


def _table_names(value: Any) -> tuple[str, ...]:
    """Resolve and validate the target table list from the ``tables`` extra."""
    if value is None:
        return DEFAULT_TABLES
    if isinstance(value, str):
        names: tuple[str, ...] = (value,)
    elif isinstance(value, (list, tuple)):
        names = tuple(value)
    else:
        raise TypeError("tables must be a table name or a list of table names")
    cleaned = [name for name in names if isinstance(name, str) and name.strip()]
    if not cleaned or len(cleaned) != len(names):
        raise ValueError("tables entries must be non-empty table names")
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for name in cleaned:
        if name not in seen:
            unique.append(name)
            seen.add(name)
    return tuple(unique)


@checkpoint(
    METADATA_CHECKPOINT_ID,
    summary=(
        "The gold tables carry dbxmetagen's applied metadata: a non-blank "
        "comment on every table and column, a PI classification tag on the "
        "sensitive columns, and a business-domain tag on each table."
    ),
)
def check_metadata(ctx: CheckContext) -> CheckResult:
    """Assert comments + PI tags + domain tags on the gold tables, from UC state."""
    spark = ctx.require_spark()
    if not ctx.catalog or not ctx.schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('04_metadata', "
            "spark=spark, catalog=config.catalog, schema=config.schema).",
            {"catalog": ctx.catalog, "schema": ctx.schema},
        )

    try:
        tables = _table_names(ctx.extras.get("tables"))
    except (TypeError, ValueError) as exc:
        return _fail(
            f"Invalid tables configuration: {exc}.",
            {"stage": "configuration", "error_type": type(exc).__name__},
        )

    pi_tag_name = ctx.extras.get("pi_tag_name") or DEFAULT_PI_TAG_NAME
    domain_tag_name = ctx.extras.get("domain_tag_name") or DEFAULT_DOMAIN_TAG_NAME
    min_pi_columns = ctx.extras.get("min_pi_columns")
    if min_pi_columns is None:
        min_pi_columns = DEFAULT_MIN_PI_COLUMNS
    expected_pi_columns = ctx.extras.get("expected_pi_columns")
    if expected_pi_columns is not None:
        expected_pi_columns = set(expected_pi_columns)

    catalog = ctx.catalog
    quoted_catalog = "`" + catalog.replace("`", "``") + "`"
    schema_lit = _literal(ctx.schema)
    table_in = ", ".join(_literal(name) for name in tables)

    # 1. Existence + table-level comment (comment mode, table grain). We read
    #    information_schema rather than DESCRIBE so tags and comments come from
    #    the same observable surface and one missing table is a clean failure.
    try:
        table_rows = spark.sql(
            f"""/* metadata:tables */
            SELECT table_name, comment
            FROM {quoted_catalog}.information_schema.tables
            WHERE table_schema = {schema_lit}
              AND table_name IN ({table_in})"""
        ).collect()
    except Exception as exc:  # noqa: BLE001 - participant-facing RED state
        return _fail(
            f"Could not read information_schema.tables in catalog {catalog} "
            f"({type(exc).__name__}). Confirm the catalog is accessible.",
            {"stage": "tables", "catalog": catalog, "error_type": type(exc).__name__},
        )

    table_comments = {row[0]: row[1] for row in table_rows}
    missing_tables = [name for name in tables if name not in table_comments]
    if missing_tables:
        return _fail(
            f"Target table(s) {missing_tables} do not exist in "
            f"{catalog}.{ctx.schema}. Build the gold layer (03_gold) before "
            "generating metadata.",
            {"stage": "tables", "missing_tables": missing_tables},
        )

    uncommented_tables = [
        name for name in tables if _is_blank(table_comments.get(name))
    ]
    if uncommented_tables:
        return _fail(
            f"Table(s) {uncommented_tables} have no comment (null/blank). Run "
            "dbxmetagen `comment` mode and apply it so every target table is "
            "described.",
            {"stage": "table_comment", "uncommented_tables": uncommented_tables},
        )

    # 2. Column-level comment coverage (comment mode, column grain). The column
    #    set is read live, so coverage is derived from the actual tables — no
    #    hardcoded column names — and one blank comment fails.
    try:
        column_rows = spark.sql(
            f"""/* metadata:columns */
            SELECT table_name, column_name, comment
            FROM {quoted_catalog}.information_schema.columns
            WHERE table_schema = {schema_lit}
              AND table_name IN ({table_in})"""
        ).collect()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read information_schema.columns in catalog {catalog} "
            f"({type(exc).__name__}).",
            {"stage": "columns", "catalog": catalog, "error_type": type(exc).__name__},
        )

    columns_by_table: dict[str, int] = dict.fromkeys(tables, 0)
    blank_comment_columns: list[str] = []
    total_columns = 0
    for table_name, column_name, comment in ((r[0], r[1], r[2]) for r in column_rows):
        columns_by_table[table_name] = columns_by_table.get(table_name, 0) + 1
        total_columns += 1
        if _is_blank(comment):
            blank_comment_columns.append(f"{table_name}.{column_name}")

    tables_without_columns = [name for name in tables if columns_by_table.get(name, 0) == 0]
    if tables_without_columns:
        return _fail(
            f"No columns found for table(s) {tables_without_columns} in "
            f"information_schema. The tables must exist with columns before "
            "metadata can be checked.",
            {"stage": "columns", "tables_without_columns": tables_without_columns},
        )

    if blank_comment_columns:
        return _fail(
            f"{len(blank_comment_columns)} of {total_columns} column(s) have a "
            f"null/blank comment. dbxmetagen `comment` mode must comment every "
            "column; an empty comment does not count.",
            {
                "stage": "column_comment",
                "blank_comment_columns": sorted(blank_comment_columns)[:_MAX_EXAMPLES],
                "blank_count": len(blank_comment_columns),
                "total_columns": total_columns,
            },
        )

    # 3. PI classification tag (pi mode, column grain). A missing tag key returns
    #    zero rows; a blank tag value is treated as unset — both must fail so a
    #    stripped or emptied PI tag cannot pass.
    try:
        pi_rows = spark.sql(
            f"""/* metadata:column_tags */
            SELECT table_name, column_name, tag_value
            FROM {quoted_catalog}.information_schema.column_tags
            WHERE schema_name = {schema_lit}
              AND table_name IN ({table_in})
              AND tag_name = {_literal(pi_tag_name)}"""
        ).collect()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read information_schema.column_tags in catalog {catalog} "
            f"({type(exc).__name__}).",
            {"stage": "pi_tag", "catalog": catalog, "error_type": type(exc).__name__},
        )

    pi_tagged: set[str] = set()
    blank_pi_values: list[str] = []
    for table_name, column_name, tag_value in ((r[0], r[1], r[2]) for r in pi_rows):
        key = f"{table_name}.{column_name}"
        if _is_blank(tag_value):
            blank_pi_values.append(key)
        else:
            pi_tagged.add(key)

    if blank_pi_values:
        return _fail(
            f"{len(blank_pi_values)} column(s) carry the `{pi_tag_name}` tag with "
            "a blank value. A PI classification tag must have a non-empty value.",
            {
                "stage": "pi_tag",
                "pi_tag_name": pi_tag_name,
                "blank_value_columns": sorted(blank_pi_values)[:_MAX_EXAMPLES],
            },
        )

    if expected_pi_columns is not None:
        missing_pi = expected_pi_columns - pi_tagged
        unexpected_pi = pi_tagged - expected_pi_columns
        if missing_pi or unexpected_pi:
            return _fail(
                f"The `{pi_tag_name}`-tagged columns do not match the expected "
                f"set: {len(missing_pi)} missing, {len(unexpected_pi)} "
                "unexpected.",
                {
                    "stage": "pi_tag",
                    "pi_tag_name": pi_tag_name,
                    "missing": sorted(missing_pi)[:_MAX_EXAMPLES],
                    "unexpected": sorted(unexpected_pi)[:_MAX_EXAMPLES],
                },
            )
    elif len(pi_tagged) < min_pi_columns:
        return _fail(
            f"Only {len(pi_tagged)} column(s) carry the `{pi_tag_name}` PI tag; "
            f"expected at least {min_pi_columns}. Run dbxmetagen `pi` mode and "
            "apply it so the sensitive columns are classified.",
            {
                "stage": "pi_tag",
                "pi_tag_name": pi_tag_name,
                "pi_tagged_columns": len(pi_tagged),
                "min_pi_columns": min_pi_columns,
            },
        )

    # 4. Business-domain tag (domain mode, table grain). Each target table must
    #    carry a non-blank domain tag.
    try:
        domain_rows = spark.sql(
            f"""/* metadata:table_tags */
            SELECT table_name, tag_value
            FROM {quoted_catalog}.information_schema.table_tags
            WHERE schema_name = {schema_lit}
              AND table_name IN ({table_in})
              AND tag_name = {_literal(domain_tag_name)}"""
        ).collect()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read information_schema.table_tags in catalog {catalog} "
            f"({type(exc).__name__}).",
            {"stage": "domain_tag", "catalog": catalog, "error_type": type(exc).__name__},
        )

    domain_values = {
        row[0]: row[1] for row in ((r[0], r[1]) for r in domain_rows)
    }
    undomained_tables = [
        name for name in tables if _is_blank(domain_values.get(name))
    ]
    if undomained_tables:
        return _fail(
            f"Table(s) {undomained_tables} have no non-blank `{domain_tag_name}` "
            "tag. Run dbxmetagen `domain` mode and apply it so each table is "
            "classified into a business domain.",
            {
                "stage": "domain_tag",
                "domain_tag_name": domain_tag_name,
                "untagged_tables": undomained_tables,
            },
        )

    return CheckResult(
        METADATA_CHECKPOINT_ID,
        True,
        f"Metadata applied: all {len(tables)} gold table(s) and their "
        f"{total_columns} columns are commented, {len(pi_tagged)} column(s) "
        f"carry the `{pi_tag_name}` PI tag, and every table carries a "
        f"`{domain_tag_name}` tag.",
        {
            "stage": "done",
            "tables": list(tables),
            "total_columns": total_columns,
            "columns_by_table": columns_by_table,
            "pi_tag_name": pi_tag_name,
            "pi_tagged_columns": sorted(pi_tagged),
            "domain_tag_name": domain_tag_name,
            "domain_values": domain_values,
        },
    )
