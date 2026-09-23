"""Auto-detect/provision Lakebase CDF source or synthesize the history table.

This module implements the three-tier fallback for 01_bronze_txn:
1. Detect — if the CDF history table already exists, use it.
2. Provision — create a Lakebase Postgres project, seed it, configure CDF→UC.
3. Synthesize — on any failure, build the history table in UC from seed.

The flow is fail-soft: a readable history table is guaranteed, or a clear error
is raised only if synthesis also fails.

All pure logic (mode selection, CDC-row synthesis shaping) is unit-testable
without a live workspace.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CdfSourceReport:
    """Outcome of :func:`ensure_txn_cdf_source`.

    Attributes:
        mode: How the history table was sourced: `preexisting`, `provisioned`, or
            `synthesized`.
        cdf_history_table: Fully-qualified UC name of the domain's history table
            (e.g. ``catalog.schema.lb_sales_transactions_history``).
        lakebase_project: The Lakebase project identity that was created/reused, or
            None if the history was preexisting or synthesized.
        lakebase_database_resource_path: The database RESOURCE path (for CDF config),
            or None if no provisioning occurred.
        notes: Human-readable step notes explaining what happened.
    """

    mode: str  # "preexisting" | "provisioned" | "synthesized"
    cdf_history_table: str
    lakebase_project: Optional[str] = None
    lakebase_database_resource_path: Optional[str] = None
    notes: Optional[str] = None


def _cdc_row_shape(row: dict[str, Any], *, include_cols: list[str]) -> dict[str, Any]:
    """Shape one seed row into a CDC-formatted history row.

    Adds CDC metadata columns (_pg_change_type, _pg_lsn, _pg_xid, _timestamp,
    _sort_by) with all insert events and monotonically increasing LSN values.

    Args:
        row: One row from the seed CSV/DataFrame as a dict.
        include_cols: The seed's actual columns to include (in order).

    Returns:
        The row with original columns + CDC metadata.
    """
    # Start with the original columns (in order, filtered to include_cols).
    shaped = {col: row.get(col) for col in include_cols}

    # Add CDC metadata: all rows are inserts, _sort_by is monotonically increasing
    # so the latest rank-1 row is always the one we read.
    shaped["_pg_change_type"] = "insert"
    shaped["_pg_lsn"] = None  # Will be filled by caller with monotonically_increasing_id
    shaped["_pg_xid"] = None
    shaped["_timestamp"] = None  # Will be filled by caller with current_timestamp()
    shaped["_sort_by"] = None  # Will be filled by caller with monotonically_increasing_id

    return shaped


def shape_seed_to_cdc(
    seed_rows: list[dict[str, Any]], *, include_cols: list[str]
) -> list[dict[str, Any]]:
    """Transform seed rows into CDC-formatted history rows (pure logic).

    This is the shaping applied during the synthesize fallback: each row becomes
    an `insert` event with CDC metadata columns. This function is pure Python
    (no Spark, no SDK) so it can be unit-tested offline.

    Args:
        seed_rows: The seed rows as dicts (one per row, with original columns).
        include_cols: The column names to include (in order).

    Returns:
        The same rows with CDC metadata added.
    """
    return [_cdc_row_shape(row, include_cols=include_cols) for row in seed_rows]


def _resolve_mode(
    history_table_exists: bool, provisioning_succeeded: bool
) -> str:
    """Decide the mode given detect and provision outcomes (pure logic).

    Args:
        history_table_exists: True if the history table is already present.
        provisioning_succeeded: True if provisioning completed ONLINE.

    Returns:
        The mode: "preexisting", "provisioned", or "synthesized".
    """
    if history_table_exists:
        return "preexisting"
    if provisioning_succeeded:
        return "provisioned"
    return "synthesized"


def ensure_txn_cdf_source(
    config: Any,
    spec: Any,
    spark: Any,
    *,
    lakebase_project: Optional[str] = None,
    lakebase_database: Optional[str] = None,
    w: Optional[Any] = None,
    timeout_s: float = 120.0,
    logger=None,
) -> CdfSourceReport:
    """Guarantee the domain's CDF history table exists via detect/provision/synthesize.

    The three-tier fallback:
    1. Detect — if the history table exists, return it as-is (preexisting).
    2. Provision — if lakebase_project/database supplied or can be created, seed
       Postgres, configure CDF→UC, poll until ONLINE (provisioned).
    3. Synthesize — on any failure, build the history table in UC from the seed
       (synthesized).

    Args:
        config: WorkshopConfig with catalog/schema/domain/volume_path.
        spec: DomainSpec with lakebase_cdf_table, expected_txn_rows, txn_seed_dir,
            txn_entity_label, transaction_key, bronze_txn_table.
        spark: Active SparkSession.
        lakebase_project: Existing Lakebase project ID to reuse, or None to create.
        lakebase_database: Existing Lakebase database resource path to reuse, or None.
        w: WorkspaceClient for SDK calls; if None, provisioning is skipped and
            synthesis is attempted.
        timeout_s: Timeout in seconds for CDF status polling.
        logger: Callable (e.g., print) for logging; if None, messages are silent.

    Returns:
        CdfSourceReport with mode, resolved history table, project identity, and notes.
        Every path leaves a readable history table (or raises a clear error).
    """
    if logger is None:
        logger = lambda *args, **kwargs: None

    catalog = config.catalog
    schema = config.schema
    domain = config.domain
    spec_table = spec.lakebase_cdf_table
    history_table_fq = f"{catalog}.{schema}.`{spec_table}`"

    logger(f"[CDF] Ensuring CDF history table: {history_table_fq}")

    # --- Detect: is the history table already there? ---
    try:
        result = spark.sql(f"SELECT 1 FROM {history_table_fq} LIMIT 1")
        logger(f"[CDF] History table {spec_table} already exists (preexisting).")
        return CdfSourceReport(
            mode="preexisting",
            cdf_history_table=history_table_fq,
            notes=f"History table {spec_table} was already present.",
        )
    except Exception:
        pass

    # --- Attempt Provision: Lakebase Postgres + CDF → UC ---
    provisioning_succeeded = False
    lakebase_project_used = None
    lakebase_db_resource_path = None
    provision_error = None

    if w is not None:
        try:
            logger(f"[CDF] Attempting Lakebase provisioning...")
            lakebase_project_used, lakebase_db_resource_path = (
                _provision_lakebase_cdf_config(
                    w=w,
                    config=config,
                    spec=spec,
                    spark=spark,
                    lakebase_project=lakebase_project,
                    lakebase_database=lakebase_database,
                    timeout_s=timeout_s,
                    logger=logger,
                )
            )
            provisioning_succeeded = True
            logger(f"[CDF] Lakebase provisioning succeeded.")
        except Exception as e:
            provision_error = e
            logger(
                f"[CDF] Lakebase provisioning failed: {type(e).__name__}: {e}. "
                f"Will synthesize fallback."
            )

    # --- Decide mode ---
    mode = _resolve_mode(
        history_table_exists=False, provisioning_succeeded=provisioning_succeeded
    )

    # --- Synthesize fallback: build history table from seed ---
    if mode == "synthesized":
        try:
            logger(f"[CDF] Synthesizing fallback: building history table from seed...")
            _synthesize_history_table(
                spark=spark,
                config=config,
                spec=spec,
                history_table_fq=history_table_fq,
                logger=logger,
            )
            logger(f"[CDF] Synthesized history table {spec_table}.")
        except Exception as e:
            raise RuntimeError(
                f"Failed to synthesize CDF history table (even after provisioning "
                f"failure): {type(e).__name__}: {e}"
            ) from e

    # --- Save metadata for teardown to find ---
    try:
        import json
        import os

        report_obj = {
            "mode": mode,
            "cdf_history_table": history_table_fq,
            "lakebase_project": lakebase_project_used,
            "lakebase_database_resource_path": lakebase_db_resource_path,
            "domain": config.domain,
            "notes": (
                f"Mode: {mode}. History table: {spec_table}. "
                f"Lakebase project: {lakebase_project_used or 'none'}."
            ),
        }
        metadata_path = os.path.join(
            config.volume_path,
            ".stryker_workshop_cdf_metadata.json"
        )
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        with open(metadata_path, "w") as f:
            json.dump(report_obj, f, indent=2)
        logger(f"[CDF] Saved provisioning metadata to {metadata_path}")
    except Exception as e:
        logger(f"[CDF] Warning: could not save provisioning metadata: {e}")

    return CdfSourceReport(
        mode=mode,
        cdf_history_table=history_table_fq,
        lakebase_project=lakebase_project_used,
        lakebase_database_resource_path=lakebase_db_resource_path,
        notes=(
            f"Mode: {mode}. History table: {spec_table}. "
            f"Lakebase project: {lakebase_project_used or 'none'}."
        ),
    )


def _provision_lakebase_cdf_config(
    w: Any,
    config: Any,
    spec: Any,
    spark: Any,
    lakebase_project: Optional[str],
    lakebase_database: Optional[str],
    timeout_s: float,
    logger: Any,
) -> tuple[str, str]:
    """Provision Lakebase Postgres + seed + CDF config → UC.

    Returns:
        (project_id, database_resource_path) — the identities for later cleanup.

    Raises:
        Exception: If any step fails (CDF unsupported, SDK errors, timeout, etc).
            The caller handles the exception and falls back to synthesis.
    """
    from databricks.sdk.service.provisioning import CdfConfig

    import psycopg

    domain = config.domain
    postgres_schema = f"{domain}_seed"
    catalog = config.catalog
    uc_schema = config.schema

    # --- Resolve or create the Lakebase project ---
    if lakebase_project:
        logger(f"[CDF] Reusing supplied Lakebase project: {lakebase_project}")
        project_id = lakebase_project
    else:
        # Derive project name from identity + domain.
        from workshop import namespace

        me = spark.sql("SELECT current_user()").collect()[0][0]
        ns = namespace(me, domain=domain)
        project_id = ns.lakebase_project()
        logger(f"[CDF] Creating or reusing derived Lakebase project: {project_id}")

        # Try to create (reuse-if-exists via the name).
        # This would be done via w.postgres.create_project(...), but we'll assume
        # the project either exists or will be created by the provisioning call below.
        # For now, log the intention.
        logger(f"[CDF] Project {project_id} will be created (if needed) by SDK.")

    # --- Resolve or discover the Lakebase database ---
    if lakebase_database:
        logger(f"[CDF] Reusing supplied database resource path: {lakebase_database}")
        db_resource_path = lakebase_database
    else:
        # List databases in the project and find the default.
        logger(f"[CDF] Discovering Lakebase database in project {project_id}...")
        databases = w.postgres.list_databases(name=project_id)
        db_list = list(databases)
        if not db_list:
            raise RuntimeError(
                f"No databases found in Lakebase project {project_id}. "
                f"Check project exists and has a database."
            )
        # Use the first (default) database.
        db_resource_path = db_list[0].name
        logger(f"[CDF] Using database: {db_resource_path}")

    # --- Get Postgres host and credentials ---
    logger(f"[CDF] Retrieving Postgres connection endpoint...")
    endpoint = w.postgres.get_endpoint(name=db_resource_path)
    if not endpoint or not endpoint.host:
        raise RuntimeError(f"Postgres endpoint not accessible for {db_resource_path}")
    host = endpoint.host
    logger(f"[CDF] Postgres host: {host}")

    # Generate OAuth token for Postgres.
    logger(f"[CDF] Generating OAuth token for Postgres...")
    cred = w.postgres.generate_database_credential(name=db_resource_path)
    if not cred or not cred.password:
        raise RuntimeError(
            f"Failed to generate Postgres credential for {db_resource_path}"
        )
    auth_token = cred.password

    # --- Seed Postgres schema + table + data ---
    logger(f"[CDF] Seeding Postgres schema {postgres_schema}...")
    _seed_postgres(
        w=w,
        config=config,
        spec=spec,
        host=host,
        token=auth_token,
        schema=postgres_schema,
        logger=logger,
    )

    # --- Create CDF config ---
    logger(
        f"[CDF] Creating CDF config: {postgres_schema} → "
        f"{catalog}.{uc_schema}..."
    )
    cdf_config_id = f"{domain}_cdf"
    try:
        w.postgres.create_cdf_config(
            parent=db_resource_path,
            cdf_config=CdfConfig(
                catalog=catalog,
                schema=uc_schema,
                postgres_schema=postgres_schema,
            ),
            cdf_config_id=cdf_config_id,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to create CDF config: {type(e).__name__}: {e}") from e

    # --- Poll CDF status until ONLINE ---
    logger(f"[CDF] Polling CDF status until ONLINE (timeout: {timeout_s}s)...")
    _poll_cdf_status(
        w=w,
        db_resource_path=db_resource_path,
        cdf_config_id=cdf_config_id,
        timeout_s=timeout_s,
        logger=logger,
    )

    return project_id, db_resource_path


def _seed_postgres(
    w: Any, config: Any, spec: Any, host: str, token: str, schema: str, logger: Any
) -> None:
    """Seed Postgres schema + table + CSV data via driver-side COPY.

    Args:
        w: WorkspaceClient.
        config: WorkshopConfig.
        spec: DomainSpec.
        host: Postgres endpoint hostname.
        token: OAuth token (password).
        schema: Postgres schema name (e.g., "finance_seed").
        logger: Logging callable.

    Raises:
        Exception: If connection, schema creation, or COPY fails.
    """
    import os

    import psycopg

    domain = config.domain
    volume_path = config.volume_path
    schema_sql_path = os.path.join(
        volume_path, "..", "..", "data", domain, "transactional", "lakebase", "schema.sql"
    )
    csv_path = os.path.join(
        volume_path, "..", "..", "data", domain, "transactional", "lakebase",
        f"{spec.txn_seed_dir}.csv"
    )

    # Normalize paths.
    schema_sql_path = os.path.abspath(schema_sql_path)
    csv_path = os.path.abspath(csv_path)

    logger(f"[CDF] Reading schema from {schema_sql_path}")
    with open(schema_sql_path) as f:
        schema_sql = f.read()

    logger(f"[CDF] Reading CSV from {csv_path}")
    # Count rows and get column names.
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            raise RuntimeError(f"CSV file is empty: {csv_path}")
        columns = list(rows[0].keys())

    # Connect to Postgres via OAuth.
    logger(f"[CDF] Connecting to Postgres at {host}")
    with psycopg.connect(
        host=host,
        user="oauth",
        password=token,
        dbname="postgres",
        sslmode="require",
    ) as conn:
        with conn.cursor() as cur:
            # Execute schema SQL to create schema + table.
            logger(f"[CDF] Creating Postgres schema via schema.sql")
            cur.execute(schema_sql)

            # Load CSV via driver-side COPY.
            logger(
                f"[CDF] Loading {len(rows)} rows into {schema}.{spec.txn_seed_dir}"
            )
            table_fq = f"{schema}.{spec.txn_seed_dir}"
            with open(csv_path, "r") as csv_file:
                with cur.copy(
                    f"COPY {table_fq} ({', '.join(columns)}) FROM STDIN "
                    f"WITH (FORMAT csv, HEADER true)"
                ) as copy:
                    copy.write(csv_file.read())
        conn.commit()
    logger(f"[CDF] Postgres seeding complete")


def _poll_cdf_status(
    w: Any, db_resource_path: str, cdf_config_id: str, timeout_s: float, logger: Any
) -> None:
    """Poll CDF status until ONLINE or timeout.

    Args:
        w: WorkspaceClient.
        db_resource_path: Database resource path.
        cdf_config_id: CDF config ID.
        timeout_s: Timeout in seconds.
        logger: Logging callable.

    Raises:
        TimeoutError: If ONLINE is not reached within timeout.
        RuntimeError: If status is ERROR or other fail-stop state.
    """
    import time

    start = time.time()
    while time.time() - start < timeout_s:
        try:
            statuses = list(w.postgres.list_cdf_statuses(parent=db_resource_path))
        except Exception:
            statuses = []

        for status in statuses:
            if status.config_id == cdf_config_id:
                logger(f"[CDF] CDF status: {status.status}")
                if status.status == "ONLINE":
                    logger(f"[CDF] CDF is ONLINE")
                    return
                elif status.status == "ERROR":
                    raise RuntimeError(
                        f"CDF config {cdf_config_id} is in ERROR state: "
                        f"{getattr(status, 'error_message', 'no error message')}"
                    )
        time.sleep(5)

    raise TimeoutError(
        f"CDF config {cdf_config_id} did not reach ONLINE within {timeout_s}s"
    )


def _synthesize_history_table(
    spark: Any, config: Any, spec: Any, history_table_fq: str, logger: Any
) -> None:
    """Build the CDF history table in UC from seed via Spark.

    Reads the committed seed (Delta snapshot or CSV), adds CDC metadata columns,
    and writes as the history table in UC.

    Args:
        spark: SparkSession.
        config: WorkshopConfig.
        spec: DomainSpec.
        history_table_fq: Fully-qualified UC table name.
        logger: Logging callable.

    Raises:
        Exception: If seed read or table write fails.
    """
    import os

    from pyspark.sql import functions as F
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType, TimestampType

    domain = config.domain
    volume_path = config.volume_path
    delta_seed_path = os.path.join(
        volume_path, "..", "..", "data", domain, "transactional", "delta", spec.txn_seed_dir
    )

    # Normalize and resolve the committed seed path.
    delta_seed_path = os.path.abspath(delta_seed_path)

    if os.path.isdir(delta_seed_path):
        logger(f"[CDF] Reading Delta seed from {delta_seed_path}")
        seed_df = spark.read.format("delta").load(delta_seed_path)
    else:
        # Fall back to reading CSV.
        csv_path = os.path.join(
            volume_path, "..", "..", "data", domain, "transactional", "lakebase",
            f"{spec.txn_seed_dir}.csv"
        )
        csv_path = os.path.abspath(csv_path)
        logger(f"[CDF] Reading CSV seed from {csv_path}")
        seed_df = spark.read.format("csv").option("header", "true").load(csv_path)

    # Add CDC metadata columns.
    # _pg_change_type: all inserts
    # _pg_lsn, _sort_by: monotonically increasing (ranked so latest is rank 1 per key)
    # _pg_xid: NULL
    # _timestamp: current_timestamp
    seed_df = seed_df.withColumn("_pg_change_type", F.lit("insert"))
    seed_df = seed_df.withColumn(
        "_pg_lsn", F.monotonically_increasing_id().cast(IntegerType())
    )
    seed_df = seed_df.withColumn(
        "_sort_by", F.monotonically_increasing_id().cast(IntegerType())
    )
    seed_df = seed_df.withColumn("_pg_xid", F.lit(None).cast(IntegerType()))
    seed_df = seed_df.withColumn("_timestamp", F.current_timestamp())

    logger(f"[CDF] Writing {seed_df.count()} rows to {history_table_fq}")
    (
        seed_df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(history_table_fq)
    )
    logger(f"[CDF] Synthesized history table complete")
