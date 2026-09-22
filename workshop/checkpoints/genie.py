"""The ``06_genie`` checkpoint: an observable, per-participant Genie Agent.

Ticket #11 has the participant build a curated Genie Agent (formerly a Genie
Space) over the gold tables and Metric Views produced by #8/#10. This checkpoint
proves the *deployed* agent, reading **only externally-observable Genie state**
through the Genie API — never the notebook, the creation mechanism, or any
intermediate variable. A participant can reach the same state with the Databricks
SDK, the ``databricks genie create-space`` CLI, or the Genie UI, and it passes
identically.

Three observable facts are asserted, each a distinct false-pass guard:

* **The caller's own agent exists.** A whole team shares one workspace, and a
  Genie Agent is workspace-scoped, so the agent name must carry a per-participant
  identity suffix (see #22). The check therefore takes the expected
  ``agent_name`` as a **required** input — there is deliberately no default,
  fixed, or shared name baked in — and resolves the caller's own agent by that
  exact title (or verifies a supplied ``genie_space_id`` carries it). A missing
  or ambiguous name is RED.
* **It is configured over the expected data assets.** The agent's attached data
  sources (tables *and* Metric Views) must be a superset of the expected set.
  The Finance default is the two gold tables plus the two Metric Views; a
  domain supplies its own via ``expected_sources``. Attaching none, or the wrong
  ones, is RED.
* **It answers the benchmark questions sanely.** Each benchmark question is asked
  through the Conversation API; the reply must reach a terminal *completed*
  state with generated SQL that references at least one expected source. An empty
  answer, a failure, a clarifying question, or SQL that never touches the
  curated data is RED — a hallucinated or off-topic answer cannot pass.

**Domain-generic.** No Finance-only object name is hardcoded in the logic. The
expected sources, the benchmark questions, and the tag/name inputs are all
overridable through ``workshop.check`` extras so Security (#13) and ITSM (#14)
reuse this module with their own agent, sources, and questions — no edits.

**Off-platform testable.** Like every other checkpoint, this one takes its
Databricks dependency by injection rather than importing an SDK at module load:
pass a normalized Genie client (or a raw ``WorkspaceClient``) as the ``genie``
extra. When neither is supplied it lazily constructs a ``WorkspaceClient`` on a
live workspace; unit tests inject a fake client and never touch the network.

Run it as::

    workshop.check(
        "06_genie",
        catalog=config.catalog,
        schema=config.schema,
        genie=WorkspaceClient(),           # or a normalized client / fake
        agent_name=agent_name,             # per-participant, required
        genie_space_id=space_id,           # optional fast path
    )

Extras forwarded through ``ctx.extras``:

* ``agent_name`` — the expected per-participant agent title (**required**).
* ``genie`` — a normalized Genie client, a raw ``WorkspaceClient``, or ``None``
  to build one from the ambient workspace credentials.
* ``genie_space_id`` — the agent's space id, when already known (skips the
  by-title lookup but still verifies the title matches ``agent_name``).
* ``expected_sources`` — the data assets that must be attached (default: the
  Finance gold tables and Metric Views). Local names are resolved in the
  participant schema; a dotted name is treated as an explicit fully-qualified
  reference.
* ``benchmark_questions`` — the questions to ask (default: Finance samples).
  Pass ``[]`` (or ``ask_benchmarks=False``) to assert structure only, e.g. when
  the Conversation API is unavailable.
* ``ask_benchmarks`` — set ``False`` to skip the answer phase entirely.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from workshop.context import CheckContext
from workshop.registry import checkpoint
from workshop.results import CheckResult

GENIE_CHECKPOINT_ID = "06_genie"

#: The data assets a Finance agent must curate — the #8 gold tables plus the #10
#: Metric Views. Local names resolve in the participant schema. Overridable via
#: the ``expected_sources`` extra so Security/ITSM point at their own assets.
DEFAULT_EXPECTED_SOURCES: tuple[str, ...] = (
    "gold_sales",
    "gold_contract_performance",
    "finance_sales_metrics",
    "finance_contract_metrics",
)

#: Pre-authored Finance benchmark questions. Each should drive Genie to generate
#: SQL over one of the curated sources. Overridable via ``benchmark_questions``.
DEFAULT_BENCHMARK_QUESTIONS: tuple[str, ...] = (
    "What were total net sales by product family?",
    "Which sales region had the highest gross margin?",
)

#: Terminal Conversation-API status that means Genie produced an answer.
_COMPLETED_STATUS = "completed"

_UNSET = object()


# --- normalized client interface -------------------------------------------
# The checkpoint speaks to Genie through three small, stable operations. The
# live adapter (:class:`_SdkGenieClient`) maps the SDK/REST shapes onto them;
# tests supply a fake implementing the same surface. Keeping the interface
# narrow isolates all SDK-shape fragility to the adapter.


@dataclass(frozen=True)
class GenieSpaceRef:
    """A lightweight agent reference from a listing: id and display title."""

    space_id: str
    title: str


@dataclass(frozen=True)
class GenieSpace:
    """One agent's observable configuration: id, title, and attached sources.

    ``sources`` is the flat list of fully-qualified source identifiers attached
    to the agent — both plain tables and Metric Views — exactly as Genie stores
    them, before normalization.
    """

    space_id: str
    title: str
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenieAnswer:
    """The observable outcome of asking one question through the agent."""

    status: str
    sql: str | None = None
    text: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class _ExpectedSource:
    """One expected data asset: how to show it, and how to match it."""

    display: str
    normalized: str
    segment: str


def _fail(message: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(GENIE_CHECKPOINT_ID, False, message, details)


def _normalize_reference(value: str) -> str:
    """Compare UC references independent of SQL quoting/case/whitespace.

    Mirrors ``metrics._normalize_reference`` — backticks, double quotes, and
    spaces are removed and the result lowercased; dots are preserved so
    ``catalog.schema.table`` stays comparable.
    """
    return value.replace("`", "").replace('"', "").replace(" ", "").lower()


def _expected_sources(ctx: CheckContext) -> list[_ExpectedSource]:
    """Resolve default or caller-supplied expected data assets.

    A local name (no dot) resolves in the participant schema; a dotted name is
    taken as an explicit fully-qualified reference. Raises on a malformed
    ``expected_sources`` value so the mistake surfaces as a clear failure.
    """
    raw = ctx.extras.get("expected_sources")
    if raw is None:
        names: tuple[str, ...] = DEFAULT_EXPECTED_SOURCES
    elif isinstance(raw, str):
        names = (raw,)
    elif isinstance(raw, Sequence):
        names = tuple(raw)
    else:
        raise TypeError("expected_sources must be a name or a list of names")
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("expected_sources entries must be non-empty names")

    resolved: list[_ExpectedSource] = []
    seen: set[str] = set()
    for name in names:
        display = name if "." in name else ctx.fully_qualified(name)
        normalized = _normalize_reference(display)
        if normalized in seen:
            continue
        seen.add(normalized)
        segment = normalized.rsplit(".", 1)[-1]
        resolved.append(_ExpectedSource(display, normalized, segment))
    return resolved


def _benchmark_questions(value: Any) -> tuple[str, ...]:
    """Resolve the benchmark questions from an extra.

    Unset preserves the Finance defaults. An explicit empty list disables the
    answer phase (structure-only). A non-empty list overrides the defaults.
    """
    if value is _UNSET or value is None:
        return DEFAULT_BENCHMARK_QUESTIONS
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        raise TypeError("benchmark_questions must be a question or a list of questions")
    questions = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in questions):
        raise ValueError("benchmark_questions entries must be non-empty question strings")
    return questions


def _sql_matches(sql: str, expected: list[_ExpectedSource]) -> list[str]:
    """Return the display names of expected sources the SQL references.

    A source matches if its normalized fully-qualified reference appears in the
    normalized SQL, or its object-name segment appears as a delimited token.
    Distinctive object names (``gold_sales``, ``finance_sales_metrics``) make
    the segment match reliable while the delimiter guard avoids substring
    false-positives.
    """
    normalized_sql = _normalize_reference(sql)
    matched: list[str] = []
    for source in expected:
        if source.normalized and source.normalized in normalized_sql:
            matched.append(source.display)
            continue
        segment = re.escape(source.segment)
        if source.segment and re.search(rf"(?<![a-z0-9_]){segment}(?![a-z0-9_])", normalized_sql):
            matched.append(source.display)
    return matched


# --- live client resolution -------------------------------------------------


class _SdkGenieClient:
    """Normalize the Databricks SDK / Genie REST surface onto our interface.

    Uses the SDK's typed listing/conversation calls where they are stable, and
    the raw workspace REST client for the serialized-space payload (the attached
    data sources), which the typed ``get_space`` model does not expose. Only ever
    constructed on a live workspace, so importing the SDK here is safe.
    """

    def __init__(self, workspace: Any) -> None:
        self._w = workspace

    def list_spaces(self) -> list[GenieSpaceRef]:
        refs: list[GenieSpaceRef] = []
        page_token: str | None = None
        while True:
            resp = self._w.genie.list_spaces(page_token=page_token)
            for space in getattr(resp, "spaces", None) or []:
                space_id = getattr(space, "space_id", None) or getattr(space, "id", None)
                title = getattr(space, "title", None) or getattr(space, "name", "")
                if space_id:
                    refs.append(GenieSpaceRef(str(space_id), str(title or "")))
            page_token = getattr(resp, "next_page_token", None)
            if not page_token:
                return refs

    def get_space(self, space_id: str) -> GenieSpace:
        space = self._w.genie.get_space(space_id, include_serialized_space=True)
        title = getattr(space, "title", None) or ""
        serialized = getattr(space, "serialized_space", None)
        return GenieSpace(str(space_id), str(title), _sources_from_serialized(serialized))

    def ask(self, space_id: str, question: str) -> GenieAnswer:
        message = self._w.genie.start_conversation_and_wait(space_id, question)
        status = getattr(getattr(message, "status", None), "value", None) or getattr(
            message, "status", None
        )
        sql: str | None = None
        text: str | None = None
        for attachment in getattr(message, "attachments", None) or []:
            query = getattr(attachment, "query", None)
            if query is not None and getattr(query, "query", None):
                sql = query.query
            body = getattr(attachment, "text", None)
            if body is not None and getattr(body, "content", None):
                text = body.content
        error = getattr(getattr(message, "error", None), "error", None) or getattr(
            message, "error", None
        )
        return GenieAnswer(
            status=str(status or "").lower(),
            sql=sql,
            text=text,
            error=str(error) if error else None,
        )


def _sources_from_serialized(serialized: Any) -> tuple[str, ...]:
    """Extract attached source identifiers from a ``serialized_space`` payload.

    ``serialized_space`` is a JSON string (version 2) whose ``data_sources``
    holds ``tables`` and ``metric_views`` arrays, each entry carrying an
    ``identifier``. Parsing is defensive: a missing or malformed payload yields
    no sources (RED at the superset check) rather than an exception.
    """
    if isinstance(serialized, str):
        try:
            serialized = json.loads(serialized)
        except (ValueError, TypeError):
            return ()
    if not isinstance(serialized, Mapping):
        return ()
    data_sources = serialized.get("data_sources")
    if not isinstance(data_sources, Mapping):
        return ()
    identifiers: list[str] = []
    for group in ("tables", "metric_views"):
        entries = data_sources.get(group)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, Mapping):
                identifier = entry.get("identifier")
                if isinstance(identifier, str) and identifier.strip():
                    identifiers.append(identifier)
    return tuple(identifiers)


def _resolve_client(ctx: CheckContext) -> Any:
    """Return the injected client, wrap a raw WorkspaceClient, or build one.

    A normalized client (fake or :class:`_SdkGenieClient`) is used directly; a
    raw ``WorkspaceClient`` (has ``.genie``) is wrapped; ``None`` triggers a lazy
    ``WorkspaceClient()`` build. The SDK import is deferred to here so ``import
    workshop`` never needs ``databricks-sdk`` installed.
    """
    injected = ctx.extras.get("genie")
    if injected is not None:
        if all(hasattr(injected, name) for name in ("list_spaces", "get_space", "ask")):
            return injected
        if hasattr(injected, "genie"):
            return _SdkGenieClient(injected)
        raise TypeError(
            "the 'genie' extra must be a WorkspaceClient or a normalized Genie "
            "client exposing list_spaces/get_space/ask"
        )
    # Lazy, live-only import so `import workshop` never needs databricks-sdk.
    from databricks.sdk import WorkspaceClient

    return _SdkGenieClient(WorkspaceClient())


def _locate_space(client: Any, ctx: CheckContext, agent_name: str) -> GenieSpace | CheckResult:
    """Resolve the caller's own agent, by supplied id or by exact title match."""
    space_id = ctx.extras.get("genie_space_id")
    if space_id:
        try:
            space = client.get_space(str(space_id))
        except Exception as exc:  # noqa: BLE001 - participant-facing RED state
            return _fail(
                f"Could not read Genie agent '{space_id}' ({type(exc).__name__}). "
                "Confirm the agent exists and you have access.",
                {"stage": "get_space", "space_id": str(space_id), "error_type": type(exc).__name__},
            )
        if space.title.strip() != agent_name.strip():
            return _fail(
                f"Genie agent '{space_id}' is titled {space.title!r}, not the "
                f"expected per-participant name {agent_name!r}.",
                {"stage": "identity", "space_id": space.space_id, "observed_title": space.title},
            )
        return space

    try:
        refs = client.list_spaces()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not list Genie agents ({type(exc).__name__}). Genie may be "
            "disabled or gated on this workspace, or you may lack access.",
            {"stage": "list_spaces", "error_type": type(exc).__name__},
        )
    matches = [ref for ref in refs if ref.title.strip() == agent_name.strip()]
    if not matches:
        return _fail(
            f"No Genie agent named {agent_name!r} exists. Create your "
            "per-participant agent before running this checkpoint.",
            {"stage": "identity", "expected_title": agent_name, "space_count": len(refs)},
        )
    if len(matches) > 1:
        return _fail(
            f"Found {len(matches)} Genie agents named {agent_name!r}; the "
            "per-participant name must be unique. Remove the duplicates.",
            {"stage": "identity", "expected_title": agent_name, "matches": len(matches)},
        )
    try:
        return client.get_space(matches[0].space_id)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"Could not read Genie agent {matches[0].space_id!r} "
            f"({type(exc).__name__}).",
            {"stage": "get_space", "space_id": matches[0].space_id, "error_type": type(exc).__name__},
        )


@checkpoint(
    GENIE_CHECKPOINT_ID,
    summary=(
        "The caller's per-participant Genie Agent exists, is configured over the "
        "expected gold tables and Metric Views, and answers the benchmark "
        "questions with SQL that references the curated data."
    ),
)
def check_genie(ctx: CheckContext) -> CheckResult:
    """Validate the deployed Genie Agent using only observable Genie state."""
    if not ctx.catalog or not ctx.schema:
        return _fail(
            "No catalog/schema to check. Call workshop.check('06_genie', "
            "catalog=config.catalog, schema=config.schema, genie=..., "
            "agent_name=...).",
            {"catalog": ctx.catalog, "schema": ctx.schema},
        )

    agent_name = ctx.extras.get("agent_name")
    if not isinstance(agent_name, str) or not agent_name.strip():
        return _fail(
            "No agent_name given. A Genie Agent is workspace-scoped and shared "
            "across a team, so pass your per-participant agent name: "
            "workshop.check('06_genie', ..., agent_name=your_agent_name).",
            {"stage": "configuration", "reason": "missing_agent_name"},
        )

    try:
        expected = _expected_sources(ctx)
        questions = _benchmark_questions(ctx.extras.get("benchmark_questions", _UNSET))
    except (TypeError, ValueError) as exc:
        return _fail(
            f"Invalid Genie checkpoint configuration: {exc}.",
            {"stage": "configuration", "error_type": type(exc).__name__},
        )
    ask_benchmarks = ctx.extras.get("ask_benchmarks", True)
    if not ask_benchmarks:
        questions = ()

    try:
        client = _resolve_client(ctx)
    except Exception as exc:  # noqa: BLE001 - participant-facing RED state
        return _fail(
            "This checkpoint needs Genie access. Pass a WorkspaceClient (or a "
            "normalized Genie client) as genie=..., or run it where a "
            f"WorkspaceClient can be built ({type(exc).__name__}: {exc}).",
            {"stage": "client", "error_type": type(exc).__name__},
        )

    located = _locate_space(client, ctx, agent_name)
    if isinstance(located, CheckResult):
        return located
    space = located

    observed = {_normalize_reference(source) for source in space.sources}
    missing = [source.display for source in expected if source.normalized not in observed]
    if missing:
        return _fail(
            f"Genie agent {agent_name!r} is not configured over all expected "
            f"data assets; missing: {', '.join(missing)}. Attach the gold tables "
            "and Metric Views.",
            {
                "stage": "sources",
                "space_id": space.space_id,
                "expected": [source.display for source in expected],
                "observed": list(space.sources),
                "missing": missing,
            },
        )

    asked: list[dict[str, Any]] = []
    for question in questions:
        try:
            answer = client.ask(space.space_id, question)
        except Exception as exc:  # noqa: BLE001
            return _fail(
                f"Genie agent {agent_name!r} could not answer {question!r} "
                f"({type(exc).__name__}). The Conversation API may be gated; if "
                "so, re-run with ask_benchmarks=False to check structure only.",
                {"stage": "ask", "space_id": space.space_id, "question": question,
                 "error_type": type(exc).__name__},
            )
        if answer.status != _COMPLETED_STATUS:
            return _fail(
                f"Genie agent {agent_name!r} did not complete an answer to "
                f"{question!r} (status {answer.status!r}).",
                {"stage": "answer", "space_id": space.space_id, "question": question,
                 "status": answer.status, "error": answer.error},
            )
        if not answer.sql or not answer.sql.strip():
            return _fail(
                f"Genie agent {agent_name!r} answered {question!r} without "
                "generating any SQL, so the answer cannot be trusted as grounded "
                "in the curated data.",
                {"stage": "answer", "space_id": space.space_id, "question": question,
                 "text": answer.text},
            )
        referenced = _sql_matches(answer.sql, expected)
        if not referenced:
            return _fail(
                f"Genie agent {agent_name!r} answered {question!r} with SQL that "
                "does not reference any expected data asset — likely an off-topic "
                "or hallucinated answer.",
                {"stage": "answer", "space_id": space.space_id, "question": question,
                 "sql": answer.sql},
            )
        asked.append({"question": question, "referenced": referenced})

    return CheckResult(
        GENIE_CHECKPOINT_ID,
        True,
        f"Genie agent {agent_name!r} is configured over "
        f"{len(expected)} expected data asset(s)"
        + (
            f" and answered {len(asked)} benchmark question(s) with grounded SQL."
            if asked
            else " (benchmark answers not checked)."
        ),
        {
            "stage": "done",
            "space_id": space.space_id,
            "agent_name": agent_name,
            "expected_sources": [source.display for source in expected],
            "attached_sources": list(space.sources),
            "questions_asked": asked,
        },
    )
