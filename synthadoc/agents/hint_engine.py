# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import logging
import re
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
        (
            pat.get("keywords", []),
            # answer_keywords: narrower list safe for body-scan; defaults to keywords
            pat.get("answer_keywords", pat.get("keywords", [])),
            pat.get("hints", []),
        )
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


# ── dynamic follow-up hint generation ────────────────────────────────────────

# Scaffold pages that exist in every wiki — not useful as follow-up subjects.
_SCAFFOLD_SLUGS = frozenset({"index", "overview", "purpose", "dashboard"})

# Strips common question-opener phrases so we can extract the core subject.
_QUESTION_PREFIX_RE = re.compile(
    r"^(?:what(?:'s| (?:is|are|were|was|do you know about|does))|"
    r"how (?:does|did|is|are)|"
    r"which|tell me about|explain|describe|"
    r"can you (?:tell me about|explain|describe\s*)?|"
    r"who (?:is|are)|"
    r"why (?:is|did|are))\s+",
    re.IGNORECASE,
)
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
# Second-pass: strip any remaining bare question word that _QUESTION_PREFIX_RE
# missed because it was not followed by a recognised verb (e.g. "What raw…",
# "What file types…", "Which documents…").
_LEADING_QUESTION_WORD_RE = re.compile(
    r"^(?:what|which|who|why|where|when|how)\s+",
    re.IGNORECASE,
)
_TRAILING_STOP_WORDS = frozenset({
    "for", "of", "in", "at", "by", "from", "to",
    "the", "a", "an", "and", "or", "each", "every",
    # Common question-final verbs that are not part of the subject phrase
    "cover", "include", "contain", "discuss", "show",
    "explain", "describe", "mean", "do",
    # Question words that appear after "and" in compound questions
    # (e.g. "What is X and what are Y?" → [:5] ends in "and what")
    "what", "which", "who", "why", "where", "when", "how",
    # Relationship verbs from generated "How does X connect to Y?" hints —
    # when the user re-asks a generated hint, "connect" lands in the subject slice.
    "connect", "relate", "link", "apply", "compare",
})
# Auxiliary / linking verbs that mark the start of a predicate in
# "Which X has/is Y?" questions.  Words at or after these positions are not
# part of the subject phrase and must be dropped before the phrase is used.
_AUX_VERBS = frozenset({
    "is", "are", "was", "were", "be",
    "has", "have", "had",
    "does", "do", "did",
    "will", "would", "can", "could", "should", "may", "might", "must",
})
_HAS_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


def _kw_match(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears as a whole word in text.

    Uses word-boundary matching so 'old' does not fire inside 'threshold',
    'bold', 'folder', etc.  Case-insensitive.
    """
    if not keywords:
        return False
    pattern = r"\b(?:" + "|".join(re.escape(kw) for kw in keywords) + r")\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def _slug_to_title(slug: str) -> str:
    """Convert a wiki slug to a short readable label.

    Strips trailing year/FY qualifiers (e.g. -fy2025, -2025) so the resulting
    phrase fits naturally inside a hint sentence.
    """
    cleaned = re.sub(r"[-_](?:fy)?\d{4}$", "", slug, flags=re.IGNORECASE)
    return cleaned.replace("-", " ").replace("_", " ")


def _dynamic_followup(question: str, answer: str) -> str | None:
    """Return one contextual follow-up question derived from the Q&A pair.

    Iterates all non-scaffold [[wiki-links]] in the answer and returns the
    first hint that is not identical to the question asked (avoids circular
    chips when the answer only cites the same page the question is about).
    Returns None when no usable, non-circular hint can be composed.
    """
    # Extract core subject from the question once — reused for every candidate.
    subject = _QUESTION_PREFIX_RE.sub("", question.strip().rstrip("?")).strip()
    subject = _LEADING_ARTICLE_RE.sub("", subject)
    # Second pass: strip bare question words not caught above (e.g. "What raw…").
    subject = _LEADING_QUESTION_WORD_RE.sub("", subject)
    words = subject.split()[:5]
    # Truncate at the first auxiliary verb — marks start of predicate in
    # "Which X has/is Y?" questions (e.g. "portfolio company has the highest").
    for i, w in enumerate(words):
        if w.lower() in _AUX_VERBS:
            words = words[:i]
            break
    while words and words[-1].lower() in _TRAILING_STOP_WORDS:
        words.pop()
    subject = " ".join(words)

    # Use simple template for CJK, empty, or single-word subjects (too generic
    # for the "How does X connect to Y?" form).
    use_simple = not subject or len(words) < 2 or bool(_HAS_CJK_RE.search(subject))
    subject_words = set(subject.lower().split()) if not use_simple else set()
    q_norm = question.strip().lower().rstrip("?")

    seen_slugs: set[str] = set()
    for m in re.finditer(r"\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]", answer):
        candidate = m.group(1).strip()
        if candidate in _SCAFFOLD_SLUGS or candidate in seen_slugs:
            continue
        seen_slugs.add(candidate)

        title = _slug_to_title(candidate)
        title_words = set(title.lower().split())

        if use_simple or len(subject_words & title_words) >= min(2, len(subject_words)):
            hint = f"What does {title} cover?"
        else:
            hint = f"How does {subject} connect to {title}?"

        if hint.lower().rstrip("?") != q_norm:
            return hint

    return None


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
        for q_kws, a_kws, hints in reversed(extra_patterns):
            _topic_patterns.insert(0, (q_kws, a_kws, hints))

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
        question: str = "",
        previous_hints: list[str] | None = None,
    ) -> tuple[list[str], int]:
        """Returns (next_hints, new_cursor). Cursor always advances.

        Priority order:
        1. Topic keyword match (3 static topic hints, unchanged).
        2. Dynamic follow-up: 2 pool hints + 1 question derived from the Q&A.
        3. Fallback: 3 pool hints from the rotating window.

        Topic match takes full priority so domain-specific guidance is never
        crowded out. Dynamic follow-up fires only when a question is supplied
        and the answer contains at least one non-scaffold [[wiki-link]].
        """
        pool = HintEngine.build_pool(mode)
        if not pool:
            return [], cursor
        n = 3
        start = cursor % len(pool)
        # Double the pool so a single slice handles wrap-around cleanly
        window = (pool * 2)[start:start + n]
        next_cursor = (start + n) % len(pool)

        def _first_topic_match(text: str, use_answer_keywords: bool = False) -> list[str] | None:
            """Return the first matching topic hint set for text, or None.

            use_answer_keywords=True selects each pattern's answer_keywords list,
            which may be narrower than its question keywords to avoid false
            positives on common domain words (e.g. "draft" in financial reports).
            Matching uses word boundaries so 'old' does not fire inside 'threshold'.
            """
            for q_kws, a_kws, hints in _topic_patterns:
                keywords = a_kws if use_answer_keywords else q_kws
                if _kw_match(text, keywords):
                    topic = hints[:n]
                    if previous_hints is None or sorted(topic) != sorted(previous_hints):
                        return topic
            return None

        # Question intent takes priority — the question is the user's actual goal
        # and is far less likely to contain accidental domain keyword matches than
        # the answer body (e.g. "draft" in "September Draft methodology").
        if question:
            topic = _first_topic_match(question, use_answer_keywords=False)
            if topic is not None:
                return topic, next_cursor

        # Answer body: catches emergent signals the question didn't reveal
        # (e.g. the answer surfaces "stale" or "contradiction"). Uses narrower
        # answer_keywords to avoid false positives on common domain words.
        topic = _first_topic_match(answer, use_answer_keywords=True)
        if topic is not None:
            return topic, next_cursor

        # Dynamic follow-up: replace the 3rd pool hint with a question synthesised
        # from the Q&A pair so at least one chip is always contextually relevant.
        if question:
            dynamic = _dynamic_followup(question, answer)
            if dynamic and dynamic not in window:
                return window[:2] + [dynamic], next_cursor

        return window, next_cursor
