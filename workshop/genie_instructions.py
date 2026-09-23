"""Build and splice the participant Genie Code hints into a personal file.

Genie Code — the in-workspace coding assistant — does **not** auto-discover the
repo's ``AGENTS.md`` by walking the directory tree. What it *does* do, verified
live, is auto-load each user's personal instructions file at
``~/.assistant_instructions.md`` (``/Workspace/Users/<email>/.assistant_instructions.md``)
at the start of every session. So the workshop delivers its three-rung hint
ladder by *injecting* it into that personal file from ``00_setup`` — and removes
it again on cleanup.

That personal file may already hold the participant's own instructions, so the
splice must be surgical: the workshop's content is wrapped in a pair of
``<!-- STRYKER-WORKSHOP-START -->`` / ``<!-- STRYKER-WORKSHOP-END -->``
sentinels, and every operation preserves everything outside those sentinels
verbatim.

Everything here is pure Python — no Spark, no Databricks SDK, no network — so it
is unit-testable off-platform. The ``00_setup`` notebook supplies the SDK glue
(reading the source file, reading/writing the personal file through the
workspace files API); this module just transforms text.

Three functions carry the contract:

* :func:`build_injection_block` — turn the hint-ladder source into a
  sentinel-wrapped block, with the participant's repo root and domain filled in.
* :func:`merge_block` — splice a block into a personal file, replacing an
  existing workshop block in place or appending when none is present, and
  leaving all personal content untouched. Idempotent across re-runs.
* :func:`strip_block` — remove only the workshop block, restoring the personal
  content.
"""

from __future__ import annotations

import re

#: Sentinels that delimit the workshop's block inside the personal file. Only the
#: text between (and including) these markers is ever added, replaced, or removed.
SENTINEL_START = "<!-- STRYKER-WORKSHOP-START -->"
SENTINEL_END = "<!-- STRYKER-WORKSHOP-END -->"

#: The heading prepended to the injected block so a participant reading their
#: personal file can see where the workshop's content begins.
HINTS_HEADER = "## Stryker Workshop — Genie Code Hints"

#: Shown for the domain line before the participant has chosen a domain.
_DOMAIN_UNCHOSEN = "not yet chosen — ask me"

# Matches a single HTML comment at the very start of the text, with any leading
# and trailing whitespace. Non-greedy + DOTALL so a multi-line comment matches
# only up to its own ``-->``. Applied repeatedly to peel the source file's
# leading maintainer comment(s) without touching the ``<!-- rules:start -->``
# style anchors that live *after* the first real content.
_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->[ \t]*\n?", re.DOTALL)


def _strip_leading_html_comments(text: str) -> str:
    """Drop any HTML comment(s) that precede the first real content.

    The hint-ladder source opens with the ``stryker-workshop:participant-hint-ladder``
    marker and a maintainer explanation comment; neither belongs in a
    participant's personal instructions. Stops at the first non-comment,
    non-blank line, so in-body anchors (``<!-- rules:start -->`` and friends) are
    preserved.
    """
    while True:
        match = _LEADING_COMMENT.match(text)
        if not match:
            return text.lstrip("\n")
        text = text[match.end() :]


def build_injection_block(
    source_text: str, repo_root: str, domain: str | None = None
) -> str:
    """Build the sentinel-wrapped hint block from the hint-ladder source.

    Strips the maintainer HTML comment(s) from ``source_text``, prepends the
    workshop heading plus the participant's resolved ``repo_root`` and
    ``domain``, and wraps the whole thing between :data:`SENTINEL_START` and
    :data:`SENTINEL_END`.

    Args:
        source_text: Raw contents of ``docs/genie/.assistant_instructions.md``.
        repo_root: Absolute path of the participant's clone (so Genie Code can
            resolve ``solutions/<domain>/<module>.py`` and friends).
        domain: The participant's chosen domain (``finance``/``security``/``itsm``),
            or ``None``/blank before one is chosen.

    Returns:
        The block text, terminated by a single trailing newline.
    """
    body = _strip_leading_html_comments(source_text).strip("\n")
    domain_line = domain.strip() if domain and domain.strip() else _DOMAIN_UNCHOSEN
    header = (
        f"{HINTS_HEADER}\n\n"
        f"Workshop repo root: {repo_root}\n"
        f"My domain: {domain_line}\n"
    )
    inner = f"{header}\n{body}" if body else header.rstrip("\n")
    return f"{SENTINEL_START}\n{inner}\n{SENTINEL_END}\n"


def _find_block(text: str) -> tuple[int, int] | None:
    """Return ``(start, end)`` char offsets of the sentinel block, or ``None``.

    ``end`` is exclusive and points just past :data:`SENTINEL_END`. Returns
    ``None`` if the start sentinel is absent, or the end sentinel does not follow
    it (a malformed half-block is left untouched by callers).
    """
    start = text.find(SENTINEL_START)
    if start == -1:
        return None
    end = text.find(SENTINEL_END, start + len(SENTINEL_START))
    if end == -1:
        return None
    return start, end + len(SENTINEL_END)


def merge_block(existing_text: str, block: str) -> str:
    """Splice ``block`` into ``existing_text``, preserving personal content.

    If a workshop block is already present it is replaced **in place** (so a
    re-run with a changed domain/repo-root updates cleanly); otherwise the block
    is appended after the existing content. Everything outside the sentinels is
    preserved verbatim. Idempotent: merging the same block twice yields the same
    result.

    Args:
        existing_text: Current contents of the personal file (may be empty).
        block: A block produced by :func:`build_injection_block`.

    Returns:
        The merged file contents.
    """
    # Replace in place: keep everything before/after the sentinels byte-for-byte
    # and drop the block's trailing newline so a re-merge reproduces this exactly.
    found = _find_block(existing_text)
    if found is not None:
        start, end = found
        return existing_text[:start] + block.rstrip("\n") + existing_text[end:]

    # Append: no prior block. Empty/blank file → just the block.
    if not existing_text.strip():
        return block
    return existing_text.rstrip("\n") + "\n\n" + block


def strip_block(existing_text: str) -> str:
    """Remove only the workshop block, restoring the personal content.

    Deletes the region from :data:`SENTINEL_START` through :data:`SENTINEL_END`
    (inclusive) and collapses the blank separator the injection introduced, so a
    file that only ever held appended personal content plus one workshop block
    round-trips back to that personal content. Text with no workshop block (or a
    malformed half-block) is returned unchanged. Idempotent.

    Args:
        existing_text: Current contents of the personal file.

    Returns:
        The file contents with the workshop block removed.
    """
    found = _find_block(existing_text)
    if found is None:
        return existing_text
    start, end = found
    before = existing_text[:start].rstrip("\n")
    after = existing_text[end:].lstrip("\n")
    if before and after:
        return f"{before}\n\n{after}"
    if before:
        return f"{before}\n"
    return after
