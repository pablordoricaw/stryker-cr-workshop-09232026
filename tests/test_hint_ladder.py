"""Repo invariants for the participant hint ladder (#15).

These are structural, dependency-free checks (no Spark, no SDK, no network) that
*lock* the three-rung hint ladder so it cannot silently rot. Each test is written
to FAIL on the specific defect it guards:

1. **Exact per-checkpoint mapping.** The Solution-map table in the participant
   ``AGENTS.md`` maps every registered ``workshop.check()`` id to the *exact*
   expected ``solutions/<domain>/<module>.py`` (``03_gold`` → ``03_gold.py``,
   ``05_metrics`` → ``05_metric_views.py``, …), and that file exists in all three
   domains. A wrong row (e.g. ``03_gold`` → ``04_metadata.py``) fails the test.
2. **``smoke`` / ``00_setup`` marked solution-less in the ladder.** Their table
   rows must say "none" and carry no ``solutions/`` pointer; an invented pointer
   fails.
3. **The release swap uses the documented recipe.** The promotion commands are
   parsed out of the fenced ``bash`` block in ``AGENTS.md`` and executed in a
   throwaway git repo; the end state is verified. The two docs' recipes must be
   the identical ordered command sequence. A reordered / broken / missing
   ``git rm`` or ``git mv`` in either doc fails the test.
4. **Discipline + fallback live in their enforceable sections.** The
   one-rung-at-a-time / no-whole-project-dump rules must sit inside the Rules
   section, and the open-the-solution-file-directly fallback inside the Fallback
   section (both delimited by stable HTML-comment anchors).

The maintainer worktree/Git workflow lives in the root ``AGENTS.md`` on ``dev``
and is a separate file; these tests treat the two as distinct on purpose.
"""

from __future__ import annotations

import os
import re
import subprocess

import workshop

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(workshop.__file__)))

# The participant hint ladder's source path on `dev`. The release recipe moves
# this to the repo root as `AGENTS.md` on `main`.
PARTICIPANT_SRC = os.path.join("docs", "participant", "AGENTS.md")
MAINTAINER_AGENTS = "AGENTS.md"
CONTRIBUTING = "CONTRIBUTING.md"

DOMAINS = ("finance", "security", "itsm")

# Checkpoints that intentionally have no gated solution file: `smoke` is a
# fresh-clone self-test and `00_setup` provisions rather than teaching a build.
SOLUTIONLESS = frozenset({"smoke", "00_setup"})

# The only checkpoint whose id differs from its solution module file name.
ID_TO_MODULE_OVERRIDE = {"05_metrics": "05_metric_views"}

# Sentinel that marks the participant file, and a stable slice of the maintainer
# workflow that must never appear in the participant file.
PARTICIPANT_SENTINEL = "stryker-workshop:participant-hint-ladder"
MAINTAINER_MARKER = "Repository Agent Workflow"


def _read(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _module_for(checkpoint_id: str) -> str:
    return ID_TO_MODULE_OVERRIDE.get(checkpoint_id, checkpoint_id)


def _checkpoint_ids() -> list[str]:
    return list(workshop.registry.ids())


def _between(text: str, start: str, end: str) -> str:
    """Return the text between two anchor markers, failing loudly if absent."""
    assert start in text, f"missing anchor {start!r}"
    assert end in text, f"missing anchor {end!r}"
    head = text.split(start, 1)[1]
    body = head.split(end, 1)[0]
    assert body.strip(), f"empty region between {start!r} and {end!r}"
    return body


def _solution_map(text: str) -> dict[str, str]:
    """Parse the marked Solution-map table → {checkpoint_id: second-column cell}."""
    section = _between(text, "<!-- solution-map:start -->", "<!-- solution-map:end -->")
    mapping: dict[str, str] = {}
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = re.match(r"^`([^`]+)`$", cells[0])  # only rows whose id is `backticked`
        if not first:
            continue  # header / separator rows
        mapping[first.group(1)] = cells[1]
    return mapping


def _promotion_recipe_commands(text: str) -> list[str]:
    """The executable command lines of the 'Promote a Workshop Release' recipe.

    Extracts the fenced ``bash`` blocks from that section, excludes the tag/push
    block (not runnable in a throwaway repo), and returns the ordered, stripped
    command lines. This is what both the consistency check and the executed dry
    run key off.
    """
    section = text.split("## Promote a Workshop Release", 1)[1]
    section = re.split(r"\n## ", section, 1)[0]
    blocks = re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)
    commands: list[str] = []
    for block in blocks:
        if "git tag" in block or "git push" in block:
            continue  # tag/push happens after promotion; not part of the swap
        commands.extend(line for line in block.splitlines() if line.strip())
    return commands


def _git(args: list[str], cwd: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# 0. The participant file is a distinct file, not the maintainer workflow.
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# 1. Exact per-checkpoint solution mapping (a wrong row must fail).
# --------------------------------------------------------------------------- #
def test_solution_map_covers_registry_ids_with_exact_modules() -> None:
    text = _read(PARTICIPANT_SRC)
    mapping = _solution_map(text)
    ids = _checkpoint_ids()

    # The table lists exactly the registered checkpoints — no missing, no extra.
    assert set(mapping) == set(ids), (
        f"solution map ids {sorted(mapping)} != registry ids {sorted(ids)}"
    )

    for cid in ids:
        cell = mapping[cid]
        if cid in SOLUTIONLESS:
            continue  # asserted in the solution-less test
        module = _module_for(cid)
        # The cell must point at EXACTLY this module (and nothing else) for the
        # per-domain template. A mismatched row (03_gold → 04_metadata.py) fails.
        found = re.findall(r"solutions/<domain>/(\S+?)\.py", cell)
        assert found == [module], (
            f"checkpoint {cid} maps to {found}, expected exactly ['{module}']"
        )
        # ...and that module is a real gated solution in every domain.
        for domain in DOMAINS:
            rel = os.path.join("solutions", domain, f"{module}.py")
            assert os.path.isfile(os.path.join(REPO_ROOT, rel)), (
                f"missing gated solution for {cid} / {domain}: {rel}"
            )


# --------------------------------------------------------------------------- #
# 2. smoke / 00_setup are marked solution-less IN the ladder.
# --------------------------------------------------------------------------- #
def test_solutionless_checkpoints_marked_in_ladder() -> None:
    text = _read(PARTICIPANT_SRC)
    mapping = _solution_map(text)
    for cid in SOLUTIONLESS:
        assert cid in mapping, f"{cid} missing from the solution map"
        cell = mapping[cid]
        assert "none" in cell.lower(), (
            f"{cid} must be marked as having no gated solution, got {cell!r}"
        )
        # An invented gated pointer (e.g. solutions/<domain>/00_setup.py) must fail.
        assert "solutions/" not in cell, (
            f"{cid} must not carry a solutions/ pointer, got {cell!r}"
        )
        # And no such gated file exists on disk in any domain.
        for domain in DOMAINS:
            assert not os.path.isfile(
                os.path.join(REPO_ROOT, "solutions", domain, f"{cid}.py")
            ), f"unexpected gated solution for solution-less checkpoint {cid}/{domain}"


# --------------------------------------------------------------------------- #
# 4. Discipline + fallback phrasing scoped to their enforceable sections.
# --------------------------------------------------------------------------- #
def test_rules_section_states_one_rung_and_no_whole_dump() -> None:
    rules = _between(_read(PARTICIPANT_SRC), "<!-- rules:start -->", "<!-- rules:end -->")
    lower = rules.lower()
    assert "one rung at a time" in lower, "Rules section must state one-rung-at-a-time"
    assert "never dump the whole project solution" in lower, (
        "Rules section must forbid dumping the whole project solution"
    )


def test_fallback_section_says_open_solution_directly() -> None:
    fb = _between(
        _read(PARTICIPANT_SRC), "<!-- fallback:start -->", "<!-- fallback:end -->"
    )
    lower = fb.lower()
    assert "free edition" in lower, "fallback must name the Free Edition venue"
    assert "directly" in lower, "fallback must say to open the solution file directly"
    assert "solutions/<domain>/<module>.py" in fb, (
        "fallback must point at the per-checkpoint solution file"
    )


# --------------------------------------------------------------------------- #
# 3. Release swap: parse the documented recipe, run it, verify the end state.
# --------------------------------------------------------------------------- #
def test_release_recipe_is_consistent_across_docs() -> None:
    agents = _promotion_recipe_commands(_read(MAINTAINER_AGENTS))
    contributing = _promotion_recipe_commands(_read(CONTRIBUTING))

    # Both recipes must contain the swap's critical ops...
    for cmds in (agents, contributing):
        assert "git merge --no-ff --no-commit dev" in cmds
        assert "git rm -rf --ignore-unmatch AGENTS.md CLAUDE.md docs/agents generators" in cmds
        assert "git mv docs/participant/AGENTS.md AGENTS.md" in cmds
        assert 'git commit -m "chore(release): promote dev to main"' in cmds
        # ...ordered so the maintainer file is removed before the participant
        # file is moved into its place.
        assert cmds.index(
            "git rm -rf --ignore-unmatch AGENTS.md CLAUDE.md docs/agents generators"
        ) < cmds.index("git mv docs/participant/AGENTS.md AGENTS.md")

    # ...and the two docs must be the identical ordered command sequence.
    assert agents == contributing, (
        "AGENTS.md and CONTRIBUTING.md release recipes differ:\n"
        f"AGENTS.md={agents}\nCONTRIBUTING.md={contributing}"
    )


def test_release_recipe_executes_and_swaps(tmp_path) -> None:
    """Run the *documented* promotion commands in a throwaway git repo.

    Seeds a `main` base + a `dev` branch carrying the maintainer files and the
    real participant hint ladder, then executes the exact command lines parsed
    from AGENTS.md and verifies the resulting tree.
    """
    commands = _promotion_recipe_commands(_read(MAINTAINER_AGENTS))
    # Guard: extraction must have actually found the recipe (not silently empty).
    assert "git mv docs/participant/AGENTS.md AGENTS.md" in commands
    assert "git rm -rf --ignore-unmatch AGENTS.md CLAUDE.md docs/agents generators" in commands

    participant_text = _read(PARTICIPANT_SRC)
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_str = str(repo)

    _git(["init", "-q"], repo_str)
    _git(["config", "user.email", "t@example.com"], repo_str)
    _git(["config", "user.name", "Test"], repo_str)
    _git(["checkout", "-q", "-b", "main"], repo_str)

    # --- main base: participant-ready-ish, no maintainer files ---
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    (repo / "solutions").mkdir()
    (repo / "solutions" / "keep.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "-A"], repo_str)
    _git(["commit", "-q", "-m", "base main"], repo_str)

    # --- dev: adds the maintainer files + the participant hint ladder source ---
    _git(["checkout", "-q", "-b", "dev"], repo_str)
    (repo / "AGENTS.md").write_text(
        "# Repository Agent Workflow\n\nmaintainer only\n", encoding="utf-8"
    )
    (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "docs" / "agents" / "domain.md").write_text("x\n", encoding="utf-8")
    (repo / "generators").mkdir()
    (repo / "generators" / "gen.py").write_text("x\n", encoding="utf-8")
    (repo / "docs" / "participant").mkdir(parents=True)
    (repo / "docs" / "participant" / "AGENTS.md").write_text(
        participant_text, encoding="utf-8"
    )
    _git(["add", "-A"], repo_str)
    _git(["commit", "-q", "-m", "dev adds instructions"], repo_str)

    # --- back on main, run the documented promotion recipe verbatim ---
    _git(["checkout", "-q", "main"], repo_str)
    script = "set -e\n" + "\n".join(commands) + "\n"
    result = subprocess.run(
        ["bash", "-c", script], cwd=repo_str, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (
        f"documented recipe failed (exit {result.returncode}):\n{result.stderr}"
    )

    # --- verify the swapped end state ---
    swapped = (repo / "AGENTS.md")
    assert swapped.is_file(), "root AGENTS.md must exist after the swap"
    swapped_text = swapped.read_text(encoding="utf-8")
    assert swapped_text == participant_text, (
        "root AGENTS.md must be byte-identical to the participant hint ladder"
    )
    assert PARTICIPANT_SENTINEL in swapped_text
    assert MAINTAINER_MARKER not in swapped_text
    assert not (repo / "docs" / "participant" / "AGENTS.md").exists()
    assert not (repo / "CLAUDE.md").exists()
    assert not (repo / "docs" / "agents").exists()
    assert not (repo / "generators").exists()
    # base workshop content survives the promotion.
    assert (repo / "README.md").is_file()
    assert (repo / "solutions" / "keep.txt").is_file()
