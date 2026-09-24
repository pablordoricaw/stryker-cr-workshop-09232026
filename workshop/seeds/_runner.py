"""``run_seeds`` runs every seed hook that applies to a run's domain.

Called by the setup notebook right after provisioning. Like ``workshop.check``,
it is failure-isolated: a hook that raises becomes a failed :class:`SeedResult`
rather than aborting the notebook, so one broken later-ticket hook can't block a
participant from finishing setup.
"""

from __future__ import annotations

from typing import Any

from workshop.config import WorkshopConfig

from ._context import SeedContext, SeedResult
from ._registry import SeedRegistry
from ._registry import seed_registry as default_registry


def _normalize(seed_name: str, raw: Any) -> SeedResult:
    """Coerce a hook's return value into a :class:`SeedResult`.

    Accepts a :class:`SeedResult`, a bare ``bool``, a ``(bool, message)`` tuple,
    or ``None`` (a hook that just did its work and returned nothing).
    """
    if isinstance(raw, SeedResult):
        if raw.seed:
            return raw
        return SeedResult(seed_name, raw.ok, raw.message, raw.details)
    if raw is None:
        return SeedResult(seed_name, True, "Seed hook ran.")
    if isinstance(raw, bool):
        return SeedResult(seed_name, raw, "Seeded." if raw else "Seed reported failure.")
    if (
        isinstance(raw, tuple)
        and len(raw) == 2
        and isinstance(raw[0], bool)
        and isinstance(raw[1], str)
    ):
        return SeedResult(seed_name, raw[0], raw[1])
    return SeedResult(
        seed_name,
        False,
        f"Seed hook returned an unsupported type ({type(raw).__name__}); "
        f"expected SeedResult, bool, (bool, str), or None.",
    )


def _load_error_results() -> list[SeedResult]:
    """Surface any seed module that failed to import as a failed SeedResult.

    Deferred import of the package avoids an import cycle (the package imports
    this runner).
    """
    from . import LOAD_ERRORS  # noqa: PLC0415 - deferred to break the cycle

    return [
        SeedResult(
            module_name,
            False,
            f"Seed module '{module_name}' failed to import: "
            f"{type(exc).__name__}: {exc}. This is a workshop bug, so tell your "
            f"facilitator. Other seeds are unaffected.",
            {"unavailable": True, "error_type": type(exc).__name__},
        )
        for module_name, exc in sorted(LOAD_ERRORS.items())
    ]


def run_seeds(
    config: WorkshopConfig,
    *,
    spark: Any = None,
    registry: SeedRegistry | None = None,
    include_load_errors: bool = True,
    **extras: Any,
) -> list[SeedResult]:
    """Run every registered seed hook that applies to ``config.domain``.

    Args:
        config: The resolved environment names (see ``workshop.resolve_config``).
        spark: Active Spark session, forwarded to each hook via the context.
        registry: Registry to run hooks from; defaults to the shared one every
            hook registers on.
        include_load_errors: When ``True`` (default), append a failed result for
            each seed module that failed to import, so the notebook surfaces it.
        **extras: Forwarded to each hook via ``ctx.extras``.

    Returns:
        A list of :class:`SeedResult`, one per hook that ran (plus any load
        errors), in stable name order.
    """
    reg = registry if registry is not None else default_registry
    results: list[SeedResult] = []

    for hook in reg.hooks_for(config.domain):
        ctx = SeedContext(config=config, spark=spark, extras=extras)
        try:
            raw = hook.fn(ctx)
        except Exception as exc:  # noqa: BLE001 - isolate one failing hook
            results.append(
                SeedResult(
                    hook.name,
                    False,
                    f"Seed hook errored: {type(exc).__name__}: {exc}",
                    {"error_type": type(exc).__name__},
                )
            )
            continue
        results.append(_normalize(hook.name, raw))

    if include_load_errors and reg is default_registry:
        results.extend(_load_error_results())

    return results
