# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synthadoc.agents._base import BaseAgent
from synthadoc.agents._utils import parse_json_string_array
from synthadoc.agents.action_agent import ActionAgent
from synthadoc.agents._query_utils import (
    build_synthesis_system, decompose_question, history_block, trim_history,
    strip_answer_tags,
)
from synthadoc.agents.query_agent import QueryResult
from synthadoc.cli._wiki import CROSS_WIKI_ROUTING_PATH   # single source of truth
from synthadoc.providers.base import LLMProvider, Message
logger = logging.getLogger(__name__)

# NOTE: Do NOT define _OPERATION_KEYWORDS here.
# Operation detection is handled entirely by ActionAgent.detect() called in _run().
# Any keyword list here would duplicate ActionAgent's logic and diverge over time.

_MAX_CONTEXT_CHARS = 80_000
_HTTP_TIMEOUT = 15.0
_HISTORY_BUDGET = 4000


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

    async def run(self, question: str, history: list[dict] | None = None) -> QueryResult:  # type: ignore[override]
        return await self._run(question, history)

    async def _run(self, question: str, history: list[dict] | None = None) -> QueryResult:
        # Pre-flight: detect operations → route to local wiki
        # ActionAgent.detect() is a fast regex check — always run, even without orchestrator.
        _action = ActionAgent(
            self._provider,
            self._orchestrator,
            Path(self._registry.get(self._own_wiki_name, {}).get("path", ".")),
        )
        if _action.detect(question, history=None):
            _result = await _action.run(question)
            if _result is not None:
                return QueryResult(
                    question=question,
                    answer=_result.message,
                    citations=[],
                    knowledge_gap=not _result.success,
                    cacheable=False,
                    cross_wiki_skipped=True,
                    cross_wiki_skip_reason="operation detected",
                )

        sub_questions = await decompose_question(self._provider, question)
        target_wikis = await self._wiki_pick(question, sub_questions)

        raw_results: list[Any] = list(await asyncio.gather(
            *[self._fetch_retrieve(base_url, question, sub_questions)
              for _, base_url in target_wikis],
            return_exceptions=True,
        ))

        pages, offline_wikis, warnings = self._merge_results(target_wikis, raw_results)

        if not pages:
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
                    cacheable=False,
                    cross_wiki_offline=offline_wikis,
                    cross_wiki_searched=[n for n, _ in target_wikis],
                )
            return QueryResult(
                question=question,
                answer="No relevant pages found across the queried wikis.",
                citations=[],
                knowledge_gap=True,
                cacheable=False,
                cross_wiki_searched=[n for n, _ in target_wikis],
            )

        purpose_summaries = {
            name: resp.purpose_summary
            for (name, _), resp in zip(target_wikis, raw_results)
            if isinstance(resp, _RetrieveResponse) and resp.purpose_summary
        }

        trimmed_history = trim_history(history or [], _HISTORY_BUDGET)
        context = self._build_cross_wiki_context(pages)
        synthesis_prompt = self._build_cross_wiki_synthesis_prompt(
            question, context, purpose_summaries,
            offline_wikis=offline_wikis, warnings=warnings,
            history=trimmed_history,
        )
        synthesis_system = build_synthesis_system(question)

        resp = await self._provider.complete(
            messages=[Message(role="user", content=synthesis_prompt)],
            system=synthesis_system,
            temperature=0.0,
            max_tokens=self._max_tokens,
        )

        cited_slugs = [
            f"{p['wiki_name']}::{p['slug']}"
            for p in pages[:10]
        ]
        return QueryResult(
            question=question,
            answer=strip_answer_tags(resp.text),
            citations=cited_slugs,
            tokens_used=resp.total_tokens,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            knowledge_gap=False,
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
            name: f"http://127.0.0.1:{entry['port']}"
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
        pages: list[dict] = []
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
            for page in result_pages:
                pages.append({**page, "wiki_name": name})
            if result_routing_warning:
                warnings.append(f"{name}: {result_routing_warning}")
        pages.sort(key=lambda p: p["score"], reverse=True)
        return pages, offline, warnings

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
            "Answer the question using ONLY the pages below.\n"
            "Cite sources as [[wiki-name::PageTitle]].\n"
            "Respond in the same language as the question.\n"
            "Extract all specific facts — dates, numbers, names — even when they appear briefly.\n\n"
            + scope_block + offline_block
            + f"Question: {question}\n\nPages:\n{context}"
        )
