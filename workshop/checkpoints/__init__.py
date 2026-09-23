"""Checkpoint modules — auto-discovered so later tickets add checks by dropping
a file here.

Any module in this package (except those whose name starts with ``_``) is
imported when :func:`load_all` runs, which triggers the ``@checkpoint``
decorators inside it to register on the default registry. ``workshop/__init__``
calls :func:`load_all` on import, so ``import workshop`` is enough to make every
checkpoint available — a later ticket never edits a central list.

**Per-module isolation:** discovery catches each module's import failure so a
single broken checkpoint module — e.g. one that imports an unavailable optional
dependency — can never break ``import workshop`` or the connection-free smoke
checkpoint. A module that fails to import is recorded in :data:`LOAD_ERRORS` and
surfaced as an *unavailable* checkpoint (keyed by the module name) that returns
a failed result explaining the problem, instead of taking the whole framework
down.
"""

from __future__ import annotations

import importlib
import pkgutil

from workshop.registry import CheckpointRegistry
from workshop.registry import registry as _default_registry
from workshop.results import CheckResult

# module name -> the exception raised while importing it (most recent load_all).
LOAD_ERRORS: dict[str, Exception] = {}


def _register_unavailable(
    reg: CheckpointRegistry, module_name: str, exc: Exception
) -> None:
    """Register a placeholder so a failed module surfaces as an unavailable check."""

    def _unavailable(ctx, _mod: str = module_name, _exc: Exception = exc) -> CheckResult:
        return CheckResult(
            checkpoint=_mod,
            passed=False,
            message=(
                f"Checkpoint module '{_mod}' failed to import: "
                f"{type(_exc).__name__}: {_exc}. This is a workshop bug — tell "
                f"your facilitator. Other checkpoints are unaffected."
            ),
            details={"unavailable": True, "error_type": type(_exc).__name__},
        )

    try:
        reg.register(
            module_name,
            _unavailable,
            summary="(unavailable: module failed to import)",
            replace=True,
        )
    except Exception:  # noqa: BLE001 - never let surfacing an error raise
        pass


def _discover(
    search_paths: list[str],
    package_name: str,
    errors: dict[str, Exception],
    reg: CheckpointRegistry,
) -> list[str]:
    """Import every non-private module under ``search_paths``, isolating failures.

    Returns the names of the modules that imported cleanly. Broken modules are
    recorded in ``errors`` and registered as unavailable checkpoints on ``reg``.
    """
    loaded: list[str] = []
    for module_info in pkgutil.iter_modules(search_paths):
        if module_info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{package_name}.{module_info.name}")
            loaded.append(module_info.name)
        except Exception as exc:  # noqa: BLE001 - isolate one broken module
            errors[module_info.name] = exc
            _register_unavailable(reg, module_info.name, exc)
    return loaded


def load_all(registry: CheckpointRegistry | None = None) -> list[str]:
    """Import every checkpoint module so its checks self-register.

    Idempotent: re-importing an already-imported module is a no-op. Returns the
    list of module names that loaded cleanly; see :data:`LOAD_ERRORS` for any
    that failed.
    """
    reg = registry if registry is not None else _default_registry
    return _discover(list(__path__), __name__, LOAD_ERRORS, reg)
