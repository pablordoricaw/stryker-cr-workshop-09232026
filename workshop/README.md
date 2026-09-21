# workshop/ — the `workshop.check()` validation seam

The single test seam every workshop checkpoint runs through. Participant
notebooks and maintainer CI both call `workshop.check(<id>)`; there is no second
test framework.

## Participant usage

```python
import workshop
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
| `context.py`        | `CheckContext` — spark / catalog / schema / extras handed to a check |
| `registry.py`       | `CheckpointRegistry` + `@checkpoint` / `register` API       |
| `runner.py`         | `check()` — looks up, runs, and normalizes a checkpoint      |
| `checkpoints/`      | One module per checkpoint; auto-discovered on import        |

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

## Running the framework tests

```bash
uv run pytest        # from the repo root
```
