# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

_HINTS_BY_MODE: dict[str, list[str]] = {
    "NEW_WIKI": [
        "How do I ingest my first document?",
        "What sources can Synthadoc ingest?",
        "How do I set up a scheduled ingest?",
    ],
    "EXPLORER": [
        "What topics does this wiki cover?",
        "Show me a summary of the most-cited pages",
        "What are the stale pages in my wiki?",
    ],
    "HEALTH_CHECK": [
        "Which pages are marked stale?",
        "Show me pages with contradictions",
        "How do I run a lint check?",
    ],
    "POWER_USER": [
        "What changed in the wiki this week?",
        "Which pages have the most citations?",
        "Export my wiki as llms.txt",
    ],
}

_TOPIC_HINT_PATTERNS: list[tuple[list[str], list[str]]] = [
    (
        ["stale", "outdated", "old"],
        ["How do I mark a page as active?", "Run: synthadoc lint", "Which pages need review?"],
    ),
    (
        ["ingest", "source", "document", "pdf", "url"],
        ["What file types can I ingest?", "How do I bulk ingest?", "How do I re-ingest with --force?"],
    ),
    (
        ["export", "llms", "graph", "json"],
        ["Export as llms.txt for AI tools", "Export as GraphML", "Filter export by lifecycle state"],
    ),
    (
        ["lifecycle", "active", "archive", "draft"],
        ["How do lifecycle states work?", "How do I archive a page?", "What is candidates staging?"],
    ),
]


class HintEngine:
    @staticmethod
    def initial_hints(mode: str) -> list[str]:
        return _HINTS_BY_MODE.get(mode, _HINTS_BY_MODE["POWER_USER"])

    @staticmethod
    def after_response(answer: str, mode: str) -> list[str]:
        answer_lower = answer.lower()
        for keywords, hints in _TOPIC_HINT_PATTERNS:
            if any(kw in answer_lower for kw in keywords):
                return hints
        return _HINTS_BY_MODE.get(mode, _HINTS_BY_MODE["POWER_USER"])
