"""Checkpoint modules — auto-discovered so later tickets add checks by dropping
a file here.

Any module in this package (except those whose name starts with ``_``) is
imported when :func:`load_all` runs, which triggers the ``@checkpoint``
decorators inside it to register on the default registry. ``workshop/__init__``
calls :func:`load_all` on import, so ``import workshop`` is enough to make every
checkpoint available — a later ticket never edits a central list.
"""

from __future__ import annotations

import importlib
import pkgutil


def load_all() -> list[str]:
    """Import every checkpoint module so its checks self-register.

    Idempotent: re-importing an already-imported module is a no-op. Returns the
    list of module names that were loaded, for debugging/telemetry.
    """
    loaded: list[str] = []
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module_info.name}")
        loaded.append(module_info.name)
    return loaded
