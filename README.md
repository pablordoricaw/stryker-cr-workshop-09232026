# Stryker Databricks Workshop

A 4-hour, self-paced, hands-on workshop. You'll build the **same end-to-end
project** on **your team's domain dataset** — Finance (Orthopedics), Security
(infrastructure), or ITSM (IT-Ops):

> ingest documents + transactional data → **medallion** (bronze → silver → gold)
> → auto-generate **governance metadata** → a **semantic layer** (UC Metric
> Views) → a natural-language **Genie agent** → a working **data app**.

Starter notebooks with `# TODO`s, a per-checkpoint validation seam
(`workshop.check()`), and a Genie-Code hint agent make sure everyone finishes
the whole thing — whether you use Databricks every day or have never opened it.

## Everything runs in the Databricks Workspace UI — no local setup

**You do not need a local development environment.** There is no terminal step,
no `git` on your laptop, no CLI, and no admin action required. You work entirely
in the **Databricks Workspace UI**, and you get help from **Genie Code** (the
in-workspace coding assistant) as you go. A single **setup notebook** creates a
schema and UC Volume inside your team's **existing catalog** and seeds your data
— you bring the catalog (the workshop never creates one), so no catalog-creation
privilege is required.

## Get the workshop repo into your workspace

Pick **one** of the two paths below. Both land the same files in your Databricks
workspace; choose whichever your environment allows.

### Option A — Fork, then clone your fork as a Workspace Git folder

1. **Fork** this repository to your own GitHub account (top-right **Fork**
   button on GitHub).
2. In Databricks, open the sidebar and go to **Workspace → (your home) → Create
   → Git folder** (also called a *Repo*).
3. Paste the **HTTPS URL of your fork** (e.g.
   `https://github.com/<you>/stryker-cr-workshop-09232026`), pick the default
   branch, and click **Create Git folder**.
4. Open the newly cloned folder in the Workspace. You're ready — start with the
   setup notebook.

> Forking (rather than cloning this repo directly) means you can commit your own
> progress and pull updates without needing write access here.

### Option B — Download a ZIP and upload it to the workspace

Use this when you can't or don't want to connect a Git provider to the
workspace.

1. On GitHub, click **Code → Download ZIP**, then **unzip it on your machine**
   (uploading the raw `.zip` does not expand it in the workspace).
2. In Databricks, go to **Workspace → (your home) → Import**.
3. Choose **File / Folder** and upload the unzipped workshop folder (drag-and-
   drop the folder, or import files preserving the directory structure).
4. Open the imported folder in the Workspace. You're ready — start with the
   setup notebook.

## How you know you passed: `workshop.check()`

Each checkpoint ends with a validation call. **The first cell of every notebook**
is this copy-pasteable bootstrap — it puts the repo root on the path so `import
workshop` works no matter where the notebook lives in your Git folder (don't
hardcode a path; this finds the root for you):

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

Then, at any checkpoint:

```python
workshop.check("smoke")
# [✅ PASS] smoke: workshop.check() is wired up correctly. ...
```

`workshop.check(<checkpoint_id>)` returns a structured pass/fail result with a
targeted, human-readable message telling you exactly what's missing and where to
look. It asserts only **observable state** — that the catalog objects, row
counts, tags, metric views, Genie answers, and synced tables you were supposed
to produce actually exist — never *how* you wrote your notebook. There's no
single "right" set of cells; if the result is green, you passed.

Run the **`smoke`** checkpoint right now, before you connect to anything: it
returns green from a fresh clone and confirms the validation seam is working.

## Getting unstuck

If you're stuck, ask **Genie Code** in the workspace. It reads this repo and
gives graded help — a nudge and a doc link first, then an API/skeleton, and only
then a checkpoint solution — so you get unblocked without skipping the learning.
A gated `solutions/` directory holds the full reference if you need it.

## Optional Tier-3 stretch modules

Finished early or want more? Three **optional** modules for strong engineers,
strictly additive to the graded path (skip them and your workshop is still
complete):

1. **Package your work as a DAB** — split what you built into three
   independently-deployable Databricks Asset Bundles.
2. **Add your own metrics / Genie questions** — extend the semantic + Genie
   layers with your own governed Metric View and benchmark questions.
3. **From-scratch mode** — a uniform convention for flipping any build stage from
   guided (`# TODO` + hints) to build-it-yourself, with the checkpoint unchanged.

Start at [`docs/stretch/README.md`](docs/stretch/README.md); the starters live in
`notebooks/stretch/`.

## Repository layout

| Path          | What's here                                                        |
| ------------- | ------------------------------------------------------------------ |
| `notebooks/`  | Participant starter notebooks (`# TODO` scaffolds) for each module |
| `workshop/`   | The `workshop.check()` validation framework                        |
| `data/`       | Committed synthetic data (PDFs + transactional seeds) per domain   |
| `app/`        | The provided data app you wire to your Genie agent                 |
| `solutions/`  | Gated reference solutions (top rung of the hint ladder)            |
| `resources/`  | Databricks Asset Bundle (DAB) resource definitions                 |
| `docs/stretch/` | Optional Tier-3 stretch modules (package-as-DAB, add-your-own)   |

## Prerequisites

- Access to a Databricks workspace **or** a free
  [Databricks Free Edition](https://www.databricks.com/learn/free-edition)
  account (self-sign-up; use this as your fallback venue).
- A GitHub account (only for **Option A**).

Your facilitator will confirm any workspace toggles needed on the day.

## Workshop release versions

Workshop releases on `main` are identified by annotated [Semantic Version](https://semver.org/) tags. The version reflects the participant-facing impact:

- `v1.0.0` — first stable workshop release.
- `v1.1.0` — new exercises, modules, or materially expanded content.
- `v1.1.1` — corrections, clarified instructions, broken-link fixes, or other compatible workshop fixes.
- `v2.0.0` — changes that substantially alter the workshop flow or invalidate prior setup/materials.
- `v1.2.0-rc.1` — optional rehearsal/review release before a major workshop event.
