# `libs/` — vendored wheels

## `dbxmetagen-0.10.68-py3-none-any.whl`

A **prebuilt, pinned** wheel of [dbxmetagen](https://github.com/databricks-industry-solutions/dbxmetagen)
at tag **`v0.10.68`**, vendored into the repo so `04_metadata` can install it
**without cloning from GitHub at notebook runtime**.

- **sha256:** `765be35f7e0606adcec40d61343118b4f1c4253a7505d54b93e8df27d12154de`
  (of *this* committed artifact; Hatchling builds are not guaranteed byte-reproducible,
  so a fresh build may differ in bytes while being functionally identical).
- **Pure-Python** (`py3-none-any`) — no native code, no CPU-architecture concerns.
- dbxmetagen's own dependencies are **not** in this wheel (a wheel never bundles its
  dependencies). Installing it still resolves the transitive tree (`mlflow`,
  `ydata-profiling`, `openai`, …) from **PyPI at runtime**, so `04_metadata` needs
  **PyPI egress**. Where egress is blocked, `04_metadata` detects it and falls back to
  a manual-metadata path — see that notebook.

### Why vendored instead of `%pip install git+…`

The original `%pip install git+https://github.com/…@v0.10.68` clones **and builds**
dbxmetagen from source at runtime, which hangs on workspaces without github.com egress
(observed on the delivery-class workspace). We cannot pre-upload the wheel to a shared
UC Volume in the delivery workspaces (no access), so it ships in the repo and installs
via a repo-relative path from the notebook. See issue #28 for the full rationale.

### Rebuild recipe (maintainer, on a machine with internet)

```bash
git clone --branch v0.10.68 --depth 1 https://github.com/databricks-industry-solutions/dbxmetagen.git
cd dbxmetagen && uv build          # produces dist/dbxmetagen-0.10.68-py3-none-any.whl
shasum -a 256 dist/dbxmetagen-0.10.68-py3-none-any.whl
```

Then copy the wheel here, replacing the existing one, and update the sha256 above.
