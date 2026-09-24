"""``workshop.check`` is the single test seam participants and CI both call.

The runner is deliberately forgiving: an unknown checkpoint id or a checkpoint
that raises becomes a *failed* :class:`CheckResult` with a clear message, never
a traceback in a participant's face. That keeps the seam safe to call from a
notebook cell at every checkpoint.
"""

from __future__ import annotations

from typing import Any

from .context import CheckContext
from .registry import CheckpointRegistry
from .registry import registry as default_registry
from .results import CheckResult


def _normalize(checkpoint_id: str, raw: Any) -> CheckResult:
    """Coerce a checkpoint's return value into a :class:`CheckResult`.

    Accepts a :class:`CheckResult` (returned as-is, but stamped with the id if
    the checkpoint left it blank), a bare ``bool``, or a ``(bool, message)``
    tuple.
    """
    if isinstance(raw, CheckResult):
        if raw.checkpoint == checkpoint_id or not raw.checkpoint:
            # Ensure the id is populated even if the checkpoint omitted it.
            if raw.checkpoint:
                return raw
            return CheckResult(checkpoint_id, raw.passed, raw.message, raw.details)
        # A checkpoint returning some *other* id is a bug worth surfacing.
        return CheckResult(
            checkpoint_id,
            False,
            f"Checkpoint returned a result for '{raw.checkpoint}' instead of "
            f"'{checkpoint_id}'.",
            {"returned_checkpoint": raw.checkpoint},
        )
    if isinstance(raw, bool):
        return CheckResult(
            checkpoint_id,
            raw,
            "Passed." if raw else "Failed.",
        )
    if (
        isinstance(raw, tuple)
        and len(raw) == 2
        and isinstance(raw[0], bool)
        and isinstance(raw[1], str)
    ):
        return CheckResult(checkpoint_id, raw[0], raw[1])
    return CheckResult(
        checkpoint_id,
        False,
        f"Checkpoint returned an unsupported type ({type(raw).__name__}); "
        f"expected CheckResult, bool, or (bool, str).",
    )


def check(
    checkpoint_id: str,
    *,
    spark: Any = None,
    catalog: str | None = None,
    schema: str | None = None,
    registry: CheckpointRegistry | None = None,
    **extras: Any,
) -> CheckResult:
    """Run one checkpoint and return a structured pass/fail result.

    This is the one call participants make at each checkpoint, and the one call
    maintainer CI makes to assert every domain's solution is green.

    Args:
        checkpoint_id: The checkpoint to run (e.g. ``"smoke"``).
        spark: Active Spark session, for workspace-dependent checkpoints.
        catalog: Participant's Unity Catalog catalog.
        schema: Participant's schema.
        registry: Registry to look the checkpoint up in; defaults to the shared
            module-level registry that all built-in checkpoints register on.
        **extras: Forwarded to the checkpoint via ``ctx.extras`` for
            checkpoint-specific inputs.

    Returns:
        A :class:`CheckResult`. Unknown ids and checkpoints that raise both come
        back as ``passed=False`` with an explanatory ``message``.
    """
    reg = registry if registry is not None else default_registry

    if checkpoint_id not in reg:
        known = ", ".join(reg.ids()) or "(none registered yet)"
        return CheckResult(
            checkpoint_id,
            False,
            f"Unknown checkpoint '{checkpoint_id}'. Registered checkpoints: {known}.",
            {"registered": reg.ids()},
        )

    ctx = CheckContext(spark=spark, catalog=catalog, schema=schema, extras=extras)
    cp = reg.get(checkpoint_id)
    try:
        raw = cp.fn(ctx)
    except Exception as exc:  # noqa: BLE001 - surface any failure as a clean result
        return CheckResult(
            checkpoint_id,
            False,
            f"Check errored: {type(exc).__name__}: {exc}",
            {"error_type": type(exc).__name__},
        )
    return _normalize(checkpoint_id, raw)
