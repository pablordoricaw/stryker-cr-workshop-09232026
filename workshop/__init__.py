"""``workshop`` — the single validation seam for the Stryker Databricks workshop.

Participants call :func:`check` at each checkpoint to get an unambiguous
pass/fail plus a targeted message::

    import workshop
    print(workshop.check("smoke"))
    # [✅ PASS] smoke: workshop.check() is wired up correctly. ...

In a Databricks Git folder the repo root is on ``sys.path``, so ``import
workshop`` works from any notebook with no install step.

Checks assert only externally-observable state (catalog objects, row counts,
tag/comment presence, metric-view resolvability, Genie answer sanity,
synced-table row parity) — never notebook cell structure or intermediate
variables. Later tickets extend the workshop by registering new checkpoints; see
:mod:`workshop.registry` for the registration API.
"""

from __future__ import annotations

from .bootstrap import bootstrap, find_repo_root
from .context import CheckContext
from .registry import (
    Checkpoint,
    CheckpointRegistry,
    DuplicateCheckpointError,
    UnknownCheckpointError,
    checkpoint,
    register,
    registry,
)
from .results import CheckResult
from .runner import check

# Import the checkpoint modules so their @checkpoint decorators self-register on
# the default registry. Done here (after the registry is defined) so a plain
# ``import workshop`` makes every checkpoint — the smoke check today, everything
# later tickets add — immediately available to workshop.check().
from . import checkpoints as _checkpoints  # noqa: E402

_checkpoints.load_all()

# module name -> import exception for any checkpoint module that failed to load.
# Empty in normal operation; a broken later-ticket module lands here instead of
# breaking ``import workshop`` (the module is also surfaced as an unavailable
# checkpoint keyed by its module name).
checkpoint_load_errors = _checkpoints.LOAD_ERRORS

__all__ = [
    "check",
    "checkpoint",
    "register",
    "registry",
    "bootstrap",
    "find_repo_root",
    "checkpoint_load_errors",
    "CheckResult",
    "CheckContext",
    "Checkpoint",
    "CheckpointRegistry",
    "DuplicateCheckpointError",
    "UnknownCheckpointError",
]
