# Stryker Databricks Workshop

![Platform: Databricks](https://img.shields.io/badge/Platform-Databricks-FF3621?logo=databricks&logoColor=white)
![Lakeflow](https://img.shields.io/badge/Lakeflow-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAIVBMVEX%2F%2F%2F%2F8w778wbz%2Bwr38wb36v7r7wLv%2FYEb%2FYUj%2FYEf%2FX0ZHYPIGAAAAAXRSTlMAQObYZgAAAAFvck5UAc%2Bid5oAAABuSURBVCjPrZFJDsAgDAPDkgby%2FweXUIKEoad2DlwGY0sQ%2FUqIAxQxDeKbSPkgmNtxoWDj9NhMcsgGGoYRUgxpu1HUjsx9IJQoo9BuSjPB8PJaZ2RFjKK95YA16QNcUDeYFA9sT4qv2LrE%2Bfz3CzeqUAS0Uz86oQAAAABJRU5ErkJggg%3D%3D)
![Lakebase](https://img.shields.io/badge/Lakebase-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAElBMVEX%2F%2F%2F%2F6v7r%2Fw73%2FXkX%2FX0b%2FYEcRmtWXAAAAAXRSTlMAQObYZgAAAFRJREFUKM%2BtkkESABEMBJHx%2Fy%2BTkthluKDd9KQypYTwlEi4SBOD0OBSLCd2Ow7q2nJbcNlK6uEJepzvQhRuBWQFgFjMRW6myRrDKOD8xEQXxNuPUABeCgKPeWIUjwAAAABJRU5ErkJggg%3D%3D)
![Unity Catalog](https://img.shields.io/badge/Unity_Catalog-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAGFBMVEX%2F%2F%2F%2F%2FX0b6vrn6v7r%2Bwr3%2FX0X%2FXkT%2FYEfA0FutAAAAAXRSTlMAQObYZgAAAAFvck5UAc%2Bid5oAAABvSURBVCjPpZFLDoAwCET5Ve5%2FY22mkhaLMZENKS8wUyD6E8yboiiA6lpXM0VO5AY28ojWR6CjpzaLSojNJo5VMD2fdgXzmd25UchdAE7YO4FDWYFnUI162VVlN3%2FQo7NaCZzYZonz2hMoD1Wf9nucAaUBuSTbLk8AAAAASUVORK5CYII%3D)
![Genie Code](https://img.shields.io/badge/Genie_Code-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAElBMVEX%2F%2F%2F%2F%2FXkX%2FX0b%2FYEf6v7r9wbybda%2B9AAAAAXRSTlMAQObYZgAAAF5JREFUKM%2FNkFEOgDAIQ6HA%2Fa8soC4Y2TL%2F7A%2FkdSsEop%2BIJxzSO4C0DjsXcB%2BF2ZCrqvZbFa6pu7FheGsupSxWPyTK15UPw8KogyP%2BTHnyusCbr24b6o%2Fo4i9RuzoAg%2BABjmebNh0AAAAASUVORK5CYII%3D)
![Genie Agents](https://img.shields.io/badge/Genie_Agents-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAElBMVEX%2F%2F%2F%2F%2FXkX%2FX0b%2FYEf6v7r9wbybda%2B9AAAAAXRSTlMAQObYZgAAAF5JREFUKM%2FNkFEOgDAIQ6HA%2Fa8soC4Y2TL%2F7A%2FkdSsEop%2BIJxzSO4C0DjsXcB%2BF2ZCrqvZbFa6pu7FheGsupSxWPyTK15UPw8KogyP%2BTHnyusCbr24b6o%2Fo4i9RuzoAg%2BABjmebNh0AAAAASUVORK5CYII%3D)
![Databricks Apps](https://img.shields.io/badge/Databricks_Apps-1B3139?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAJFBMVEX%2F%2F%2F%2F6wLv8wr3%2FYUf%2FX0b%2FYEf9wr38w77%2FYEb8wLv7v7v6v7pOiGY7AAAAAXRSTlMAQObYZgAAAAFvck5UAc%2Bid5oAAABlSURBVCjPrZBLDsAgCAXRgqi9%2F30LD9PWhUmbOKsXJ8iHaCsJZEsHOyJvUdRSFXtdiVUFfxLFCREM0VQ152aJKxDaztOxNzAL9jEwX%2BlDMEQN4SvdAluFSL%2FF9NW6eZS4OMHmc1y1jQRhKCPTFwAAAABJRU5ErkJggg%3D%3D)

A ~4-hour, self-paced, hands-on workshop where you build the **same end-to-end data project** on **your team's domain dataset**, **entirely in the Databricks Workspace UI with no local setup required**. You pick one domain: Finance (Orthopedics), Security (infrastructure), or ITSM (IT-Ops). All of the workshop data is synthetically generated. You'll work through guided starter notebooks with `# TODO`s, validated at each checkpoint with `workshop.check()`, and get contextual help from **Genie Code** as you go.

## Workshop Architecture

![Workshop architecture showing Finance, Security, and ITSM source domains flowing through bronze, silver, and gold medallion layers into governance metadata and UC Metric Views, then a Genie agent and Databricks data app.](assets/diagrams/workshop-architecture.svg)

The diagram traces the full path you'll build. You start by ingesting two kinds of source data: unstructured documents (PDFs) and structured transactional records. Both flow through the **medallion architecture**, refined from **bronze** (raw landing) to **silver** (parsed and cleaned) to **gold** (joined, business-ready tables). On top of gold, you auto-generate **governance metadata**, then define a **semantic layer** of UC Metric Views. Those governed metrics feed a natural-language **Genie agent**, and finally a **Databricks data app** puts the whole pipeline behind a working interface.

## Table of Contents

- [What you'll build in the workshop](#what-youll-build-in-the-workshop)
  - [The workshop path](#the-workshop-path)
  - [Repository layout](#repository-layout)
- [Getting started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Get the workshop into your workspace](#get-the-workshop-into-your-workspace)
  - [You've got the code, now what?](#youve-got-the-code-now-what)
- [How you know you passed: workshop.check()](#how-you-know-you-passed-workshopcheck)
- [Getting help from Genie Code](#getting-help-from-genie-code)
- [Optional Tier-3 stretch modules](#optional-tier-3-stretch-modules)
- [Workshop releases](#workshop-releases)
- [Furthering your Databricks skills](#furthering-your-databricks-skills)

## What you'll build in the workshop

You build for **one domain** of your choice: Finance (Orthopedics), Security (infrastructure), or ITSM (IT-Ops). You don't build for all three. Whichever domain you pick, you build the same medallion architecture:

1. **Set up** your workspace schema and UC Volume (you bring an existing catalog; no catalog-creation privilege needed).
2. **Bronze layer**: ingest PDFs (documents) and a transactional seed dataset.
3. **Silver layer**: parse documents with AI Functions, classify and extract domain-specific fields.
4. **Gold layer**: join extracted documents to transactions, build a fact table and a reconciled mart.
5. **Governance**: auto-generate metadata (comments, tags) on your gold layer.
6. **Semantic layer**: author UC Metric Views over your gold tables.
7. **Agent**: build a curated Genie agent as a natural-language interface.
8. **App**: wire the provided FastAPI data app to your Genie agent and a Lakebase synced table.

Each step is guided with `# TODO` cells, collapsible hints, and checkpoint validation. Everything runs in the **Databricks Workspace UI**: there is no terminal, no local `git`, no CLI, and no admin action required.

### The workshop path

Here is the module sequence you will walk, from `00_setup` through `07_app`, plus cleanup, with optional stretch modules:

```
00_setup                    Set up your schema, UC Volume, and domain config
01_bronze_docs              Land PDF documents into a UC Volume bronze table
01_bronze_txn               Land transactional data into a bronze table
02_silver_docs              Parse documents with AI Functions; classify and extract
03_gold                     Join fact to extracted docs; build gold tables
04_metadata                 Auto-generate governance metadata with dbxmetagen
05_metric_views             Author two UC Metric Views over gold tables
06_genie                    Build a Genie agent over gold tables and metric views
07_app                      Wire the provided FastAPI app to the Genie agent and Lakebase
99_teardown                 Clean up your personal instructions file
```

Optional stretch modules (after finishing 07_app):
```
stretch/package_as_dab      Package your work as deployable Databricks Asset Bundles
stretch/add_your_own        Extend metric views and Genie questions
```

### Repository layout

```
stryker-cr-workshop-09232026/
├── notebooks/
│   ├── 00_setup.py              Setup: configure domain and provision schema/volume
│   ├── 01_bronze_docs.py        Bronze layer for documents
│   ├── 01_bronze_txn.py         Bronze layer for transactions
│   ├── 02_silver_docs.py        Parse, classify, extract with AI Functions
│   ├── 03_gold.py               Join and build gold tables
│   ├── 04_metadata.py           Auto-generate governance metadata
│   ├── 05_metric_views.py       Author UC Metric Views
│   ├── 06_genie.py              Build a Genie agent
│   ├── 07_app.py                Wire the FastAPI data app
│   ├── 99_teardown.py           Cleanup
│   └── stretch/
│       ├── package_as_dab.py    (Optional) Package as DABs
│       └── add_your_own.py      (Optional) Extend metrics and Genie
├── workshop/                    The workshop.check() validation framework
├── data/                        Synthetic PDFs and transactional seeds per domain (Finance/Security/ITSM)
├── app/                         The provided FastAPI data app you wire to your Genie agent
├── solutions/                   Gated reference solutions, one per checkpoint, per domain (the last rung of the hint ladder)
├── resources/                   Databricks Asset Bundle (DAB) resource definitions
├── docs/
│   ├── genie/
│   │   └── .assistant_instructions.md   Hint ladder (injected into Genie Code)
│   └── stretch/
│       └── README.md            Tier-3 stretch module guide
└── assets/
    └── diagrams/
        └── workshop-architecture.svg   The workshop data flow diagram
```

## Getting started

### Prerequisites

- **Databricks workspace access**, or a free [Databricks Free Edition](https://www.databricks.com/learn/free-edition) account for self-sign-up (see the note below).
- **GitHub account** (only if you choose **Option A** below; optional for Option B).
- Your facilitator will confirm any workspace toggles needed on the day.

> [!NOTE]
> **Databricks Free Edition works for this workshop.** Here is how its limits play out for the steps that could be affected:
> - **Databricks App (`07_app`): you can deploy it.** Free Edition allows up to 3 apps, so the one you build fits easily. It auto-stops 24 hours after you deploy it, so if you come back the next day, redeploy or restart it to demo again.
> - **Lakebase synced table (`07_app`): you can build it.** Free Edition includes one Lakebase project with scale-to-zero compute, which is all this module needs (you only ever create one).
> - **AI Functions / Foundation Models (`02_silver_docs`, `04_metadata`): they work, but throttle.** Free Edition has no provisioned throughput and some models may be unavailable, so the AI-powered steps can hit rate limits. If a call is throttled, slow down and retry.
> - **Genie Code: may be unavailable.** If it is, the hint ladder falls back to reading the solution directly (see [Free-Edition fallback](#free-edition-fallback) below).

### Get the workshop into your workspace

Pick **one** of the two paths below. Both land the same files in your Databricks workspace; choose whichever your environment allows.

#### Option A: Fork, then clone your fork as a Workspace Git folder

1. **Fork** this repository to your own GitHub account (top-right **Fork** button on GitHub).
2. In Databricks, open the sidebar and go to **Workspace → (your home) → Create → Git folder** (also called a *Repo*).
3. Paste the **HTTPS URL of your fork** (e.g., `https://github.com/<you>/stryker-cr-workshop-09232026`), pick the default branch, and click **Create Git folder**.
4. Open the newly cloned folder in the Workspace.

> [!TIP]
> Forking (rather than cloning this repo directly) means you can commit your own progress and pull updates without needing write access here.

#### Option B: Download a ZIP and upload it to the workspace

Use this when you can't or don't want to connect a Git provider to the workspace.

1. On GitHub, click **Code → Download ZIP**, then **unzip it on your machine** (uploading the raw `.zip` does not expand it in the workspace).
2. In Databricks, go to **Workspace → (your home) → Import**.
3. Choose **File / Folder** and upload the unzipped workshop folder (drag-and-drop the folder, or import files preserving the directory structure).
4. Open the imported folder in the Workspace.

### You've got the code, now what?

Open `notebooks/00_setup.py` and run the bootstrap cell (the first cell, which puts the repo on the path), then walk through the setup steps. When you finish, come back here and run the [`smoke` checkpoint](#how-you-know-you-passed-workshopcheck) to confirm everything is wired up, then follow [the workshop path](#the-workshop-path) from `01_bronze_docs` through `07_app`.

## How you know you passed: workshop.check()

Each checkpoint validates the **observable state** you built (the catalog objects, row counts, tags, metric views, Genie answers, and synced tables you were supposed to produce), never *how* you wrote your notebook.

**The mandatory bootstrap cell** (first cell in every notebook):

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

The result is a structured pass/fail message with targeted guidance on exactly what's missing and where to look. There's no single "right" set of cells; **if the result is green, you passed.**

**Run the `smoke` checkpoint right now**, before you connect to anything; it returns green from a fresh clone and confirms the validation seam is working.

## Getting help from Genie Code

**Genie Code** is the in-workspace coding assistant integrated throughout the Databricks workspace. It helps you get unblocked without skipping the learning.

### Opening Genie Code

Genie Code is available in notebooks, the SQL editor, and other Databricks environments. To open it:

- **Click the Genie Code icon** (a magic lamp) in the upper-right corner of any page or notebook.
- Or from the Workspace home, select **Code** in the prompt box, enter your prompt, and submit.
- Once the side pane opens, click **Maximize** to expand to full-page mode if needed.

See the [Databricks Genie Code documentation](https://docs.databricks.com/genie-code/navigate-genie-code) for more details.

> [!NOTE]
> Facilitator: confirm the exact way to open Genie Code in your workspace, in case your environment has custom configuration.

### How the hint ladder works

Genie Code provides help **one rung at a time**, escalated only as you ask:

1. **Nudge + doc link**: a conceptual pointer and where to read, no code.
2. **API shape / skeleton**: the call shape or a skeleton, gaps to fill yourself.
3. **Checkpoint solution**: the gated reference for the **current checkpoint only** (e.g., `solutions/<domain>/01_bronze_docs.py`).

### Genie Code knows your checkpoint

When you run a `workshop.check("<checkpoint_id>")` cell in a notebook, Genie Code **infers your current checkpoint** from the notebook you're in or the checkpoint cell itself, so you don't need to memorize IDs. You can also name your checkpoint explicitly in conversation: "I'm on `01_bronze_docs`" or "Help with the silver layer."

### Worked example: the rung ladder

Suppose you're stuck on building a bronze documents table (`01_bronze_docs`). Here's how the ladder climbs:

**You ask:** "I'm stuck on 01_bronze_docs."

**Rung 1 (Nudge + doc link):**
> Copy the committed source PDFs from `data/<domain>/` into your UC Volume, then register a **bronze documents table** over the raw files. Start with these concepts: UC Volumes documentation and creating Delta tables from files. The hint cell in the notebook has more.

**You try, then ask again:** "Still stuck. Show me the shape."

**Rung 2 (API shape / skeleton):**
> Copy files into the Volume path from your config:
> ```python
> import shutil
> shutil.copytree(source_pdf_path, your_volume_path, dirs_exist_ok=True)
> ```
> Then create the bronze table over the landed files with columns for metadata (filename, path). Fill the `# TODO` cell and keep the hint collapsed if you're learning from scratch.

**You try, still stuck, ask once more:** "I need the full reference."

**Rung 3 (Checkpoint solution):**
> Open your domain's solution file: `solutions/<domain>/01_bronze_docs.py`. Follow that module for the current checkpoint only. The same one-checkpoint-at-a-time discipline applies: read only the code for this step, not the whole file.

### Free-Edition fallback

Genie Code is guaranteed on Stryker workspaces but may be unavailable on Databricks Free Edition. If you can't reach Genie Code, the hint ladder degrades to **read the solution directly**:

1. Open `solutions/<domain>/<module>.py` for your domain and current checkpoint.
2. Start with the notebook's collapsible **💡 Hint** cells first; the gated solution is the last resort.
3. The same one-checkpoint-at-a-time discipline still applies: read only the file for your current checkpoint.

## Optional Tier-3 stretch modules

Finished early or want more? Three optional modules for strong engineers, strictly additive to the graded path:

1. **Package your work as a DAB**: split what you built into two independently-deployable Databricks Asset Bundles (pipeline + app).
2. **Add your own metrics / Genie questions**: extend the semantic layer and Genie agent with your own governed Metric View and benchmark questions.
3. **From-scratch mode**: a convention for flipping any build stage from guided (`# TODO` + hints) to build-it-yourself, with the checkpoint unchanged.

Start at [`docs/stretch/README.md`](docs/stretch/README.md); the starters live in `notebooks/stretch/`.

## Workshop releases

Workshop releases on `main` are identified by annotated [Semantic Version](https://semver.org/) tags (see [GitHub releases](https://github.com/pablordoricaw/stryker-cr-workshop-09232026/releases)). Use these to pin to a stable workshop version in your fork or for reproducible deployments.

Here is how SemVer translates to this workshop:

- `v1.0.0`: first stable workshop release.
- `v1.1.0`: new exercises, modules, or materially expanded content.
- `v1.1.1`: corrections, clarified instructions, broken-link fixes, or other compatible workshop fixes.
- `v2.0.0`: changes that substantially alter the workshop flow or invalidate prior setup/materials.
- `v1.2.0-rc.1`: optional rehearsal/review release before a major workshop event.

## Furthering your Databricks skills

Want to keep building after the workshop? Explore the official [Databricks Training and Certification](https://www.databricks.com/learn/training/home) catalog for self-paced courses, instructor-led training, and certification paths across data engineering, analytics, and AI.
