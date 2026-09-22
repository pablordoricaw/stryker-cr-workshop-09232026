"""FastAPI smoke tests for the provided workshop app (``app/``).

Guards the core acceptance behaviors of the shipped app:
  * it imports and starts with BOTH participant gaps unfilled (no exception at
    import/startup — the gaps raise only when their route is hit);
  * ``GET /`` and ``GET /api/health`` work regardless of the gaps; and
  * the two gap routes return HTTP 501 only when called, and request bodies are
    validated (422).

The app lives in ``<repo>/app/`` as a standalone app (not a package), so the
fixture puts that directory on ``sys.path`` and imports it exactly as the Apps
runtime would. Requires ``fastapi`` + ``httpx`` (dev dependencies); skipped if
absent so the framework test run never hard-fails on an optional dep.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

APP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"
)
_APP_MODULES = ("app", "backend", "models")


@pytest.fixture
def client():
    """Import the app fresh from app/ and yield a TestClient (startup runs here)."""
    sys.path.insert(0, APP_DIR)
    for name in _APP_MODULES:
        sys.modules.pop(name, None)
    try:
        appmod = importlib.import_module("app")
        with TestClient(appmod.app) as test_client:
            yield test_client
    finally:
        for name in _APP_MODULES:
            sys.modules.pop(name, None)
        try:
            sys.path.remove(APP_DIR)
        except ValueError:
            pass


def test_app_imports_and_starts_with_gaps_unfilled(client):
    # Reaching here means import + startup succeeded even though neither gap is
    # filled — the gaps must not raise at import/startup.
    assert client is not None


def test_index_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<html" in resp.content.lower()


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # No resources wired in the test env, so both are reported unconfigured.
    assert body["genie_configured"] is False
    assert body["lakebase_configured"] is False


def test_serving_gap_returns_501_when_hit(client):
    resp = client.get("/api/serving")
    assert resp.status_code == 501
    assert "GAP 2" in resp.json()["detail"]


def test_ask_gap_returns_501_when_hit(client):
    resp = client.post("/api/ask", json={"question": "hi"})
    assert resp.status_code == 501
    assert "GAP 1" in resp.json()["detail"]


def test_ask_request_validation_422(client):
    resp = client.post("/api/ask", json={})
    assert resp.status_code == 422


def test_openapi_available(client):
    assert client.get("/openapi.json").status_code == 200
