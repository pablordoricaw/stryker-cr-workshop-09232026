"""Behavioral tests for the observable-state ``07_app`` checkpoint.

Every test drives the real ``workshop.check`` seam with an injected fake app
client, so no Databricks SDK, notebook, or network is needed. The fake serves
only observable platform state — a Databricks App's deploy/run state and a
Lakebase synced table's source/key/sync state (and optionally its served row
count) — which is exactly what the checkpoint is allowed to assert on.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.app import (
    APP_CHECKPOINT_ID,
    AppInfo,
    SyncedTableInfo,
)

CATALOG = "team-catalog"
SCHEMA = "finance data"  # a space in the schema name exercises quoting
APP = "stryker-finance-ada-lovelace"
SYNCED = "lb_finance_ada.public.gold_contract_performance"
OWNER = "ada@example.com"


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
    """Serve one app's state and one synced table's state (+ optional counts)."""

    def __init__(self, *, app=..., synced=..., rows=None, probe_status=None, raise_on=None):
        self._app = _app() if app is ... else app
        self._synced = _synced() if synced is ... else synced
        self._rows = rows
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

    def count_rows(self, info):
        return self._rows

    def probe(self, url):
        return self._probe


class FakeAppsNoCounter:
    """A minimal client without count_rows/probe (exercises the fallback path)."""

    def __init__(self, *, app=..., synced=...):
        self._app = _app() if app is ... else app
        self._synced = _synced() if synced is ... else synced

    def get_app(self, name):
        return self._app

    def get_synced_table(self, name):
        return self._synced


def _check(client, **kwargs):
    kwargs.setdefault("app_name", APP)
    kwargs.setdefault("synced_table", SYNCED)
    return workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=client, **kwargs
    )


# --- registration / wiring --------------------------------------------------


def test_registered():
    assert APP_CHECKPOINT_ID in workshop.registry


def test_requires_catalog_and_schema():
    result = workshop.check(
        APP_CHECKPOINT_ID, apps=FakeApps(), app_name=APP, synced_table=SYNCED
    )
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_requires_app_name():
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, apps=FakeApps(),
        synced_table=SYNCED,
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
        app_name=APP,
    )
    assert result.passed is False
    assert result.details["reason"] == "missing_synced_table"


def test_requires_a_workspace_when_no_client_injected():
    # No client and no SDK off-platform: the lazy build fails and surfaces a
    # clean RED rather than a traceback.
    result = workshop.check(
        APP_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, app_name=APP,
        synced_table=SYNCED,
    )
    assert result.passed is False
    assert result.details["stage"] == "client"


def test_rejects_unusable_apps_extra():
    result = _check(object())
    assert result.passed is False
    assert result.details["stage"] == "client"


# --- happy path -------------------------------------------------------------


def test_green_when_synced_online_and_app_running():
    result = _check(FakeApps())
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["app_name"] == APP
    assert result.details["synced_table"] == SYNCED


def test_green_without_counter_relies_on_online_state():
    result = _check(FakeAppsNoCounter())
    assert result.passed is True
    assert result.details["stage"] == "done"


def test_green_with_row_parity():
    result = _check(FakeApps(rows=42), expected_row_count=42)
    assert result.passed is True
    assert result.details["served_rows"] == 42


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


def test_wrong_primary_key_is_red():
    result = _check(FakeApps(synced=_synced(pk=("order_id",))))
    assert result.passed is False
    assert result.details["stage"] == "synced_key"


def test_still_provisioning_is_red():
    result = _check(
        FakeApps(synced=_synced(provisioning="provisioning",
                                detailed="synced_table_provisioning"))
    )
    assert result.passed is False
    assert result.details["stage"] == "synced_offline"


def test_offline_synced_is_red():
    result = _check(
        FakeApps(synced=_synced(detailed="synced_tabled_offline"))
    )
    assert result.passed is False
    assert result.details["stage"] == "synced_offline"


def test_pipeline_failed_is_red():
    # An "online" state that carries a pipeline failure must not pass.
    result = _check(
        FakeApps(synced=_synced(detailed="synced_table_online_pipeline_failed"))
    )
    assert result.passed is False
    assert result.details["stage"] == "synced_offline"


def test_empty_served_rows_is_red():
    result = _check(FakeApps(rows=0))
    assert result.passed is False
    assert result.details["stage"] == "synced_empty"


def test_row_parity_mismatch_is_red():
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


def test_ownership_guard_rejects_other_owner():
    other = _app(creator="grace@example.com", sp="sp-someone-else")
    result = _check(FakeApps(app=other), owner=OWNER)
    assert result.passed is False
    assert result.details["stage"] == "app_ownership"


def test_ownership_guard_accepts_own_app():
    result = _check(FakeApps(app=_app(creator=OWNER)), owner=OWNER)
    assert result.passed is True


def test_unhealthy_probe_is_red():
    result = _check(FakeApps(probe_status=503))
    assert result.passed is False
    assert result.details["stage"] == "app_health"


def test_probe_disabled_skips_health():
    result = _check(FakeApps(probe_status=503), probe_health=False)
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
