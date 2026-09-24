"""Auto-detect/provision Lakebase CDF source or synthesize the history table.

This module implements the three-tier fallback for 01_bronze_txn:
1. Detect. If the CDF history table already exists, use it.
2. Provision. Create a Lakebase Postgres project, seed it, configure CDF→UC.
3. Synthesize. On any failure, build the history table in UC from seed.

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

import csv
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
        lakebase_project_created: True if the Lakebase project was created by this run
            (vs. supplied/reused). Only meaningful if mode == "provisioned".
        notes: Human-readable step notes explaining what happened.
    """

    mode: str  # "preexisting" | "provisioned" | "synthesized"
    cdf_history_table: str
    lakebase_project: Optional[str] = None
    lakebase_database_resource_path: Optional[str] = None
    lakebase_project_created: bool = False
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


def _as_fq_table(name: str, catalog: str, schema: str) -> str:
    """Convert a table name to fully-qualified form, handling already-qualified names.

    If the name already contains a dot (e.g., 'catalog.schema.table'), return it unchanged.
    Otherwise, qualify it as catalog.schema.`name`.

    This helper ensures that CdfStatus.uc_table (which is already fully-qualified) is used
    verbatim, while spec-provided table names (which are bare) are properly qualified.

    Args:
        name: Table name, either bare ('table_name') or already qualified ('cat.sch.table').
        catalog: Catalog name (for qualification if needed).
        schema: Schema name (for qualification if needed).

    Returns:
        Fully-qualified table name ready for Spark SQL (with backticks if needed).
    """
    if "." in name:
        # Already qualified; return unchanged
        return name
    # Bare name; qualify it
    return f"{catalog}.{schema}.`{name}`"


def _history_table_readable(spark: Any, history_table_fq: str) -> bool:
    """Check if a history table is readable in UC.

    Attempts a simple SELECT 1 query to verify the table exists and is accessible.
    This is a pure readability check without side effects.

    Args:
        spark: SparkSession.
        history_table_fq: Fully-qualified table name (e.g., "catalog.schema.table").

    Returns:
        True if the table is readable, False if any error occurs.
    """
    try:
        spark.sql(f"SELECT 1 FROM {history_table_fq} LIMIT 1").collect()
        return True
    except Exception:
        return False


def _resolve_mode(
    history_table_exists: bool, provisioning_succeeded: bool
) -> str:
    """Decide the mode given detect and provision outcomes (pure logic).

    Args:
        history_table_exists: True if the history table is already present.
        provisioning_succeeded: True if provisioning completed, CDF reached ONLINE,
            AND the UC history table is readable (verified post-provision).

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
    1. Detect. If history table exists, return it (preexisting).
    2. Provision. Create/reuse Lakebase project, seed Postgres, configure CDF (provisioned).
    3. Synthesize. On any failure, build history table in UC from committed seed (synthesized).

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
    if _history_table_readable(spark, history_table_fq):
        logger(f"[CDF] History table {spec_table} already exists (preexisting).")
        return CdfSourceReport(
            mode="preexisting",
            cdf_history_table=history_table_fq,
            notes=f"History table {spec_table} was already present.",
        )

    # --- Attempt Provision: Lakebase Postgres + CDF → UC ---
    provisioning_succeeded = False
    lakebase_project_used = None
    lakebase_db_resource_path = None
    discovered_uc_table = None

    # Provisioning requires both SDK (w) and an explicitly supplied project
    if w is not None and lakebase_project is not None:
        try:
            logger(f"[CDF] Attempting Lakebase provisioning with project {lakebase_project}...")
            (lakebase_project_used, lakebase_db_resource_path,
             discovered_uc_table) = (
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
    elif w is not None and lakebase_project is None:
        logger(
            f"[CDF] No Lakebase project supplied; skipping provisioning and falling back to synthesis."
        )

    # --- Decide mode ---
    mode = _resolve_mode(
        history_table_exists=False, provisioning_succeeded=provisioning_succeeded
    )

    # --- Synthesize fallback: build history table from seed ---
    actual_history_table = spec_table  # Default to spec name
    if mode == "provisioned" and discovered_uc_table:
        # Use the discovered CDF-created table name for provisioned mode
        actual_history_table = discovered_uc_table

    if mode == "synthesized":
        actual_history_table = spec_table  # Synthesized uses the spec name
        try:
            logger(f"[CDF] Synthesizing fallback: building history table from seed...")
            history_table_fq_synth = f"{catalog}.{schema}.`{actual_history_table}`"
            _synthesize_history_table(
                spark=spark,
                config=config,
                spec=spec,
                repo_root=repo_root,
                history_table_fq=history_table_fq_synth,
                logger=logger,
            )
            logger(f"[CDF] Synthesized history table {actual_history_table}.")
        except Exception as e:
            raise RuntimeError(
                f"Failed to synthesize CDF history table (even after provisioning "
                f"failure): {type(e).__name__}: {e}"
            ) from e

    # --- Build fully-qualified table name with actual table name ---
    # If mode is "provisioned", actual_history_table is already fully-qualified from CDF discovery
    if mode == "provisioned":
        actual_history_table_fq = _as_fq_table(actual_history_table, catalog, schema)
    else:
        # For preexisting and synthesized, use the spec name (bare)
        actual_history_table_fq = f"{catalog}.{schema}.`{actual_history_table}`"

    # --- Save metadata for teardown to find ---
    try:
        import json

        report_obj = {
            "mode": mode,
            "cdf_history_table": actual_history_table_fq,
            "lakebase_project": lakebase_project_used,
            "lakebase_database_resource_path": lakebase_db_resource_path,
            "domain": config.domain,
            "notes": (
                f"Mode: {mode}. History table: {actual_history_table}. "
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
        cdf_history_table=actual_history_table_fq,
        lakebase_project=lakebase_project_used,
        lakebase_database_resource_path=lakebase_db_resource_path,
        notes=(
            f"Mode: {mode}. History table: {actual_history_table}. "
            f"Lakebase project: {lakebase_project_used or 'none'}."
        ),
    )


def _provision_lakebase_cdf_config(
    w: Any,
    config: Any,
    spec: Any,
    spark: Any,
    repo_root: str,
    lakebase_project: str,
    lakebase_database: Optional[str],
    timeout_s: float,
    logger: Any,
) -> tuple[str, str, str]:
    """Provision Lakebase Postgres + seed + CDF config → UC, with readability verification.

    Participants must create the Lakebase project beforehand; this function uses the
    supplied project to discover branch/database, seed Postgres, and configure CDF.

    Performs the full three-step sequence:
    1. Discover Lakebase project branch and database.
    2. Seed Postgres schema + table and configure CDF.
    3. Poll until CDF reaches STREAMING and verify the UC history table is readable.

    Only returns successfully if all steps complete AND the UC table is verified readable.

    Returns:
        (project_id, database_resource_path, discovered_uc_table)
        These are the identities needed by the notebook and the actual UC table created by CDF.

    Raises:
        Exception: If any step fails (branch not found, database not found, CDF errors,
            timeout, table not readable after STREAMING, etc). The caller handles the
            exception and falls back to synthesis. The participant owns the project,
            so this function never deletes it on failure.

    API Reference (per authoritative lakehouse-sync.md):
    - project: projects/<PROJECT_ID>
    - branch: projects/<PROJECT_ID>/branches/<BRANCH_ID>
    - endpoint: projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID>
    - database: projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID> (resource path)
    - CdfConfig imported from databricks.sdk.service.postgres
    - parent for CDF is DATABASE resource path, not project or database name
    - list_cdf_statuses catches NotFound (404) when none exist
    """
    from databricks.sdk.service.postgres import CdfConfig, EndpointType

    domain = config.domain
    postgres_schema = f"{domain}_seed"
    catalog = config.catalog
    uc_schema = config.schema
    project_id = lakebase_project

    try:
        # --- Use the supplied Lakebase project ---
        logger(f"[CDF] Using supplied Lakebase project: {project_id}")

        # --- Discover the production branch and database ---
        logger(f"[CDF] Discovering branch and database for project {project_id}...")

        # List branches to get the default branch
        branches = list(w.postgres.list_branches(parent=f"projects/{project_id}"))
        production_branch = None

        # Find the branch marked as default
        for branch in branches:
            if hasattr(branch, "status") and hasattr(branch.status, "default"):
                if branch.status.default:
                    production_branch = branch.name
                    break

        if not production_branch:
            # Fallback: use the first branch
            if branches:
                production_branch = branches[0].name
            else:
                raise RuntimeError(f"No branches found in project {project_id}")

        logger(f"[CDF] Using branch: {production_branch}")

        # --- Discover or use the supplied database ---
        db_resource_path = None
        if lakebase_database:
            # Participant supplied a database resource path; use it directly
            logger(f"[CDF] Using supplied database: {lakebase_database}")
            db_resource_path = lakebase_database
        else:
            # Discover the default databricks_postgres database
            logger(f"[CDF] Discovering default database in {production_branch}...")
            databases = list(w.postgres.list_databases(parent=production_branch))
            for db in databases:
                # Match on postgres_database name
                if hasattr(db, "status") and hasattr(db.status, "postgres_database"):
                    if db.status.postgres_database == "databricks_postgres":
                        db_resource_path = db.name
                        break
                # Fallback: check spec
                elif hasattr(db, "spec") and hasattr(db.spec, "postgres_database"):
                    if db.spec.postgres_database == "databricks_postgres":
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

        # Prefer read-write endpoint
        endpoint = None
        for ep in endpoints:
            if (hasattr(ep, "spec") and hasattr(ep.spec, "endpoint_type") and
                ep.spec.endpoint_type == EndpointType.ENDPOINT_TYPE_READ_WRITE):
                endpoint = ep
                break

        if not endpoint:
            # Fallback to first endpoint
            endpoint = endpoints[0]

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
        cred = w.postgres.generate_database_credential(endpoint=endpoint_fq)
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

        # --- Create or reuse CDF config (idempotent) ---
        logger(
            f"[CDF] Creating or reusing CDF config: {postgres_schema} → "
            f"{catalog}.{uc_schema}..."
        )
        cdf_config_id = f"{domain}_cdf"

        # Check if config already exists to make this idempotent
        existing_configs = [
            c for c in w.postgres.list_cdf_configs(parent=db_resource_path)
            if getattr(c, "cdf_config_id", None) == cdf_config_id
        ]

        if existing_configs:
            # Reuse existing config
            cfg_name = existing_configs[0].name
            logger(f"[CDF] CDF config already exists: {cfg_name}")
        else:
            # Create new config
            logger(f"[CDF] Creating new CDF config with ID {cdf_config_id}...")
            cfg_result = w.postgres.create_cdf_config(
                parent=db_resource_path,
                cdf_config=CdfConfig(
                    catalog=catalog,
                    schema=uc_schema,
                    postgres_schema=postgres_schema,
                ),
                cdf_config_id=cdf_config_id,
            )
            # Try to get the resource name from the LRO result
            try:
                cfg_name = cfg_result.wait().name
                logger(f"[CDF] CDF config created: {cfg_name}")
            except Exception:
                # Fallback: re-list to find the just-created config
                logger(f"[CDF] Fallback: re-listing to find created config...")
                configs = [
                    c for c in w.postgres.list_cdf_configs(parent=db_resource_path)
                    if getattr(c, "cdf_config_id", None) == cdf_config_id
                ]
                if configs:
                    cfg_name = configs[0].name
                    logger(f"[CDF] Found created config: {cfg_name}")
                else:
                    raise RuntimeError(
                        f"Failed to create or find CDF config {cdf_config_id}"
                    )

        # --- Poll CDF status until STREAMING and discover actual UC table ---
        logger(f"[CDF] Polling CDF status until STREAMING (timeout: {timeout_s}s)...")
        discovered_uc_table = _poll_cdf_status(
            w=w,
            cfg_resource_name=cfg_name,
            postgres_table_seed=spec.txn_seed_dir,
            timeout_s=timeout_s,
            logger=logger,
        )

        # --- Verify UC history table is readable (post-provision verification) ---
        # Use the discovered UC table name
        if not discovered_uc_table:
            # Fallback to spec-assumed name if discovery didn't return a table
            discovered_uc_table = spec.lakebase_cdf_table

        # discovered_uc_table may be already fully-qualified; use helper to avoid double-qualification
        history_table_fq = _as_fq_table(discovered_uc_table, catalog, uc_schema)
        logger(f"[CDF] Verifying UC history table is readable: {history_table_fq}...")
        _verify_history_table_readable(
            spark=spark,
            history_table_fq=history_table_fq,
            timeout_s=30.0,
            logger=logger,
        )

        return project_id, db_resource_path, discovered_uc_table

    except Exception as e:
        # Participant owns the project, so we never delete it on failure
        # Re-raise the original exception for the caller to handle
        raise


def _seed_postgres(
    config: Any, spec: Any, repo_root: str, host: str, user: str, token: str,
    schema: str, logger: Any
) -> None:
    """Seed Postgres schema + table + CSV data via driver-side COPY, idempotently.

    On a re-run, this function checks if the table is already fully seeded and skips
    the COPY to avoid duplicate key violations. If the table exists with a different
    row count, it is truncated and reloaded. On a fresh run, the COPY proceeds as normal.

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

    expected_row_count = len(rows)
    table_fq = f"{schema}.{spec.txn_seed_dir}"

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

            # Check current row count to decide whether to skip, truncate+reload, or load fresh
            try:
                cur.execute(f"SELECT count(*) FROM {table_fq}")
                current_row_count = cur.fetchone()[0]
            except Exception as e:
                # Table may not exist yet or query failed; treat as empty (0 rows)
                logger(f"[CDF] Could not query table row count: {e}; treating as empty")
                current_row_count = 0

            if current_row_count == expected_row_count:
                # Table already fully seeded; skip COPY
                logger(
                    f"[CDF] Postgres table {table_fq} already has {current_row_count} rows; "
                    f"skipping seed load"
                )
            elif current_row_count > 0:
                # Partial or mismatched load; truncate and reload
                logger(
                    f"[CDF] Postgres table {table_fq} has {current_row_count} rows "
                    f"(expected {expected_row_count}); truncating and reloading"
                )
                cur.execute(f"TRUNCATE TABLE {table_fq}")

                logger(
                    f"[CDF] Loading {expected_row_count} rows into {table_fq}"
                )
                with open(csv_path, "r") as csv_file:
                    with cur.copy(
                        f"COPY {table_fq} ({', '.join(columns)}) FROM STDIN "
                        f"WITH (FORMAT csv, HEADER true)"
                    ) as copy:
                        copy.write(csv_file.read())
            else:
                # Fresh load (0 rows in table)
                logger(
                    f"[CDF] Loading {expected_row_count} rows into {table_fq}"
                )
                with open(csv_path, "r") as csv_file:
                    with cur.copy(
                        f"COPY {table_fq} ({', '.join(columns)}) FROM STDIN "
                        f"WITH (FORMAT csv, HEADER true)"
                    ) as copy:
                        copy.write(csv_file.read())

        conn.commit()
    logger(f"[CDF] Postgres seeding complete")


def _poll_cdf_status(
    w: Any, cfg_resource_name: str, postgres_table_seed: str,
    timeout_s: float, logger: Any
) -> Optional[str]:
    """Poll CDF status until STREAMING and return discovered UC table name.

    Args:
        w: WorkspaceClient.
        cfg_resource_name: CDF config resource name (the parent for list_cdf_statuses).
        postgres_table_seed: The postgres table seed name to match (for discovery).
        timeout_s: Timeout in seconds.
        logger: Logging callable.

    Returns:
        The discovered UC table name (from status.uc_table) when CDF reaches STREAMING.
        Note: uc_table is already fully-qualified (e.g., 'catalog.schema.table').

    Raises:
        TimeoutError: If STREAMING is not reached within timeout.
        RuntimeError: If status is TERMINATED.
    """
    import time
    from databricks.sdk.errors.platform import NotFound
    from databricks.sdk.service.postgres import CdfState

    start = time.time()
    while time.time() - start < timeout_s:
        try:
            statuses = list(w.postgres.list_cdf_statuses(parent=cfg_resource_name))
        except NotFound:
            # Empty list returns 404
            logger(f"[CDF] CDF config not yet ready; retrying...")
            statuses = []
        except Exception as e:
            logger(f"[CDF] Error listing CDF statuses: {e}; retrying...")
            statuses = []

        # Find the matching CdfStatus by postgres_table
        matching_status = None
        for status in statuses:
            # Match by postgres_table containing the seed directory name
            postgres_table = getattr(status, "postgres_table", "")
            if postgres_table and postgres_table_seed in postgres_table:
                matching_status = status
                break

        # Fallback: if only one status, assume it's ours
        if not matching_status and len(statuses) == 1:
            matching_status = statuses[0]

        if matching_status:
            state = getattr(matching_status, "state", None)
            postgres_table = getattr(matching_status, "postgres_table", "")
            uc_table = getattr(matching_status, "uc_table", "")
            status_detail = getattr(matching_status, "status_detail", "")

            logger(
                f"[CDF] CDF status: state={state}, postgres_table={postgres_table}, "
                f"uc_table={uc_table}, detail={status_detail}"
            )

            if state == CdfState.CDF_STATE_STREAMING:
                logger(f"[CDF] CDF is STREAMING; returning discovered uc_table: {uc_table}")
                return uc_table
            elif state == CdfState.CDF_STATE_TERMINATED:
                raise RuntimeError(
                    f"CDF for {postgres_table} terminated: {status_detail}"
                )
            # else: SNAPSHOTTING, SKIPPED, or other non-final states; keep polling

        time.sleep(5)

    raise TimeoutError(
        f"CDF config {cfg_resource_name} did not reach STREAMING within {timeout_s}s"
    )


def _verify_history_table_readable(
    spark: Any, history_table_fq: str, timeout_s: float = 30.0, logger: Any = None
) -> None:
    """Verify UC history table is readable with a bounded grace poll.

    After CDF reaches ONLINE, the synced Delta table may not be immediately
    accessible. This function polls until the table is readable or a grace
    timeout is reached.

    Args:
        spark: SparkSession.
        history_table_fq: Fully-qualified UC table name.
        timeout_s: Grace timeout in seconds (default 30s).
        logger: Logging callable (optional).

    Raises:
        RuntimeError: If the table is not readable within the grace timeout.
    """
    import time

    if logger is None:
        logger = lambda *args, **kwargs: None

    start = time.time()
    while time.time() - start < timeout_s:
        if _history_table_readable(spark, history_table_fq):
            logger(f"[CDF] History table {history_table_fq} is now readable")
            return
        logger(f"[CDF] History table not yet readable; polling (elapsed: {time.time() - start:.1f}s)...")
        time.sleep(2)

    raise RuntimeError(
        f"History table {history_table_fq} did not become readable within {timeout_s}s "
        f"after CDF reached ONLINE. CDF provisioning failed."
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
    from pyspark.sql.types import IntegerType, LongType, TimestampNTZType

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

    # Use a single monotonically_increasing_id() and assign to both _pg_lsn and _sort_by
    # to ensure they have the same value and consistent ordering
    mono_id = F.monotonically_increasing_id().cast(LongType())
    seed_df = seed_df.withColumn("_pg_lsn", mono_id)
    seed_df = seed_df.withColumn("_sort_by", F.col("_pg_lsn"))
    seed_df = seed_df.withColumn("_pg_xid", F.lit(None).cast(IntegerType()))
    seed_df = seed_df.withColumn("_timestamp", F.current_timestamp().cast(TimestampNTZType()))

    logger(f"[CDF] Writing {seed_df.count()} rows to {history_table_fq}")
    (
        seed_df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(history_table_fq)
    )
    logger(f"[CDF] Synthesized history table complete")
