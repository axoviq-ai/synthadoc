# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

SessionMode = Literal["NEW_WIKI", "EXPLORER", "HEALTH_CHECK", "POWER_USER"]

_INITIAL_HINT_COUNT = 3

NEW_WIKI: SessionMode = "NEW_WIKI"
EXPLORER: SessionMode = "EXPLORER"
HEALTH_CHECK: SessionMode = "HEALTH_CHECK"
POWER_USER: SessionMode = "POWER_USER"

# ── bundled defaults (hints.json shipped alongside this module) ───────────────

_BUNDLED_HINTS = Path(__file__).parent / "hints.json"

# Minimal emergency fallback used only when hints.json is missing or unreadable
_FALLBACK_BY_MODE: dict[str, list[str]] = {
    "POWER_USER": [
        "What changed in the wiki this week?",
        "Which pages have the most citations?",
        "Export my wiki as llms.txt",
    ],
}
_FALLBACK_PATTERNS: list[tuple[list[str], list[str]]] = []


def _load_hints_file(path: Path) -> tuple[dict[str, list[str]], list[tuple[list[str], list[str]]]]:
    """Parse a hints.json file into (by_mode, topic_patterns). Returns empty structures on error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("HintEngine: could not load %s (%s)", path, exc)
        return {}, []
    by_mode = {
        mode: [h for h in hints if isinstance(h, str)]
        for mode, hints in data.get("by_mode", {}).items()
    }
    patterns = [
        (pat.get("keywords", []), pat.get("hints", []))
        for pat in data.get("topic_patterns", [])
        if pat.get("keywords") and pat.get("hints")
    ]
    return by_mode, patterns

# ── working copies (reset by configure()) ────────────────────────────────────

def _init_working_copies() -> tuple[dict, list, dict]:
    by_mode, patterns = _load_hints_file(_BUNDLED_HINTS)
    if not by_mode:
        by_mode = {k: list(v) for k, v in _FALLBACK_BY_MODE.items()}
        patterns = list(_FALLBACK_PATTERNS)
    return by_mode, patterns, {}


_hints_by_mode, _topic_patterns, _pool_cache = _init_working_copies()


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
        _hints_by_mode, _topic_patterns, _pool_cache = _init_working_copies()

        if hints_path is None or not hints_path.exists():
            return

        extra_by_mode, extra_patterns = _load_hints_file(hints_path)

        for mode, extras in extra_by_mode.items():
            existing = _hints_by_mode.get(mode, [])
            _hints_by_mode[mode] = existing + [h for h in extras if h not in existing]

        # User patterns prepended so they fire before bundled ones
        for kws, hints in reversed(extra_patterns):
            _topic_patterns.insert(0, (kws, hints))

        logger.info(
            "HintEngine: merged %s (%d modes, %d patterns)",
            hints_path, len(extra_by_mode), len(extra_patterns),
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
        return HintEngine.build_pool(mode)[:_INITIAL_HINT_COUNT]

    @staticmethod
    def after_response(answer: str, mode: SessionMode) -> list[str]:
        """Backward-compatible (no rotation). Used by CLI / query-agent paths."""
        hints, _ = HintEngine.after_response_windowed(answer, mode, 0)
        return hints

    @staticmethod
    def after_response_windowed(
        answer: str, mode: SessionMode, cursor: int, *,
        previous_hints: list[str] | None = None,
    ) -> tuple[list[str], int]:
        """Returns (next_hints, new_cursor). Cursor always advances.

        Topic keyword match overrides which hints are shown but does not
        freeze the cursor — rotation continues on every response.
        If a topic match would repeat previous_hints, that pattern is skipped
        so the pool rotation stays visible across consecutive queries.
        """
        pool = HintEngine.build_pool(mode)
        if not pool:
            return [], cursor
        n = 3
        start = cursor % len(pool)
        # Double the pool so a single slice handles wrap-around cleanly
        window = (pool * 2)[start:start + n]
        next_cursor = (start + n) % len(pool)

        # Topic match: show contextually relevant hints but still advance cursor.
        # Skip a match whose hints equal the previous set — breaks feedback loops
        # where common words (e.g. "source", "active") repeatedly fire the same pattern.
        answer_lower = answer.lower()
        for keywords, hints in _topic_patterns:
            if any(kw in answer_lower for kw in keywords):
                topic = hints[:n]
                if previous_hints is None or sorted(topic) != sorted(previous_hints):
                    return topic, next_cursor

        return window, next_cursor
