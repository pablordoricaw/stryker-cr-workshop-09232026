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
**byte-for-byte** (leading/trailing blank lines, whitespace-only files, and
files with no final newline all round-trip unchanged). A workshop block is
recognized only when the start sentinel is immediately followed by the workshop
heading (:data:`HINTS_HEADER`), so a stray or coincidental sentinel string in
the participant's own text is never treated as the workshop's block — it is left
alone rather than clobbered.

Everything here is pure Python — no Spark, no Databricks SDK, no network — so it
is unit-testable off-platform. The ``00_setup`` notebook supplies the SDK glue
(reading the source file, reading/writing the personal file through the
workspace files API); this module just transforms text.

Three functions carry the contract:

* :func:`build_injection_block` — turn the hint-ladder source into a
  sentinel-wrapped block, with the participant's repo root and domain filled in.
* :func:`merge_block` — splice a block into a personal file, guaranteeing exactly
  one workshop block afterward (replace in place, or append when none is present,
  or collapse several into one), and leaving all personal content byte-for-byte
  untouched. Idempotent across re-runs.
* :func:`strip_block` — remove every workshop block, restoring the personal
  content byte-for-byte.
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


def _find_blocks(text: str) -> list[tuple[int, int]]:
    """Locate every well-formed workshop block, as ``(start, end)`` char spans.

    A **workshop block** is what :func:`build_injection_block` emits: a
    :data:`SENTINEL_START` marker whose content opens with the :data:`HINTS_HEADER`
    line, closed by the next :data:`SENTINEL_END` marker. The returned span runs
    from the ``<`` of ``SENTINEL_START`` through ``SENTINEL_END`` **plus the one
    trailing newline the block carries** (so removing the span is byte-exact
    against an append), and never over any surrounding personal whitespace.

    This is deliberately conservative so it never clobbers the participant's own
    content:

    * The :data:`HINTS_HEADER` anchor means a bare or coincidental sentinel
      *string* in personal text — a lone marker, an inline mention, or a
      START/END pair that is not the workshop's — is **not** matched.
    * A ``SENTINEL_START`` that is not header-anchored, or that has no following
      ``SENTINEL_END``, is skipped (the scan resumes just past that marker), so a
      dangling personal ``START`` can never consume the real block or the text
      between them.
    * A header-anchored ``START`` is paired with the **first** ``SENTINEL_END``
      that has no other ``SENTINEL_START`` before it — a well-formed block's body
      never contains a start marker. This "innermost" pairing means an unclosed
      header-anchored start cannot borrow a *later* block's end and swallow the
      content between them.

    Spans are returned in document order and never overlap.
    """
    blocks: list[tuple[int, int]] = []
    i = 0
    while True:
        start = text.find(SENTINEL_START, i)
        if start == -1:
            return blocks
        after_start = start + len(SENTINEL_START)
        # Ours only if the workshop header opens the block (tolerating the
        # newline(s) between the marker and the heading). This is the signal that
        # distinguishes the workshop's block from a stray/personal sentinel.
        if text[after_start:].lstrip("\r\n").startswith(HINTS_HEADER):
            end = text.find(SENTINEL_END, after_start)
            next_start = text.find(SENTINEL_START, after_start)
            # A well-formed block has an end, and no further start before that
            # end. If another start intervenes, THIS start is malformed/unclosed
            # — skip it so the later (real) start gets paired instead.
            if end != -1 and (next_start == -1 or next_start > end):
                span_end = end + len(SENTINEL_END)
                # The block always ships one trailing newline; fold it into the
                # span so a strip of an appended block restores the file exactly.
                if text[span_end : span_end + 1] == "\n":
                    span_end += 1
                blocks.append((start, span_end))
                i = span_end
                continue
        # Not a workshop block (no header, no closing marker, or an intervening
        # start): leave it as personal content and resume just past this marker.
        i = after_start


def merge_block(existing_text: str, block: str) -> str:
    """Splice ``block`` into ``existing_text``, preserving personal content exactly.

    Guarantees **exactly one** workshop block afterward and leaves every byte
    outside the workshop block(s) untouched:

    * No existing block → the block is appended to ``existing_text`` verbatim (no
      separator is inserted, so the participant's own trailing whitespace is never
      mutated; the block's own leading marker line and ``existing_text``'s own
      trailing newline provide the boundary).
    * One existing block → it is replaced **in place**, preserving position and
      surrounding whitespace.
    * Several existing blocks → the first is replaced in place and the rest are
      removed, collapsing to a single block while keeping the personal content
      between them.

    Idempotent: merging the same block again reproduces the result byte-for-byte.

    Args:
        existing_text: Current contents of the personal file (may be empty).
        block: A block produced by :func:`build_injection_block`.

    Returns:
        The merged file contents.
    """
    blocks = _find_blocks(existing_text)
    if not blocks:
        # Append verbatim. `"" + block == block`, and for non-empty content the
        # block follows directly — no inserted separator to mutate on round trip.
        return existing_text + block

    first_start, first_end = blocks[0]
    parts = [existing_text[:first_start], block]
    prev_end = first_end
    for start, end in blocks[1:]:
        parts.append(existing_text[prev_end:start])  # personal text between blocks
        prev_end = end  # drop this extra block
    parts.append(existing_text[prev_end:])
    return "".join(parts)


def strip_block(existing_text: str) -> str:
    """Remove every workshop block, restoring the personal content byte-for-byte.

    Deletes each well-formed workshop block span (see :func:`_find_blocks`) and
    leaves everything else exactly as it was — including leading/trailing blank
    lines, whitespace-only files, and files with no final newline. A
    ``build → merge → strip`` round trip returns the original personal text
    unchanged. Text with no workshop block (or only malformed/half sentinels) is
    returned untouched. Idempotent.

    Args:
        existing_text: Current contents of the personal file.

    Returns:
        The file contents with every workshop block removed.
    """
    blocks = _find_blocks(existing_text)
    if not blocks:
        return existing_text
    parts: list[str] = []
    prev_end = 0
    for start, end in blocks:
        parts.append(existing_text[prev_end:start])
        prev_end = end
    parts.append(existing_text[prev_end:])
    return "".join(parts)
