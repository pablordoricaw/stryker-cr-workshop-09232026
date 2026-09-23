"""Streamlit smoke tests for the provided workshop app (``app/``).

Guards the core acceptance behaviors of the shipped app:
  * it renders with BOTH participant gaps unfilled (no exception on the initial
    run; the gaps raise only when their serving/chat action is triggered);
  * a visible title is shown; and
  * triggering each gap surfaces its ``PARTICIPANT GAP`` message in the UI rather
    than crashing the app.

The app lives in ``<repo>/app/`` as a standalone app (not a package), so the
fixture puts that directory on ``sys.path`` and drives ``app.py`` through
Streamlit's headless ``AppTest`` exactly as the Apps runtime would import it.
Requires ``streamlit`` (a dev dependency); skipped if absent so the framework
test run never hard-fails on an optional dep.
"""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

APP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"
)
APP_PY = os.path.join(APP_DIR, "app.py")
_APP_MODULES = ("backend",)


@pytest.fixture
def at():
    """Build an AppTest for app/app.py with app/ importable, then run it once."""
    sys.path.insert(0, APP_DIR)
    for name in _APP_MODULES:
        sys.modules.pop(name, None)
    try:
        yield AppTest.from_file(APP_PY, default_timeout=30).run()
    finally:
        for name in _APP_MODULES:
            sys.modules.pop(name, None)
        try:
            sys.path.remove(APP_DIR)
        except ValueError:
            pass


def test_app_renders_with_gaps_unfilled(at):
    # A clean initial run means the page renders even though neither gap is
    # filled; the gaps must not raise until their action is triggered.
    assert not at.exception


def test_title_present(at):
    assert any("Workshop data app" in t.value for t in at.title)


def test_serving_gap_surfaces_message(at):
    # Clicking "Load rows" triggers GAP 2 (the Lakebase read).
    at.button[0].click().run()
    assert not at.exception
    assert any("GAP 2" in w.value for w in at.warning)


def test_ask_gap_surfaces_message(at):
    # Submitting a question triggers GAP 1 (the Genie call).
    at.chat_input[0].set_value("hi").run()
    assert not at.exception
    assert any("GAP 1" in m.value for m in at.markdown)
