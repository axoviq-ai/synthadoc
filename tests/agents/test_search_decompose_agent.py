# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.search_decompose_agent import SearchDecomposeAgent
from synthadoc.providers.base import CompletionResponse


def _make_agent(response_text: str = "", side_effect=None):
    provider = AsyncMock()
    if side_effect:
        provider.complete.side_effect = side_effect
    else:
        provider.complete.return_value = CompletionResponse(
            text=response_text, input_tokens=10, output_tokens=10
        )
    return SearchDecomposeAgent(provider=provider)


# ── happy path ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_returns_keyword_strings():
    """decompose() must return a list of terse search strings from valid JSON."""
    agent = _make_agent('["Canada hardiness zones", "frost dates Canadian cities"]')
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canada hardiness zones", "frost dates Canadian cities"]


@pytest.mark.asyncio
async def test_decompose_single_result_returned_as_list():
    """A single-element JSON array must be returned as a one-element list."""
    agent = _make_agent('["Canadian frost dates"]')
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canadian frost dates"]


@pytest.mark.asyncio
async def test_decompose_caps_at_four():
    """decompose() must cap results at 4 even if the LLM returns more."""
    agent = _make_agent('["a", "b", "c", "d", "e", "f"]')
    result = await agent.decompose("broad topic")
    assert len(result) == 4


@pytest.mark.asyncio
async def test_decompose_strips_markdown_fences():
    """LLMs sometimes wrap JSON in ```json fences — these must be stripped."""
    agent = _make_agent('```json\n["zone map Canada", "frost dates"]\n```')
    result = await agent.decompose("Canadian growing zones")
    assert result == ["zone map Canada", "frost dates"]


@pytest.mark.asyncio
async def test_decompose_filters_whitespace_only_strings():
    """Whitespace-only strings in the LLM array must be filtered out."""
    agent = _make_agent('["valid query", "   ", "\\t", "another valid"]')
    result = await agent.decompose("topic")
    assert result == ["valid query", "another valid"]


# ── fallback cases ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_invalid_json_falls_back():
    """Invalid JSON response must fall back to [query]."""
    agent = _make_agent("not json at all")
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canadian frost dates"]


@pytest.mark.asyncio
async def test_decompose_empty_array_falls_back():
    """Empty JSON array must fall back to [query]."""
    agent = _make_agent("[]")
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canadian frost dates"]


@pytest.mark.asyncio
async def test_decompose_json_object_falls_back():
    """JSON object (not array) must fall back to [query]."""
    agent = _make_agent('{"queries": ["a", "b"]}')
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canadian frost dates"]


@pytest.mark.asyncio
async def test_decompose_all_whitespace_after_filter_falls_back():
    """If all entries are whitespace after filtering, fall back to [query]."""
    agent = _make_agent('["  ", "\\t"]')
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canadian frost dates"]


@pytest.mark.asyncio
async def test_decompose_provider_exception_falls_back():
    """Any provider exception must fall back to [query] — never crash."""
    agent = _make_agent(side_effect=RuntimeError("network error"))
    result = await agent.decompose("Canadian frost dates")
    assert result == ["Canadian frost dates"]


@pytest.mark.asyncio
async def test_decompose_truncates_long_query():
    """Queries longer than 2000 chars must be truncated before the LLM call."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["short result"]', input_tokens=5, output_tokens=5
    )
    agent = SearchDecomposeAgent(provider=provider)
    long_query = "x" * 3000
    await agent.decompose(long_query)
    called_content = provider.complete.call_args[0][0][0].content \
        if provider.complete.call_args[0] else \
        provider.complete.call_args[1]["messages"][0].content
    assert "x" * 2001 not in called_content


# ── prompt shape ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_prompt_requests_search_strings_not_questions():
    """The prompt must explicitly ask for search strings, not questions."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["result"]', input_tokens=5, output_tokens=5
    )
    agent = SearchDecomposeAgent(provider=provider)
    await agent.decompose("topic")
    prompt_text = provider.complete.call_args[0][0][0].content \
        if provider.complete.call_args[0] else \
        provider.complete.call_args[1]["messages"][0].content
    # Must ask for search strings / queries, not sub-questions
    assert any(kw in prompt_text.lower() for kw in ["search string", "search query", "search queries", "keyword"])


# ── site: local-file filter ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_filters_site_local_filename():
    """Suggestions using site: with a local filename (e.g. site:purpose.md) must be removed."""
    agent = _make_agent('["site:purpose.md artificial intelligence wiki topics", "large language models survey 2024"]')
    result = await agent.decompose("What are the key topics in this wiki?")
    assert result == ["large language models survey 2024"]


@pytest.mark.asyncio
async def test_decompose_filters_site_various_extensions():
    """site: with .txt, .pdf, .json, .yaml, .toml, .py extensions must all be filtered."""
    for ext in ("txt", "pdf", "json", "yaml", "toml", "py"):
        agent = _make_agent(f'["site:config.{ext} topic query", "valid search query"]')
        result = await agent.decompose("some topic")
        assert f"site:config.{ext}" not in " ".join(result), f"site:config.{ext} should be filtered"
        assert "valid search query" in result


@pytest.mark.asyncio
async def test_decompose_preserves_valid_site_searches():
    """site: with a real web domain (e.g. site:arxiv.org) must NOT be filtered."""
    agent = _make_agent('["site:arxiv.org transformer attention 2024", "attention mechanism survey"]')
    result = await agent.decompose("transformer attention mechanisms")
    assert result == ["site:arxiv.org transformer attention 2024", "attention mechanism survey"]


@pytest.mark.asyncio
async def test_decompose_all_local_site_falls_back():
    """If all suggestions are site:local and none remain after filter, fall back to [query]."""
    agent = _make_agent('["site:purpose.md topic", "site:config.toml settings"]')
    result = await agent.decompose("What topics does this wiki cover?")
    assert result == ["What topics does this wiki cover?"]


# ── wikipedia URL filter ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_filters_wikipedia_url():
    """Suggestions containing a Wikipedia URL must be removed."""
    agent = _make_agent('["https://en.wikipedia.org/wiki/Knowledge_base", "knowledge base structure"]')
    result = await agent.decompose("wiki knowledge base")
    assert result == ["knowledge base structure"]


@pytest.mark.asyncio
async def test_decompose_filters_wikipedia_url_no_scheme():
    """Wikipedia URL without https:// prefix must also be filtered."""
    agent = _make_agent('["en.wikipedia.org/wiki/Machine_learning", "machine learning overview"]')
    result = await agent.decompose("machine learning")
    assert result == ["machine learning overview"]


@pytest.mark.asyncio
async def test_decompose_filters_other_language_wikipedia():
    """Non-English Wikipedia domains (fr.wikipedia.org etc.) must also be filtered."""
    agent = _make_agent('["fr.wikipedia.org/wiki/Apprentissage_automatique", "machine learning survey"]')
    result = await agent.decompose("machine learning")
    assert result == ["machine learning survey"]


@pytest.mark.asyncio
async def test_decompose_preserves_non_wikipedia_wiki_urls():
    """URLs containing 'wiki' that are NOT Wikipedia must NOT be filtered."""
    agent = _make_agent('["https://wiki.archlinux.org/title/Systemd", "systemd linux service"]')
    result = await agent.decompose("systemd service management")
    assert result == ["https://wiki.archlinux.org/title/Systemd", "systemd linux service"]


# ── performance ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_calls_provider_exactly_once():
    """decompose() must make exactly one LLM call regardless of output count."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["q1", "q2", "q3"]', input_tokens=10, output_tokens=10
    )
    agent = SearchDecomposeAgent(provider=provider)
    await agent.decompose("broad topic")
    assert provider.complete.call_count == 1
