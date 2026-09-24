"""Participant import-path robustness: `import workshop` must work from a
nested notebooks/ directory the way it does in a Databricks Git folder, not
only from the repo root with pytest's pythonpath injection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import workshop
from workshop.bootstrap import bootstrap, find_repo_root


def _repo_root() -> str:
    # .../workshop/__init__.py -> .../workshop -> repo root
    return os.path.dirname(os.path.dirname(os.path.abspath(workshop.__file__)))


def test_find_repo_root_from_repo_root():
    root = _repo_root()
    assert find_repo_root(root) == root


def test_find_repo_root_from_nested_notebooks_dir():
    root = _repo_root()
    nested = os.path.join(root, "notebooks")
    assert find_repo_root(nested) == root


def test_find_repo_root_returns_none_when_absent(tmp_path):
    assert find_repo_root(str(tmp_path)) is None


def test_bootstrap_is_idempotent():
    root = _repo_root()
    bootstrap(root)
    before = list(sys.path).count(root)
    bootstrap(root)
    after = list(sys.path).count(root)
    assert after == before  # no duplicate insertion
    assert root in sys.path


# The canonical first-cell snippet documented in README.md / workshop/README.md.
# Self-contained on purpose: it must run before `workshop` is importable.
_BOOTSTRAP_SNIPPET = textwrap.dedent(
    """
    import os, sys
    _root = os.path.abspath(os.getcwd())
    while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):
        _parent = os.path.dirname(_root)
        if _parent == _root:
            raise SystemExit("ROOT_NOT_FOUND")
        _root = _parent
    if _root not in sys.path:
        sys.path.insert(0, _root)

    import workshop
    result = workshop.check("smoke")
    assert result.passed, result
    print("OK:" + _root)
    """
)


def test_import_from_nested_cwd_without_pythonpath():
    """Simulate the notebook flow: run from notebooks/ with the repo root NOT on
    the path, apply the bootstrap snippet, and confirm `import workshop` and the
    offline smoke check both succeed.
    """
    root = _repo_root()
    notebooks = os.path.join(root, "notebooks")
    assert os.path.isdir(notebooks)

    # Strip PYTHONPATH so the repo root is not injected the way pytest does.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = ""

    proc = subprocess.run(
        [sys.executable, "-c", _BOOTSTRAP_SNIPPET],
        cwd=notebooks,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout.strip().splitlines()[-1] == f"OK:{root}"


def test_bare_import_fails_from_nested_cwd_without_bootstrap():
    """Control: without the bootstrap snippet, the bare import fails from
    notebooks/, which is exactly why the snippet exists.
    """
    root = _repo_root()
    notebooks = os.path.join(root, "notebooks")

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = ""

    proc = subprocess.run(
        [sys.executable, "-c", "import workshop"],
        cwd=notebooks,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "ModuleNotFoundError" in proc.stderr
