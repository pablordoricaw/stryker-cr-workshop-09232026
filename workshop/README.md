# workshop/ — the `workshop.check()` validation seam

The single test seam every workshop checkpoint runs through. Participant
notebooks and maintainer CI both call `workshop.check(<id>)`; there is no second
test framework.

## Making `import workshop` work in notebooks (canonical first cell)

In a Databricks Git folder the repo root is **not** guaranteed to be on
`sys.path` — a notebook's working directory is its own folder. Every starter
notebook's **first cell** is this one canonical, self-contained bootstrap (it
must run before `workshop` is importable, so it can't import from the repo).
Ticket authors: reuse this exact snippet; do not invent variants.

```python
# --- Workshop bootstrap: run this first in every notebook ---
import os, sys
_root = os.path.abspath(os.getcwd())
while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        raise RuntimeError("workshop repo root not found; open this notebook inside the cloned workshop Git folder.")
    _root = _parent
if _root not in sys.path:
    sys.path.insert(0, _root)

import workshop
```

The same anchor logic is available programmatically once `workshop` is imported:
`workshop.bootstrap()` (idempotent path insert, returns the root) and
`workshop.find_repo_root()`. Both are dependency-free and Free-Edition-safe. The
snippet is validated end-to-end by a nested-CWD subprocess regression test in
`tests/test_bootstrap.py`.

## Participant usage

```python
result = workshop.check("smoke")     # returns a CheckResult
print(result)                        # [✅ PASS] smoke: ...
if result:                           # CheckResult is truthy when it passed
    ...
```

`workshop.check` never raises: an unknown id or a checkpoint that throws comes
back as `passed=False` with an explanatory message.

## Module map

| Module              | Responsibility                                              |
| ------------------- | ----------------------------------------------------------- |
| `results.py`        | `CheckResult` — the structured pass/fail contract           |
| `context.py`        | `CheckContext` — spark / catalog / schema / extras handed to a check (backtick-safe `fully_qualified`) |
| `registry.py`       | `CheckpointRegistry` + `@checkpoint` / `register` API       |
| `runner.py`         | `check()` — looks up, runs, and normalizes a checkpoint      |
| `bootstrap.py`      | `find_repo_root` / `bootstrap` — the notebook import path fix |
| `checkpoints/`      | One module per checkpoint; auto-discovered, failure-isolated |

## Adding a checkpoint (for later tickets)

Drop a module into `workshop/checkpoints/` — it's auto-discovered on `import
workshop`, so there is **no central list to edit**. Register with the decorator:

```python
# workshop/checkpoints/bronze_docs.py
from workshop import CheckResult, checkpoint
from workshop.context import CheckContext

@checkpoint("bronze_docs", summary="Documents landed in the UC Volume")
def check_bronze_docs(ctx: CheckContext) -> CheckResult:
    spark = ctx.require_spark()  # fails cleanly if run with no workspace
    count = spark.sql(
        f"SELECT count(*) FROM {ctx.fully_qualified('bronze_docs')}"
    ).collect()[0][0]
    passed = count >= 20
    return CheckResult(
        checkpoint="bronze_docs",
        passed=passed,
        message=(
            f"{count} documents landed." if passed
            else f"Found only {count} documents; expected >= 20. "
                 f"Re-run the ingestion cell."
        ),
        details={"row_count": count},
    )
```

A checkpoint may also return a bare `bool` or a `(bool, message)` tuple; the
runner normalizes those into a `CheckResult`.

### Rules for a good checkpoint

- **Assert only externally-observable state**: catalog objects, row counts,
  tag/comment presence, metric-view resolvability, Genie answer sanity,
  synced-table row parity. **Never** inspect notebook cell structure or
  intermediate variables — participants may reach the same observable state many
  different ways.
- **Write a targeted failure message**: say what's wrong and where to look, not
  just "failed".
- **Reach for the workspace through `ctx`**: `ctx.require_spark()` and
  `ctx.fully_qualified(table)` fail with a clear message instead of an
  `AttributeError` when run with no connection.
- **Pick a unique id.** Duplicate ids raise at import; use
  `@checkpoint(id, replace=True)` only if you deliberately override.
- **Optional dependencies are isolated, not free.** If your module's import
  fails (e.g. an optional dependency is missing), discovery records it in
  `workshop.checkpoint_load_errors` and surfaces the module as an *unavailable*
  checkpoint (keyed by the module name) rather than breaking `import workshop`.
  Still, keep top-level imports light and import heavy/optional deps inside the
  check function so your checkpoint stays runnable.

## Running the framework tests

```bash
uv run pytest        # from the repo root
```
