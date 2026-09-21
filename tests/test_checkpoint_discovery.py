"""Auto-discovery must isolate a broken checkpoint module: one module that fails
to import (e.g. an unavailable optional dependency) must not break `import
workshop` or the offline smoke checkpoint.
"""

from __future__ import annotations

import importlib
import sys

import workshop
from workshop.checkpoints import _discover
from workshop.registry import CheckpointRegistry


def test_smoke_still_green_after_import():
    # If discovery were fragile, importing workshop (done at module load) would
    # already have failed. Confirm the connection-free smoke check is green.
    assert workshop.check("smoke").passed is True


def test_broken_module_is_isolated(tmp_path):
    # Build a throwaway checkpoint package: one good module, one that raises on
    # import (simulating a missing optional dependency).
    pkg = tmp_path / "throwaway_checkpoints"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "good.py").write_text("LOADED = True\n")
    (pkg / "broken.py").write_text(
        "raise ImportError('optional dependency not installed')\n"
    )

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("throwaway_checkpoints")
        reg = CheckpointRegistry()
        errors: dict[str, Exception] = {}

        # Must NOT raise, despite broken.py.
        loaded = _discover(list(package.__path__), package.__name__, errors, reg)

        assert "good" in loaded
        assert "broken" not in loaded
        assert "broken" in errors
        assert isinstance(errors["broken"], ImportError)

        # The broken module is surfaced as an unavailable checkpoint.
        result = workshop.check("broken", registry=reg)
        assert result.passed is False
        assert "failed to import" in result.message
        assert result.details["unavailable"] is True
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name == "throwaway_checkpoints" or name.startswith(
                "throwaway_checkpoints."
            ):
                del sys.modules[name]


def test_no_load_errors_in_normal_operation():
    # The shipped package (just smoke today) imports cleanly.
    assert workshop.checkpoint_load_errors == {}
