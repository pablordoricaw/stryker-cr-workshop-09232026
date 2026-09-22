# app/

The **provided data app** (Python / FastAPI) participants wire to their own Genie
agent and a Lakebase-synced gold table. It is deployed and started from the
Databricks Apps UI or a notebook step — no web terminal required. The driver
notebook is `notebooks/07_app.py`; the full reference is
`solutions/finance/07_app.py`.

## What it serves

| Route | Purpose |
| ----- | ------- |
| `GET /` | Minimal single-page UI (`static/index.html`) |
| `GET /api/health` | Liveness + wiring snapshot (never touches Genie/Lakebase) |
| `GET /api/serving?limit=N` | Rows from the **Lakebase-synced serving table** |
| `POST /api/ask` | An answer relayed from the participant's **Genie agent** |

## The two participant gaps

The app ships **complete except for exactly two functions** in `backend.py`,
each marked with a `PARTICIPANT GAP` banner and a `TODO`:

1. **Genie connection** — `Backend.ask_genie` calls the Genie Conversation API.
2. **Lakebase read** — `Backend.fetch_serving_rows` reads the synced serving table.

The app **starts cleanly with the gaps unfilled**: each gap raises only when its
route is called (returning HTTP 501), so you can deploy and start the app first
and fill the gaps after. `GET /` and `GET /api/health` always work.

## Layout

| File | Role |
| ---- | ---- |
| `app.py` | FastAPI routing, static hosting, health (complete — don't edit) |
| `backend.py` | Data-access layer — **contains the two gaps you fill** |
| `models.py` | Pydantic request/response models |
| `static/index.html` | Minimal UI |
| `app.yaml` | Apps runtime command + resource wiring (`valueFrom`) |
| `requirements.txt` | `databricks-sdk` + `psycopg[binary]` (not pre-installed) |

## Wiring (resources & config)

Resource ids are never hardcoded — they come from wired app resources via
`app.yaml`'s `valueFrom`, and from Lakebase's auto-injected `PG*` /
`LAKEBASE_ENDPOINT` env vars:

- **Genie space** resource → key `genie-space` (permission *Can run*) → `GENIE_SPACE_ID`
- **Lakebase database** resource → key `postgres` (*Can connect and create*) →
  `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` + `LAKEBASE_ENDPOINT`
- `SERVING_TABLE` / `SERVING_LIMIT` — point at **your** synced serving table as
  `<schema>.<table>` in Postgres. A synced table lands in a Postgres schema
  matching its Unity Catalog schema (your participant schema), so this is
  `<your_schema>.<your_served_table>`.

## Run it

- **Local dev:** `uvicorn app:app --port 8000` (health + UI work; the data routes
  need a workspace + wired resources).
- **Deploy + start:** deploy from the Apps UI or the CLI, then **start the app** —
  deploying can leave it stopped. See `notebooks/07_app.py`.

Validated through `workshop.check("07_app", ...)` like every other checkpoint —
it asserts the synced table serves the expected gold data and the app is deployed
and running.

## Per-participant naming

A whole team shares one workspace, so the **app name, the Lakebase project, and
the synced table are namespaced per participant** (identity suffix, like the #11
Genie agent). There is no shared/fixed app name.
