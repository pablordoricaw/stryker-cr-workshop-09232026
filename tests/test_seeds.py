"""Tests for the seed-hook framework — registry, discovery, and run_seeds."""

from __future__ import annotations

import pytest

import workshop
from workshop import (
    SeedContext,
    SeedResult,
    resolve_config,
    run_seeds,
)
from workshop.seeds import DuplicateSeedError, SeedRegistry
from workshop.seeds.placeholder import PLACEHOLDER_SEED_NAME

FINANCE = resolve_config(catalog="c", domain="finance")


# --- registry ---------------------------------------------------------------


def test_register_and_duplicate_and_replace():
    reg = SeedRegistry()
    reg.register("a", lambda ctx: True)
    assert "a" in reg and reg.names() == ["a"]

    with pytest.raises(DuplicateSeedError):
        reg.register("a", lambda ctx: True)

    reg.register("a", lambda ctx: False, replace=True)  # allowed with replace
    assert len(reg) == 1


def test_empty_name_rejected():
    reg = SeedRegistry()
    with pytest.raises(ValueError):
        reg.register("", lambda ctx: True)


def test_domain_filtering():
    reg = SeedRegistry()
    reg.register("all", lambda ctx: True)  # domains=None -> all
    reg.register("fin", lambda ctx: True, domains="finance")
    reg.register("fin_sec", lambda ctx: True, domains=("finance", "security"))

    assert [h.name for h in reg.hooks_for("finance")] == ["all", "fin", "fin_sec"]
    assert [h.name for h in reg.hooks_for("security")] == ["all", "fin_sec"]
    assert [h.name for h in reg.hooks_for("itsm")] == ["all"]


def test_unknown_domain_rejected_at_registration():
    reg = SeedRegistry()
    with pytest.raises(ValueError, match="Unknown seed domain"):
        reg.register("x", lambda ctx: True, domains="marketing")


# --- run_seeds --------------------------------------------------------------


def test_run_seeds_runs_matching_hooks_in_name_order():
    reg = SeedRegistry()
    reg.register("zeta", lambda ctx: SeedResult("zeta", True, "z"))
    reg.register("alpha", lambda ctx: SeedResult("alpha", True, "a"))
    reg.register("other_domain", lambda ctx: True, domains="security")

    results = run_seeds(FINANCE, registry=reg)
    assert [r.seed for r in results] == ["alpha", "zeta"]
    assert all(r.ok for r in results)


def test_run_seeds_isolates_a_raising_hook():
    reg = SeedRegistry()

    def _boom(ctx):
        raise ValueError("kaboom")

    reg.register("boom", _boom)
    reg.register("fine", lambda ctx: True)

    results = {r.seed: r for r in run_seeds(FINANCE, registry=reg)}
    assert results["boom"].ok is False
    assert "kaboom" in results["boom"].message
    assert results["fine"].ok is True


def test_run_seeds_normalizes_return_types():
    reg = SeedRegistry()
    reg.register("as_none", lambda ctx: None)
    reg.register("as_true", lambda ctx: True)
    reg.register("as_tuple", lambda ctx: (False, "nope"))

    results = {r.seed: r for r in run_seeds(FINANCE, registry=reg)}
    assert results["as_none"].ok is True
    assert results["as_true"].ok is True
    assert results["as_tuple"].ok is False
    assert results["as_tuple"].message == "nope"


def test_context_carries_config_and_extras():
    reg = SeedRegistry()
    seen = {}

    def _capture(ctx: SeedContext):
        seen["catalog"] = ctx.config.catalog
        seen["domain"] = ctx.domain
        seen["extras"] = dict(ctx.extras)
        return True

    reg.register("capture", _capture)
    run_seeds(FINANCE, registry=reg, expected_rows=2500)
    assert seen["catalog"] == "c"
    assert seen["domain"] == "finance"
    assert seen["extras"] == {"expected_rows": 2500}


def test_require_spark_without_session_is_isolated():
    reg = SeedRegistry()
    reg.register("needs_spark", lambda ctx: ctx.require_spark())
    (result,) = run_seeds(FINANCE, registry=reg)
    assert result.ok is False
    assert "needs a Databricks workspace" in result.message


# --- default registry + placeholder + load-error surfacing ------------------


def test_placeholder_is_registered_and_green():
    assert PLACEHOLDER_SEED_NAME in workshop.seed_registry
    results = {r.seed: r for r in run_seeds(FINANCE)}
    assert results[PLACEHOLDER_SEED_NAME].ok is True


def test_load_errors_are_surfaced_on_the_default_registry(monkeypatch):
    monkeypatch.setitem(
        workshop.seeds.LOAD_ERRORS, "brokenseed", ImportError("missing dep")
    )
    results = {r.seed: r for r in run_seeds(FINANCE)}
    assert results["brokenseed"].ok is False
    assert results["brokenseed"].details["unavailable"] is True


def test_custom_registry_does_not_surface_default_load_errors(monkeypatch):
    monkeypatch.setitem(workshop.seeds.LOAD_ERRORS, "brokenseed", ImportError("x"))
    reg = SeedRegistry()
    reg.register("only", lambda ctx: True)
    assert [r.seed for r in run_seeds(FINANCE, registry=reg)] == ["only"]
