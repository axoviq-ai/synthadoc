# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""A trusted routing scope must not be judged weak on its own, scope-lowered score.

BM25's IDF is relative to the pages searched, so a correct but narrow routing branch
(biography pages that share vocabulary) scores low in absolute terms. ``_run_search``
already keeps that scoped result when its top page matches the full-corpus top page, but
the knowledge-gap check then compared the low scoped score with the weak-score threshold
and reported a gap for a question the wiki answers (seen live: "Who was Alan Turing?").
The gap check must use the full-corpus score in that case.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synthadoc.agents.query_agent import QueryAgent
from synthadoc.core.routing import RoutingIndex
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiPage, WikiStorage

_THRESHOLD = 2.0


def _page(store: WikiStorage, slug: str, title: str, content: str) -> None:
    store.write_page(slug, WikiPage(title=title, tags=[], status="active",
                                    confidence="high", content=content, sources=[]))


def _wiki(tmp_wiki) -> WikiStorage:
    """Three pioneer pages sharing vocabulary (so their terms are common inside the branch)
    among five unrelated pages (so the same terms are rare in the full corpus)."""
    store = WikiStorage(tmp_wiki / "wiki")
    for slug, who in (("alan-turing", "Alan Turing"), ("grace-hopper", "Grace Hopper"),
                      ("konrad-zuse", "Konrad Zuse")):
        _page(store, slug, who, f"{who} made a major contribution to computing as a pioneer "
                                f"of early computer science.")
    for i in range(5):
        _page(store, f"unrelated-{i}", f"Unrelated Topic {i}",
              f"This page discusses topic {i}, which has nothing to do with computing pioneers.")
    return store


def _agent(tmp_wiki, store: WikiStorage, branch_pages: list[str], *, answer="Turing was a pioneer."):
    routing_path = tmp_wiki / "ROUTING.md"
    RoutingIndex({"Pioneers": branch_pages}).save(routing_path)
    calls = iter([
        CompletionResponse(text='["Who was Turing?"]', input_tokens=10, output_tokens=5),
        CompletionResponse(text='["Pioneers"]', input_tokens=10, output_tokens=5),
    ])

    async def complete(**_kwargs):
        try:
            return next(calls)
        except StopIteration:
            return CompletionResponse(text=answer, input_tokens=50, output_tokens=20)

    provider = AsyncMock()
    provider.complete.side_effect = complete
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    return QueryAgent(provider=provider, store=store, search=search,
                      routing_path=routing_path, gap_score_threshold=_THRESHOLD)


@pytest.mark.asyncio
async def test_a_trusted_scope_reports_the_full_corpus_score_for_the_gap_check(tmp_wiki):
    store = _wiki(tmp_wiki)
    agent = _agent(tmp_wiki, store, ["alan-turing", "grace-hopper", "konrad-zuse"])
    _subs, candidates, warning, gap_score = await agent._search_for_gap("Who was Turing?")
    scoped_max = max(c.score for c in candidates)
    assert warning == "" and all(not c.slug.startswith("unrelated-") for c in candidates)
    assert scoped_max < _THRESHOLD, "scenario must reproduce a scope-lowered score"
    assert gap_score >= _THRESHOLD > scoped_max


@pytest.mark.asyncio
async def test_a_trusted_scope_is_not_reported_as_a_knowledge_gap(tmp_wiki):
    store = _wiki(tmp_wiki)
    agent = _agent(tmp_wiki, store, ["alan-turing", "grace-hopper", "konrad-zuse"])
    result = await agent.run("Who was Turing?")
    assert result.knowledge_gap is False


@pytest.mark.asyncio
async def test_run_search_keeps_its_three_value_contract(tmp_wiki):
    store = _wiki(tmp_wiki)
    agent = _agent(tmp_wiki, store, ["alan-turing", "grace-hopper", "konrad-zuse"])
    subs, candidates, warning = await agent._run_search("Who was Turing?")
    assert subs and candidates and warning == ""


@pytest.mark.asyncio
async def test_without_routing_the_gap_score_is_the_top_candidate_score(tmp_wiki):
    store = _wiki(tmp_wiki)
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["alan turing"]', input_tokens=10, output_tokens=5)
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=_THRESHOLD)
    _subs, candidates, _warning, gap_score = await agent._search_for_gap("alan turing")
    assert gap_score == max(c.score for c in candidates) > 0


@pytest.mark.asyncio
async def test_a_wrong_scope_still_falls_back_and_uses_the_full_corpus_score(tmp_wiki):
    """Routing picked an unrelated page: the fallback to the full corpus still happens,
    with its warning, and the gap score is that of the full-corpus candidates."""
    store = _wiki(tmp_wiki)
    agent = _agent(tmp_wiki, store, ["unrelated-0", "unrelated-1"])
    _subs, candidates, warning, gap_score = await agent._search_for_gap("Who was Turing?")
    assert "ROUTING.md" in warning
    assert candidates[0].slug == "alan-turing"
    assert gap_score == max(c.score for c in candidates)
