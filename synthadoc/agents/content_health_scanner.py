# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure-Python heuristic scanner for wiki content quality issues.

No LLM dependency. Designed to run post-ingest on changed pages only.
Callers receive a list of ContentIssue instances that can be serialised
with dataclasses.asdict() for storage in WikiPage.content_health_issues.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class ContentIssue:
    type: str        # duplicate_section | empty_section | thin_section | unclosed_code_block | orphaned_heading | broken_list_nesting
    severity: str    # critical | high | medium | low
    location: str    # section heading text or "line N"
    description: str


# Issue types the content-health resolver can never fix, because fixing them means
# writing new facts. They stay on the page (and in the lint report) for a human
# editor, but are not offered to the resolver or counted for its hint chip.
REPORT_ONLY_ISSUE_TYPES: frozenset[str] = frozenset({"thin_section"})

# Reference and link sections are short by nature and never flagged as thin.
# Compared after _normalise_heading.
_REFERENCE_HEADINGS: frozenset[str] = frozenset({
    "see also", "sources", "references", "further reading", "external links",
    "related", "related pages", "bibliography", "notes", "citations",
})


def resolvable_issues(issues: list[dict]) -> list[dict]:
    """The subset of stored issues the content-health resolver can act on."""
    return [i for i in issues if i.get("type") not in REPORT_ONLY_ISSUE_TYPES]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_heading(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for heading comparison."""
    text = text.lower()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_code_blocks(content: str) -> str:
    """Replace text inside ``` fences with blank lines.

    Prevents headings inside code examples from triggering false positives.
    """
    return re.sub(r"```.*?```", lambda m: "\n" * m.group().count("\n"), content, flags=re.DOTALL)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


@dataclass
class Section:
    """One heading and its own body (up to the next heading of any level).

    ``start`` is the heading's line index and ``end`` the index of the next
    heading (or EOF), so ``lines[start + 1:end]`` is the body.
    """
    heading: str
    level: int
    start: int
    end: int


def _section_spans(lines: list[str]) -> list[Section]:
    """Return every heading in *lines* with its line range (see :class:`Section`)."""
    heads = [(i, m) for i, line in enumerate(lines) if (m := _HEADING_RE.match(line))]
    return [
        Section(heading=m.group(2).strip(), level=len(m.group(1)), start=i,
                end=heads[k + 1][0] if k + 1 < len(heads) else len(lines))
        for k, (i, m) in enumerate(heads)
    ]


def _extract_sections(clean: str) -> list[tuple[str, str, int]]:
    """Return [(heading_text, body_text, heading_level)] for all headings."""
    lines = clean.split("\n")
    return [(s.heading, "\n".join(lines[s.start + 1:s.end]), s.level) for s in _section_spans(lines)]


def _has_subsections(sections: list[tuple[str, str, int]], k: int) -> bool:
    """True when section *k* is directly followed by a deeper heading (its sub-section)."""
    return k + 1 < len(sections) and sections[k + 1][2] > sections[k][2]


def _subtree_word_count(sections: list[tuple[str, str, int]], k: int) -> int:
    """Words in section *k*'s own body plus all of its sub-sections."""
    level = sections[k][2]
    total = len(sections[k][1].split())
    for _heading, body, sub_level in sections[k + 1:]:
        if sub_level <= level:
            break
        total += len(body.split())
    return total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_page(slug: str, content: str, thin_section_min_words: int = 50) -> list[ContentIssue]:
    """Scan one page's markdown content. Returns issues found, empty list if clean."""
    issues: list[ContentIssue] = []
    clean = _strip_code_blocks(content)
    sections = _extract_sections(clean)

    # 1. duplicate_section — normalise headings and count occurrences
    normalised_counts: dict[str, list[str]] = {}
    for heading, _body, _level in sections:
        key = _normalise_heading(heading)
        normalised_counts.setdefault(key, []).append(heading)
    for _key, headings in normalised_counts.items():
        if len(headings) > 1:
            issues.append(ContentIssue(
                type="duplicate_section",
                severity="critical",
                location=headings[0],
                description=f"Section '{headings[0]}' appears {len(headings)} times",
            ))

    # 2. empty_section and thin_section — H1 is the page title, not a content section.
    # A heading whose content lives in its sub-sections is a parent, not empty, and
    # its length includes those sub-sections.
    for k, (heading, body, level) in enumerate(sections):
        if level < 2:
            continue
        has_subsections = _has_subsections(sections, k)
        word_count = _subtree_word_count(sections, k)
        if not body.split() and not has_subsections:
            issues.append(ContentIssue(
                type="empty_section",
                severity="critical",
                location=heading,
                description=f"Section '## {heading}' has no content",
            ))
        elif (word_count < thin_section_min_words
                and _normalise_heading(heading) not in _REFERENCE_HEADINGS):
            issues.append(ContentIssue(
                type="thin_section",
                severity="high",
                location=heading,
                description=f"Section '## {heading}' has only {word_count} words (min {thin_section_min_words})",
            ))

    # 3. unclosed_code_block — odd fence count on original content
    fence_count = len(re.findall(r"^```", content, re.MULTILINE))
    if fence_count % 2 != 0:
        issues.append(ContentIssue(
            type="unclosed_code_block",
            severity="high",
            location="line 1",
            description=f"Odd number of ``` fences ({fence_count}) — likely unclosed code block",
        ))

    # 4. orphaned_heading — H1 appearing after the first line
    lines = content.split("\n")
    clean_lines = _strip_code_blocks(content).split("\n")
    for i, line in enumerate(clean_lines[1:], start=2):
        if re.match(r"^# [^#]", line):
            issues.append(ContentIssue(
                type="orphaned_heading",
                severity="medium",
                location=f"line {i}",
                description=f"H1 heading '{lines[i - 1].strip()}' appears outside the title position (line {i})",
            ))

    # 5. broken_list_nesting — indent jump not a multiple of 2 or 4
    list_re = re.compile(r"^(\s*)[-*+]\s")
    prev_indent = 0
    for i, line in enumerate(lines, start=1):
        m = list_re.match(line)
        if m:
            indent = len(m.group(1))
            if indent > prev_indent and (indent - prev_indent) not in (2, 4):
                issues.append(ContentIssue(
                    type="broken_list_nesting",
                    severity="medium",
                    location=f"line {i}",
                    description=f"List indent jump of {indent - prev_indent} spaces at line {i} (expected 2 or 4)",
                ))
            prev_indent = indent
        elif not line.startswith((" ", "\t")):
            prev_indent = 0

    return issues


def scan_pages(
    pages: dict[str, str],
    thin_section_min_words: int = 50,
) -> dict[str, list[ContentIssue]]:
    """Scan multiple pages. Returns {slug: [issues]}. Omits clean pages."""
    return {
        slug: issues
        for slug, content in pages.items()
        if (issues := scan_page(slug, content, thin_section_min_words))
    }


def refresh_wiki_health_issues(
    store: "WikiStorage",
    slugs: "list[str] | None" = None,
    thin_section_min_words: int = 50,
    skip_slugs: "frozenset[str]" = frozenset(),
) -> int:
    """Scan all active pages and write back any whose content_health_issues changed.

    Returns the count of pages updated.  Pass *slugs* to restrict to a subset;
    omit it (or pass None) to scan the whole wiki.  Pages in *skip_slugs* and
    pages that are not ACTIVE are always skipped.
    """
    from dataclasses import asdict
    from synthadoc.storage.wiki import LifecycleState

    updated = 0
    for slug in (slugs if slugs is not None else store.list_pages()):
        if slug in skip_slugs:
            continue
        page = store.read_page(slug)
        if page is None or page.status != LifecycleState.ACTIVE:
            continue
        new_issues = [asdict(i) for i in scan_page(slug, page.content or "", thin_section_min_words)]
        if new_issues != (page.content_health_issues or []):
            page.content_health_issues = new_issues
            store.write_page(slug, page)
            updated += 1
    return updated
