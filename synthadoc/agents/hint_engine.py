# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

SessionMode = Literal["NEW_WIKI", "EXPLORER", "HEALTH_CHECK", "POWER_USER"]

NEW_WIKI: SessionMode = "NEW_WIKI"
EXPLORER: SessionMode = "EXPLORER"
HEALTH_CHECK: SessionMode = "HEALTH_CHECK"
POWER_USER: SessionMode = "POWER_USER"

# ── built-in defaults (never mutated) ────────────────────────────────────────

_BUILTIN_BY_MODE: dict[str, list[str]] = {
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

_BUILTIN_PATTERNS: list[tuple[list[str], list[str]]] = [
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

# ── working copies (reset by configure()) ────────────────────────────────────

_hints_by_mode: dict[str, list[str]] = {k: list(v) for k, v in _BUILTIN_BY_MODE.items()}
_topic_patterns: list[tuple[list[str], list[str]]] = list(_BUILTIN_PATTERNS)
_pool_cache: dict[str, list[str]] = {}


class HintEngine:

    @classmethod
    def configure(cls, hints_path: Path | None = None) -> None:
        """Reset to built-ins and merge hints.json if it exists.

        hints.json schema::

            {
              "by_mode": {
                "EXPLORER": ["Custom hint 1", "Custom hint 2"],
                "MY_ROLE":  ["New role hint"]
              },
              "topic_patterns": [
                { "keywords": ["kubernetes"], "hints": ["How does K8s fit?"] }
              ]
            }

        Entries in by_mode extend (not replace) the built-ins for that mode.
        Custom topic_patterns take priority over built-ins.
        """
        global _hints_by_mode, _topic_patterns, _pool_cache
        _hints_by_mode = {k: list(v) for k, v in _BUILTIN_BY_MODE.items()}
        _topic_patterns = list(_BUILTIN_PATTERNS)
        _pool_cache = {}

        if hints_path is None or not hints_path.exists():
            return

        try:
            data = json.loads(hints_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("HintEngine: could not load %s (%s) — using built-in hints", hints_path, exc)
            return

        for mode, extra in data.get("by_mode", {}).items():
            existing = _hints_by_mode.get(mode, [])
            new_hints = [h for h in extra if isinstance(h, str) and h not in existing]
            _hints_by_mode[mode] = existing + new_hints

        # User patterns prepended so they fire before built-ins
        for pat in reversed(data.get("topic_patterns", [])):
            kws = pat.get("keywords", [])
            hints = pat.get("hints", [])
            if kws and hints:
                _topic_patterns.insert(0, (kws, hints))

        logger.info(
            "HintEngine: loaded %s (%d extra modes, %d extra patterns)",
            hints_path,
            sum(1 for m in data.get("by_mode", {}) if m in _hints_by_mode),
            len(data.get("topic_patterns", [])),
        )

    @staticmethod
    def build_pool(mode: str) -> list[str]:
        """Full hint pool: mode hints first, then other-mode hints (deduped). Cached."""
        if mode not in _pool_cache:
            primary = list(_hints_by_mode.get(mode, _hints_by_mode.get("POWER_USER", [])))
            seen: set[str] = set(primary)
            others: list[str] = []
            for m, hs in _hints_by_mode.items():
                if m == mode:
                    continue
                for h in hs:
                    if h not in seen:
                        seen.add(h)
                        others.append(h)
            _pool_cache[mode] = primary + others
        return _pool_cache[mode]

    @staticmethod
    def initial_hints(mode: SessionMode) -> list[str]:
        return HintEngine.build_pool(mode)[:3]

    @staticmethod
    def after_response(answer: str, mode: SessionMode) -> list[str]:
        """Backward-compatible (no rotation). Used by CLI / query-agent paths."""
        hints, _ = HintEngine.after_response_windowed(answer, mode, 0)
        return hints

    @staticmethod
    def after_response_windowed(
        answer: str, mode: SessionMode, cursor: int
    ) -> tuple[list[str], int]:
        """Returns (next_hints, new_cursor).

        Topic keyword match returns relevant hints without advancing the cursor
        so the rotation position is preserved for the next non-topic query.
        """
        answer_lower = answer.lower()
        for keywords, hints in _topic_patterns:
            if any(kw in answer_lower for kw in keywords):
                return hints[:3], cursor

        pool = HintEngine.build_pool(mode)
        if not pool:
            return [], cursor
        n = 3
        start = cursor % len(pool)
        # Double the pool so a single slice handles wrap-around cleanly
        window = (pool * 2)[start:start + n]
        next_cursor = (start + n) % len(pool)
        return window, next_cursor
