# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from synthadoc.agents._base import BaseAgent
from synthadoc.agents._utils import parse_json_string_array
from synthadoc.agents.action_agent import ActionAgent
from synthadoc.agents._query_utils import (
    STOPWORDS, build_synthesis_system, decompose_question, has_cjk,
    history_block, translate_for_retrieval, trim_history, strip_answer_tags,
)
from synthadoc.agents.query_agent import QueryResult, _guard_c_suppress
from synthadoc.agents.search_decompose_agent import SearchDecomposeAgent
from synthadoc.cli._wiki import CROSS_WIKI_ROUTING_PATH, peer_base_url
from synthadoc.providers.base import LLMProvider, Message
logger = logging.getLogger(__name__)

# NOTE: Do NOT define _OPERATION_KEYWORDS here.
# Operation detection is handled entirely by ActionAgent.detect() called in _run().
# Any keyword list here would duplicate ActionAgent's logic and diverge over time.

_MAX_CONTEXT_CHARS = 80_000
_HTTP_TIMEOUT = 15.0
_HISTORY_BUDGET = 4000

# Any detected operation (lint, ingest, lifecycle changes, agentic workflows,
# etc.) must not actually run while cross-wiki search is enabled: dispatching it
# via ActionAgent.run() here would silently fire the action's real side effects
# (e.g. a lint job genuinely starts) when the user asked expecting a wiki-chat
# answer, with no indication that their request was redirected. Tell the user
# cross-wiki mode itself is what's in the way instead of running anything. #524
_OPERATION_BLOCKED_UNDER_CROSS_WIKI_MESSAGE = (
    "**Actions and agentic workflows** (lint, re-ingestion, contradiction/orphan "
    "resolution, lifecycle changes, etc.) need the full chat session on a single "
    "wiki and can't run while cross-wiki search is enabled.\n\n"
    "Turn off cross-wiki search (deselect the \U0001F310 icon) and ask again to "
    "run this."
)


_NEGATIVE_ADMISSION_RE = re.compile(
    r"\b("
    r"do(?:es)?\s+not\s+contain"
    r"|no\s+information\s+(?:about|on|regarding|in)"
    r"|not\s+mentioned"
    r"|not\s+found\s+in\s+the\s+provided(?:\s+pages)?"
    r"|do(?:es)?\s+not\s+discuss"
    r"|do(?:es)?\s+not\s+provide"
    r"|lack(?:s)?\s+information"
    r"|no\s+mention\s+of"
    r")\b",
    re.IGNORECASE,
)

_GENERIC_QUERY_WORDS: frozenset[str] = frozenset({
    "application", "applications",
    "information", "informations",
    "page", "pages",
    "detail", "details",
    "data", "content", "contents",
    "document", "documents",
    "wiki", "wikis",
    "query", "queries",
    "answer", "answers",
    "question", "questions",
})


def _extract_meaningful_terms(text: str) -> set[str]:
    """Extract non-generic content words and roots for relevance verification."""
    terms: set[str] = set()
    for w in text.split():
        bare = w.lower().rstrip("s'?!.,\"():;").replace("-", " ")
        orig_lower = w.lower().rstrip("'?!.,\"():;")
        if (
            (len(w) >= 4 or (len(w) >= 2 and w.upper() == w))
            and bare not in STOPWORDS
            and orig_lower not in STOPWORDS
            and bare not in _GENERIC_QUERY_WORDS
            and orig_lower not in _GENERIC_QUERY_WORDS
        ):
            for part in bare.split():
                if len(part) >= 3 and part not in STOPWORDS and part not in _GENERIC_QUERY_WORDS:
                    terms.add(part)
                    root = part
                    if root.endswith("ing") and len(root) > 5:
                        root = root[:-3]
                    elif root.endswith("ment") and len(root) > 6:
                        root = root[:-4]
                    elif root.endswith("tion") and len(root) > 6:
                        root = root[:-4]
                    if len(root) >= 3 and root not in STOPWORDS and root not in _GENERIC_QUERY_WORDS:
                        terms.add(root)
    return terms


def _get_question_parts(question: str, sub_questions: list[str] | None = None) -> list[str]:
    """Return distinct question parts, using sub_questions if multi-element, else splitting on conjunctions."""
    if sub_questions and len(sub_questions) > 1:
        return sub_questions
    parts = re.split(r"\s+(?:and|as well as)\s+|[;?]+", question, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [question]


@dataclass
class _RetrieveResponse:
    wiki_name: str
    pages: list[dict]
    purpose_summary: str | None
    routing_warning: str


def _parse_cross_wiki_routing(md: str) -> list[dict]:
    """Parse CROSS_WIKI_ROUTING.md into a list of {wikis, keywords} dicts.

    Last entry with empty keywords is treated as the default fallback.
    """
    rules: list[dict] = []
    current: dict | None = None
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("## "):
            if current is not None:
                rules.append(current)
            current = {"wikis": [], "keywords": []}
        elif current is not None and line.lower().startswith("wikis:"):
            current["wikis"] = [w.strip() for w in line[6:].split(",") if w.strip()]
        elif current is not None and line.lower().startswith("keywords:"):
            current["keywords"] = [k.strip() for k in line[9:].split(",") if k.strip()]
    if current is not None:
        rules.append(current)
    return rules


def _pick_wikis_from_routing(question: str, rules: list[dict]) -> list[str]:
    """Return wiki list from first matching rule; last rule (empty keywords) is default."""
    q = question.lower()
    default: list[str] | None = None
    for rule in rules:
        if not rule["keywords"]:
            default = rule["wikis"]
            continue
        if any(kw.lower() in q for kw in rule["keywords"]):
            return rule["wikis"]
    return default or []


class CrossWikiQueryAgent(BaseAgent):
    def __init__(
        self,
        provider: LLMProvider,
        registry: dict,
        own_wiki_name: str,
        cross_wiki_routing_path: Path | None = None,
        http_timeout_secs: float = _HTTP_TIMEOUT,
        max_tokens: int = 8192,
        orchestrator: object | None = None,
        gap_score_threshold: float = 2.0,
    ) -> None:
        super().__init__(provider)
        self._registry = registry
        self._own_wiki_name = own_wiki_name
        # CROSS_WIKI_ROUTING_PATH imported from cli._wiki — single source of truth
        self._routing_path = cross_wiki_routing_path or (
            CROSS_WIKI_ROUTING_PATH if CROSS_WIKI_ROUTING_PATH.exists() else None
        )
        self._http_timeout = http_timeout_secs
        self._max_tokens = max_tokens
        self._orchestrator = orchestrator
        self._gap_score_threshold = gap_score_threshold

    async def run(  # type: ignore[override]
        self,
        question: str,
        history: list[dict] | None = None,
        on_wikis_selected: Callable[[list[str]], None] | None = None,
    ) -> QueryResult:
        return await self._run(question, history, on_wikis_selected=on_wikis_selected)

    async def _run(
        self,
        question: str,
        history: list[dict] | None = None,
        on_wikis_selected: Callable[[list[str]], None] | None = None,
    ) -> QueryResult:
        # Pre-flight: detect operations → route to local wiki
        # ActionAgent.detect() is a fast regex check — always run, even without orchestrator.
        _action = ActionAgent(
            self._provider,
            self._orchestrator,
            Path(self._registry.get(self._own_wiki_name, {}).get("path", ".")),
        )
        if _action.detect(question, history=None):
            # classify() runs the same LLM extraction _run() would, but never
            # calls _dispatch() — a genuine action's side effects (e.g. a lint
            # job actually starting) must never fire here. It also resolves
            # detect()'s own false positives: "how do I roll back a Kubernetes
            # deployment?" matches the fast regex pre-check's literal "roll
            # back" substring but isn't a synthadoc action, and must fall
            # through to normal cross-wiki search rather than being blocked.
            # Guard the LLM call: if classify() throws (provider error, timeout)
            # fall through to normal search rather than returning a 500.
            try:
                action_type = await _action.classify(question)
            except Exception as exc:
                logger.warning("cross-wiki classify() failed (%s) — falling through to search", exc)
                action_type = None
            if action_type is not None:
                if on_wikis_selected is not None:
                    on_wikis_selected([])
                return QueryResult(
                    question=question,
                    answer=_OPERATION_BLOCKED_UNDER_CROSS_WIKI_MESSAGE,
                    citations=[],
                    knowledge_gap=False,
                    cacheable=False,
                    cross_wiki_skipped=True,
                    cross_wiki_skip_reason="operation detected",
                )

        # Translate CJK queries to English so BM25 on peer wikis can match
        # English page content.  The original question is preserved for synthesis
        # so the user still receives a response in their language.
        retrieval_question = question
        if has_cjk(question):
            retrieval_question = await translate_for_retrieval(self._provider, question)

        sub_questions = await decompose_question(self._provider, retrieval_question)
        target_wikis = await self._wiki_pick(question, sub_questions)
        if on_wikis_selected is not None:
            on_wikis_selected([n for n, _ in target_wikis])

        raw_results: list[Any] = list(await asyncio.gather(
            *[self._fetch_retrieve(base_url, question, sub_questions)
              for _, base_url in target_wikis],
            return_exceptions=True,
        ))

        pages, offline_wikis, warnings = self._merge_results(target_wikis, raw_results)

        purpose_summaries = {
            name: resp.purpose_summary
            for (name, _), resp in zip(target_wikis, raw_results)
            if isinstance(resp, _RetrieveResponse) and resp.purpose_summary
        }
        domain_ctx = "; ".join(f"{name}: {s}" for name, s in purpose_summaries.items()) if purpose_summaries else ""

        if not pages:
            try:
                suggested = await SearchDecomposeAgent(self._provider).run(
                    retrieval_question, domain_context=domain_ctx
                ) or [retrieval_question]
            except Exception as exc:
                logger.warning("SearchDecomposeAgent failed: %s", exc)
                suggested = [retrieval_question]

            if offline_wikis:
                offline_str = ", ".join(offline_wikis)
                return QueryResult(
                    question=question,
                    answer=(
                        f"All target wikis were offline ({offline_str}) — no results available. "
                        f"Run `synthadoc serve --all --background` to start them."
                    ),
                    citations=[],
                    knowledge_gap=True,
                    suggested_searches=suggested,
                    cacheable=False,
                    cross_wiki_offline=offline_wikis,
                    cross_wiki_searched=[n for n, _ in target_wikis],
                )
            return QueryResult(
                question=question,
                answer="No relevant pages found across the queried wikis.",
                citations=[],
                knowledge_gap=True,
                suggested_searches=suggested,
                cacheable=False,
                cross_wiki_searched=[n for n, _ in target_wikis],
            )

        trimmed_history = trim_history(history or [], _HISTORY_BUDGET)
        context = self._build_cross_wiki_context(pages)
        synthesis_prompt = self._build_cross_wiki_synthesis_prompt(
            question, context, purpose_summaries,
            offline_wikis=offline_wikis, warnings=warnings,
            history=trimmed_history,
        )
        synthesis_system = build_synthesis_system(question)

        try:
            resp = await self._provider.complete(
                messages=[Message(role="user", content=synthesis_prompt)],
                system=synthesis_system,
                temperature=0.0,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            logger.error("cross-wiki synthesis LLM call failed: %s", exc)
            return QueryResult(
                question=question,
                answer=(
                    "The synthesis step could not be completed due to a provider error. "
                    "Pages were retrieved but could not be synthesised into an answer."
                ),
                citations=[],
                knowledge_gap=True,
                suggested_searches=[],
                cacheable=False,
                routing_warning=str(exc),
                cross_wiki_offline=offline_wikis,
                cross_wiki_searched=[n for n, _ in target_wikis],
            )

        answer_text = strip_answer_tags(resp.text)
        knowledge_gap = False
        suggested: list[str] = []

        matching_cited_pages = [
            f"{p['wiki_name']}::{p['slug']}"
            for p in pages[:10]
            if f"{p['wiki_name']}::{p['slug']}" in answer_text
            or (bool(p.get("title")) and f"{p['wiki_name']}::{p['title']}" in answer_text)
            or f"[[{p['slug']}]]" in answer_text
            or (bool(p.get("title")) and f"[[{p['title']}]]" in answer_text)
            or (bool(p.get("title")) and p["title"] in answer_text)
        ]

        cited_page_objs = [
            p for p in pages
            if f"{p['wiki_name']}::{p['slug']}" in matching_cited_pages
            or (bool(p.get("title")) and f"{p['wiki_name']}::{p['title']}" in matching_cited_pages)
            or (bool(p.get("title")) and f"[[{p['title']}]]" in answer_text)
            or (bool(p.get("title")) and p["title"] in answer_text)
            or f"[[{p['slug']}]]" in answer_text
        ]
        cited_text = " ".join(
            f"{p.get('title', '')} {p.get('content', '')} {p.get('slug', '').replace('-', ' ')}"
            for p in cited_page_objs
        ).lower()

        parts = _get_question_parts(retrieval_question, sub_questions)
        parts_with_terms = [
            (part, _extract_meaningful_terms(part))
            for part in parts
        ]
        parts_with_terms = [(part, terms) for part, terms in parts_with_terms if terms]
        uncovered_parts = [
            part for part, terms in parts_with_terms
            if not any(t in cited_text for t in terms)
        ]

        has_negative_admission = bool(_NEGATIVE_ADMISSION_RE.search(answer_text))
        starts_with_gap = answer_text.startswith("[GAP]")

        if starts_with_gap:
            answer_text = answer_text[len("[GAP]"):].lstrip("\n")
            knowledge_gap = True
        elif has_negative_admission and (uncovered_parts or not matching_cited_pages):
            knowledge_gap = True
        else:
            max_score = max((p.get("score", 0.0) for p in pages), default=0.0)
            if max_score < self._gap_score_threshold:
                if not matching_cited_pages or not parts_with_terms:
                    knowledge_gap = _guard_c_suppress(True, answer_text, "cross_wiki")
                else:
                    if not uncovered_parts:
                        knowledge_gap = False
                    else:
                        knowledge_gap = _guard_c_suppress(True, answer_text, "cross_wiki")

        if knowledge_gap:
            decompose_query = retrieval_question
            if not starts_with_gap and uncovered_parts and len(uncovered_parts) < len(parts_with_terms):
                decompose_query = " ".join(uncovered_parts)

            try:
                suggested = await SearchDecomposeAgent(self._provider).run(
                    decompose_query, domain_context=domain_ctx
                ) or [decompose_query]
            except Exception as exc:
                logger.warning("SearchDecomposeAgent failed: %s", exc)
                suggested = [decompose_query]
            cited_slugs = matching_cited_pages
        else:
            cited_slugs = [
                f"{p['wiki_name']}::{p['slug']}"
                for p in pages[:10]
            ]

        return QueryResult(
            question=question,
            answer=answer_text,
            citations=cited_slugs,
            tokens_used=resp.total_tokens,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            knowledge_gap=knowledge_gap,
            suggested_searches=suggested,
            routing_warning="; ".join(warnings) if warnings else "",
            cacheable=True,
            cross_wiki_offline=offline_wikis,
            cross_wiki_searched=[n for n, _ in target_wikis],
        )

    async def _wiki_pick(
        self, question: str, sub_questions: list[str]
    ) -> list[tuple[str, str]]:
        """Return [(wiki_name, base_url)] for wikis to query. Always includes own_wiki."""
        all_wikis = {
            name: peer_base_url(entry)
            for name, entry in self._registry.items()
            if "port" in entry
        }

        # Try CROSS_WIKI_ROUTING.md first
        selected_names: list[str] | None = None
        if self._routing_path and self._routing_path.exists():
            try:
                md = self._routing_path.read_text(encoding="utf-8")
                rules = _parse_cross_wiki_routing(md)
                picked = _pick_wikis_from_routing(question, rules)
                if picked:
                    selected_names = picked
            except Exception as exc:
                logger.warning("CROSS_WIKI_ROUTING.md parse error: %s — falling back to LLM", exc)

        # LLM auto-routing
        if selected_names is None:
            wiki_list = "\n".join(
                f"- {name}: {entry.get('purpose_summary') or name}"
                for name, entry in self._registry.items()
            )
            prompt = (
                f"You are routing a query to the most relevant knowledge wikis.\n\n"
                f"Available wikis:\n{wiki_list}\n\n"
                f"Question: {question}\n"
                f"Sub-questions: {sub_questions}\n\n"
                f"Return a JSON array of wiki names likely to contain relevant information. "
                f"Include at most 3 wikis. Return only the array, no explanation."
            )
            try:
                resp = await asyncio.wait_for(
                    self._provider.complete(
                        messages=[Message(role="user", content=prompt)],
                        temperature=0.0,
                        max_tokens=100,
                    ),
                    timeout=15.0,
                )
                parsed = parse_json_string_array(resp.text, 5)
                selected_names = parsed or list(all_wikis.keys())
            except Exception as exc:
                logger.warning("_wiki_pick LLM call failed: %s — using all wikis", exc)
                selected_names = list(all_wikis.keys())

        # Always include own wiki; filter to registered wikis only
        valid = {n for n in all_wikis}
        selected = [n for n in selected_names if n in valid]
        if self._own_wiki_name not in selected and self._own_wiki_name in valid:
            selected.append(self._own_wiki_name)
        if not selected:
            selected = list(all_wikis.keys())

        return [(name, all_wikis[name]) for name in selected if name in all_wikis]

    async def _fetch_retrieve(
        self, base_url: str, question: str, sub_questions: list[str]
    ) -> _RetrieveResponse:
        import httpx
        payload = {"question": question, "sub_questions": sub_questions, "top_k": 10}
        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            resp = await client.post(f"{base_url}/retrieve", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return _RetrieveResponse(
            wiki_name=data["wiki_name"],
            pages=data.get("pages", []),
            purpose_summary=data.get("purpose_summary"),
            routing_warning=data.get("routing_warning", ""),
        )

    def _merge_results(
        self,
        target_wikis: list[tuple[str, str]],
        raw_results: list[Any],
    ) -> tuple[list[dict], list[str], list[str]]:
        ranked: list[tuple[int, dict]] = []   # (rank within its wiki, page)
        offline: list[str] = []
        warnings: list[str] = []
        for (name, _), result in zip(target_wikis, raw_results):
            if isinstance(result, Exception):
                logger.warning("wiki %s offline: %s", name, result)
                offline.append(name)
                continue
            # Support both _RetrieveResponse objects and plain dicts (e.g. in tests)
            if isinstance(result, dict):
                result_pages = result.get("pages", [])
                result_routing_warning = result.get("routing_warning", "")
            else:
                result_pages = result.pages
                result_routing_warning = result.routing_warning
            ranked += [(rank, {**page, "wiki_name": name}) for rank, page in enumerate(result_pages, 1)]
            if result_routing_warning:
                warnings.append(f"{name}: {result_routing_warning}")
        # Each wiki returns its pages best first. Raw scores are not comparable
        # across wikis (BM25 depends on each corpus; fused ranks are another
        # scale), so interleave by position: every wiki's best page comes first.
        ranked.sort(key=lambda item: item[0])   # stable: equal ranks keep wiki order
        return [page for _, page in ranked], offline, warnings

    def _build_cross_wiki_context(self, pages: list[dict]) -> str:
        parts: list[str] = []
        used = 0
        for p in pages:
            chunk = f"### [{p['wiki_name']}] {p['title']}\n{p['content']}"
            if used + len(chunk) > _MAX_CONTEXT_CHARS:
                remaining = _MAX_CONTEXT_CHARS - used
                if remaining > 100:
                    parts.append(chunk[:remaining])
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n\n".join(parts)

    def _build_cross_wiki_synthesis_prompt(
        self,
        question: str,
        context: str,
        purpose_summaries: dict[str, str],
        *,
        offline_wikis: list[str],
        warnings: list[str],
        history: list[dict],
    ) -> str:
        prefix = history_block(history, question) if history else ""
        scope_block = ""
        if purpose_summaries:
            lines = "\n".join(f"- {name}: {summary}" for name, summary in purpose_summaries.items())
            scope_block = f"Wiki scopes:\n{lines}\n\n"
        offline_block = ""
        if offline_wikis:
            offline_str = ", ".join(offline_wikis)
            offline_block = (
                f"NOTE: The following wikis were offline and could not be searched: {offline_str}. "
                f"Results are from available wikis only.\n\n"
            )
        return prefix + (
            "You are answering from content drawn from multiple knowledge wikis.\n"
            "Each page is labeled with its source wiki in brackets, e.g. [finance-wiki].\n"
            "Answer the question using the pages below.\n"
            "Cite sources as [[wiki-name::PageTitle]].\n"
            "Respond in the same language as the question.\n"
            "Extract all specific facts — dates, numbers, names — even when they appear briefly.\n"
            "If the pages below do not answer the question, start your reply with [GAP] on its own line; "
            "if they do answer it, do not write [GAP].\n\n"
            + scope_block + offline_block
            + f"Question: {question}\n\nPages:\n{context}"
        )
