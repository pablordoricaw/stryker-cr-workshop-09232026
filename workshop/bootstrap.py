"""Make ``import workshop`` work from anywhere inside the repo.

In a Databricks Git folder, starter notebooks live under ``notebooks/`` and the
repo root is **not** guaranteed to be on ``sys.path`` — the notebook's working
directory is typically its own folder, so a bare ``import workshop`` can fail
for every participant.

The canonical fix is a tiny, self-contained first cell (documented in the
top-level ``README.md`` and ``workshop/README.md``) that walks up from the
current directory to the repo root — anchored on ``workshop/__init__.py``, never
a hardcoded path — and puts it on ``sys.path`` *before* importing workshop::

    import os, sys
    _root = os.path.abspath(os.getcwd())
    while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):
        _parent = os.path.dirname(_root)
        if _parent == _root:
            raise RuntimeError("workshop repo root not found; open this "
                               "notebook inside the cloned workshop Git folder.")
        _root = _parent
    if _root not in sys.path:
        sys.path.insert(0, _root)

    import workshop

Once ``workshop`` is importable, :func:`bootstrap` exposes the identical anchor
logic as a reusable, idempotent call — handy for notebooks that re-run their
cells or code that wants the repo root programmatically. It is dependency-free
and Free-Edition-safe (pure stdlib, no Spark, no network).
"""

from __future__ import annotations

import os
import sys

# A directory is the repo root iff it contains the importable ``workshop``
# package. This is the most reliable anchor: it is exactly what we need on the
# path, so it can never point at the wrong directory.
_ANCHOR = ("workshop", "__init__.py")


def find_repo_root(start: str | None = None) -> str | None:
    """Walk up from ``start`` (default: CWD) to the repo root.

    Returns the first ancestor directory that contains ``workshop/__init__.py``,
    or ``None`` if the filesystem root is reached without finding it.
    """
    path = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(path, *_ANCHOR)):
            return path
        parent = os.path.dirname(path)
        if parent == path:  # reached the filesystem root
            return None
        path = parent


def bootstrap(start: str | None = None) -> str:
    """Ensure the repo root is on ``sys.path`` and return it.

    Idempotent: inserting the same root twice is a no-op. Raises a
    participant-friendly error if the repo root cannot be located (e.g. the
    notebook was opened outside the cloned workshop Git folder).
    """
    root = find_repo_root(start)
    if root is None:
        raise RuntimeError(
            "Could not locate the workshop repo root (no workshop/__init__.py "
            f"found walking up from {os.path.abspath(start or os.getcwd())!r}). "
            "Open this notebook from inside the cloned workshop Git folder."
        )
    if root not in sys.path:
        sys.path.insert(0, root)
    return root
