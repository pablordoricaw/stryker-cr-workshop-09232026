"""Tests for the checkpoint registration API that later tickets build on."""

from __future__ import annotations

import pytest

import workshop
from workshop import (
    CheckContext,
    CheckpointRegistry,
    CheckResult,
    DuplicateCheckpointError,
    UnknownCheckpointError,
)


def test_decorator_registration():
    reg = CheckpointRegistry()

    @reg.checkpoint("cp", summary="a summary")
    def _cp(ctx: CheckContext) -> CheckResult:
        return CheckResult("cp", True, "ok")

    assert "cp" in reg
    assert reg.get("cp").summary == "a summary"
    assert reg.describe()["cp"] == "a summary"


def test_direct_registration():
    reg = CheckpointRegistry()
    reg.register("cp", lambda ctx: True, summary="s")
    assert "cp" in reg
    assert len(reg) == 1


def test_duplicate_id_is_rejected():
    reg = CheckpointRegistry()
    reg.register("cp", lambda ctx: True)
    with pytest.raises(DuplicateCheckpointError):
        reg.register("cp", lambda ctx: False)


def test_duplicate_id_allowed_with_replace():
    reg = CheckpointRegistry()
    reg.register("cp", lambda ctx: True)
    reg.register("cp", lambda ctx: False, replace=True)
    assert workshop.check("cp", registry=reg).passed is False


def test_empty_id_is_rejected():
    reg = CheckpointRegistry()
    with pytest.raises(ValueError):
        reg.register("", lambda ctx: True)


def test_get_unknown_raises():
    reg = CheckpointRegistry()
    with pytest.raises(UnknownCheckpointError):
        reg.get("nope")


def test_ids_are_sorted():
    reg = CheckpointRegistry()
    reg.register("b", lambda ctx: True)
    reg.register("a", lambda ctx: True)
    assert reg.ids() == ["a", "b"]


def test_default_registry_has_smoke():
    # The auto-discovery loader registered the smoke checkpoint on import.
    assert "smoke" in workshop.registry
    assert "smoke" in workshop.registry.ids()


def test_result_to_dict_is_json_shaped():
    result = CheckResult("cp", True, "ok", {"n": 1})
    assert result.to_dict() == {
        "checkpoint": "cp",
        "passed": True,
        "message": "ok",
        "details": {"n": 1},
    }
