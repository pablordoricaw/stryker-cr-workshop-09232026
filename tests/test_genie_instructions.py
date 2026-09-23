"""Unit tests for the Genie Code hint-ladder injection helpers (#27).

These pin the pure-text contract of :mod:`workshop.genie_instructions` — the
build → merge → strip pipeline that splices the hint ladder into a participant's
``~/.assistant_instructions.md``. They are dependency-free (no Spark, no SDK) and
stand in for the safety guarantees the live validation must NOT prove by
mutating a real personal file: personal content is preserved, re-runs are
idempotent, and cleanup removes only the workshop block.

The build tests use the real hint-ladder source shipped at
``docs/genie/.assistant_instructions.md`` so they also catch regressions in that
file (e.g. the maintainer comment sneaking back into the participant view).
"""

from __future__ import annotations

import os

import workshop
from workshop.genie_instructions import (
    HINTS_HEADER,
    SENTINEL_END,
    SENTINEL_START,
    build_injection_block,
    merge_block,
    strip_block,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(workshop.__file__)))
SOURCE_PATH = os.path.join("docs", "genie", ".assistant_instructions.md")
MAINTAINER_MARKER = "stryker-workshop:participant-hint-ladder"


def _source() -> str:
    with open(os.path.join(REPO_ROOT, SOURCE_PATH), encoding="utf-8") as handle:
        return handle.read()


# --------------------------------------------------------------------------- #
# build_injection_block
# --------------------------------------------------------------------------- #
def test_build_strips_maintainer_comment_and_wraps_in_sentinels() -> None:
    block = build_injection_block(_source(), "/Workspace/Repos/me/stryker", "finance")

    # Sentinel-wrapped, exactly once each, START before END.
    assert block.startswith(SENTINEL_START + "\n")
    assert block.rstrip("\n").endswith(SENTINEL_END)
    assert block.count(SENTINEL_START) == 1
    assert block.count(SENTINEL_END) == 1
    assert block.index(SENTINEL_START) < block.index(SENTINEL_END)
    assert block.endswith("\n")

    # The maintainer HTML comment (and its now-corrected explanation) is stripped.
    assert MAINTAINER_MARKER not in block
    assert "auto-discover" not in block.lower()

    # Header + resolved repo root + domain are prepended.
    assert HINTS_HEADER in block
    assert "Workshop repo root: /Workspace/Repos/me/stryker" in block
    assert "My domain: finance" in block

    # The ladder body survives, including its in-body anchors and rungs.
    assert "# Workshop hints" in block
    assert "<!-- rules:start -->" in block
    assert "solutions/<domain>/06_genie.py" in block


def test_build_reports_domain_not_yet_chosen_when_blank() -> None:
    for domain in (None, "", "   "):
        block = build_injection_block(_source(), "/x", domain)
        assert "My domain: not yet chosen — ask me" in block


def test_build_uses_the_exact_header_and_domain_line_for_each_domain() -> None:
    for domain in ("finance", "security", "itsm"):
        block = build_injection_block(_source(), "/repo", domain)
        assert f"My domain: {domain}" in block


def test_build_strips_leading_comments_but_keeps_body_anchor_comments() -> None:
    src = (
        "<!-- marker -->\n"
        "<!--\n  multi-line maintainer note\n-->\n\n"
        "# Real heading\n\n"
        "<!-- rules:start -->\nkeep this anchor\n<!-- rules:end -->\n"
    )
    block = build_injection_block(src, "/repo", "finance")
    assert "marker" not in block
    assert "multi-line maintainer note" not in block
    assert "# Real heading" in block
    assert "<!-- rules:start -->" in block
    assert "keep this anchor" in block


# --------------------------------------------------------------------------- #
# merge_block
# --------------------------------------------------------------------------- #
def test_merge_appends_when_no_block_present_and_preserves_personal() -> None:
    personal = "# My own instructions\n\nAlways use tabs.\n"
    block = build_injection_block(_source(), "/repo", "finance")

    merged = merge_block(personal, block)

    # Personal content is preserved verbatim, and the block is present after it.
    assert personal.rstrip("\n") in merged
    assert merged.index("My own instructions") < merged.index(SENTINEL_START)
    assert SENTINEL_START in merged and SENTINEL_END in merged


def test_merge_into_empty_file_is_just_the_block() -> None:
    block = build_injection_block(_source(), "/repo", "finance")
    assert merge_block("", block) == block
    assert merge_block("   \n\n", block) == block


def test_merge_replaces_existing_block_in_place_preserving_personal() -> None:
    before = "# Top personal\nkeep top\n"
    after = "# Bottom personal\nkeep bottom\n"
    old = build_injection_block(_source(), "/old/repo", "finance")
    # A personal file with the block sandwiched between personal content.
    existing = merge_block(before, old)
    existing = existing.rstrip("\n") + "\n\n" + after

    new = build_injection_block(_source(), "/new/repo", "security")
    merged = merge_block(existing, new)

    # Exactly one block, updated to the new repo root + domain.
    assert merged.count(SENTINEL_START) == 1
    assert merged.count(SENTINEL_END) == 1
    assert "Workshop repo root: /new/repo" in merged
    assert "My domain: security" in merged
    assert "/old/repo" not in merged
    assert "My domain: finance" not in merged

    # Both blocks of personal content survive, in order, around the block.
    assert "keep top" in merged and "keep bottom" in merged
    assert merged.index("keep top") < merged.index(SENTINEL_START)
    assert merged.index(SENTINEL_END) < merged.index("keep bottom")


def test_merge_is_idempotent_on_reruns() -> None:
    personal = "# Notes\nremember me\n"
    block = build_injection_block(_source(), "/repo", "itsm")
    once = merge_block(personal, block)
    twice = merge_block(once, block)
    assert once == twice


# --------------------------------------------------------------------------- #
# strip_block
# --------------------------------------------------------------------------- #
def test_strip_round_trips_appended_block_back_to_personal() -> None:
    personal = "# My own instructions\n\nAlways use tabs.\n"
    block = build_injection_block(_source(), "/repo", "finance")
    merged = merge_block(personal, block)
    assert strip_block(merged) == personal


def test_strip_removes_only_the_block_preserving_surrounding_content() -> None:
    before = "# Top\nkeep top\n"
    after = "# Bottom\nkeep bottom\n"
    block = build_injection_block(_source(), "/repo", "finance")
    existing = merge_block(before, block).rstrip("\n") + "\n\n" + after

    stripped = strip_block(existing)

    assert SENTINEL_START not in stripped
    assert SENTINEL_END not in stripped
    assert "Stryker Workshop" not in stripped
    assert "keep top" in stripped
    assert "keep bottom" in stripped


def test_strip_leaves_a_file_without_a_block_untouched() -> None:
    personal = "# Just my notes\nno workshop block here\n"
    assert strip_block(personal) == personal


def test_strip_is_idempotent() -> None:
    block = build_injection_block(_source(), "/repo", "finance")
    merged = merge_block("# Notes\nkeep\n", block)
    once = strip_block(merged)
    assert strip_block(once) == once


def test_strip_ignores_a_malformed_half_block() -> None:
    # A dangling START with no END must not eat the rest of the file.
    text = f"# Notes\n{SENTINEL_START}\nhalf a block, no end\n"
    assert strip_block(text) == text
