# app/

The **provided data app** (Python / Streamlit) participants wire to their own
Genie agent and a Lakebase-synced gold table. It is deployed and started from the
Databricks Apps UI or a notebook step; no web terminal required. The driver
notebook is `notebooks/07_app.py`; the full reference is
`solutions/finance/07_app.py`.

## What it shows

Three tabs:

| Tab | Purpose |
| --- | ------- |
| **📊 Data app** | KPI strip, Lakebase-powered charts, and an interactive table of rows from the **Lakebase-synced serving table**, plus an **Ask Genie** chat that relays answers (and the generated SQL) from the participant's **Genie agent** |
| **🎉 Congratulations** | A recap of the end-to-end pipeline built across the workshop checkpoints (`00_setup` → `07_app`) |
| **ℹ️ About** | An overview of Databricks Apps and links to more resources |

The KPIs and charts populate once the Lakebase read gap is wired; until then the
Data app tab shows a friendly panel.

## The two participant gaps

The app ships **complete except for exactly two functions** in `backend.py`,
each marked with a `PARTICIPANT GAP` banner and a `TODO`:

1. **Genie connection**: `Backend.ask_genie` calls the Genie Conversation API.
2. **Lakebase read**: `Backend.fetch_serving_rows` reads the synced serving table.

The app **renders cleanly with the gaps unfilled**: the initial page never calls
a gap, and the serving/chat actions catch the `NotImplementedError` a gap raises
and show a friendly panel instead of crashing. So you can deploy and start the
app first and fill the gaps after.

## Layout

```
app/
├── app.py             # Streamlit UI: layout, widgets, error handling (complete; don't edit)
├── backend.py         # Data-access layer: contains the two gaps you fill
├── app.yaml           # Apps runtime command + resource wiring (valueFrom)
├── pyproject.toml     # Dependency manifest: installed with uv on Databricks Apps
├── uv.lock            # Pinned dependency lock (regenerate with: cd app && uv lock)
├── README.md          # This file
└── .streamlit/
    └── config.toml    # Theme (light + Databricks accent)
```

## Wiring (resources & config)

Resource ids are never hardcoded; they come from wired app resources via
`app.yaml`'s `valueFrom`, and from Lakebase's auto-injected `PG*` /
`LAKEBASE_ENDPOINT` env vars:

- **Genie space** resource → key `genie-space` (permission *Can run*) → `GENIE_SPACE_ID`
- **Lakebase database** resource → key `postgres` (*Can connect and create*) →
  `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` + `LAKEBASE_ENDPOINT`
- `SERVING_TABLE` / `SERVING_LIMIT`: point at **your** synced serving table as
  `<schema>.<table>` in Postgres. A synced table lands in a Postgres schema
  matching its Unity Catalog schema (your participant schema), so this is
  `<your_schema>.<your_served_table>`.

## Dependencies

Deps are installed with **uv** from `pyproject.toml` + `uv.lock`. Databricks Apps
takes the uv path only when the app directory has both files and **no**
`requirements.txt` (a `requirements.txt` always forces pip). The uv path ships
**no pre-installed libraries**, so every runtime dep, including `streamlit` and
`pandas`, is declared in `pyproject.toml`. After editing deps, regenerate the
lock with `cd app && uv lock` and commit `uv.lock`.

## Run it

- **Local dev:** `streamlit run app.py` (or `uv run streamlit run app.py` to use
  the locked env). The UI renders; the serving/chat actions need a workspace +
  wired resources, and show a friendly panel until the two gaps are filled.
- **Deploy + start:** deploy from the Apps UI or the CLI, then **start the app**:
  deploying can leave it stopped. See `notebooks/07_app.py`.

Validated through `workshop.check("07_app", ...)` like every other checkpoint;
it asserts the synced table serves the expected gold data and the app is deployed
and running. (Streamlit serves no `/api/health`, so the checkpoint's optional HTTP
health probe is off by default.)

## Per-participant naming

A whole team shares one workspace, so the **app name, the Lakebase project, and
the synced table are namespaced per participant** (identity suffix, like the #11
Genie agent). There is no shared/fixed app name.
