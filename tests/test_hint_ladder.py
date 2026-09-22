"""Repo invariants for the participant hint ladder (#15).

These are structural, dependency-free checks (no Spark, no SDK, no network) that
lock in the three-rung hint ladder so it cannot silently rot:

1. **Every checkpoint is covered.** The participant ``AGENTS.md`` references every
   registered ``workshop.check()`` id, and — for every checkpoint that has a
   gated solution — the referenced ``solutions/<domain>/<module>.py`` exists for
   all three domains (finance, security, itsm). The ladder cannot silently miss a
   checkpoint or a domain.
2. **The discipline is documented.** One rung at a time, never the whole project
   solution at once, plus the Genie-Code-absent fallback (open the per-checkpoint
   solution file directly).
3. **The release swap holds.** Simulating the documented ``dev`` → ``main``
   promotion produces a tree whose root ``AGENTS.md`` is the participant hint
   ladder, with the maintainer workflow, ``CLAUDE.md``, ``docs/agents/``,
   ``generators/``, and the ``docs/participant/`` source all absent.

The maintainer worktree/Git workflow lives in the root ``AGENTS.md`` on ``dev``
and is a separate file; these tests treat the two as distinct on purpose.
"""

from __future__ import annotations

import os
import shutil

import workshop

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(workshop.__file__)))

# The participant hint ladder's source path on `dev`. The release recipe moves
# this to the repo root as `AGENTS.md` on `main`.
PARTICIPANT_SRC = os.path.join("docs", "participant", "AGENTS.md")

DOMAINS = ("finance", "security", "itsm")

# Checkpoints that intentionally have no gated solution file: `smoke` is a
# fresh-clone self-test and `00_setup` provisions rather than teaching a build.
SOLUTIONLESS = frozenset({"smoke", "00_setup"})

# The only checkpoint whose id differs from its solution module file name.
ID_TO_MODULE_OVERRIDE = {"05_metrics": "05_metric_views"}

# Sentinel that marks the participant file, and a stable slice of the maintainer
# workflow that must never appear in the participant file (used by the release
# recipe's flipped assertion, mirrored here).
PARTICIPANT_SENTINEL = "stryker-workshop:participant-hint-ladder"
MAINTAINER_MARKER = "Repository Agent Workflow"


def _read(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _module_for(checkpoint_id: str) -> str:
    return ID_TO_MODULE_OVERRIDE.get(checkpoint_id, checkpoint_id)


def _checkpoint_ids() -> list[str]:
    return list(workshop.registry.ids())


def test_participant_file_exists_and_is_not_the_maintainer_file() -> None:
    text = _read(PARTICIPANT_SRC)
    assert PARTICIPANT_SENTINEL in text, "participant file is missing its sentinel"
    assert MAINTAINER_MARKER not in text, (
        "participant hint ladder must not contain the maintainer workflow marker"
    )


def test_ladder_references_every_checkpoint_id() -> None:
    text = _read(PARTICIPANT_SRC)
    missing = [cid for cid in _checkpoint_ids() if cid not in text]
    assert not missing, f"participant AGENTS.md never mentions checkpoint(s): {missing}"


def test_every_solution_bearing_checkpoint_resolves_for_all_domains() -> None:
    text = _read(PARTICIPANT_SRC)
    # The ladder must use the domain-aware template so the pointer is per-domain.
    assert "solutions/<domain>/" in text, "ladder must template solutions/<domain>/"

    for cid in _checkpoint_ids():
        if cid in SOLUTIONLESS:
            continue
        module = _module_for(cid)
        # The file names the correct solution module for this checkpoint...
        assert f"{module}.py" in text, (
            f"checkpoint {cid} should point at {module}.py in the participant ladder"
        )
        # ...and that module exists as a real gated solution in every domain.
        for domain in DOMAINS:
            rel = os.path.join("solutions", domain, f"{module}.py")
            assert os.path.isfile(os.path.join(REPO_ROOT, rel)), (
                f"missing gated solution for {cid} / {domain}: {rel}"
            )


def test_solutionless_checkpoints_are_documented_without_a_gated_file() -> None:
    # smoke and 00_setup must be present but explicitly marked as having no gated
    # solution, so the ladder never invents a solutions/<domain>/smoke.py etc.
    text = _read(PARTICIPANT_SRC)
    for cid in SOLUTIONLESS:
        assert cid in text
        for domain in DOMAINS:
            assert not os.path.isfile(
                os.path.join(REPO_ROOT, "solutions", domain, f"{cid}.py")
            ), f"unexpected gated solution for solution-less checkpoint {cid}/{domain}"


def test_one_rung_at_a_time_discipline_is_documented() -> None:
    text = _read(PARTICIPANT_SRC).lower()
    assert "one rung at a time" in text
    assert "never dump the whole project solution" in text
    # The three rungs are named.
    assert "rung 1" in text and "rung 2" in text and "rung 3" in text


def test_genie_code_absent_fallback_is_documented() -> None:
    text = _read(PARTICIPANT_SRC)
    lower = text.lower()
    assert "free edition" in lower, "fallback must name the Free Edition venue"
    assert "directly" in lower, "fallback must say to open the solution file directly"
    assert "solutions/<domain>/<module>.py" in text, (
        "fallback must point at the per-checkpoint solution file"
    )


def test_release_swap_produces_participant_agents_at_root(tmp_path) -> None:
    """Filesystem-level dry run of the documented dev→main promotion swap.

    Mirrors the recipe: strip the maintainer-only files, then move the participant
    hint ladder to the root as AGENTS.md. Asserts the resulting tree invariants
    that the recipe's shell assertions check.
    """
    root = tmp_path / "main"
    (root / "docs" / "participant").mkdir(parents=True)
    (root / "docs" / "agents").mkdir(parents=True)
    (root / "generators").mkdir(parents=True)

    # Seed a merged-from-dev tree: maintainer AGENTS.md + the real participant file.
    (root / "AGENTS.md").write_text(
        "# Repository Agent Workflow\n\nmaintainer only\n", encoding="utf-8"
    )
    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (root / "docs" / "agents" / "domain.md").write_text("x\n", encoding="utf-8")
    (root / "generators" / "gen.py").write_text("x\n", encoding="utf-8")
    participant_text = _read(PARTICIPANT_SRC)
    (root / "docs" / "participant" / "AGENTS.md").write_text(
        participant_text, encoding="utf-8"
    )

    # --- the swap: `git rm` the maintainer files, then `git mv` participant→root ---
    os.remove(root / "AGENTS.md")
    os.remove(root / "CLAUDE.md")
    shutil.rmtree(root / "docs" / "agents")
    shutil.rmtree(root / "generators")
    shutil.move(
        str(root / "docs" / "participant" / "AGENTS.md"), str(root / "AGENTS.md")
    )

    # --- the recipe's assertions ---
    assert (root / "AGENTS.md").is_file()
    swapped = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert PARTICIPANT_SENTINEL in swapped
    assert MAINTAINER_MARKER not in swapped
    assert swapped == participant_text
    assert not (root / "docs" / "participant" / "AGENTS.md").exists()
    assert not (root / "CLAUDE.md").exists()
    assert not (root / "docs" / "agents").exists()
    assert not (root / "generators").exists()
