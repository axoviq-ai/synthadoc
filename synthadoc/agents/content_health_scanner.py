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


def _extract_sections(clean: str) -> list[tuple[str, str, int]]:
    """Return [(heading_text, body_text, heading_level)] for all headings."""
    lines = clean.split("\n")
    sections: list[tuple[str, str, int]] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(#{1,6})\s+(.*)", lines[i])
        if m:
            level = len(m.group(1))
            heading = m.group(2).strip()
            body_lines: list[str] = []
            i += 1
            while i < len(lines) and not re.match(r"^#{1,6}\s+", lines[i]):
                body_lines.append(lines[i])
                i += 1
            sections.append((heading, "\n".join(body_lines), level))
        else:
            i += 1
    return sections


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

    # 2. empty_section and thin_section — H1 is the page title, not a content section
    for heading, body, level in sections:
        if level < 2:
            continue
        words = body.split()
        if not words:
            issues.append(ContentIssue(
                type="empty_section",
                severity="critical",
                location=heading,
                description=f"Section '## {heading}' has no content",
            ))
        elif len(words) < thin_section_min_words:
            issues.append(ContentIssue(
                type="thin_section",
                severity="high",
                location=heading,
                description=f"Section '## {heading}' has only {len(words)} words (min {thin_section_min_words})",
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
