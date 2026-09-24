"""Behavioral tests for the observable-state ``06_genie`` checkpoint.

Every test drives the real ``workshop.check`` seam with an injected fake Genie
client, so no Databricks SDK, notebook, or network is needed. The fake serves
only observable Genie state (agents, their owning workspace path, attached
sources, and answers), which is exactly what the checkpoint is allowed to
assert on.
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
OWNER = "/Workspace/Users/ada@example.com"
OTHER_OWNER = "/Workspace/Users/grace@example.com"
Q0 = DEFAULT_BENCHMARK_QUESTIONS[0]


def _fqn(name: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{name}"


def _default_sources() -> list[str]:
    return [_fqn(name) for name in DEFAULT_EXPECTED_SOURCES]


def _bfqn(name: str) -> str:
    return f"`{CATALOG}`.`{SCHEMA}`.`{name}`"


def _grounded_sql(name: str = "gold_sales") -> str:
    return f"SELECT product_family, SUM(net_sales) FROM {_bfqn(name)} GROUP BY 1"


def _answer(sql: str | None, status: str = "completed", text: str | None = None) -> GenieAnswer:
    return GenieAnswer(status=status, sql=sql, text=text)


def _own_space(title=AGENT, sources=None, parent=None):
    return {
        "title": title,
        "sources": _default_sources() if sources is None else sources,
        "parent_path": f"{OWNER}/genie_spaces" if parent is None else parent,
    }


class FakeGenie:
    """Serve Genie agents, their owning path, attached sources, and answers."""

    def __init__(
        self,
        *,
        spaces: dict[str, dict] | None = None,
        answers: dict[str, GenieAnswer] | None = None,
        raise_on: str | None = None,
    ) -> None:
        # space_id -> {"title": str, "sources": list[str], "parent_path": str}
        self.spaces = spaces if spaces is not None else {"sp-1": _own_space()}
        self.answers = answers or {}
        self.raise_on = raise_on
        self.asked: list[str] = []

    def list_spaces(self) -> list[GenieSpaceRef]:
        if self.raise_on == "list_spaces":
            raise RuntimeError("PERMISSION_DENIED listing spaces")
        return [
            GenieSpaceRef(sid, m["title"], m.get("parent_path"))
            for sid, m in self.spaces.items()
        ]

    def get_space(self, space_id: str) -> GenieSpace:
        if self.raise_on == "get_space":
            raise RuntimeError("RESOURCE_DOES_NOT_EXIST")
        m = self.spaces[space_id]
        return GenieSpace(space_id, m["title"], m.get("parent_path"), tuple(m.get("sources", ())))

    def ask(self, space_id: str, question: str) -> GenieAnswer:
        if self.raise_on == "ask":
            raise RuntimeError("Conversation API not enabled")
        self.asked.append(question)
        return self.answers.get(question, _answer(_grounded_sql()))


def _check(genie, **kwargs):
    kwargs.setdefault("agent_name", AGENT)
    kwargs.setdefault("owner_path", OWNER)
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


def test_custom_domain_sources_and_questions():
    sources = [_fqn("gold_incidents"), _fqn("itsm_incident_metrics")]
    genie = FakeGenie(
        spaces={"sp-9": _own_space(sources=sources)},
        answers={"How many incidents by team?": _answer(_grounded_sql("itsm_incident_metrics"))},
    )
    result = _check(
        genie,
        expected_sources=["gold_incidents", "itsm_incident_metrics"],
        benchmark_questions=["How many incidents by team?"],
    )
    assert result.passed is True
    assert result.details["questions_asked"][0]["referenced"]


# --- BLOCKING 1: benchmarks are required to pass ----------------------------


def test_disabled_benchmarks_is_red():
    # ask_benchmarks=False must NOT be a structure-only green pass.
    genie = FakeGenie()
    result = _check(genie, ask_benchmarks=False)
    assert result.passed is False
    assert result.details["stage"] == "benchmarks"
    assert genie.asked == []


def test_empty_benchmark_questions_is_red():
    result = _check(FakeGenie(), benchmark_questions=[])
    assert result.passed is False
    assert result.details["stage"] == "benchmarks"


# --- identity guards --------------------------------------------------------


def test_missing_agent_is_red():
    genie = FakeGenie(spaces={"sp-x": _own_space(title="someone_elses_agent")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "identity"
    assert result.details["expected_title"] == AGENT


def test_duplicate_owned_agent_name_is_red():
    genie = FakeGenie(spaces={"sp-1": _own_space(), "sp-2": _own_space()})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "identity"
    assert result.details["matches"] == 2


def test_space_id_with_wrong_title_is_red():
    genie = FakeGenie(spaces={"sp-1": _own_space(title="shared_default")})
    result = _check(genie, genie_space_id="sp-1")
    assert result.passed is False
    assert result.details["stage"] == "identity"
    assert result.details["observed_title"] == "shared_default"


# --- BLOCKING 3: enforce the caller's OWN namespaced agent ------------------


def test_same_title_owned_by_other_is_not_adopted():
    # A same-title agent living under another participant's path is not "yours".
    genie = FakeGenie(
        spaces={"sp-other": _own_space(parent=f"{OTHER_OWNER}/genie_spaces")}
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "ownership"


def test_explicit_id_cross_owner_is_red():
    genie = FakeGenie(
        spaces={"sp-other": _own_space(parent=f"{OTHER_OWNER}/genie_spaces")}
    )
    result = _check(genie, genie_space_id="sp-other")
    assert result.passed is False
    assert result.details["stage"] == "ownership"
    assert result.details["owner_path"] == OWNER


def test_own_agent_is_selected_over_a_same_title_other():
    # Two same-title agents; only the one under the caller's path is graded.
    genie = FakeGenie(
        spaces={
            "sp-other": _own_space(parent=f"{OTHER_OWNER}/genie_spaces"),
            "sp-mine": _own_space(parent=f"{OWNER}/genie_spaces"),
        }
    )
    result = _check(genie)
    assert result.passed is True
    assert result.details["space_id"] == "sp-mine"


def test_owner_path_matches_across_workspace_prefix():
    # Genie returns parent_path without the /Workspace prefix; owner_path may
    # carry it. Ownership must still match (regression from live validation).
    genie = FakeGenie(
        spaces={"sp-1": _own_space(parent="/Users/ada@example.com/genie_spaces")}
    )
    result = _check(genie, owner_path="/Workspace/Users/ada@example.com")
    assert result.passed is True


def test_shared_default_name_matching_another_agent_is_not_own():
    # A shared/default name that only matches another owner's agent → RED.
    genie = FakeGenie(
        spaces={"sp-shared": _own_space(title="shared_default", parent=f"{OTHER_OWNER}/x")}
    )
    result = _check(genie, agent_name="shared_default")
    assert result.passed is False
    assert result.details["stage"] == "ownership"


# --- source-configuration guards --------------------------------------------


def test_no_attached_sources_is_red():
    genie = FakeGenie(spaces={"sp-1": _own_space(sources=[])})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "sources"
    assert sorted(result.details["missing"]) == sorted(result.details["expected"])


def test_partial_sources_is_red():
    # Missing the Metric Views: the acceptance is gold *and* metrics.
    genie = FakeGenie(
        spaces={"sp-1": _own_space(sources=[_fqn("gold_sales"), _fqn("gold_contract_performance")])}
    )
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "sources"
    missing = " | ".join(result.details["missing"])
    assert "finance_sales_metrics" in missing
    assert "finance_contract_metrics" in missing


def test_source_superset_passes_despite_case_quotes_and_spaces():
    # Attached identifiers may differ only by case, backticks, or spacing.
    attached = [
        f"`{CATALOG}`.`{SCHEMA}`.`GOLD_SALES`",
        f"{CATALOG} . {SCHEMA} . Gold_Contract_Performance",
        f'"{CATALOG}"."{SCHEMA}"."finance_sales_metrics"',
        _fqn("finance_contract_metrics"),
        _fqn("bronze_sales_transactions"),  # a harmless extra
    ]
    genie = FakeGenie(spaces={"sp-1": _own_space(sources=attached)})
    result = _check(genie)
    assert result.passed is True


# --- BLOCKING 2: grounded SQL must be a real relation reference -------------


def test_answer_without_sql_is_red():
    genie = FakeGenie(answers={Q0: _answer(None, text="Which fiscal year did you mean?")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"
    assert "without" in result.message


def test_failed_answer_is_red():
    genie = FakeGenie(answers={Q0: GenieAnswer(status="failed", error="SQL_EXECUTION_EXCEPTION")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"
    assert result.details["status"] == "failed"


def test_answer_with_unrelated_from_is_red():
    genie = FakeGenie(answers={Q0: _answer("SELECT * FROM some_other_catalog.public.weather")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"
    assert "does not reference" in result.message


def test_source_name_only_in_string_literal_is_red():
    genie = FakeGenie(answers={Q0: _answer("SELECT 'gold_sales' AS label FROM other_cat.pub.weather")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"


def test_source_name_only_in_comment_is_red():
    genie = FakeGenie(answers={Q0: _answer("SELECT 1 /* gold_sales */ FROM other_cat.pub.weather -- gold_sales")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"


def test_source_name_only_as_column_alias_is_red():
    genie = FakeGenie(answers={Q0: _answer("SELECT count(*) AS gold_sales FROM other_cat.pub.weather")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"


def test_source_name_only_as_cte_name_is_red():
    genie = FakeGenie(answers={Q0: _answer("WITH gold_sales AS (SELECT 1 AS x) SELECT * FROM gold_sales")})
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "answer"


def test_cte_body_selecting_from_curated_source_is_green():
    sql = f"WITH t AS (SELECT SUM(net_sales) AS ns FROM {_bfqn('gold_sales')}) SELECT * FROM t"
    genie = FakeGenie(answers={q: _answer(sql) for q in DEFAULT_BENCHMARK_QUESTIONS})
    result = _check(genie)
    assert result.passed is True


def test_join_reference_to_curated_source_is_green():
    sql = f"SELECT * FROM other_cat.pub.dim d JOIN {_bfqn('finance_sales_metrics')} m ON d.k = m.k"
    genie = FakeGenie(answers={q: _answer(sql) for q in DEFAULT_BENCHMARK_QUESTIONS})
    result = _check(genie)
    assert result.passed is True


def test_ask_api_gated_is_red():
    genie = FakeGenie(raise_on="ask")
    result = _check(genie)
    assert result.passed is False
    assert result.details["stage"] == "ask"


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


# --- namespace resolution (#22): the check resolves the caller's own name ---


def _ns_space(ns, sources=None):
    return {
        "title": ns.genie_agent_name(),
        "sources": _default_sources() if sources is None else sources,
        "parent_path": f"{ns.owner_path()}/genie_spaces",
    }


def test_resolves_agent_and_owner_path_from_namespace():
    # No explicit agent_name/owner_path: both are derived from the namespace, so
    # the check resolves the SAME identity-derived name the notebook created.
    ns = workshop.namespace("ada@a.com", domain="finance")
    genie = FakeGenie(spaces={"sp-ns": _ns_space(ns)})
    result = workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, genie=genie, namespace=ns
    )
    assert result.passed is True
    assert result.details["agent_name"] == ns.genie_agent_name()


def test_namespace_resolves_callers_own_name_not_a_fixed_one():
    # Two participants sharing the workspace derive distinct agent names, and each
    # check resolves ITS caller's name, so B's check does not adopt A's agent.
    ns_a = workshop.namespace("ada@a.com", domain="finance")
    ns_b = workshop.namespace("grace@b.com", domain="finance")
    assert ns_a.genie_agent_name() != ns_b.genie_agent_name()
    genie = FakeGenie(spaces={"sp-a": _ns_space(ns_a)})  # only A's agent exists
    result_a = workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, genie=genie, namespace=ns_a
    )
    result_b = workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, genie=genie, namespace=ns_b
    )
    assert result_a.passed is True
    assert result_b.passed is False  # resolves B's own name; B's agent is absent
    assert result_b.details["expected_title"] == ns_b.genie_agent_name()


def test_namespace_owner_path_rejects_teammates_same_title():
    # A same-title agent living under a teammate's path is not adopted, because
    # the namespace supplies the caller's own owner_path.
    ns = workshop.namespace("ada@a.com", domain="finance")
    foreign = _ns_space(ns)
    foreign["parent_path"] = f"{OTHER_OWNER}/genie_spaces"  # someone else's namespace
    genie = FakeGenie(spaces={"sp-x": foreign})
    result = workshop.check(
        GENIE_CHECKPOINT_ID, catalog=CATALOG, schema=SCHEMA, genie=genie, namespace=ns
    )
    assert result.passed is False
    assert result.details["stage"] == "ownership"


def test_explicit_agent_name_overrides_namespace():
    # A custom setup can still pass an explicit name; it wins over the namespace.
    ns = workshop.namespace("someone-else@z.com", domain="finance")
    result = _check(FakeGenie(), namespace=ns)  # _check sets agent_name=AGENT
    assert result.passed is True
    assert result.details["agent_name"] == AGENT
