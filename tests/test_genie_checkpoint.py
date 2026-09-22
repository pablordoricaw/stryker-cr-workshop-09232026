"""Behavioral tests for the observable-state ``06_genie`` checkpoint.

Every test drives the real ``workshop.check`` seam with an injected fake Genie
client, so no Databricks SDK, notebook, or network is needed. The fake serves
only observable Genie state (agents, their attached sources, and answers), which
is exactly what the checkpoint is allowed to assert on.
"""

from __future__ import annotations

import workshop
from workshop.checkpoints.genie import (
    DEFAULT_BENCHMARK_QUESTIONS,
    DEFAULT_EXPECTED_SOURCES,
    GENIE_CHECKPOINT_ID,
    GenieAnswer,
    GenieSpace,
    GenieSpaceRef,
)

CATALOG = "team-catalog"
SCHEMA = "finance data"  # a space in the schema name exercises quoting
AGENT = "workshop_genie_finance_ada_lovelace"


def _fqn(name: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{name}"


def _default_sources() -> list[str]:
    return [_fqn(name) for name in DEFAULT_EXPECTED_SOURCES]


def _grounded_sql(name: str = "gold_sales") -> str:
    return f"SELECT product_family, SUM(net_sales) FROM `{CATALOG}`.`{SCHEMA}`.`{name}` GROUP BY 1"


class FakeGenie:
    """Serve Genie agents, their attached sources, and canned answers."""

    def __init__(
        self,
        *,
        spaces: dict[str, dict] | None = None,
        answers: dict[str, GenieAnswer] | None = None,
        raise_on: str | None = None,
    ) -> None:
        # space_id -> {"title": str, "sources": list[str]}
        self.spaces = spaces if spaces is not None else {
            "sp-1": {"title": AGENT, "sources": _default_sources()}
        }
        self.answers = answers or {}
        self.raise_on = raise_on
        self.asked: list[str] = []

    def list_spaces(self) -> list[GenieSpaceRef]:
        if self.raise_on == "list_spaces":
            raise RuntimeError("PERMISSION_DENIED listing spaces")
        return [GenieSpaceRef(sid, meta["title"]) for sid, meta in self.spaces.items()]

    def get_space(self, space_id: str) -> GenieSpace:
        if self.raise_on == "get_space":
            raise RuntimeError("RESOURCE_DOES_NOT_EXIST")
        meta = self.spaces[space_id]
        return GenieSpace(space_id, meta["title"], tuple(meta.get("sources", ())))

    def ask(self, space_id: str, question: str) -> GenieAnswer:
        if self.raise_on == "ask":
            raise RuntimeError("Conversation API not enabled")
        self.asked.append(question)
        return self.answers.get(
            question, GenieAnswer(status="completed", sql=_grounded_sql(), text="ok")
        )


def _check(genie, **kwargs):
    kwargs.setdefault("agent_name", AGENT)
    return workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, genie=genie, **kwargs
    )


# --- registration / wiring --------------------------------------------------


def test_registered():
    assert GENIE_CHECKPOINT_ID in workshop.registry


def test_requires_catalog_and_schema():
    result = workshop.check(GENIE_CHECKPOINT_ID, genie=FakeGenie(), agent_name=AGENT)
    assert result.passed is False
    assert "No catalog/schema" in result.message


def test_requires_agent_name():
    # No fixed/shared default name: the per-participant name must be supplied.
    result = workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, genie=FakeGenie()
    )
    assert result.passed is False
    assert result.details["reason"] == "missing_agent_name"


def test_blank_agent_name_is_red():
    result = _check(FakeGenie(), agent_name="   ")
    assert result.passed is False
    assert result.details["reason"] == "missing_agent_name"


def test_requires_a_workspace_when_no_client_injected():
    # With no genie client and no SDK available off-platform, the lazy build
    # fails and surfaces as a clean RED rather than a traceback.
    result = workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, agent_name=AGENT
    )
    assert result.passed is False
    assert result.details["stage"] == "client"


def test_rejects_unusable_genie_extra():
    result = _check(object())
    assert result.passed is False
    assert result.details["stage"] == "client"


# --- happy path -------------------------------------------------------------


def test_green_when_agent_exists_configured_and_answers():
    genie = FakeGenie()
    result = _check(genie)
    assert result.passed is True
    assert result.details["stage"] == "done"
    assert result.details["space_id"] == "sp-1"
    assert len(result.details["questions_asked"]) == len(DEFAULT_BENCHMARK_QUESTIONS)
    assert genie.asked == list(DEFAULT_BENCHMARK_QUESTIONS)


def test_green_via_explicit_space_id_skips_listing():
    genie = FakeGenie(raise_on="list_spaces")  # listing would fail if used
    result = _check(genie, genie_space_id="sp-1")
    assert result.passed is True
    assert result.details["space_id"] == "sp-1"


def test_green_structure_only_when_benchmarks_disabled():
    genie = FakeGenie(raise_on="ask")  # asking would fail if attempted
    result = _check(genie, ask_benchmarks=False)
    assert result.passed is True
    assert result.details["questions_asked"] == []
    assert genie.asked == []


def test_custom_domain_sources_and_questions():
    sources = [_fqn("gold_incidents"), _fqn("itsm_incident_metrics")]
    genie = FakeGenie(
        spaces={"sp-9": {"title": AGENT, "sources": sources}},
        answers={
            "How many incidents by team?": GenieAnswer(
                status="completed", sql=_grounded_sql("itsm_incident_metrics")
            )
        },
    )
    result = _check(
        genie,
        expected_sources=["gold_incidents", "itsm_incident_metrics"],
        benchmark_questions=["How many incidents by team?"],
    )
    assert result.passed is True
    assert result.details["questions_asked"][0]["referenced"]


# --- identity guards --------------------------------------------------------


def test_missing_agent_is_red():
    genie = FakeGenie(spaces={"sp-x": {"title": "someone_elses_agent", "sources": _default_sources()}})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "identity"
    assert result.details["expected_title"] == AGENT


def test_duplicate_agent_name_is_red():
    genie = FakeGenie(
        spaces={
            "sp-1": {"title": AGENT, "sources": _default_sources()},
            "sp-2": {"title": AGENT, "sources": _default_sources()},
        }
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "identity"
    assert result.details["matches"] == 2


def test_space_id_with_wrong_title_is_red():
    # A supplied space id that is not the caller's namespaced agent fails.
    genie = FakeGenie(spaces={"sp-1": {"title": "shared_default", "sources": _default_sources()}})
    result = _check(genie, genie_space_id="sp-1")
    assert result.passed is False
    assert result.details["stage"] == "identity"
    assert result.details["observed_title"] == "shared_default"


# --- source-configuration guards --------------------------------------------


def test_no_attached_sources_is_red():
    genie = FakeGenie(spaces={"sp-1": {"title": AGENT, "sources": []}})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "sources"
    assert sorted(result.details["missing"]) == sorted(result.details["expected"])


def test_partial_sources_is_red():
    # Missing the Metric Views: the acceptance is gold *and* metrics.
    genie = FakeGenie(
        spaces={"sp-1": {"title": AGENT, "sources": [_fqn("gold_sales"), _fqn("gold_contract_performance")]}}
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "sources"
    missing = " | ".join(result.details["missing"])
    assert "finance_sales_metrics" in missing
    assert "finance_contract_metrics" in missing


def test_extra_sources_still_pass_and_quoting_is_ignored():
    # A superset is fine, and attached identifiers may be quoted/spaced.
    attached = [f"`{CATALOG}`.`{SCHEMA}`.`{n}`" for n in DEFAULT_EXPECTED_SOURCES]
    attached.append(_fqn("bronze_sales_transactions"))
    genie = FakeGenie(spaces={"sp-1": {"title": AGENT, "sources": attached}})
    result = _check(genie)
    assert result.passed is True


# --- answer-sanity guards ---------------------------------------------------


def test_failed_answer_is_red():
    genie = FakeGenie(
        answers={
            DEFAULT_BENCHMARK_QUESTIONS[0]: GenieAnswer(status="failed", error="SQL_EXECUTION_EXCEPTION")
        }
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"
    assert result.details["status"] == "failed"


def test_answer_without_sql_is_red():
    # A clarifying-question / text-only reply is not a grounded answer.
    genie = FakeGenie(
        answers={
            DEFAULT_BENCHMARK_QUESTIONS[0]: GenieAnswer(
                status="completed", sql=None, text="Which fiscal year did you mean?"
            )
        }
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"
    assert "without" in result.message


def test_answer_with_off_topic_sql_is_red():
    # Completed with SQL, but the SQL never touches a curated source.
    genie = FakeGenie(
        answers={
            DEFAULT_BENCHMARK_QUESTIONS[0]: GenieAnswer(
                status="completed", sql="SELECT * FROM some_other_catalog.public.weather"
            )
        }
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"
    assert "does not reference" in result.message


def test_ask_api_gated_is_red_with_guidance():
    genie = FakeGenie(raise_on="ask")
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "ask"
    assert "ask_benchmarks=False" in result.message


# --- configuration guards ---------------------------------------------------


def test_invalid_expected_sources_is_red():
    result = _check(FakeGenie(), expected_sources=[""])
    assert result.passed is False
    assert result.details["stage"] == "configuration"


def test_invalid_benchmark_questions_is_red():
    result = _check(FakeGenie(), benchmark_questions=[123])
    assert result.passed is False
    assert result.details["stage"] == "configuration"


def test_list_spaces_permission_error_is_red():
    genie = FakeGenie(raise_on="list_spaces")
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "list_spaces"
