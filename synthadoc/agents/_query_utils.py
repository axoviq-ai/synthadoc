# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from synthadoc.agents._utils import parse_json_string_array

if TYPE_CHECKING:
    from synthadoc.providers.base import LLMProvider

logger = logging.getLogger(__name__)

_MAX_QUESTION_CHARS = 4000
_MAX_SUB_QUESTIONS = 4
_DECOMPOSE_TIMEOUT_SECS = 30.0

# ── CJK ranges (verbatim from query_agent.py) ─────────────────────────────────
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Extension A
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x2E80, 0x2EFF),   # CJK Radicals Supplement
    (0x3000, 0x303F),   # CJK Symbols and Punctuation
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0xAC00, 0xD7AF),   # Hangul Syllables
)


def has_cjk(text: str) -> bool:
    """Return True if *text* contains at least one CJK / Japanese / Korean character."""
    return any(any(lo <= ord(ch) <= hi for lo, hi in _CJK_RANGES) for ch in text)


def detect_cjk_language(text: str) -> str:
    """Return the display language name for the dominant script in *text*.

    Hiragana/katakana → Japanese; hangul → Korean; CJK ideographs only → Chinese.
    """
    for ch in text:
        cp = ord(ch)
        if 0x3041 <= cp <= 0x309F or 0x30A1 <= cp <= 0x30FC:
            return "Japanese"
        if 0xAC00 <= cp <= 0xD7AF:
            return "Korean"
    return "Chinese (Mandarin)"


# ── STOPWORDS (verbatim from query_agent.py) ──────────────────────────────────
# Stopwords excluded when extracting key terms for the content-overlap gap check.
# Keep this list lean — a false positive (treating a content word as a stopword)
# suppresses gap detection; a false negative (missing a stopword) is harmless.
STOPWORDS: frozenset[str] = frozenset({
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "should", "would", "could", "will", "does", "have", "with", "that", "this",
    "they", "them", "their", "there", "then", "than", "also", "well", "just",
    "some", "more", "very", "much", "many", "most", "from", "into", "onto",
    "about", "after", "before", "between", "during", "through",
    "these", "those", "each", "both", "your", "mine", "ours",
    "start", "grow", "good", "best", "make", "need", "want",
    # Relational verbs/nouns used in queries to describe how topics connect
    # ("how did X shape Y?", "what drove Z?", "Unix's influence on...") but
    # never recurring content words in wiki pages — spurious signal gaps result.
    # CJK queries bypass key-term extraction entirely, so these are English-only.
    "shape", "drive", "change", "enable", "allow", "improve", "evolve",
    "influence", "affect", "impact", "cause", "result", "matter", "relate",
    "connect", "involve", "emerge", "remain",
    "consistent", "align", "reflect", "correspond",
    # Analysis/evaluation verbs and structural framing nouns introduced by
    # sub-question decomposition ("How is X assessed?", "What are the components
    # of Y?") — these never repeat twice in a wiki page and cause Signal 5
    # false positives when they become the discriminating term.
    "assess", "assessed", "evaluate", "evaluated", "determine", "determined",
    "measure", "measured", "identify", "identified", "analyze", "analysed",
    "analyze", "analyzed", "examine", "examined", "review", "reviewed",
    "component", "components", "aspect", "aspects", "element", "elements",
    "feature", "features", "factor", "factors", "part", "parts",
    "step", "steps", "stage", "stages", "phase", "phases",
    "approach", "approaches", "method", "methods", "technique", "techniques",
    "process", "processes", "procedure", "procedures",
    # Comparative/analytical framers: "How does X compare to Y?", "What does
    # that imply for Z?", "What does X suggest about Y?", "How do X translate
    # into Y?" — these describe the type of reasoning requested, not content
    # wiki pages repeat ≥2 times.
    "compare", "compares", "compared", "comparison", "comparisons",
    "imply", "implies", "implied", "implication", "implicates",
    "suggest", "suggests", "suggested", "suggestion",
    "indicate", "indicates", "indicated", "indication",
    "infer", "infers", "inferred", "inference",
    "translate", "translates", "translated", "translation",
    # Category abbreviations used in sub-questions by LLM decomposition but
    # not specific named entities: "M&A deal", "ESG risks in M&A" etc.
    # Signal 6 (acronym absent) should not fire for these domain category terms.
    "m&a",
    # Contribution/achievement verbs common in biographical queries
    # ("What did X contribute to Y?", "What did X achieve?") — wiki pages
    # describe actions with specific verbs ("invented", "built") instead.
    "contribute", "achieve", "accomplish", "pioneer", "introduce",
    # Meta-wiki query words: "What topics does this wiki cover?" — "topic" and
    # "cover" describe the wiki's own structure, not page content, so they never
    # appear frequently in pages and always trigger false-positive gap detection.
    "topic", "cover", "scope", "about",
    # Request-framing verbs: "Tell me about X", "Show me X", "Explain X",
    # "Describe X", "Give me …", "Find out about X", "List X".
    # These verbs describe HOW the user wants the answer, not what the wiki
    # covers — they never appear ≥2 times in any page and always produce
    # Signal 5 false positives when they end up in the key-term set.
    "tell", "show", "explain", "describe", "give", "find", "list",
    # Superlative/comparative query qualifiers: "Which company has the highest X?"
    # These are framing words in questions but rarely repeat in content pages —
    # a page saying "GreenField has the highest leverage" won't repeat "highest"
    # twice, so gap Signal 5 fires falsely. These words carry no retrieval signal.
    "highest", "lowest", "largest", "smallest", "biggest", "greater", "lesser",
    "higher", "lower", "worst", "better", "worse", "fastest", "slowest",
    "strongest", "weakest", "richest", "cheapest", "expensive",
    # Measurement-framing nouns: "What are the key metrics/KPIs/figures for X?"
    # Users request data using these wrapper words; wiki pages contain the data
    # itself (revenue, EBITDA, rates) without needing to repeat the wrapper ≥2 times.
    "metric", "metrics", "kpi", "kpis", "indicator", "indicators",
    "statistic", "statistics", "figure", "figures",
    # Structural query framers: "Give me an overview/summary/breakdown/profile of X."
    # "What are the workstreams/considerations/criteria/package for Y?" — M&A jargon
    # that describes how the user wants the answer structured, not recurring page content.
    "overview", "summary", "summaries", "breakdown", "breakdowns",
    "profile", "profiles", "highlight", "highlights",
    "workstream", "workstreams",
    "consideration", "considerations",
    "criterion", "criteria",
    "package", "packages",
    "structure", "structures",
    # Norm-seeking framers: "What is typical/standard/common for X?" — these ask for
    # general practice, not content that pages repeat ≥2 times.
    "typical", "standard", "common", "usual", "normal",
    "general", "generally", "typically", "commonly", "usually",
    # Passive/auxiliary verb forms: "covenants are used to…" — past-tense auxiliaries
    # don't strip to base form via rstrip and rarely appear ≥2 times in wiki pages.
    "used", "uses", "use",
    # Temporal-horizon qualifiers: "near-term", "long-term", "short-term" etc.
    # Hyphens are replaced with spaces during bare-form extraction, so these
    # become two-word key terms like "near term".  Wiki pages rarely repeat a
    # horizon phrase ≥2 times and it carries no retrieval signal anyway.
    "near term", "long term", "short term", "mid term", "medium term",
    "near run", "long run", "short run",
    "near future", "long future",
})


def filter_history_by_language(
    history: list[dict], question: str
) -> list[dict]:
    """Drop turn-pairs where the assistant response is in a different script than
    the current question.

    When a prior assistant turn was (incorrectly) produced in Chinese/Japanese/Korean
    but the current question is in a Latin-script language, that turn biases the LLM
    to repeat the wrong language even when the system prompt says otherwise.  Removing
    the mismatched pair prevents the model from treating it as a precedent.

    Only removes *pairs* (the user turn that preceded the mismatched assistant turn is
    also dropped) so the history remains well-formed user/assistant alternation.
    """
    if not history:
        return history
    question_is_cjk = has_cjk(question)
    filtered: list[dict] = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg["role"] == "assistant":
            response_is_cjk = has_cjk(msg.get("content", ""))
            if question_is_cjk != response_is_cjk:
                # Language mismatch — drop this assistant turn AND its preceding user turn
                if filtered and filtered[-1]["role"] == "user":
                    filtered.pop()
                i += 1
                continue
        filtered.append(msg)
        i += 1
    return filtered


def history_block(history: list[dict], question: str = "") -> str:
    """Format conversation history as a preamble block for the synthesis prompt.

    Filters out turns where the assistant responded in a different script than
    *question* so that a prior incorrect-language response does not bias the model
    into repeating that language.
    """
    if not history:
        return ""
    kept = filter_history_by_language(history, question) if question else history
    if not kept:
        return ""
    lines = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in kept)
    return f"\n[Conversation so far]\n{lines}\n"


def build_synthesis_system(question: str) -> str:
    """Return the language-enforcement system prompt for synthesis.

    Keeping the language rule in the system prompt (rather than only in the
    user-content turn) makes it significantly harder for the LLM to drift
    into the language of conversation-history turns when the current question
    is in a different language.
    """
    lang = detect_cjk_language(question) if has_cjk(question) else ""
    if lang:
        return (
            f"The user's question is in {lang}. "
            f"You MUST respond in {lang}. "
            f"Do not respond in English or any other language, "
            f"regardless of the conversation history."
        )
    return (
        "Respond in the same language as the user's question. "
        "Do NOT use the language of the wiki pages or the conversation history — "
        "always match the language of the current question exactly."
    )


def trim_history(history: list[dict], budget_chars: int) -> list[dict]:
    """Return most-recent turns that fit within budget_chars. Chronological order preserved."""
    result = []
    used = 0
    for turn in reversed(history):
        size = len(turn.get("content", ""))
        if used + size > budget_chars:
            break
        result.append(turn)
        used += size
    return list(reversed(result))


async def decompose_question(
    provider: "LLMProvider",
    question: str,
    timeout_secs: float = _DECOMPOSE_TIMEOUT_SECS,
) -> list[str]:
    """Break question into sub-questions for BM25 retrieval. Returns [question] on any failure."""
    from synthadoc.providers.base import Message
    truncated = question[:_MAX_QUESTION_CHARS]
    try:
        resp = await asyncio.wait_for(
            provider.complete(
                messages=[Message(role="user", content=(
                    "Break this question into focused sub-questions for a knowledge base lookup.\n"
                    "Simple questions should return a single-element list.\n"
                    "Return a JSON array of strings only. No explanation.\n\n"
                    f"Question: {truncated}"
                ))],
                temperature=0.0,
            ),
            timeout=timeout_secs,
        )
    except Exception as exc:
        logger.warning("decompose failed (%s: %s) — falling back to original", type(exc).__name__, exc)
        return [question]
    filtered = parse_json_string_array(resp.text, _MAX_SUB_QUESTIONS)
    if filtered:
        return filtered
    logger.warning("decompose: not a valid JSON array — falling back to original question")
    return [question]
