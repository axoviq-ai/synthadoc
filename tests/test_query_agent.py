# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for the proportional context budget model in QueryAgent."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from synthadoc.agents.query_agent import QueryAgent
from synthadoc.config import QueryConfig
from synthadoc.storage.search import SearchResult


def _make_mock_store(pages: dict[str, tuple[str, str]]):
    """Return a mock WikiStorage that returns pages by slug.

    pages: {slug: (title, content)}
    """
    store = MagicMock()

    def _read_page(slug):
        if slug not in pages:
            return None
        title, content = pages[slug]
        page = MagicMock()
        page.title = title
        page.content = content
        return page

    store.read_page.side_effect = _read_page
    store.list_pages.return_value = list(pages.keys())
    return store


def _make_candidates(slugs: list[str]) -> list[SearchResult]:
    return [SearchResult(slug=s, score=1.0, title=s, snippet="") for s in slugs]


def _make_agent(query_config: QueryConfig, pages: dict[str, tuple[str, str]]) -> QueryAgent:
    store = _make_mock_store(pages)
    search = MagicMock()
    provider = MagicMock()
    return QueryAgent(
        provider=provider,
        store=store,
        search=search,
        query_config=query_config,
        model="gpt-4",
    )


# ── no top_n param ────────────────────────────────────────────────────────────

def test_query_agent_no_top_n_param():
    """QueryAgent no longer accepts top_n — must raise TypeError if passed."""
    with pytest.raises(TypeError):
        QueryAgent(provider=None, store=None, search=None, top_n=8)


# ── _build_wiki_context ───────────────────────────────────────────────────────

def test_build_wiki_context_respects_budget():
    """Greedy fill stops once the wiki char budget is exhausted."""
    # wiki budget = 1000 tokens * 100% * 4 chars/token = 4000 chars
    cfg = QueryConfig(
        context_window=1000,
        context_wiki_pct=100,
        context_history_pct=0,
        context_system_pct=0,
        context_index_pct=0,
    )
    # Each page produces a chunk slightly over 300 chars (title + 300-char content)
    page_content = "x" * 300
    pages = {f"page-{i}": (f"Title {i}", page_content) for i in range(10)}
    agent = _make_agent(cfg, pages)
    candidates = _make_candidates(list(pages.keys()))

    ctx = agent._build_wiki_context(candidates)
    assert len(ctx) <= 4000


def test_build_wiki_context_skips_purpose_slug():
    """The 'purpose' slug must never appear in built context."""
    cfg = QueryConfig(
        context_window=10_000,
        context_wiki_pct=100,
        context_history_pct=0,
        context_system_pct=0,
        context_index_pct=0,
    )
    pages = {
        "purpose": ("Purpose", "This is the purpose page."),
        "alan-turing": ("Alan Turing", "Alan Turing invented the Turing machine."),
    }
    agent = _make_agent(cfg, pages)
    candidates = _make_candidates(["purpose", "alan-turing"])

    ctx = agent._build_wiki_context(candidates)
    assert "Purpose page" not in ctx
    assert "Alan Turing" in ctx


def test_build_wiki_context_skips_missing_page():
    """Pages that read_page returns None for must be silently skipped."""
    cfg = QueryConfig(
        context_window=10_000,
        context_wiki_pct=100,
        context_history_pct=0,
        context_system_pct=0,
        context_index_pct=0,
    )
    pages = {"real-page": ("Real Page", "Real content.")}
    agent = _make_agent(cfg, pages)
    # Include a slug that doesn't exist in the store
    candidates = _make_candidates(["missing-slug", "real-page"])

    ctx = agent._build_wiki_context(candidates)
    assert "Real content" in ctx


def test_build_wiki_context_empty_candidates():
    """Empty candidate list produces an empty string."""
    cfg = QueryConfig(
        context_window=10_000,
        context_wiki_pct=60,
        context_history_pct=20,
        context_system_pct=15,
        context_index_pct=5,
    )
    agent = _make_agent(cfg, {})
    ctx = agent._build_wiki_context([])
    assert ctx == ""


# ── _trim_history ─────────────────────────────────────────────────────────────

def test_trim_history_drops_oldest_when_over_budget():
    """Newest turns are kept; oldest are dropped when total chars exceed the budget."""
    # history budget = 500 tokens * 100% * 4 chars/token = 2000 chars
    cfg = QueryConfig(
        context_window=500,
        context_wiki_pct=0,
        context_history_pct=100,
        context_system_pct=0,
        context_index_pct=0,
    )
    agent = _make_agent(cfg, {})

    # 10 turns, 500 chars each = 5000 total chars; budget = 2000
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 500}
        for i in range(10)
    ]
    trimmed = agent._trim_history(history)
    total = sum(len(t["content"]) for t in trimmed)
    assert total <= 2000
    # Newest turns must be retained (chronological order preserved)
    assert trimmed == history[len(history) - len(trimmed):]


def test_trim_history_empty_no_error():
    """Empty history list returns empty list without error."""
    cfg = QueryConfig()
    agent = _make_agent(cfg, {})
    assert agent._trim_history([]) == []


def test_trim_history_fits_entirely_within_budget():
    """When history is small enough to fit, all turns are returned unchanged."""
    # budget = 128_000 * 20% * 4 = 102_400 chars (default config, no model override)
    cfg = QueryConfig()
    agent = _make_agent(cfg, {})
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    trimmed = agent._trim_history(history)
    assert trimmed == history


def test_trim_history_preserves_chronological_order():
    """Result must be in the same order as the input (oldest first)."""
    cfg = QueryConfig(
        context_window=100,
        context_wiki_pct=0,
        context_history_pct=100,
        context_system_pct=0,
        context_index_pct=0,
    )
    # budget = 100 * 100% * 4 = 400 chars
    # 6 turns of 100 chars each = 600; only newest 4 fit
    agent = _make_agent(cfg, {})
    history = [{"role": "user", "content": f"msg{i}" + "z" * 95} for i in range(6)]
    trimmed = agent._trim_history(history)
    # verify oldest-to-newest order maintained
    for i in range(len(trimmed) - 1):
        assert trimmed[i]["content"] < trimmed[i + 1]["content"]


# ── _build_synthesis_prompt language instruction ──────────────────────────────

def test_synthesis_prompt_non_cjk_language_instruction():
    """Non-CJK question must include an explicit 'Do not use the language of the Pages' instruction.

    Regression: the old instruction was 'Respond in the same language as the Question' which
    the LLM overrides when source pages are written in a different language (e.g. Japanese wiki
    answering an English question in Japanese).
    """
    cfg = QueryConfig()
    agent = _make_agent(cfg, {})
    prompt = agent._build_synthesis_prompt(
        "What is a Turing machine?",
        "Page content here.",
        gap=False,
        system_ctx="",
        is_live_data=False,
    )
    assert "Do not use the language of the Pages or the conversation history" in prompt
    # Language rule is also enforced via the system prompt; verify the helper
    system = agent._build_synthesis_system("What is a Turing machine?")
    assert "same language" in system
    assert "conversation history" in system


def test_synthesis_prompt_cjk_japanese_language_instruction():
    """CJK (Japanese) question must use the explicit 'Respond in Japanese' prohibition."""
    cfg = QueryConfig()
    agent = _make_agent(cfg, {})
    # Include hiragana so _detect_cjk_language returns "Japanese"
    prompt = agent._build_synthesis_prompt(
        "チューリングマシンとは何ですか？",  # "What is a Turing machine?" in Japanese
        "Page content here.",
        gap=False,
        system_ctx="",
        is_live_data=False,
    )
    # Language rule now lives primarily in the system prompt; prompt still has belt-and-suspenders
    assert "same language" in prompt
    system = agent._build_synthesis_system("チューリングマシンとは何ですか？")
    assert "respond in Japanese" in system.lower() or "Japanese" in system
    assert "Do not respond in English or any other language" in system


# ── _filter_history_by_language / _history_block ─────────────────────────────

from synthadoc.agents.query_agent import _filter_history_by_language, _history_block  # noqa: E402


def test_filter_history_keeps_same_script_turns():
    """English question keeps English assistant turns."""
    history = [
        {"role": "user", "content": "Who is Grace Hopper?"},
        {"role": "assistant", "content": "Grace Hopper was a computer scientist."},
    ]
    result = _filter_history_by_language(history, "When did she die?")
    assert result == history


def test_filter_history_drops_mismatched_script_pair():
    """English question drops a user+assistant pair where assistant responded in Chinese."""
    cjk_response = "她于1992年12月28日去世。"  # Chinese
    history = [
        {"role": "user", "content": "When does he die?"},
        {"role": "assistant", "content": cjk_response},
        {"role": "user", "content": "What year was she born?"},
        {"role": "assistant", "content": "She was born in 1906."},
    ]
    result = _filter_history_by_language(history, "When does he pass away?")
    # The first user+assistant pair (Chinese response) must be dropped
    assert not any(cjk_response in m.get("content", "") for m in result)
    # The second pair (English response) must be kept
    assert any("1906" in m.get("content", "") for m in result)


def test_filter_history_empty_returns_empty():
    """Empty history returns empty list without error."""
    assert _filter_history_by_language([], "hello") == []


def test_history_block_passes_question_to_filter():
    """_history_block with a question filters out cross-script turns."""
    cjk_response = "她于1992年去世。"
    history = [
        {"role": "user", "content": "When does she die?"},
        {"role": "assistant", "content": cjk_response},
    ]
    block = _history_block(history, question="When does she pass away?")
    assert cjk_response not in block


def test_history_block_no_question_keeps_all():
    """_history_block without question keeps all history turns."""
    cjk_response = "她于1992年去世。"
    history = [
        {"role": "user", "content": "When does she die?"},
        {"role": "assistant", "content": cjk_response},
    ]
    block = _history_block(history)
    assert cjk_response in block


def test_build_synthesis_prompt_filters_history_for_english_question():
    """_build_synthesis_prompt strips CJK assistant turns when question is English."""
    cfg = QueryConfig()
    agent = _make_agent(cfg, {})
    cjk_response = "她于1992年去世。"
    history = [
        {"role": "user", "content": "When does she die?"},
        {"role": "assistant", "content": cjk_response},
    ]
    prompt = agent._build_synthesis_prompt(
        "When does she pass away?",
        "Page content here.",
        gap=False,
        system_ctx="",
        is_live_data=False,
        history=history,
    )
    assert cjk_response not in prompt
