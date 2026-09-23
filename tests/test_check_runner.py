"""Tests for the ``workshop.check`` runner: the single test seam's behavior."""

from __future__ import annotations

import workshop
from workshop import CheckContext, CheckResult, CheckpointRegistry


def test_check_returns_structured_result():
    result = workshop.check("smoke")
    assert isinstance(result, CheckResult)
    assert result.checkpoint == "smoke"
    assert isinstance(result.passed, bool)
    assert isinstance(result.message, str) and result.message


def test_unknown_checkpoint_fails_cleanly():
    result = workshop.check("does-not-exist")
    assert result.passed is False
    assert "Unknown checkpoint" in result.message
    assert "smoke" in result.message  # lists what *is* registered
    assert "smoke" in result.details["registered"]


def test_checkpoint_that_raises_becomes_a_failure():
    reg = CheckpointRegistry()

    @reg.checkpoint("boom")
    def _boom(ctx: CheckContext) -> CheckResult:
        raise ValueError("kaboom")

    result = workshop.check("boom", registry=reg)
    assert result.passed is False
    assert "Check errored" in result.message
    assert "kaboom" in result.message
    assert result.details["error_type"] == "ValueError"


def test_bool_return_is_normalized():
    reg = CheckpointRegistry()
    reg.register("yes", lambda ctx: True)
    reg.register("no", lambda ctx: False)

    assert workshop.check("yes", registry=reg).passed is True
    assert workshop.check("no", registry=reg).passed is False


def test_tuple_return_is_normalized():
    reg = CheckpointRegistry()
    reg.register("t", lambda ctx: (False, "not yet"))

    result = workshop.check("t", registry=reg)
    assert result.passed is False
    assert result.message == "not yet"


def test_unsupported_return_type_is_a_failure():
    reg = CheckpointRegistry()
    reg.register("weird", lambda ctx: 42)

    result = workshop.check("weird", registry=reg)
    assert result.passed is False
    assert "unsupported type" in result.message


def test_context_is_populated_from_kwargs():
    reg = CheckpointRegistry()
    seen = {}

    @reg.checkpoint("capture")
    def _capture(ctx: CheckContext) -> CheckResult:
        seen["catalog"] = ctx.catalog
        seen["schema"] = ctx.schema
        seen["extras"] = dict(ctx.extras)
        return CheckResult("capture", True, "ok")

    workshop.check(
        "capture",
        registry=reg,
        catalog="main",
        schema="participant_01",
        expected_rows=2500,
    )
    assert seen["catalog"] == "main"
    assert seen["schema"] == "participant_01"
    assert seen["extras"] == {"expected_rows": 2500}


def test_require_spark_failure_is_reported_cleanly():
    reg = CheckpointRegistry()

    @reg.checkpoint("needs_spark")
    def _needs_spark(ctx: CheckContext) -> CheckResult:
        ctx.require_spark()
        return CheckResult("needs_spark", True, "ok")

    result = workshop.check("needs_spark", registry=reg)
    assert result.passed is False
    assert "needs a Databricks workspace" in result.message
