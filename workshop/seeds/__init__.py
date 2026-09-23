"""Seed hooks — the extension point later data tickets populate.

The setup notebook provisions a participant's catalog/schema/volume and then
calls :func:`workshop.run_seeds` to load that environment's data. *What* gets
loaded is intentionally not defined here: this ticket ships the mechanism and a
no-op placeholder. Later tickets (Finance seed #4; the loading wiring in #5/#7;
Security #13; ITSM #14) add real loaders by dropping a module into this package
and decorating a function with :func:`seed_hook`.

Discovery mirrors ``workshop/checkpoints``: every non-private module here is
imported on ``import workshop`` so its ``@seed_hook`` decorators self-register —
there is no central list to edit. Framework internals are ``_``-prefixed so they
are skipped by discovery; only real seed modules (``placeholder`` today) load.

**Per-module isolation:** a seed module that fails to import (e.g. a missing
optional dependency in a later ticket) is recorded in :data:`LOAD_ERRORS` and
surfaced by ``run_seeds`` as a failed seed, instead of breaking ``import
workshop`` or any other seed.
"""

from __future__ import annotations

import importlib
import pkgutil

from ._context import SeedContext, SeedResult
from ._registry import (
    DuplicateSeedError,
    SeedFn,
    SeedHook,
    SeedRegistry,
    register_seed,
    seed_hook,
    seed_registry,
)
from ._runner import run_seeds

# module name -> the exception raised while importing it (most recent load_all).
LOAD_ERRORS: dict[str, Exception] = {}

__all__ = [
    "SeedContext",
    "SeedResult",
    "SeedHook",
    "SeedFn",
    "SeedRegistry",
    "DuplicateSeedError",
    "seed_registry",
    "register_seed",
    "seed_hook",
    "run_seeds",
    "load_all",
    "LOAD_ERRORS",
]


def load_all() -> list[str]:
    """Import every non-private seed module so its hooks self-register.

    Idempotent (re-importing an already-imported module is a no-op). Returns the
    names of modules that loaded cleanly; failures land in :data:`LOAD_ERRORS`.
    """
    LOAD_ERRORS.clear()
    loaded: list[str] = []
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{module_info.name}")
            loaded.append(module_info.name)
        except Exception as exc:  # noqa: BLE001 - isolate one broken seed module
            LOAD_ERRORS[module_info.name] = exc
    return loaded
