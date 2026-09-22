"""The ``07_app`` checkpoint: a deployed data app over a Lakebase synced table.

Ticket #12 ships a **provided FastAPI app** that participants wire to two things —
their per-participant Genie Agent (#11) and a **Lakebase synced table** created
from one of the #8 gold tables. This checkpoint proves the *deployed* slice using
**only externally-observable platform state** — never the notebook, the app source,
or how either object was created. A participant can reach the same state from the
Apps UI, the CLI, or the SDK and it passes identically.

Two independent facts are asserted, each hardened against a false pass:

* **The caller's own Lakebase synced table exists and serves the expected rows.**
  The whole team shares one workspace, so the synced table carries a
  per-participant identity suffix (see #22); the check therefore takes the
  expected ``synced_table`` name as a **required** input — there is deliberately
  no default, fixed, or shared name. It must sync from the expected gold table
  (Finance default ``gold_contract_performance``), carry the expected primary
  key, be **owned by the caller** (its Unity Catalog owner must match the
  required ``owner`` — so another participant's synced table is never adopted),
  and be **online** — Unity-Catalog-provisioned with a healthy, completed sync.
  A missing synced table is RED; the wrong source or key is RED; one owned by
  someone else is RED; a table still provisioning, offline, or whose sync
  pipeline failed is RED. Serving is verified **fail-closed**: the served row
  count (through the client's ``count_rows`` or an observed ``served_row_count``)
  must be **positive** and, when the source count is known, equal to it — and if
  the count cannot be obtained at all the checkpoint stays RED, so an online-but-
  empty/stale synced table can never pass on an unverified count.

* **The caller's own app is deployed and running.** The app name is
  per-participant too, so ``app_name`` is a **required** input with no default,
  and the app must be **owned by the caller** (creator / service principal must
  match ``owner``). It must exist, its latest deployment must have **succeeded**,
  and its compute must be **running** — deploying an app can leave it stopped,
  and a stopped app answers nothing, so a stopped/starting/errored app is RED
  (the observable form of the "app start is handled explicitly" acceptance
  criterion). When the app exposes a reachable health endpoint it is probed
  best-effort; an explicit unhealthy response is RED.

**Domain-generic.** No Finance-only object name is baked into the logic. The
gold source table, the primary key, the expected row count, and the app/synced
names are all overridable through ``workshop.check`` extras, so Security (#13)
and ITSM (#14) reuse this module with their own app, synced table, and gold
source — no edits.

**Off-platform testable.** Like every other checkpoint, this one takes its
Databricks dependency by injection rather than importing an SDK at module load:
pass a normalized app client (or a raw ``WorkspaceClient``) as the ``apps`` extra.
When neither is supplied it lazily constructs a ``WorkspaceClient`` on a live
workspace; unit tests inject a fake client and never touch the network.

Run it as::

    workshop.check(
        "07_app",
        spark=spark,                        # optional; enables source-count parity
        catalog=config.catalog,
        schema=config.schema,
        apps=WorkspaceClient(),             # or a normalized client / fake
        app_name=app_name,                  # per-participant, required
        synced_table=synced_table,          # per-participant, required (UC name)
        owner=me,                           # required — binds both to YOU
        lakebase_endpoint=endpoint,         # so served rows can be verified
        lakebase_host=host,
    )

Extras forwarded through ``ctx.extras``:

* ``app_name`` — the expected per-participant Databricks App name (**required**).
* ``synced_table`` — the fully-qualified Unity Catalog name of the caller's own
  Lakebase synced table (**required**; e.g. ``lb_cat.public.gold_contract_perf``).
* ``apps`` — a normalized app client, a raw ``WorkspaceClient``, or ``None`` to
  build one from ambient workspace credentials.
* ``source_table`` — the gold table the synced table must sync from (default
  ``gold_contract_performance``). A local name is resolved in the participant
  schema; a dotted name is treated as an explicit fully-qualified reference.
* ``primary_key_columns`` — the primary key the synced table must carry (default
  ``("contract_id",)``); compared as an order-insensitive set.
* ``owner`` — **required** ownership binding (the caller's identity, e.g.
  ``current_user()``). Both the app (creator / service principal) and the synced
  table (Unity Catalog owner) must match it, so a same-named resource owned by
  someone else is never adopted.
* ``expected_row_count`` / ``served_row_count`` — optional integers. The served
  count must be positive; when an expected count is known (given here, or counted
  from the source table when ``spark`` is provided) the served count must equal
  it. If no served count can be obtained at all, the checkpoint stays RED.
* ``require_running`` — default ``True``; set ``False`` only to accept a
  successfully-deployed-but-stopped app (not recommended — a stopped app answers
  nothing).
* ``probe_health`` — default ``True``; set ``False`` to skip the best-effort HTTP
  health probe.
* ``lakebase_endpoint`` / ``lakebase_host`` / ``lakebase_user`` /
  ``lakebase_database`` — connection hints the live SDK adapter uses to count
  served rows directly from Lakebase Postgres in the real participant flow. The
  normal invocation should pass ``lakebase_endpoint`` + ``lakebase_host`` (or an
  observed ``served_row_count``) so the fail-closed serving check can pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

APP_CHECKPOINT_ID = "07_app"

#: The gold table a Finance synced table must serve — the compact contract-grain
#: mart from #8 (one denormalized row per commercial agreement). Overridable via
#: the ``source_table`` extra so Security/ITSM point at their own serving table.
DEFAULT_SOURCE_TABLE = "gold_contract_performance"

#: The primary key that gold serving table is synced on. Overridable via
#: ``primary_key_columns`` for domain reuse.
DEFAULT_PRIMARY_KEY: tuple[str, ...] = ("contract_id",)

_UNSET = object()


# --- normalized client interface -------------------------------------------
# The checkpoint speaks to the platform through a few small, stable reads:
# get_app, get_synced_table, get_table_owner (required), plus best-effort
# count_rows and probe. The live adapter (:class:`_SdkAppClient`) maps the
# Apps/Database/Tables SDK shapes onto them; tests supply a fake implementing the
# same surface. Keeping the interface narrow isolates SDK-shape fragility here.


@dataclass(frozen=True)
class AppInfo:
    """One Databricks App's observable state.

    ``compute_state`` / ``app_state`` / ``deployment_state`` are the raw platform
    state strings (lowercased); the checkpoint interprets them so the pass/fail
    rule stays visible and unit-tested rather than hidden in the adapter.
    """

    name: str
    compute_state: str | None = None
    app_state: str | None = None
    deployment_state: str | None = None
    url: str | None = None
    creator: str | None = None
    service_principal_name: str | None = None
    service_principal_client_id: str | None = None


@dataclass(frozen=True)
class SyncedTableInfo:
    """One Lakebase synced table's observable configuration and sync state.

    ``provisioning_state`` is the Unity Catalog provisioning state (e.g.
    ``active``); ``detailed_state`` is the sync pipeline's detailed state (e.g.
    ``synced_table_online_no_pending_update``). Both are lowercased raw strings.
    """

    name: str
    source_table: str | None = None
    primary_key_columns: tuple[str, ...] = ()
    scheduling_policy: str | None = None
    provisioning_state: str | None = None
    detailed_state: str | None = None
    message: str | None = None


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(APP_CHECKPOINT_ID, False, message, details)


def _normalize_reference(value: str) -> str:
    """Compare UC references independent of SQL quoting/case/whitespace.

    Mirrors ``genie._normalize_reference`` / ``metrics._normalize_reference`` —
    backticks, double quotes, and spaces are removed and the result lowercased;
    dots are preserved so ``catalog.schema.table`` stays comparable.
    """
    return value.replace("`", "").replace('"', "").replace(" ", "").lower()


def _required_name(ctx: CheckContext, key: str) -> str | None:
    value = ctx.extras.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _primary_key(value: Any) -> tuple[str, ...]:
    """Resolve the expected primary-key columns from an extra."""
    if value is _UNSET or value is None:
        return DEFAULT_PRIMARY_KEY
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        raise TypeError("primary_key_columns must be a column name or a list of names")
    columns = tuple(value)
    if not columns or any(not isinstance(c, str) or not c.strip() for c in columns):
        raise ValueError("primary_key_columns entries must be non-empty column names")
    return columns


def _synced_online(info: SyncedTableInfo) -> bool:
    """True only when the synced table is provisioned AND actively serving data.

    The Unity Catalog provisioning state must be ``active`` and the sync
    pipeline's detailed state must be one of the ``online`` states with no
    failure — so a table still provisioning, offline, or whose pipeline failed
    (``synced_table_online_pipeline_failed``) is never treated as serving.
    """
    provisioning = (info.provisioning_state or "").lower()
    detailed = (info.detailed_state or "").lower()
    if provisioning and provisioning != "active":
        return False
    return detailed.startswith("synced_table_online") and "failed" not in detailed


def _app_running(info: AppInfo) -> bool:
    """True when the app's compute is active (and its app status is not a
    non-running state). A stopped/starting/errored compute is not running."""
    compute = (info.compute_state or "").lower()
    app_state = (info.app_state or "").lower()
    if compute != "active":
        return False
    # app_state may be absent on some reads; when present it must be running.
    return app_state in ("", "running")


def _app_deployed(info: AppInfo) -> bool:
    """True only when the app's latest deployment succeeded (never-deployed is
    ``None`` and fails this guard)."""
    return (info.deployment_state or "").lower() == "succeeded"


def _owned(info: AppInfo, owner: str) -> bool:
    """True when the app is demonstrably the caller's own.

    Matches the supplied ``owner`` against the app's creator or its service
    principal identity, so a same-named app owned by someone else is not adopted.
    """
    candidates = {
        (info.creator or "").strip().lower(),
        (info.service_principal_name or "").strip().lower(),
        (info.service_principal_client_id or "").strip().lower(),
    }
    candidates.discard("")
    return owner.strip().lower() in candidates


# --- live client resolution -------------------------------------------------


class _SdkAppClient:
    """Normalize the Databricks Apps + Database SDK surfaces onto our interface.

    Only ever constructed on a live workspace, so importing the SDK errors here
    is safe. Every read is defensive: a missing object comes back as ``None`` (a
    clean RED at the checkpoint) rather than an exception, and ``count_rows`` is
    best-effort — it returns ``None`` unless connection hints are supplied and a
    Postgres driver is importable.
    """

    def __init__(self, workspace: Any, pg: dict[str, Any] | None = None) -> None:
        self._w = workspace
        self._pg = pg or {}

    def _not_found(self, exc: Exception) -> bool:
        text = f"{type(exc).__name__} {exc}".lower()
        return "notfound" in text or "does_not_exist" in text or "not found" in text

    def get_app(self, app_name: str) -> AppInfo | None:
        try:
            app = self._w.apps.get(name=app_name)
        except Exception as exc:
            if self._not_found(exc):
                return None
            raise
        compute = getattr(getattr(app, "compute_status", None), "state", None)
        app_status = getattr(getattr(app, "app_status", None), "state", None)
        active = getattr(app, "active_deployment", None)
        deployment = getattr(getattr(active, "status", None), "state", None)
        return AppInfo(
            name=getattr(app, "name", app_name) or app_name,
            compute_state=_enum_str(compute),
            app_state=_enum_str(app_status),
            deployment_state=_enum_str(deployment),
            url=getattr(app, "url", None),
            creator=getattr(app, "creator", None),
            service_principal_name=getattr(app, "service_principal_name", None),
            service_principal_client_id=getattr(app, "service_principal_client_id", None),
        )

    def get_synced_table(self, name: str) -> SyncedTableInfo | None:
        try:
            table = self._w.database.get_synced_database_table(name=name)
        except Exception as exc:
            if self._not_found(exc):
                return None
            raise
        spec = getattr(table, "spec", None)
        status = getattr(table, "data_synchronization_status", None)
        pk = getattr(spec, "primary_key_columns", None) or ()
        return SyncedTableInfo(
            name=getattr(table, "name", name) or name,
            source_table=getattr(spec, "source_table_full_name", None),
            primary_key_columns=tuple(str(c) for c in pk),
            scheduling_policy=_enum_str(getattr(spec, "scheduling_policy", None)),
            provisioning_state=_enum_str(
                getattr(table, "unity_catalog_provisioning_state", None)
            ),
            detailed_state=_enum_str(getattr(status, "detailed_state", None)),
            message=getattr(status, "message", None),
        )

    def get_table_owner(self, name: str) -> str | None:
        """The Unity Catalog owner of the synced table (its creator identity).

        This is the ownership-scoped observable that binds the synced table to a
        participant — the analog of a Genie agent's ``parent_path``. A missing
        table or read error returns ``None`` (the checkpoint then refuses to treat
        it as the caller's own).
        """
        try:
            return getattr(self._w.tables.get(full_name=name), "owner", None)
        except Exception:  # noqa: BLE001 - unverifiable ownership → None → RED
            return None

    def count_rows(self, info: SyncedTableInfo) -> int | None:
        """Best-effort served-row count from Lakebase Postgres.

        Requires ``lakebase_endpoint`` (for the OAuth credential) plus a host, and
        an importable Postgres driver. Returns ``None`` on any missing hint or
        failure — and because serving is verified fail-closed, an unverifiable
        count keeps the checkpoint RED rather than passing.
        """
        endpoint = self._pg.get("endpoint")
        host = self._pg.get("host")
        if not endpoint or not host:
            return None
        parts = info.name.split(".")
        if len(parts) < 2:
            return None
        pg_schema, pg_table = parts[-2], parts[-1]
        try:
            token = self._w.postgres.generate_database_credential(
                endpoint=endpoint
            ).token
            # Live-only, best-effort: import the driver lazily.
            import psycopg

            user = self._pg.get("user") or self._w.current_user.me().user_name
            database = self._pg.get("database") or "databricks_postgres"
            with psycopg.connect(
                host=host, dbname=database, user=user, password=token,
                sslmode="require",
            ) as conn, conn.cursor() as cur:
                # Identifiers are the fixed synced-table name (not user input).
                cur.execute(f'SELECT count(*) FROM "{pg_schema}"."{pg_table}"')
                row = cur.fetchone()
                return int(row[0]) if row else None
        except Exception:  # noqa: BLE001 - best-effort; fall back to state proof
            return None

    def probe(self, url: str) -> int | None:
        """Best-effort authenticated GET of the app's health endpoint."""
        try:
            # Live-only, best-effort: import the HTTP client lazily.
            import requests

            cfg = getattr(self._w, "config", None)
            headers = cfg.authenticate() if cfg is not None else {}
            target = url.rstrip("/") + "/api/health"
            resp = requests.get(target, headers=headers, timeout=10, allow_redirects=False)
            return int(resp.status_code)
        except Exception:  # noqa: BLE001 - best-effort
            return None


def _enum_str(value: Any) -> str | None:
    """Lowercased string of an SDK enum/value, or ``None``."""
    if value is None:
        return None
    return str(getattr(value, "value", value)).lower()


def _resolve_client(ctx: CheckContext) -> Any:
    """Return the injected client, wrap a raw WorkspaceClient, or build one."""
    injected = ctx.extras.get("apps")
    pg = {
        "endpoint": ctx.extras.get("lakebase_endpoint"),
        "host": ctx.extras.get("lakebase_host"),
        "user": ctx.extras.get("lakebase_user"),
        "database": ctx.extras.get("lakebase_database"),
    }
    if injected is not None:
        normalized = ("get_app", "get_synced_table", "get_table_owner")
        if all(hasattr(injected, name) for name in normalized):
            return injected
        if hasattr(injected, "apps") and hasattr(injected, "database"):
            return _SdkAppClient(injected, pg)
        raise TypeError(
            "the 'apps' extra must be a WorkspaceClient or a normalized app "
            "client exposing get_app/get_synced_table/get_table_owner"
        )
    # Lazy, live-only import so `import workshop` never needs databricks-sdk.
    from databricks.sdk import WorkspaceClient

    return _SdkAppClient(WorkspaceClient(), pg)


def _expected_source(ctx: CheckContext) -> tuple[str, str]:
    """Return (display, normalized) for the expected gold source table."""
    name = ctx.extras.get("source_table") or DEFAULT_SOURCE_TABLE
    display = name if "." in name else ctx.fully_qualified(name)
    return display, _normalize_reference(display)


def _source_matches(observed: str | None, expected_norm: str) -> bool:
    """True when the synced table's source is the caller's OWN gold table.

    Requires normalized **fully-qualified** equality (same quote/case/whitespace
    normalization used elsewhere): a synced table sourced from another
    participant's ``<other-catalog>.<other-schema>.gold_contract_performance``
    shares the basename but is NOT a match — there is deliberately no
    last-segment fallback, so it cannot be adopted.
    """
    if not observed:
        return False
    return _normalize_reference(observed) == expected_norm


def _served_rows(client: Any, ctx: CheckContext, info: SyncedTableInfo) -> int | None:
    """Best-effort served row count: the client's counter, then an observed value."""
    counter = getattr(client, "count_rows", None)
    if callable(counter):
        try:
            served = counter(info)
        except Exception:  # noqa: BLE001 - best-effort; never fail the check here
            served = None
        if served is not None:
            return int(served)
    observed = ctx.extras.get("served_row_count")
    return int(observed) if isinstance(observed, int) else None


def _source_count(ctx: CheckContext) -> int | None:
    """Count rows in the expected source table when a Spark session is available."""
    explicit = ctx.extras.get("expected_row_count")
    if isinstance(explicit, int):
        return explicit
    if ctx.spark is None:
        return None
    name = ctx.extras.get("source_table") or DEFAULT_SOURCE_TABLE
    source = name if "." in name else ctx.fully_qualified(name)
    try:
        return int(ctx.spark.sql(f"SELECT count(*) FROM {source}").collect()[0][0])
    except Exception:  # noqa: BLE001 - parity is a bonus guard, not a prerequisite
        return None


@checkpoint(
    APP_CHECKPOINT_ID,
    summary=(
        "The caller's per-participant Lakebase synced table serves the expected "
        "gold data, and their provided data app is deployed and running."
    ),
)
def check_app(ctx: CheckContext) -> CheckResult:
    """Validate the deployed app + synced-table slice from observable state."""
    if not ctx.catalog or not ctx.schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('07_app', "
            "catalog=config.catalog, schema=config.schema, apps=..., "
            "app_name=..., synced_table=...).",
            {"catalog": ctx.catalog, "schema": ctx.schema},
        )

    app_name = _required_name(ctx, "app_name")
    if not app_name:
        return _fail(
            "No app_name given. A Databricks App is workspace-scoped and shared "
            "across a team, so pass your per-participant app name: "
            "workshop.check('07_app', ..., app_name=your_app_name).",
            {"stage": "configuration", "reason": "missing_app_name"},
        )
    synced_table = _required_name(ctx, "synced_table")
    if not synced_table:
        return _fail(
            "No synced_table given. A Lakebase synced table is workspace-scoped, "
            "so pass your per-participant synced-table name (the Unity Catalog "
            "name): workshop.check('07_app', ..., synced_table=your_synced_table).",
            {"stage": "configuration", "reason": "missing_synced_table"},
        )
    owner = _required_name(ctx, "owner")
    if not owner:
        return _fail(
            "No owner given. The app and synced table are workspace-scoped and "
            "shared across a team, so this checkpoint must confirm they are YOUR "
            "own — pass your identity: workshop.check('07_app', ..., "
            "owner=spark.sql('SELECT current_user()').collect()[0][0]).",
            {"stage": "configuration", "reason": "missing_owner"},
        )

    try:
        expected_source_display, expected_source_norm = _expected_source(ctx)
        expected_pk = _primary_key(ctx.extras.get("primary_key_columns", _UNSET))
    except (TypeError, ValueError) as exc:
        return _fail(
            f"Invalid app checkpoint configuration: {exc}.",
            {"stage": "configuration", "error_type": type(exc).__name__},
        )

    try:
        client = _resolve_client(ctx)
    except Exception as exc:  # noqa: BLE001 - participant-facing RED state
        return _fail(
            "This checkpoint needs workspace access. Pass a WorkspaceClient (or a "
            "normalized app client) as apps=..., or run it where a WorkspaceClient "
            f"can be built ({type(exc).__name__}: {exc}).",
            {"stage": "client", "error_type": type(exc).__name__},
        )

    # --- 1. Lakebase synced table: exists, right source/key, online, serving ---
    try:
        synced = client.get_synced_table(synced_table)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read the synced table {synced_table!r} "
            f"({type(exc).__name__}). Confirm Lakebase is enabled and you have "
            "access.",
            {"stage": "synced_read", "synced_table": synced_table,
             "error_type": type(exc).__name__},
        )
    if synced is None:
        return _fail(
            f"No Lakebase synced table named {synced_table!r} exists. Create your "
            "per-participant synced table from the gold serving table first.",
            {"stage": "synced_missing", "synced_table": synced_table},
        )

    if not _source_matches(synced.source_table, expected_source_norm):
        return _fail(
            f"Synced table {synced_table!r} does not sync from the expected gold "
            f"table {expected_source_display!r} (it syncs from "
            f"{synced.source_table!r}). Point the synced table at your gold "
            "serving table.",
            {"stage": "synced_source", "synced_table": synced_table,
             "expected_source": expected_source_display,
             "observed_source": synced.source_table},
        )

    observed_pk = {c.strip().lower() for c in synced.primary_key_columns}
    if observed_pk != {c.strip().lower() for c in expected_pk}:
        return _fail(
            f"Synced table {synced_table!r} has primary key "
            f"{list(synced.primary_key_columns)}, expected {list(expected_pk)}.",
            {"stage": "synced_key", "synced_table": synced_table,
             "expected_primary_key": list(expected_pk),
             "observed_primary_key": list(synced.primary_key_columns)},
        )

    # Ownership: the synced table must be demonstrably YOURS. Its Unity Catalog
    # owner (creator) is the ownership-scoped observable — a same-named table
    # owned by another participant is never adopted.
    owner_fn = getattr(client, "get_table_owner", None)
    if not callable(owner_fn):
        return _fail(
            "This checkpoint cannot verify synced-table ownership with the given "
            "client. Pass a WorkspaceClient (or a normalized client exposing "
            "get_table_owner).",
            {"stage": "client", "reason": "no_owner_probe"},
        )
    try:
        synced_owner = owner_fn(synced_table)
    except Exception:  # noqa: BLE001
        synced_owner = None
    if not synced_owner or synced_owner.strip().lower() != owner.strip().lower():
        return _fail(
            f"Synced table {synced_table!r} is not owned by {owner!r} (owner="
            f"{synced_owner!r}); refusing to treat another participant's synced "
            "table as yours. Create your own per-participant synced table.",
            {"stage": "synced_ownership", "synced_table": synced_table,
             "owner": owner, "observed_owner": synced_owner},
        )

    if not _synced_online(synced):
        return _fail(
            f"Synced table {synced_table!r} is not online yet "
            f"(provisioning={synced.provisioning_state!r}, "
            f"sync={synced.detailed_state!r}). Wait for the sync to complete, or "
            "re-run it — a still-provisioning, offline, or failed sync serves no "
            "up-to-date data.",
            {"stage": "synced_offline", "synced_table": synced_table,
             "provisioning_state": synced.provisioning_state,
             "detailed_state": synced.detailed_state, "message": synced.message},
        )

    # Serving proof — FAIL CLOSED. An online synced table can still be empty or
    # stale, so the checkpoint must positively verify it serves rows; if the
    # served count cannot be obtained it stays RED (never a structure-only pass).
    served = _served_rows(client, ctx, synced)
    if served is None:
        return _fail(
            f"Could not verify that synced table {synced_table!r} is serving rows. "
            "An online sync can still be empty or stale, so this checkpoint needs "
            "a served-row count. Pass the Lakebase connection hints so the count "
            "can be read (lakebase_endpoint + lakebase_host, or a served_row_count "
            "observed from your synced table).",
            {"stage": "synced_unverified", "synced_table": synced_table},
        )
    if served <= 0:
        return _fail(
            f"Synced table {synced_table!r} is online but serves 0 rows. The "
            "sync produced no data — re-run it after the gold table is populated.",
            {"stage": "synced_empty", "synced_table": synced_table,
             "served_rows": served},
        )
    expected_rows = _source_count(ctx)
    if expected_rows is not None and served != expected_rows:
        return _fail(
            f"Synced table {synced_table!r} serves {served:,} rows but the "
            f"source {expected_source_display} has {expected_rows:,}; the "
            "synced data is stale or incomplete. Re-run the sync.",
            {"stage": "synced_parity", "synced_table": synced_table,
             "served_rows": served, "expected_rows": expected_rows},
        )

    # --- 2. Databricks App: the caller's own, deployed, and running ------------
    try:
        app = client.get_app(app_name)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read the app {app_name!r} ({type(exc).__name__}). Confirm "
            "Databricks Apps is enabled and you have access.",
            {"stage": "app_read", "app_name": app_name,
             "error_type": type(exc).__name__},
        )
    if app is None:
        return _fail(
            f"No Databricks App named {app_name!r} exists. Deploy your "
            "per-participant app first.",
            {"stage": "app_missing", "app_name": app_name},
        )

    # Ownership is required: the app must be demonstrably the caller's own, so a
    # known app_name belonging to another participant is never adopted.
    if not _owned(app, owner):
        return _fail(
            f"App {app_name!r} is not owned by {owner!r} (creator="
            f"{app.creator!r}, service principal="
            f"{app.service_principal_name!r}); refusing to treat another "
            "participant's app as yours.",
            {"stage": "app_ownership", "app_name": app_name, "owner": owner,
             "creator": app.creator,
             "service_principal_name": app.service_principal_name},
        )

    if not _app_deployed(app):
        return _fail(
            f"App {app_name!r} has no successful deployment "
            f"(deployment state={app.deployment_state!r}). Deploy the app and wait "
            "for the deployment to succeed.",
            {"stage": "app_deployment", "app_name": app_name,
             "deployment_state": app.deployment_state},
        )

    require_running = ctx.extras.get("require_running", True)
    if require_running and not _app_running(app):
        return _fail(
            f"App {app_name!r} is deployed but not running "
            f"(compute state={app.compute_state!r}, app status={app.app_state!r}). "
            "Start the app — deploying an app can leave it stopped, and a stopped "
            "app answers nothing.",
            {"stage": "app_stopped", "app_name": app_name,
             "compute_state": app.compute_state, "app_state": app.app_state},
        )

    probe_health = ctx.extras.get("probe_health", True)
    prober = getattr(client, "probe", None)
    if probe_health and callable(prober) and app.url:
        try:
            status = prober(app.url)
        except Exception:  # noqa: BLE001 - best-effort; never fail on probe error
            status = None
        if status is not None and not (200 <= status < 400):
            return _fail(
                f"App {app_name!r} is running but its health endpoint returned "
                f"HTTP {status}. Check the app logs — the app is not serving "
                "successfully.",
                {"stage": "app_health", "app_name": app_name, "url": app.url,
                 "http_status": status},
            )

    return CheckResult(
        APP_CHECKPOINT_ID,
        True,
        f"App {app_name!r} is deployed and running, and synced table "
        f"{synced_table!r} serves {expected_source_display} from Lakebase.",
        {
            "stage": "done",
            "app_name": app_name,
            "app_url": app.url,
            "compute_state": app.compute_state,
            "deployment_state": app.deployment_state,
            "synced_table": synced_table,
            "source_table": expected_source_display,
            "scheduling_policy": synced.scheduling_policy,
            "detailed_state": synced.detailed_state,
            "served_rows": served,
            "expected_rows": expected_rows,
        },
    )
