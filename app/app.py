"""The provided workshop data app (FastAPI).

A small, complete FastAPI backend that serves two things:

  * ``GET  /api/serving`` — rows from the Lakebase-synced serving table, and
  * ``POST /api/ask``     — an answer relayed from the participant's Genie agent.

Both delegate to :mod:`backend`, where the **two participant gaps** live (the
Genie call and the Lakebase read). This file — routing, static hosting, health,
and error handling — is already complete and does **not** need editing.

Run locally:  ``uvicorn app:app --port 8000``
Deployed:     the ``app.yaml`` command runs the same under uvicorn.
"""

from __future__ import annotations

from pathlib import Path

from backend import SERVING_TABLE, Backend
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from models import AskIn, AskOut, HealthOut, ServingRow, ServingRowsOut

app = FastAPI(title="Stryker workshop data app")
backend = Backend()

_STATIC = Path(__file__).parent / "static"


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    """Liveness + wiring snapshot. Never touches Genie or Lakebase."""
    return HealthOut(**backend.health())


@app.get("/api/serving", response_model=ServingRowsOut)
def serving(limit: int = 100) -> ServingRowsOut | JSONResponse:
    """Rows from the Lakebase-synced serving table (participant gap 2)."""
    try:
        rows = backend.fetch_serving_rows(limit=limit)
    except NotImplementedError as exc:
        return JSONResponse(status_code=501, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
        return JSONResponse(status_code=502, content={"detail": str(exc)})
    return ServingRowsOut(
        table=SERVING_TABLE,
        row_count=len(rows),
        rows=[ServingRow(values=row) for row in rows],
    )


@app.post("/api/ask", response_model=AskOut)
def ask(payload: AskIn) -> AskOut | JSONResponse:
    """Relay a question to the participant's Genie agent (participant gap 1)."""
    try:
        result = backend.ask_genie(payload.question)
    except NotImplementedError as exc:
        return JSONResponse(status_code=501, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"detail": str(exc)})
    return AskOut(
        question=payload.question,
        status=str(result.get("status", "unknown")),
        answer=result.get("answer"),
        sql=result.get("sql"),
    )


@app.get("/")
def index() -> FileResponse:
    """Serve the minimal single-page UI."""
    return FileResponse(_STATIC / "index.html")


# Static assets (index.html + any css/js). Mounted last so the API routes win.
if _STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
