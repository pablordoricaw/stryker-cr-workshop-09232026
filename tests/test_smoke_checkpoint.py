"""The smoke checkpoint returns green from a fresh clone with no workspace.

This is the acceptance test for issue #2's fourth criterion. It must pass with
no Databricks connection, no Spark session, and no environment setup.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.smoke import SMOKE_CHECKPOINT_ID


def test_smoke_is_registered():
    assert SMOKE_CHECKPOINT_ID in workshop.registry


def test_smoke_returns_green_with_no_workspace():
    result = workshop.check(SMOKE_CHECKPOINT_ID)
    assert result.passed is True
    assert result.checkpoint == SMOKE_CHECKPOINT_ID
    assert result.message  # a real, human-readable message
    assert result.details["requires_workspace"] is False


def test_smoke_result_is_truthy():
    # CheckResult.__bool__ lets `if workshop.check(...):` read naturally.
    assert bool(workshop.check(SMOKE_CHECKPOINT_ID)) is True
