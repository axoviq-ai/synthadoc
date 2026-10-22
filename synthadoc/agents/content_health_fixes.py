# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic, loss-free content-health fixes (no LLM).

Companion to :mod:`synthadoc.agents.content_health_scanner`: the scanner finds
issues, this module repairs the ones that need no judgement and checks that a
proposed rewrite keeps every sentence of the original.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field

from synthadoc.agents.content_health_scanner import (
    Section,
    _normalise_heading,
    _section_spans,
    _strip_code_blocks,
)

_MD_LINE_PREFIX_RE = re.compile(r"^(?:\s*(?:[>*+-]|\d+[.)])\s+)+")
_MD_INLINE_RE = re.compile(r"[*_`|]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MIN_SENTENCE_WORDS = 4
_STATUS_ERR = "error"


# ---------------------------------------------------------------------------
# Sentence preservation
# ---------------------------------------------------------------------------

def _normalise_prose(text: str) -> list[str]:
    """Body lines (no headings) with list/quote markers and emphasis stripped, lowercased."""
    lines = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        line = _MD_INLINE_RE.sub(" ", _MD_LINE_PREFIX_RE.sub("", line))
        lines.append(" ".join(line.split()).lower())
    return lines


def _sentences(text: str) -> list[str]:
    """Normalised sentences of *text* with at least _MIN_SENTENCE_WORDS words."""
    return [
        sentence
        for line in _normalise_prose(text)
        for sentence in (part.strip() for part in _SENTENCE_SPLIT_RE.split(line))
        if len(sentence.split()) >= _MIN_SENTENCE_WORDS
    ]


def dropped_sentences(original: str, rewritten: str) -> list[str]:
    """Sentences of *original* that no longer appear anywhere in *rewritten*.

    Content-health fixes are structural only (headings, duplicates, empty
    sections), so every prose sentence must survive. Headings are ignored because
    fixes legitimately rename, merge or remove them; fragments shorter than
    _MIN_SENTENCE_WORDS words are ignored as noise.
    """
    haystack = " ".join(_normalise_prose(rewritten))
    return list(dict.fromkeys(s for s in _sentences(original) if s not in haystack))


# ---------------------------------------------------------------------------
# Heading preservation
# ---------------------------------------------------------------------------

@dataclass
class HeadingChange:
    kind: str          # "removed" | "added" | "level_changed" | "text_changed" | "reordered"
    before: str | None  # heading text before (None if kind == "added")
    after: str | None   # heading text after (None if kind == "removed")


def _heading_tuples(markdown: str) -> list[tuple[int, str]]:
    spans = _section_spans(_strip_code_blocks(markdown).split("\n"))
    return [(s.level, s.heading) for s in spans]


def heading_diff(before: str, after: str) -> list[HeadingChange]:
    """Ordered diff of before's headings vs after's headings.

    Extracts (level, text) pairs via _section_spans — the same mechanism the
    scanner uses for duplicate_section detection — from both versions, then
    diffs them with difflib.SequenceMatcher. Pure and opinion-free: returns
    every difference with no judgement about which are acceptable; callers
    apply their own policy. An empty list means headings are identical in
    content, level, and order.
    """
    before_h = _heading_tuples(before)
    after_h = _heading_tuples(after)

    # If sequences are identical, no changes
    if before_h == after_h:
        return []

    sm = difflib.SequenceMatcher(None, before_h, after_h, autojunk=False)

    removed_pool: list[tuple[int, str]] = []
    added_pool: list[tuple[int, str]] = []
    equal_items: list[tuple[int, str]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            equal_items.extend(before_h[i1:i2])
            continue
        removed_pool.extend(before_h[i1:i2])
        added_pool.extend(after_h[j1:j2])

    changes: list[HeadingChange] = []

    # An item that vanished from one spot and reappeared verbatim elsewhere
    # was moved, not deleted-and-recreated.
    for item in list(removed_pool):
        if item in added_pool:
            removed_pool.remove(item)
            added_pool.remove(item)
            changes.append(HeadingChange(kind="reordered", before=item[1], after=item[1]))

    # Check for reordering among items marked as equal: if their relative order
    # has changed, they're reordered.
    reordered_from_equal: set[tuple[int, str]] = set()
    for item in equal_items:
        before_pos = before_h.index(item)
        after_pos = after_h.index(item)
        if before_pos == after_pos:
            continue
        # Item changed position. Check if this is due to reordering with any other
        # heading (not just caused by removals/additions).
        for other in before_h:
            if other == item or other not in after_h:
                continue
            other_before = before_h.index(other)
            other_after = after_h.index(other)
            # Relative order changed between item and other
            if (before_pos < other_before) != (after_pos < other_after):
                reordered_from_equal.add(item)
                break

    for item in reordered_from_equal:
        changes.append(HeadingChange(kind="reordered", before=item[1], after=item[1]))

    # A remaining pair that shares either text or level was one heading
    # edited in place, not an unrelated removal plus an unrelated addition.
    # Process text matches first (same text, different level) to avoid greedy
    # level matches that would leave text matches unmatched.
    for b_item in list(removed_pool):
        b_level, b_text = b_item
        match = next((a for a in added_pool if a[1] == b_text and a[0] != b_level), None)
        if match is not None:
            removed_pool.remove(b_item)
            added_pool.remove(match)
            a_level, a_text = match
            kind = "level_changed" if b_text == a_text else "text_changed"
            changes.append(HeadingChange(kind=kind, before=b_text, after=a_text))

    # Then process level matches (same level, different text)
    for b_item in list(removed_pool):
        b_level, b_text = b_item
        match = next((a for a in added_pool if a[0] == b_level and a[1] != b_text), None)
        if match is not None:
            removed_pool.remove(b_item)
            added_pool.remove(match)
            a_level, a_text = match
            kind = "level_changed" if b_text == a_text else "text_changed"
            changes.append(HeadingChange(kind=kind, before=b_text, after=a_text))

    changes.extend(HeadingChange(kind="removed", before=h, after=None) for _, h in removed_pool)
    changes.extend(HeadingChange(kind="added", before=None, after=h) for _, h in added_pool)
    return changes


# Only "removed" (budgeted against empty_section count) and "level_changed"
# with unchanged text (budgeted against orphaned_heading count) can ever be
# tolerated. Every other kind is always rejected, regardless of issues_fixed.
_HEADING_TOLERANCE: dict[str, str] = {
    "empty_section": "removed",
    "orphaned_heading": "level_changed",
}


def heading_mismatch_error(
    slug: str, before: str, after: str, *, issues_fixed: list[str] | None = None
) -> dict | None:
    """Error result when *after* changes a heading not permitted, else None.

    Without issues_fixed: zero tolerance — any heading change is rejected.
    With issues_fixed: one 'removed' change is permitted per empty_section
    issue in the list, one 'level_changed' change (heading text unchanged) per
    orphaned_heading issue. Any other change, or more changes than
    issues_fixed accounts for, is rejected.
    """
    changes = heading_diff(before, after)
    if not changes:
        return None

    budget = Counter(issues_fixed or [])
    unexplained: list[HeadingChange] = []
    for change in changes:
        explained = False
        for issue_type, tolerated_kind in _HEADING_TOLERANCE.items():
            if change.kind != tolerated_kind:
                continue
            # heading_diff only ever emits level_changed when text is unchanged,
            # but guard the invariant explicitly rather than trust it silently.
            if tolerated_kind == "level_changed" and change.before != change.after:
                continue
            if budget.get(issue_type, 0) > 0:
                budget[issue_type] -= 1
                explained = True
                break
        if not explained:
            unexplained.append(change)

    if not unexplained:
        return None

    shown = "; ".join(f"{c.kind}: {c.before!r} -> {c.after!r}" for c in unexplained[:5])
    return {
        "status": _STATUS_ERR,
        "slug": slug,
        "heading_changes": len(unexplained),
        "error": (
            f"Rejected — nothing was written. The rewrite changes {len(unexplained)} "
            f"heading(s) beyond what the fixed issues permit, e.g. {shown}. "
            "Leave issues that cannot be fixed without changing headings for a human: "
            "dismiss them (notify, then dismiss_content_health_issues) instead of writing. "
            "Do not retry with the same content."
        ),
    }


# ---------------------------------------------------------------------------
# Duplicate-section merge
# ---------------------------------------------------------------------------

@dataclass
class MergeResult:
    content: str
    merged: list[str] = field(default_factory=list)   # headings whose copies were folded in
    skipped: list[str] = field(default_factory=list)  # copies left alone (they have sub-sections)
    source_headings: list[str] = field(default_factory=list)  # every original heading involved


def _paragraphs(lines: list[str]) -> list[list[str]]:
    """Split body lines into blank-line separated paragraphs (blank lines dropped)."""
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])
    return [p for p in paragraphs if p]


def _is_repeat(paragraph: str, haystack: str) -> bool:
    """True when every sentence of *paragraph* (or its whole text, if it has no
    full sentence) already appears in *haystack*."""
    sentences = _sentences(paragraph)
    if sentences:
        return all(s in haystack for s in sentences)
    return " ".join(_normalise_prose(paragraph)) in haystack


def merge_duplicate_sections(content: str) -> MergeResult:
    """Fold every later copy of a duplicated heading into its first occurrence.

    Headings are matched the same way the scanner flags ``duplicate_section``.
    Each later copy's paragraphs are appended to the first copy's own body,
    except paragraphs whose sentences are all already there (exact repeats);
    the later heading is then removed. A copy that has sub-sections is left in
    place and reported in ``skipped``, since moving a subtree needs judgement.
    Every sentence of *content* is still present in the result.
    """
    lines = content.split("\n")
    # Spans come from the code-stripped text (same line count) so headings inside
    # fenced code blocks are ignored, exactly as in the scanner.
    spans = _section_spans(_strip_code_blocks(content).split("\n"))

    groups: dict[str, list[int]] = {}
    for k, span in enumerate(spans):
        groups.setdefault(_normalise_heading(span.heading), []).append(k)

    def has_subsections(k: int) -> bool:
        return k + 1 < len(spans) and spans[k + 1].level > spans[k].level

    def body(span: Section) -> list[str]:
        return lines[span.start + 1:span.end]

    appended: dict[int, list[str]] = {}   # keeper index -> paragraphs to add
    removed: set[int] = set()
    result = MergeResult(content=content)
    for indices in groups.values():
        if len(indices) < 2:
            continue
        keeper, copies = indices[0], indices[1:]
        haystack = " ".join(_normalise_prose("\n".join(body(spans[keeper]))))
        for k in copies:
            if has_subsections(k):
                result.skipped.append(spans[k].heading)
                continue
            for paragraph in ("\n".join(p) for p in _paragraphs(body(spans[k]))):
                if not _is_repeat(paragraph, haystack):
                    appended.setdefault(keeper, []).append(paragraph)
                    haystack += " " + " ".join(_normalise_prose(paragraph))
            removed.add(k)
        folded = [k for k in copies if k in removed]
        if folded:
            result.merged.append(spans[keeper].heading)
            result.source_headings.extend(spans[k].heading for k in [keeper, *folded])

    if not removed:
        return result

    out = lines[:spans[0].start] if spans else lines[:]
    for k, span in enumerate(spans):
        if k in removed:
            continue
        own = lines[span.start:span.end]
        if k in appended:
            while own and not own[-1].strip():   # trailing blanks go after the merge
                own.pop()
            own += [line for p in appended[k] for line in ("", p)] + [""]
        out.extend(own)
    result.content = "\n".join(out)
    return result
