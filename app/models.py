"""Pydantic models for the provided workshop data app.

Domain-neutral shapes: the app serves rows from a Lakebase-synced *serving
table* and relays answers from a Genie agent. Nothing here is Finance-specific,
so the Security (#13) and ITSM (#14) slices reuse the same app unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    """Liveness + configuration snapshot returned by ``/api/health``.

    ``genie_configured`` / ``lakebase_configured`` report only whether the app's
    environment is wired (a Genie space id and Lakebase connection are present) —
    not whether the participant has filled the two code gaps. This is enough for
    the ``07_app`` checkpoint's best-effort health probe.
    """

    status: str = "ok"
    genie_configured: bool = False
    lakebase_configured: bool = False


class ServingRow(BaseModel):
    """One row from the Lakebase-synced serving table, as generic key/values."""

    values: dict[str, object] = Field(default_factory=dict)


class ServingRowsOut(BaseModel):
    """The rows the app reads from its Lakebase synced serving table."""

    table: str
    row_count: int
    rows: list[ServingRow] = Field(default_factory=list)


class AskIn(BaseModel):
    """A natural-language question to relay to the participant's Genie agent."""

    question: str = Field(..., min_length=1)


class AskOut(BaseModel):
    """The observable outcome of asking the Genie agent one question."""

    question: str
    status: str
    answer: str | None = None
    sql: str | None = None
