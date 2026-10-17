# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic, loss-free content-health fixes (no LLM).

Companion to :mod:`synthadoc.agents.content_health_scanner`: the scanner finds
issues, this module repairs the ones that need no judgement and checks that a
proposed rewrite keeps every sentence of the original.
"""
from __future__ import annotations

import re
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
