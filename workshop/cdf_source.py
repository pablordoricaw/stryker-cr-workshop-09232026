"""Auto-detect/provision Lakebase CDF source or synthesize the history table.

This module implements the three-tier fallback for 01_bronze_txn:
1. Detect — if the CDF history table already exists, use it.
2. Provision — create a Lakebase Postgres project, seed it, configure CDF→UC.
3. Synthesize — on any failure, build the history table in UC from seed.

The flow is fail-soft: a readable history table is guaranteed, or a clear error
is raised only if synthesis also fails.

All pure logic (mode selection, CDC-row synthesis shaping) is unit-testable
without a live workspace.

Key fixes (vs. initial version):
- Seed paths anchored to repo_root, not volume_path
- Spark reads from UC volume (staged via shutil), not /Workspace
- _pg_lsn/_sort_by are BIGINT (LongType), not INTEGER
- Provision creates/discovers projects/branches/endpoints per authoritative API
- CdfConfig imported correctly from databricks.sdk.service.postgres
- NotFound exceptions caught per SDK error handling
- Postgres connection uses correct auth (current_user, token)
- Entire provision wrapped in try/except for fail-soft fallback to synthesize
"""

from __future__ import annotations

import os
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
    """Shape one seed row into a CDC-formatted history row (pure logic).

    Adds CDC metadata columns (_pg_change_type, _pg_lsn, _pg_xid, _timestamp,
    _sort_by) with all insert events. LSN and _sort_by will be filled by Spark
    using monotonically_increasing_id().
    """
    shaped = {col: row.get(col) for col in include_cols}
    shaped["_pg_change_type"] = "insert"
    shaped["_pg_lsn"] = None  # Spark will fill with monotonically_increasing_id (BIGINT)
    shaped["_pg_xid"] = None
    shaped["_timestamp"] = None  # Spark will fill with current_timestamp()
    shaped["_sort_by"] = None  # Spark will fill with monotonically_increasing_id (BIGINT)
    return shaped


def shape_seed_to_cdc(
    seed_rows: list[dict[str, Any]], *, include_cols: list[str]
) -> list[dict[str, Any]]:
    """Transform seed rows into CDC-formatted history rows (pure logic).

    Each row becomes an `insert` event with CDC metadata columns. This function
    is pure Python (no Spark, no SDK) so it can be unit-tested offline.

    Args:
        seed_rows: The seed rows as dicts (one per row, with original columns).
        include_cols: The column names to include (in order).

    Returns:
        The same rows with CDC metadata added (LSN/timestamp values as None).
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
    repo_root: str,
    lakebase_project: Optional[str] = None,
    lakebase_database: Optional[str] = None,
    w: Optional[Any] = None,
    timeout_s: float = 120.0,
    logger=None,
) -> CdfSourceReport:
    """Guarantee the domain's CDF history table exists via detect/provision/synthesize.

    Three-tier fail-soft flow:
    1. Detect — if history table exists, return it (preexisting).
    2. Provision — create/reuse Lakebase project, seed Postgres, configure CDF (provisioned).
    3. Synthesize — on any failure, build history table in UC from committed seed (synthesized).

    Args:
        config: WorkshopConfig with catalog/schema/domain/volume_path.
        spec: DomainSpec with lakebase_cdf_table, txn_seed_dir, transaction_key, etc.
        spark: Active SparkSession.
        repo_root: Absolute path to the workshop repo root (contains data/).
        lakebase_project: Existing Lakebase project ID to reuse, or None to create/derive.
        lakebase_database: Existing Lakebase database resource path to reuse, or None.
        w: WorkspaceClient for SDK calls; if None, provisioning is skipped.
        timeout_s: Timeout in seconds for CDF status polling.
        logger: Callable (e.g., print) for logging; if None, messages are silent.

    Returns:
        CdfSourceReport with mode, resolved history table, project identity, and notes.
        Guaranteed: always leaves a readable history table (or raises only if synthesis fails).
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

    if w is not None:
        try:
            logger(f"[CDF] Attempting Lakebase provisioning...")
            lakebase_project_used, lakebase_db_resource_path = (
                _provision_lakebase_cdf_config(
                    w=w,
                    config=config,
                    spec=spec,
                    spark=spark,
                    repo_root=repo_root,
                    lakebase_project=lakebase_project,
                    lakebase_database=lakebase_database,
                    timeout_s=timeout_s,
                    logger=logger,
                )
            )
            provisioning_succeeded = True
            logger(f"[CDF] Lakebase provisioning succeeded.")
        except Exception as e:
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
                repo_root=repo_root,
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
    repo_root: str,
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

    API Reference (per authoritative lakehouse-sync.md):
    - project: projects/<PROJECT_ID>
    - branch: projects/<PROJECT_ID>/branches/<BRANCH_ID>
    - endpoint: projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID>
    - database: projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID> (resource path)
    - CdfConfig imported from databricks.sdk.service.postgres
    - parent for CDF is DATABASE resource path, not project or database name
    - list_cdf_statuses catches NotFound (404) when none exist
    """
    from databricks.sdk.service.postgres import CdfConfig

    domain = config.domain
    postgres_schema = f"{domain}_seed"
    catalog = config.catalog
    uc_schema = config.schema

    # --- Create or reuse Lakebase project ---
    if lakebase_project:
        logger(f"[CDF] Reusing supplied Lakebase project: {lakebase_project}")
        project_id = lakebase_project
    else:
        from workshop import namespace

        me = spark.sql("SELECT current_user()").collect()[0][0]
        ns = namespace(me, domain=domain)
        project_id = ns.lakebase_project()
        logger(f"[CDF] Creating or reusing derived Lakebase project: {project_id}")

        # Create project (auto-creates production branch + primary endpoint).
        # Reuse if already exists by catching the error.
        try:
            w.postgres.create_project(
                name=project_id,
                spec={"display_name": f"Workshop {domain} Lakebase project"}
            )
            logger(f"[CDF] Created Lakebase project {project_id}")
        except Exception as e:
            if "already exists" in str(e).lower() or "conflict" in str(e).lower():
                logger(f"[CDF] Project {project_id} already exists (reusing)")
            else:
                raise

    # --- Discover the production branch and database ---
    logger(f"[CDF] Discovering branch and database for project {project_id}...")

    # List branches to get the production branch id
    branches = list(w.postgres.list_branches(parent=f"projects/{project_id}"))
    production_branch = None
    for branch in branches:
        if "production" in branch.name.lower():
            production_branch = branch.name
            break

    if not production_branch:
        # Fallback: use the first branch (likely production)
        if branches:
            production_branch = branches[0].name
        else:
            raise RuntimeError(f"No branches found in project {project_id}")

    logger(f"[CDF] Using branch: {production_branch}")

    # List databases in the production branch
    databases = list(w.postgres.list_databases(parent=production_branch))
    db_resource_path = None
    for db in databases:
        # Match on postgres_database name
        if hasattr(db, "status") and hasattr(db.status, "postgres_database"):
            if db.status.postgres_database == "databricks_postgres":
                db_resource_path = db.name
                break

    if not db_resource_path:
        raise RuntimeError(
            f"Could not find databricks_postgres database in {production_branch}"
        )

    logger(f"[CDF] Using database: {db_resource_path}")

    # --- Get endpoint for Postgres connection ---
    logger(f"[CDF] Retrieving Postgres endpoint...")
    endpoints = list(w.postgres.list_endpoints(parent=production_branch))
    if not endpoints:
        raise RuntimeError(f"No endpoints found in {production_branch}")

    endpoint = endpoints[0]  # Use primary endpoint
    endpoint_fq = endpoint.name
    logger(f"[CDF] Using endpoint: {endpoint_fq}")

    # Get full endpoint details for host
    endpoint_obj = w.postgres.get_endpoint(name=endpoint_fq)
    if not hasattr(endpoint_obj, "status") or not hasattr(endpoint_obj.status, "hosts"):
        raise RuntimeError(f"Endpoint missing host information")

    host = endpoint_obj.status.hosts.host
    logger(f"[CDF] Postgres host: {host}")

    # Generate OAuth token for Postgres
    logger(f"[CDF] Generating OAuth token for Postgres...")
    cred = w.postgres.generate_database_credential(name=endpoint_fq)
    if not cred or not hasattr(cred, "token"):
        raise RuntimeError(f"Failed to generate Postgres credential")

    auth_token = cred.token

    # --- Seed Postgres schema + table + data ---
    me_user = spark.sql("SELECT current_user()").collect()[0][0]
    logger(f"[CDF] Seeding Postgres schema {postgres_schema}...")
    _seed_postgres(
        config=config,
        spec=spec,
        repo_root=repo_root,
        host=host,
        user=me_user,
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
    w.postgres.create_cdf_config(
        parent=db_resource_path,
        cdf_config=CdfConfig(
            catalog=catalog,
            schema=uc_schema,
            postgres_schema=postgres_schema,
        ),
        cdf_config_id=cdf_config_id,
    )

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
    config: Any, spec: Any, repo_root: str, host: str, user: str, token: str,
    schema: str, logger: Any
) -> None:
    """Seed Postgres schema + table + CSV data via driver-side COPY.

    Args:
        config: WorkshopConfig.
        spec: DomainSpec.
        repo_root: Absolute path to the workshop repo root.
        host: Postgres endpoint hostname.
        user: Current user (email/principal for OAuth).
        token: OAuth token (password).
        schema: Postgres schema name (e.g., "finance_seed").
        logger: Logging callable.

    Raises:
        Exception: If connection, schema creation, or COPY fails.
    """
    import psycopg

    domain = config.domain
    schema_sql_path = os.path.join(
        repo_root, "data", domain, "transactional", "lakebase", "schema.sql"
    )
    csv_path = os.path.join(
        repo_root, "data", domain, "transactional", "lakebase",
        f"{spec.txn_seed_dir}.csv"
    )

    logger(f"[CDF] Reading schema from {schema_sql_path}")
    with open(schema_sql_path) as f:
        schema_sql = f.read()

    logger(f"[CDF] Reading CSV from {csv_path}")
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            raise RuntimeError(f"CSV file is empty: {csv_path}")
        columns = list(rows[0].keys())

    logger(f"[CDF] Connecting to Postgres at {host} as user {user}")
    with psycopg.connect(
        host=host,
        user=user,
        password=token,
        dbname="databricks_postgres",
        sslmode="require",
    ) as conn:
        with conn.cursor() as cur:
            logger(f"[CDF] Creating Postgres schema via schema.sql")
            cur.execute(schema_sql)

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
        RuntimeError: If status is ERROR.
    """
    import time
    from databricks.sdk.errors.platform import NotFound

    start = time.time()
    while time.time() - start < timeout_s:
        try:
            statuses = list(w.postgres.list_cdf_statuses(parent=db_resource_path))
        except NotFound:
            # Empty list returns 404
            logger(f"[CDF] CDF config not yet ready; retrying...")
            statuses = []
        except Exception as e:
            logger(f"[CDF] Error listing CDF statuses: {e}; retrying...")
            statuses = []

        for status in statuses:
            if status.config_id == cdf_config_id:
                status_str = getattr(status, "status", "UNKNOWN")
                logger(f"[CDF] CDF status: {status_str}")
                if status_str == "ONLINE":
                    logger(f"[CDF] CDF is ONLINE")
                    return
                elif status_str == "ERROR":
                    error_msg = getattr(status, "error_message", "no error message")
                    raise RuntimeError(
                        f"CDF config {cdf_config_id} is in ERROR state: {error_msg}"
                    )
        time.sleep(5)

    raise TimeoutError(
        f"CDF config {cdf_config_id} did not reach ONLINE within {timeout_s}s"
    )


def _synthesize_history_table(
    spark: Any, config: Any, spec: Any, repo_root: str, history_table_fq: str,
    logger: Any
) -> None:
    """Build the CDF history table in UC from seed via Spark.

    Stages committed seed (Delta or CSV) into UC volume, then reads it, adds CDC
    metadata columns (with BIGINT types for _pg_lsn and _sort_by), and writes as
    the history table in UC.

    Args:
        spark: SparkSession.
        config: WorkshopConfig.
        spec: DomainSpec.
        repo_root: Absolute path to the workshop repo root.
        history_table_fq: Fully-qualified UC table name.
        logger: Logging callable.

    Raises:
        Exception: If seed read or table write fails.
    """
    import shutil

    from pyspark.sql import functions as F
    from pyspark.sql.types import LongType, TimestampType

    domain = config.domain
    volume_path = config.volume_path

    # Build path to committed Delta seed
    delta_seed_path = os.path.join(
        repo_root, "data", domain, "transactional", "delta", spec.txn_seed_dir
    )

    # Stage the committed seed into UC volume
    staged_seed = os.path.join(
        volume_path, domain, "transactional", "delta", spec.txn_seed_dir
    )

    logger(f"[CDF] Staging seed from {delta_seed_path} to {staged_seed}")
    if os.path.isdir(staged_seed):
        logger(f"[CDF] Staged seed already exists; removing to refresh")
        shutil.rmtree(staged_seed)

    os.makedirs(os.path.dirname(staged_seed), exist_ok=True)
    shutil.copytree(delta_seed_path, staged_seed)
    logger(f"[CDF] Staged seed complete")

    # Read the staged seed
    logger(f"[CDF] Reading staged Delta seed from {staged_seed}")
    seed_df = spark.read.format("delta").load(staged_seed)

    # Add CDC metadata columns
    logger(f"[CDF] Adding CDC metadata columns")
    seed_df = seed_df.withColumn("_pg_change_type", F.lit("insert"))

    # Use a single monotonically_increasing_id for both _pg_lsn and _sort_by
    # This ensures consistent ordering
    mono_id = F.monotonically_increasing_id().cast(LongType())
    seed_df = seed_df.withColumn("_pg_lsn", mono_id)
    seed_df = seed_df.withColumn("_sort_by", mono_id)
    seed_df = seed_df.withColumn("_pg_xid", F.lit(None).cast(LongType()))
    seed_df = seed_df.withColumn("_timestamp", F.current_timestamp().cast(TimestampType()))

    logger(f"[CDF] Writing {seed_df.count()} rows to {history_table_fq}")
    (
        seed_df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(history_table_fq)
    )
    logger(f"[CDF] Synthesized history table complete")
