"""The smoke checkpoint: a trivial, always-registered check.

It proves the framework is wired up correctly and returns GREEN from a fresh
clone with no Databricks workspace. It is the one checkpoint that asserts purely
local state (that the framework itself loaded), so it doubles as the fresh-clone
health check for participants and the smoke test for CI.
"""

from __future__ import annotations

from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

SMOKE_CHECKPOINT_ID = "smoke"


@checkpoint(
    SMOKE_CHECKPOINT_ID,
    summary="Framework self-test; returns green from a fresh clone, no workspace needed.",
)
def check_smoke(ctx: CheckContext) -> CheckResult:
    """Always pass. If this runs at all, ``workshop.check`` is working."""
    return CheckResult(
        checkpoint=SMOKE_CHECKPOINT_ID,
        passed=True,
        message=(
            "workshop.check() is wired up correctly. You're ready to start the "
            "workshop. Later checkpoints will validate your Databricks work."
        ),
        details={"requires_workspace": False},
    )
