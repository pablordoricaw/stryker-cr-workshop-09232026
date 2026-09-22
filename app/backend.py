"""Data-access layer for the provided workshop app — WITH THE TWO PARTICIPANT GAPS.

This module ships **complete except for exactly two functions** each participant
fills in:

  * GAP 1 of 2 — :meth:`Backend.ask_genie`   (the Genie Conversation API call)
  * GAP 2 of 2 — :meth:`Backend.fetch_serving_rows`  (the Lakebase read)

Everything around them — configuration, connection setup, health reporting, and
error handling — is already written. Find each ``PARTICIPANT GAP`` banner below,
replace the ``raise NotImplementedError(...)`` with the few lines it describes,
then redeploy. The reference implementation is in
``solutions/finance/07_app.py``.

Design notes:
  * Authentication uses the Databricks SDK ``Config`` / ``WorkspaceClient`` — never
    hardcoded tokens (they are auto-injected for a deployed app).
  * Resource ids come from environment variables wired via ``app.yaml``'s
    ``valueFrom`` (Genie space) and Lakebase's auto-injected ``PG*`` /
    ``LAKEBASE_ENDPOINT`` vars — never hardcoded.
  * The app **starts cleanly even with the gaps unfilled**: the gaps raise only
    when their route is called, so the app can be deployed and started (and the
    ``07_app`` checkpoint's app-side can pass) before the gaps are filled.
"""

from __future__ import annotations

import os

# The Genie space id is injected from the app's `genie-space` resource (app.yaml).
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")

# The Lakebase-synced serving table, as <schema>.<table> in Postgres. A synced
# table lands in a Postgres schema matching its Unity Catalog schema (your
# participant schema), so this is `<your_schema>.<your_served_table>`. Each
# participant sets SERVING_TABLE via the app's env (see notebooks/07_app.py); the
# default below is only a placeholder for local/dev runs.
SERVING_TABLE = os.getenv("SERVING_TABLE", "finance.gold_contract_performance_served")

# Max rows the serving screen reads.
SERVING_LIMIT = int(os.getenv("SERVING_LIMIT", "100"))


def _lakebase_configured() -> bool:
    """True when Lakebase connection env is present (resource wired)."""
    return bool(os.getenv("PGHOST"))


def _genie_configured() -> bool:
    """True when a Genie space id is present (resource wired)."""
    return bool(GENIE_SPACE_ID)


class Backend:
    """The app's data access layer. Two methods are participant gaps."""

    def __init__(self) -> None:
        # Lazy — the SDK client is only built when a data route is called, so the
        # app process starts even if the SDK/creds are not yet available.
        self._workspace = None

    # -- shared helpers (already written) -----------------------------------

    def _ws(self):
        """Return a cached ``WorkspaceClient`` (auto-detects injected creds)."""
        if self._workspace is None:
            from databricks.sdk import WorkspaceClient

            self._workspace = WorkspaceClient()
        return self._workspace

    def _lakebase_connection(self):
        """Open a Lakebase (Postgres) connection using the injected app identity.

        Prefers the auto-injected ``PGPASSWORD``; otherwise mints a short-lived
        OAuth credential from the injected ``LAKEBASE_ENDPOINT``. This helper is
        already written — GAP 2 only has to *use* it to run a query.
        """
        import psycopg

        host = os.environ["PGHOST"]
        database = os.getenv("PGDATABASE", "databricks_postgres")
        user = os.environ["PGUSER"]
        port = int(os.getenv("PGPORT", "5432"))
        password = os.getenv("PGPASSWORD")
        if not password:
            endpoint = os.environ["LAKEBASE_ENDPOINT"]
            password = self._ws().postgres.generate_database_credential(
                endpoint=endpoint
            ).token
        return psycopg.connect(
            host=host, dbname=database, user=user, password=password,
            port=port, sslmode="require",
        )

    def health(self) -> dict:
        return {
            "status": "ok",
            "genie_configured": _genie_configured(),
            "lakebase_configured": _lakebase_configured(),
        }

    # =======================================================================
    # PARTICIPANT GAP 1 of 2 — Genie Conversation API connection
    # -----------------------------------------------------------------------
    # Relay `question` to the participant's Genie agent (space id GENIE_SPACE_ID)
    # through the Conversation API and return (status, answer_text, sql).
    #
    # TODO(participant): replace the raise below with, roughly:
    #   msg = self._ws().genie.start_conversation_and_wait(GENIE_SPACE_ID, question)
    #   status = getattr(getattr(msg, "status", None), "value", None) or str(msg.status)
    #   answer_text, sql = None, None
    #   for a in (msg.attachments or []):
    #       if getattr(a, "query", None):  sql = a.query.query
    #       if getattr(a, "text", None):   answer_text = a.text.content
    #   return {"status": str(status).lower(), "answer": answer_text, "sql": sql}
    #
    # See solutions/finance/07_app.py for the complete implementation.
    # =======================================================================
    def ask_genie(self, question: str) -> dict:
        raise NotImplementedError(
            "PARTICIPANT GAP 1 of 2: wire this to the Genie Conversation API. "
            "See the TODO in app/backend.py."
        )

    # =======================================================================
    # PARTICIPANT GAP 2 of 2 — Lakebase read
    # -----------------------------------------------------------------------
    # Read up to `limit` rows from the Lakebase-synced serving table
    # (SERVING_TABLE) and return them as a list of dicts. Use the already-written
    # `self._lakebase_connection()` helper.
    #
    # TODO(participant): replace the raise below with, roughly:
    #   schema, table = SERVING_TABLE.split(".", 1)
    #   with self._lakebase_connection() as conn, conn.cursor() as cur:
    #       cur.execute(f'SELECT * FROM "{schema}"."{table}" LIMIT %s', (limit,))
    #       cols = [c.name for c in cur.description]
    #       return [dict(zip(cols, row)) for row in cur.fetchall()]
    #
    # See solutions/finance/07_app.py for the complete implementation.
    # =======================================================================
    def fetch_serving_rows(self, limit: int = SERVING_LIMIT) -> list[dict]:
        raise NotImplementedError(
            "PARTICIPANT GAP 2 of 2: read the Lakebase synced serving table. "
            "See the TODO in app/backend.py."
        )
