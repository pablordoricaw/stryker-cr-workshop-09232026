# Stryker Databricks Workshop

![Platform: Databricks](https://img.shields.io/badge/Platform-Databricks-FF3621?logo=databricks&logoColor=white)
![Lakeflow](https://img.shields.io/badge/Lakeflow-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAIVBMVEX%2F%2F%2F%2F8w778wbz%2Bwr38wb36v7r7wLv%2FYEb%2FYUj%2FYEf%2FX0ZHYPIGAAAAAXRSTlMAQObYZgAAAAFvck5UAc%2Bid5oAAABuSURBVCjPrZFJDsAgDAPDkgby%2FweXUIKEoad2DlwGY0sQ%2FUqIAxQxDeKbSPkgmNtxoWDj9NhMcsgGGoYRUgxpu1HUjsx9IJQoo9BuSjPB8PJaZ2RFjKK95YA16QNcUDeYFA9sT4qv2LrE%2Bfz3CzeqUAS0Uz86oQAAAABJRU5ErkJggg%3D%3D)
![Lakebase](https://img.shields.io/badge/Lakebase-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAElBMVEX%2F%2F%2F%2F6v7r%2Fw73%2FXkX%2FX0b%2FYEcRmtWXAAAAAXRSTlMAQObYZgAAAFRJREFUKM%2BtkkESABEMBJHx%2Fy%2BTkthluKDd9KQypYTwlEi4SBOD0OBSLCd2Ow7q2nJbcNlK6uEJepzvQhRuBWQFgFjMRW6myRrDKOD8xEQXxNuPUABeCgKPeWIUjwAAAABJRU5ErkJggg%3D%3D)
![Unity Catalog](https://img.shields.io/badge/Unity_Catalog-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAGFBMVEX%2F%2F%2F%2F%2FX0b6vrn6v7r%2Bwr3%2FX0X%2FXkT%2FYEfA0FutAAAAAXRSTlMAQObYZgAAAAFvck5UAc%2Bid5oAAABvSURBVCjPpZFLDoAwCET5Ve5%2FY22mkhaLMZENKS8wUyD6E8yboiiA6lpXM0VO5AY28ojWR6CjpzaLSojNJo5VMD2fdgXzmd25UchdAE7YO4FDWYFnUI162VVlN3%2FQo7NaCZzYZonz2hMoD1Wf9nucAaUBuSTbLk8AAAAASUVORK5CYII%3D)
![Genie Code](https://img.shields.io/badge/Genie_Code-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAElBMVEX%2F%2F%2F%2F%2FXkX%2FX0b%2FYEf6v7r9wbybda%2B9AAAAAXRSTlMAQObYZgAAAF5JREFUKM%2FNkFEOgDAIQ6HA%2Fa8soC4Y2TL%2F7A%2FkdSsEop%2BIJxzSO4C0DjsXcB%2BF2ZCrqvZbFa6pu7FheGsupSxWPyTK15UPw8KogyP%2BTHnyusCbr24b6o%2Fo4i9RuzoAg%2BABjmebNh0AAAAASUVORK5CYII%3D)
![Genie Agents](https://img.shields.io/badge/Genie_Agents-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAElBMVEX%2F%2F%2F%2F%2FXkX%2FX0b%2FYEf6v7r9wbybda%2B9AAAAAXRSTlMAQObYZgAAAF5JREFUKM%2FNkFEOgDAIQ6HA%2Fa8soC4Y2TL%2F7A%2FkdSsEop%2BIJxzSO4C0DjsXcB%2BF2ZCrqvZbFa6pu7FheGsupSxWPyTK15UPw8KogyP%2BTHnyusCbr24b6o%2Fo4i9RuzoAg%2BABjmebNh0AAAAASUVORK5CYII%3D)
![Databricks Apps](https://img.shields.io/badge/Databricks_Apps-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAJFBMVEX%2F%2F%2F%2F6wLv8wr3%2FYUf%2FX0b%2FYEf9wr38w77%2FYEb8wLv7v7v6v7pOiGY7AAAAAXRSTlMAQObYZgAAAAFvck5UAc%2Bid5oAAABlSURBVCjPrZBLDsAgCAXRgqi9%2F30LD9PWhUmbOKsXJ8iHaCsJZEsHOyJvUdRSFXtdiVUFfxLFCREM0VQ152aJKxDaztOxNzAL9jEwX%2BlDMEQN4SvdAluFSL%2FF9NW6eZS4OMHmc1y1jQRhKCPTFwAAAABJRU5ErkJggg%3D%3D)

A 4-hour, self-paced, hands-on workshop. You'll build the **same end-to-end
project** on **your team's domain dataset** — Finance (Orthopedics), Security
(infrastructure), or ITSM (IT-Ops):

> ingest documents + transactional data → **medallion** (bronze → silver → gold)
> → auto-generate **governance metadata** → a **semantic layer** (UC Metric
> Views) → a natural-language **Genie agent** → a working **data app**.

Starter notebooks with `# TODO`s, a per-checkpoint validation seam
(`workshop.check()`), and a Genie-Code hint agent make sure everyone finishes
the whole thing — whether you use Databricks every day or have never opened it.

## Workshop Architecture

![Workshop architecture showing Finance, Security, and ITSM source domains flowing through bronze, silver, and gold medallion layers into governance metadata and UC Metric Views, then a Genie agent and Databricks data app.](assets/diagrams/workshop-architecture.svg)

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

Every build notebook has collapsible **💡 Hint** cells on each `# TODO`. Beyond
those, ask **Genie Code** in the workspace: it gives graded help **one rung at a
time** — a nudge and a doc link first, then an API shape or skeleton, and only
then the checkpoint solution — for the **one checkpoint you're on**, so you get
unblocked without skipping the learning. The gated `solutions/<domain>/`
directory holds the full reference as the last rung.

Genie Code knows how to help because `00_setup` installs the workshop's hint
ladder into your personal instructions file (`~/.assistant_instructions.md`),
which Genie Code auto-loads each session — with your repo root and chosen domain
filled in. It's added surgically, so any personal instructions of your own are
preserved. When you finish, run `notebooks/99_teardown.py` to remove it.

**Free-Edition fallback.** Genie Code is guaranteed on the Stryker workspaces but
may be unavailable on Databricks Free Edition. If you can't reach it, the hint
ladder degrades to *read the solution* rather than stranding you: open
`solutions/<domain>/<module>.py` for your domain and current checkpoint
directly — the same one-checkpoint-at-a-time discipline still applies.

## Optional Tier-3 stretch modules

Finished early or want more? Three **optional** modules for strong engineers,
strictly additive to the graded path (skip them and your workshop is still
complete):

1. **Package your work as a DAB** — split what you built into two
   independently-deployable Databricks Asset Bundles (pipeline + app) that target
   the schema `00_setup` provisioned.
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
| `docs/genie/` | The hint ladder `00_setup` installs into Genie Code's instructions |
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
