"""Behavioral tests for the observable-state ``07_app`` checkpoint.

Every test drives the real ``workshop.check`` seam with an injected fake app
client, so no Databricks SDK, notebook, or network is needed. The fake serves
only observable platform state. That state is a Databricks App's deploy/run
state and a Lakebase synced table's source/key/owner/sync state (and its served
row count), which is exactly what the checkpoint is allowed to assert on.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.app import (
    APP_CHECKPOINT_ID,
    AppInfo,
    SyncedTableInfo,
    _SdkAppClient,
    _synced_online,
)

CATALOG = "team-catalog"
SCHEMA = "finance data"  # a space in the schema name exercises quoting
APP = "stryker-finance-ada-lovelace"
# The synced table lives in the participant's OWN existing catalog/schema (no
# Lakebase catalog is created/registered), with a per-participant table name.
SYNCED = f"{CATALOG}.{SCHEMA}.gold_contract_performance_served_ada"
OWNER = "ada@example.com"
OTHER = "grace@example.com"


def _synced(
    *,
    source=None,
    pk=("contract_id",),
    provisioning="active",
    detailed="synced_table_online_no_pending_update",
):
    return SyncedTableInfo(
        name=SYNCED,
        source_table=(
            source if source is not None
            else f"{CATALOG}.{SCHEMA}.gold_contract_performance"
        ),
        primary_key_columns=pk,
        scheduling_policy="snapshot",
        provisioning_state=provisioning,
        detailed_state=detailed,
    )


def _app(
    *,
    compute="active",
    app_state="running",
    deployment="succeeded",
    url="https://app.example.databricksapps.com",
    creator=OWNER,
    sp=None,
):
    return AppInfo(
        name=APP,
        compute_state=compute,
        app_state=app_state,
        deployment_state=deployment,
        url=url,
        creator=creator,
        service_principal_name=sp,
    )


class FakeApps:
    """Serve one app + one synced table's observable state (owner, rows, probe)."""

    def __init__(
        self, *, app=..., synced=..., rows=3, synced_owner=OWNER,
        probe_status=None, raise_on=None,
    ):
        self._app = _app() if app is ... else app
        self._synced = _synced() if synced is ... else synced
        self._rows = rows
        self._synced_owner = synced_owner
        self._probe = probe_status
        self.raise_on = raise_on

    def get_app(self, name):
        if self.raise_on == "get_app":
            raise RuntimeError("PERMISSION_DENIED reading app")
        return self._app

    def get_synced_table(self, name):
        if self.raise_on == "get_synced_table":
            raise RuntimeError("PERMISSION_DENIED reading synced table")
        return self._synced

    def get_table_owner(self, name):
        return self._synced_owner

    def count_rows(self, info):
        return self._rows

    def probe(self, url):
        return self._probe


class FakeAppsNoCounter:
    """A client that can verify ownership but NOT serve a row count.

    Exercises the fail-closed serving check: with no obtainable count, an
    online synced table must still be RED (unverified), never a structure pass.
    """

    def __init__(self, *, app=..., synced=..., synced_owner=OWNER):
        self._app = _app() if app is ... else app
        self._synced = _synced() if synced is ... else synced
        self._synced_owner = synced_owner

    def get_app(self, name):
        return self._app

    def get_synced_table(self, name):
        return self._synced

    def get_table_owner(self, name):
        return self._synced_owner


def _check(client, **kwargs):
    kwargs.setdefault("app_name", APP)
    kwargs.setdefault("synced_table", SYNCED)
    kwargs.setdefault("owner", OWNER)
    return workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=client, **kwargs
    )


# --- registration / wiring --------------------------------------------------


def test_registered():
    assert APP_CHECKPOINT_ID in workshop.registry


def test_requires_catalog_and_schema():
    result = workshop.check(
        APP_CHECKPOINT_ID, apps=FakeApps(), app_name=APP, synced_table=SYNCED,
        owner=OWNER,
    )
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_requires_app_name():
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=FakeApps(),
        synced_table=SYNCED, owner=OWNER,
    )
    assert result.passed is False
    assert result.details["reason"] == "missing_app_name"


def test_blank_app_name_is_red():
    result = _check(FakeApps(), app_name="   ")
    assert result.passed is False
    assert result.details["reason"] == "missing_app_name"


def test_requires_synced_table():
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=FakeApps(),
        app_name=APP, owner=OWNER,
    )
    assert result.passed is False
    assert result.details["reason"] == "missing_synced_table"


def test_requires_owner():
    # Ownership is not optional: without an owner the checkpoint cannot confirm
    # the app and synced table are the caller's OWN.
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=FakeApps(),
        app_name=APP, synced_table=SYNCED,
    )
    assert result.passed is False
    assert result.details["reason"] == "missing_owner"


def test_requires_a_workspace_when_no_client_injected():
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, app_name=APP,
        synced_table=SYNCED, owner=OWNER,
    )
    assert result.passed is False
    assert result.details["stage"] == "client"


def test_rejects_unusable_apps_extra():
    result = _check(object())
    assert result.passed is False
    assert result.details["stage"] == "client"


# --- happy path -------------------------------------------------------------


def test_green_when_owned_synced_serving_and_app_running():
    result = _check(FakeApps())
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["app_name"] == APP
    assert result.details["synced_table"] == SYNCED
    assert result.details["served_rows"] == 3


def test_green_with_row_parity():
    result = _check(FakeApps(rows=42), expected_row_count=42)
    assert result.passed is True
    assert result.details["served_rows"] == 42


def test_green_with_observed_served_row_count_extra():
    # No counter on the client, but an observed served_row_count is supplied.
    result = _check(FakeAppsNoCounter(), served_row_count=5)
    assert result.passed is True
    assert result.details["served_rows"] == 5


def test_source_match_is_quoting_and_case_insensitive():
    attached = f'`{CATALOG}`.`{SCHEMA}`.`GOLD_CONTRACT_PERFORMANCE`'
    result = _check(FakeApps(synced=_synced(source=attached)))
    assert result.passed is True


def test_custom_domain_overrides_are_green():
    # A Security-like slice: different source table, key, synced + app names.
    synced = _synced(
        source=f"{CATALOG}.{SCHEMA}.gold_incidents", pk=("incident_id",)
    )
    result = _check(
        FakeApps(synced=synced),
        source_table="gold_incidents",
        primary_key_columns=["incident_id"],
    )
    assert result.passed is True


# --- synced-table guards ----------------------------------------------------


def test_synced_read_error_is_red():
    result = _check(FakeApps(raise_on="get_synced_table"))
    assert result.passed is False
    assert result.details["stage"] == "synced_read"


def test_missing_synced_table_is_red():
    result = _check(FakeApps(synced=None))
    assert result.passed is False
    assert result.details["stage"] == "synced_missing"


def test_wrong_source_table_is_red():
    result = _check(FakeApps(synced=_synced(source=f"{CATALOG}.{SCHEMA}.gold_sales")))
    assert result.passed is False
    assert result.details["stage"] == "synced_source"


def test_same_basename_wrong_catalog_schema_is_red():
    # Another participant's <other>.<other>.gold_contract_performance shares the
    # basename but is NOT the caller's own, so it must be RED (no basename fallback).
    other = "other-catalog.other-schema.gold_contract_performance"
    result = _check(FakeApps(synced=_synced(source=other)))
    assert result.passed is False
    assert result.details["stage"] == "synced_source"


def test_wrong_primary_key_is_red():
    result = _check(FakeApps(synced=_synced(pk=("order_id",))))
    assert result.passed is False
    assert result.details["stage"] == "synced_key"


def test_synced_owned_by_other_is_red():
    # A synced table whose Unity Catalog owner is someone else is not adopted.
    result = _check(FakeApps(synced_owner=OTHER))
    assert result.passed is False
    assert result.details["stage"] == "synced_ownership"
    assert result.details["observed_owner"] == OTHER


def test_synced_owner_unverifiable_is_red():
    result = _check(FakeApps(synced_owner=None))
    assert result.passed is False
    assert result.details["stage"] == "synced_ownership"


def test_client_without_owner_probe_is_red():
    # A normalized client is required to expose get_table_owner (enforced at
    # resolution); one lacking it cannot verify ownership.
    class NoOwner:
        def get_app(self, name):
            return _app()

        def get_synced_table(self, name):
            return _synced()

    result = _check(NoOwner())
    assert result.passed is False
    assert result.details["stage"] == "client"


def test_still_provisioning_is_red():
    result = _check(
        FakeApps(synced=_synced(provisioning="provisioning",
                                detailed="synced_table_provisioning"))
    )
    assert result.passed is False
    assert result.details["stage"] == "synced_offline"


def test_offline_synced_is_red():
    result = _check(FakeApps(synced=_synced(detailed="synced_tabled_offline")))
    assert result.passed is False
    assert result.details["stage"] == "synced_offline"


def test_pipeline_failed_is_red():
    result = _check(
        FakeApps(synced=_synced(detailed="synced_table_online_pipeline_failed"))
    )
    assert result.passed is False
    assert result.details["stage"] == "synced_offline"


def test_unverifiable_served_count_is_red():
    # Online + owned, but no served-row count can be obtained → FAIL CLOSED.
    result = _check(FakeAppsNoCounter())
    assert result.passed is False
    assert result.details["stage"] == "synced_unverified"


def test_empty_served_rows_is_red():
    result = _check(FakeApps(rows=0))
    assert result.passed is False
    assert result.details["stage"] == "synced_empty"


def test_stale_row_parity_mismatch_is_red():
    result = _check(FakeApps(rows=10), expected_row_count=99)
    assert result.passed is False
    assert result.details["stage"] == "synced_parity"


# --- app guards -------------------------------------------------------------


def test_app_read_error_is_red():
    result = _check(FakeApps(raise_on="get_app"))
    assert result.passed is False
    assert result.details["stage"] == "app_read"


def test_missing_app_is_red():
    result = _check(FakeApps(app=None))
    assert result.passed is False
    assert result.details["stage"] == "app_missing"


def test_app_owned_by_other_is_red():
    other = _app(creator=OTHER, sp="sp-someone-else")
    result = _check(FakeApps(app=other))
    assert result.passed is False
    assert result.details["stage"] == "app_ownership"


def test_stopped_app_is_red():
    # Deploying can leave the app stopped; a stopped app answers nothing.
    result = _check(FakeApps(app=_app(compute="stopped", app_state="unavailable")))
    assert result.passed is False
    assert result.details["stage"] == "app_stopped"


def test_never_deployed_app_is_red():
    result = _check(FakeApps(app=_app(deployment=None)))
    assert result.passed is False
    assert result.details["stage"] == "app_deployment"


def test_failed_deployment_is_red():
    result = _check(FakeApps(app=_app(deployment="failed")))
    assert result.passed is False
    assert result.details["stage"] == "app_deployment"


def test_unhealthy_probe_is_red_when_opted_in():
    # The HTTP health probe is opt-in (the provided Streamlit app has no
    # /api/health); enabling it makes an explicit unhealthy response RED.
    result = _check(FakeApps(probe_status=503), probe_health=True)
    assert result.passed is False
    assert result.details["stage"] == "app_health"


def test_probe_off_by_default_skips_health():
    # Default: no probe, so an unhealthy endpoint does not fail the checkpoint.
    result = _check(FakeApps(probe_status=503))
    assert result.passed is True


def test_require_running_false_accepts_stopped_but_deployed():
    result = _check(
        FakeApps(app=_app(compute="stopped", app_state="unavailable")),
        require_running=False,
    )
    assert result.passed is True


# --- configuration guards ---------------------------------------------------


def test_invalid_primary_key_is_red():
    result = _check(FakeApps(), primary_key_columns=[""])
    assert result.passed is False
    assert result.details["stage"] == "configuration"


# --- live SDK adapter (w.postgres synced-table surface) ---------------------
# These exercise `_SdkAppClient.get_synced_table` against a fake WorkspaceClient
# shaped like the modern Lakebase Autoscaling SDK, with no network. The synced-table
# GET returns ONLY status (no spec), so the adapter reads the source table from
# the Unity Catalog table entry's `source_table` property and the primary key
# from Postgres. These guard that multi-source mapping and pin the retired legacy
# `w.database` surface out. (The Postgres primary-key/count reads are proven live;
# here, with no Lakebase hints, they degrade to () / None as designed.)


class _Enum:
    """A stand-in for an SDK enum member (has `.value`, like SyncedTableState)."""

    def __init__(self, value: str):
        self.value = value


class _FakeStatus:
    def __init__(self, detailed_state, provisioning_state, message=None):
        self.detailed_state = detailed_state
        self.unity_catalog_provisioning_state = provisioning_state
        self.message = message


class _FakeSyncedTable:
    """Shaped like databricks.sdk.service.postgres.SyncedTable (status only).

    The real GET response carries NO ``.spec``, so a ``spec`` here would be a trap:
    the adapter must not read source/PK from it.
    """

    def __init__(self, status):
        self.status = status


class _FakeUCTable:
    def __init__(self, properties):
        self.properties = properties


class _FakePostgres:
    def __init__(self, *, table=None, error=None):
        self._table = table
        self._error = error
        self.names: list[str] = []

    def get_synced_table(self, name):
        self.names.append(name)
        if self._error is not None:
            raise self._error
        return self._table


class _FakeTables:
    def __init__(self, uc_table=None):
        self._uc_table = uc_table
        self.full_names: list[str] = []

    def get(self, full_name):
        self.full_names.append(full_name)
        return self._uc_table


class _FakeWorkspace:
    def __init__(self, postgres, tables=None):
        self.postgres = postgres
        self.tables = tables or _FakeTables()


def test_sdk_adapter_maps_postgres_synced_table():
    pg = _FakePostgres(
        table=_FakeSyncedTable(
            status=_FakeStatus(
                detailed_state=_Enum("SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE"),
                provisioning_state=_Enum("ACTIVE"),
            ),
        )
    )
    tables = _FakeTables(
        _FakeUCTable({"source_table": "cat.sch.gold_contract_performance"})
    )
    # No Lakebase hints (pg={}) → the primary key read degrades to ().
    client = _SdkAppClient(_FakeWorkspace(pg, tables), pg={})
    info = client.get_synced_table("cat.sch.gold_contract_performance_served_ada")

    # The synced-table GET name is the "synced_tables/" prefixed UC name.
    assert pg.names == ["synced_tables/cat.sch.gold_contract_performance_served_ada"]
    # Status maps from the nested .status; source comes from the UC table property.
    assert info.name == "cat.sch.gold_contract_performance_served_ada"
    assert tables.full_names == ["cat.sch.gold_contract_performance_served_ada"]
    assert info.source_table == "cat.sch.gold_contract_performance"
    assert info.provisioning_state == "active"
    assert info.detailed_state == "synced_table_online_no_pending_update"
    assert _synced_online(info) is True
    # Without Lakebase hints the PK is unobservable here (proven live otherwise).
    assert info.primary_key_columns == ()


def _adapter_info_for_state(detailed_state: str):
    """Build the live adapter's SyncedTableInfo for a given sync detailed_state."""
    pg = _FakePostgres(
        table=_FakeSyncedTable(
            status=_FakeStatus(_Enum(detailed_state), _Enum("ACTIVE"))
        )
    )
    tables = _FakeTables(
        _FakeUCTable({"source_table": "cat.sch.gold_contract_performance"})
    )
    client = _SdkAppClient(_FakeWorkspace(pg, tables), pg={})
    return client.get_synced_table("cat.sch.gold_contract_performance_served_ada")


def test_sdk_adapter_provisioning_state_is_not_online():
    # `.wait()` on create can return at SYNCED_TABLE_PROVISIONING, and a not-yet-online
    # table must NOT pass the online guard (the checkpoint stays RED until serving).
    info = _adapter_info_for_state("SYNCED_TABLE_PROVISIONING")
    assert info.detailed_state == "synced_table_provisioning"
    assert _synced_online(info) is False


def test_sdk_adapter_triggered_update_is_online():
    # SYNCED_TABLE_ONLINE_TRIGGERED_UPDATE is a real live state (observed even for a
    # SNAPSHOT request), and is accepted as online by the startswith('synced_table_online')
    # logic, so the checkpoint proceeds to the serving proof.
    info = _adapter_info_for_state("SYNCED_TABLE_ONLINE_TRIGGERED_UPDATE")
    assert info.detailed_state == "synced_table_online_triggered_update"
    assert _synced_online(info) is True


def test_sdk_adapter_source_table_missing_property_is_none():
    # A synced table whose UC entry has no source_table property → source None →
    # the checkpoint's source guard goes RED (never a false adopt).
    pg = _FakePostgres(
        table=_FakeSyncedTable(
            status=_FakeStatus(_Enum("SYNCED_TABLE_ONLINE"), _Enum("ACTIVE"))
        )
    )
    client = _SdkAppClient(
        _FakeWorkspace(pg, _FakeTables(_FakeUCTable({}))), pg={}
    )
    info = client.get_synced_table("cat.sch.tbl")
    assert info.source_table is None


def test_sdk_adapter_synced_not_found_returns_none():
    pg = _FakePostgres(error=RuntimeError("RESOURCE_DOES_NOT_EXIST: no such table"))
    client = _SdkAppClient(_FakeWorkspace(pg))
    assert client.get_synced_table("cat.sch.tbl") is None


def test_sdk_adapter_synced_read_error_propagates():
    pg = _FakePostgres(error=RuntimeError("PERMISSION_DENIED"))
    client = _SdkAppClient(_FakeWorkspace(pg))
    try:
        client.get_synced_table("cat.sch.tbl")
    except RuntimeError as exc:
        assert "PERMISSION_DENIED" in str(exc)
    else:  # pragma: no cover - explicit failure if no raise
        raise AssertionError("expected a non-not-found error to propagate")


def test_sdk_adapter_count_rows_without_hints_is_none():
    # Fail-closed: with no Lakebase endpoint/host hints, the served-row count is
    # unobtainable and must be None (keeps the checkpoint RED, never a false pass).
    client = _SdkAppClient(_FakeWorkspace(_FakePostgres()), pg={})
    info = SyncedTableInfo(name="cat.sch.tbl")
    assert client.count_rows(info) is None


# --- namespace resolution (#22): the check resolves the caller's own names ---


def test_resolves_app_and_synced_table_from_namespace():
    # No explicit app_name/synced_table/owner: all three are derived from the
    # namespace, so the check resolves the SAME names the notebook created.
    ns = workshop.namespace(OWNER, domain="finance")
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=FakeApps(), namespace=ns
    )
    assert result.passed is True
    assert result.details["app_name"] == ns.app_name()
    assert result.details["synced_table"] == ns.synced_table_fqn(CATALOG, SCHEMA)


def test_namespace_binds_ownership_to_the_caller():
    # A different participant's namespace derives a different owner, so the check
    # refuses to adopt objects owned by someone else. This is the two-participant guard.
    other = workshop.namespace(OTHER, domain="finance")
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA,
        apps=FakeApps(),  # app + synced table owned by OWNER (ada), not OTHER (grace)
        namespace=other,
    )
    assert result.passed is False
    assert result.details["stage"] == "synced_ownership"
    assert result.details["owner"] == other.owner


def test_explicit_names_override_namespace():
    ns = workshop.namespace("someone-else@z.com", domain="finance")
    result = _check(FakeApps(), namespace=ns)  # _check sets app/synced/owner explicitly
    assert result.passed is True
    assert result.details["app_name"] == APP


def test_namespace_serving_base_flows_through_for_non_finance_domain():
    # FOLD-IN #22: a non-Finance domain gets its OWN serving table through the
    # namespace by passing serving_base (+ its own source_table), with no ad-hoc
    # synced_table override, and the checkpoint resolves that derived name.
    ns = workshop.namespace(OWNER, domain="itsm")
    expected = ns.synced_table_fqn(CATALOG, SCHEMA, base="gold_incidents_served")
    fake = FakeApps(synced=_synced(source=f"{CATALOG}.{SCHEMA}.gold_incidents"))
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=fake,
        namespace=ns, serving_base="gold_incidents_served", source_table="gold_incidents",
    )
    assert result.passed is True
    assert result.details["synced_table"] == expected
    assert result.details["synced_table"].endswith(f"gold_incidents_served_{ns.suffix}")


def test_explicit_synced_table_wins_over_namespace_serving_base():
    # An explicit synced_table still wins, even when serving_base is also given.
    ns = workshop.namespace(OWNER, domain="finance")
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=FakeApps(),
        namespace=ns, synced_table=SYNCED, serving_base="gold_incidents_served",
    )
    assert result.passed is True
    assert result.details["synced_table"] == SYNCED
