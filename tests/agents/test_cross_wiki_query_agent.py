# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.agents.cross_wiki_query_agent import CrossWikiQueryAgent

REGISTRY = {
    "coordinator": {"path": "/wikis/coord", "port": 7070, "purpose_summary": "Finance domain"},
    "target":      {"path": "/wikis/target", "port": 7071, "purpose_summary": "Legal domain"},
}

def _make_provider(answer="Test answer [[Page1]]"):
    provider = MagicMock()
    resp = MagicMock()
    resp.text = answer
    resp.total_tokens = 100
    resp.input_tokens = 80
    resp.output_tokens = 20
    provider.complete = AsyncMock(return_value=resp)
    return provider

@pytest.mark.asyncio
async def test_run_returns_query_result():
    provider = _make_provider()
    agent = CrossWikiQueryAgent(
        provider=provider,
        registry=REGISTRY,
        own_wiki_name="coordinator",
    )
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "due-diligence", "title": "Due Diligence", "score": 3.5, "content": "DD content"}],
        "purpose_summary": "Legal domain",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        result = await agent.run("what are the DD requirements?")
    assert result.answer == "Test answer [[Page1]]"
    assert result.knowledge_gap is False

@pytest.mark.asyncio
async def test_offline_wiki_degraded_gracefully():
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    # coordinator returns pages, target raises (offline)
    coord_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "valuation", "title": "Valuation", "score": 4.0, "content": "val content"}],
        "purpose_summary": "Finance",
        "routing_warning": "",
    }
    async def fetch_side_effect(base_url, question, sub_qs):
        if "7070" in base_url:
            return coord_resp
        raise ConnectionError("offline")
    with patch.object(agent, "_fetch_retrieve", fetch_side_effect):
        result = await agent.run("what is the valuation methodology?")
    assert "coordinator" in result.cross_wiki_searched
    assert "target" in result.cross_wiki_offline
    assert result.answer  # still got an answer from coordinator

@pytest.mark.asyncio
async def test_all_wikis_offline_knowledge_gap():
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    with patch.object(agent, "_fetch_retrieve", AsyncMock(side_effect=ConnectionError("offline"))):
        result = await agent.run("anything?")
    assert result.knowledge_gap is True
    assert len(result.cross_wiki_offline) > 0

@pytest.mark.asyncio
async def test_cross_wiki_skipped_for_action():
    """ActionAgent.detect() → cross_wiki_skipped, routed to local."""
    from synthadoc.agents.query_agent import QueryResult as QR
    local_result = QR(question="run lint", answer="Starting lint...", citations=[])
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    with patch("synthadoc.agents.cross_wiki_query_agent.ActionAgent") as MockAction:
        action_inst = MagicMock()
        action_inst.detect.return_value = True
        action_inst.run = AsyncMock(return_value=MagicMock(message="Lint started", success=True))
        MockAction.return_value = action_inst
        result = await agent.run("run lint")
    assert result.cross_wiki_skipped is True

@pytest.mark.asyncio
async def test_wiki_pick_lm_parses_json():
    provider = _make_provider()
    resp = MagicMock()
    resp.text = '["coordinator", "target"]'
    resp.total_tokens = 10
    provider.complete = AsyncMock(return_value=resp)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    picked = await agent._wiki_pick("what is leverage?", ["what is leverage?"])
    names = [name for name, _ in picked]
    assert "coordinator" in names
    assert "target" in names

@pytest.mark.asyncio
async def test_wiki_pick_always_includes_own():
    provider = _make_provider()
    resp = MagicMock()
    resp.text = '["target"]'  # LLM only picks target
    resp.total_tokens = 10
    provider.complete = AsyncMock(return_value=resp)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    picked = await agent._wiki_pick("anything", ["anything"])
    names = [name for name, _ in picked]
    assert "coordinator" in names  # always included

def test_cross_wiki_routing_md_parsed():
    from synthadoc.agents.cross_wiki_query_agent import _parse_cross_wiki_routing
    md = """# Cross-Wiki Routing

## finance queries
wikis: finance-wiki, legal-wiki
keywords: M&A, LBO, valuation

## default
wikis: finance-wiki, legal-wiki, ops-wiki
"""
    rules = _parse_cross_wiki_routing(md)
    assert len(rules) == 2
    finance = rules[0]
    assert "finance-wiki" in finance["wikis"]
    assert "lbo" in [k.lower() for k in finance["keywords"]]

def test_cross_wiki_routing_md_keyword_match():
    from synthadoc.agents.cross_wiki_query_agent import _pick_wikis_from_routing
    rules = [
        {"wikis": ["finance-wiki", "legal-wiki"], "keywords": ["M&A", "LBO", "valuation"]},
        {"wikis": ["finance-wiki", "legal-wiki", "ops-wiki"], "keywords": []},  # default
    ]
    result = _pick_wikis_from_routing("what is the LBO valuation?", rules)
    assert result == ["finance-wiki", "legal-wiki"]

def test_cross_wiki_routing_md_default_fallback():
    from synthadoc.agents.cross_wiki_query_agent import _pick_wikis_from_routing
    rules = [
        {"wikis": ["finance-wiki"], "keywords": ["M&A"]},
        {"wikis": ["finance-wiki", "ops-wiki"], "keywords": []},  # default
    ]
    result = _pick_wikis_from_routing("how do I deploy the app?", rules)
    assert result == ["finance-wiki", "ops-wiki"]  # default


@pytest.mark.asyncio
async def test_no_pages_no_offline_returns_gap():
    """All wikis return empty pages with no offline → knowledge_gap=True (line 151)."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    empty_resp = {"wiki_name": "coordinator", "pages": [], "purpose_summary": "", "routing_warning": ""}
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=empty_resp)):
        result = await agent.run("what is the conversion ratio?")
    assert result.knowledge_gap is True
    assert result.cross_wiki_offline == []


@pytest.mark.asyncio
async def test_wiki_pick_uses_routing_file(tmp_path):
    """When routing file exists and matches keywords, uses it (lines 213-220)."""
    routing_file = tmp_path / "CROSS_WIKI_ROUTING.md"
    routing_file.write_text("## finance\nwikis: coordinator\nkeywords: leverage\n")
    provider = _make_provider()
    agent = CrossWikiQueryAgent(
        provider=provider, registry=REGISTRY, own_wiki_name="coordinator",
        cross_wiki_routing_path=routing_file,
    )
    retrieve_resp = {"wiki_name": "coordinator", "pages": [
        {"slug": "lev", "title": "Leverage", "score": 4.0, "content": "leverage info"}
    ], "purpose_summary": "Finance", "routing_warning": ""}
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        result = await agent.run("what is leverage?")
    assert result.answer


@pytest.mark.asyncio
async def test_wiki_pick_lm_failure_falls_back_to_all():
    """LLM call raises → _wiki_pick falls back to all wikis (lines 247-249)."""
    provider = _make_provider()
    provider.complete = AsyncMock(side_effect=RuntimeError("API error"))
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    picked = await agent._wiki_pick("anything?", ["anything?"])
    picked_names = [name for name, _ in picked]
    assert "coordinator" in picked_names
    assert "target" in picked_names


@pytest.mark.asyncio
async def test_merge_results_with_retrieve_response_object_and_warning():
    """_merge_results handles _RetrieveResponse objects and routing_warning (lines 298-299, 303)."""
    from synthadoc.agents.cross_wiki_query_agent import _RetrieveResponse
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    resp_obj = _RetrieveResponse(
        wiki_name="coordinator",
        pages=[{"slug": "p", "title": "P", "score": 2.0, "content": "page content"}],
        purpose_summary="Finance",
        routing_warning="partial index",
    )
    target_wikis = [("coordinator", "http://127.0.0.1:7070")]
    raw_results = [resp_obj]
    pages, offline, warnings = agent._merge_results(target_wikis, raw_results)
    assert len(pages) == 1
    assert pages[0]["wiki_name"] == "coordinator"
    assert any("partial index" in w for w in warnings)


def test_build_context_truncates_long_content():
    """Context builder truncates when total exceeds _MAX_CONTEXT_CHARS (lines 313-314)."""
    from synthadoc.agents.cross_wiki_query_agent import CrossWikiQueryAgent, _MAX_CONTEXT_CHARS
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    big_content = "x" * (_MAX_CONTEXT_CHARS + 500)
    pages = [
        {"wiki_name": "coordinator", "title": "A", "score": 5.0, "content": big_content},
        {"wiki_name": "target", "title": "B", "score": 4.0, "content": "short"},
    ]
    ctx = agent._build_cross_wiki_context(pages)
    assert len(ctx) <= _MAX_CONTEXT_CHARS + 200  # truncated


@pytest.mark.asyncio
async def test_fetch_retrieve_builds_correct_payload():
    """_fetch_retrieve posts to /retrieve and returns a _RetrieveResponse (lines 259-273)."""
    from synthadoc.agents.cross_wiki_query_agent import CrossWikiQueryAgent, _RetrieveResponse
    from unittest.mock import AsyncMock, MagicMock, patch
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={
        "wiki_name": "target",
        "pages": [{"slug": "p", "title": "P", "score": 1.0, "content": "c"}],
        "purpose_summary": "Legal",
        "routing_warning": "",
    })
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await agent._fetch_retrieve("http://127.0.0.1:7071", "what is leverage?", ["what is leverage?"])

    assert isinstance(result, _RetrieveResponse)
    assert result.wiki_name == "target"
    assert len(result.pages) == 1


@pytest.mark.asyncio
async def test_wiki_pick_invalid_llm_names_falls_back_to_all():
    """LLM returns names not in registry → selected is empty → falls back to all (line 252)."""
    provider = _make_provider()
    resp = MagicMock()
    resp.text = '["nonexistent-wiki-x", "nonexistent-wiki-y"]'
    resp.total_tokens = 10
    provider.complete = AsyncMock(return_value=resp)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="not-in-registry")
    picked = await agent._wiki_pick("anything?", ["anything?"])
    picked_names = [name for name, _ in picked]
    # Fallback: all wikis returned since selected was empty
    assert len(picked_names) > 0


@pytest.mark.asyncio
async def test_wiki_pick_routing_parse_error_falls_back_to_llm(tmp_path):
    """Routing file parse raises → logs warning and falls back to LLM (lines 214-215)."""
    from synthadoc.agents.cross_wiki_query_agent import _parse_cross_wiki_routing
    routing_file = tmp_path / "CROSS_WIKI_ROUTING.md"
    routing_file.write_text("## finance\nwikis: coordinator\nkeywords: leverage\n")
    provider = _make_provider()
    resp = MagicMock()
    resp.text = '["coordinator"]'
    resp.total_tokens = 10
    provider.complete = AsyncMock(return_value=resp)
    agent = CrossWikiQueryAgent(
        provider=provider, registry=REGISTRY, own_wiki_name="coordinator",
        cross_wiki_routing_path=routing_file,
    )
    with patch("synthadoc.agents.cross_wiki_query_agent._parse_cross_wiki_routing",
               side_effect=ValueError("bad format")):
        picked = await agent._wiki_pick("what is leverage?", ["what is leverage?"])
    # Falls back to LLM which picks coordinator
    assert any(name == "coordinator" for name, _ in picked)


def test_synthesis_prompt_includes_scope_block():
    """purpose_summaries → scope block in synthesis prompt (lines 334-335)."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    prompt = agent._build_cross_wiki_synthesis_prompt(
        question="what is leverage?",
        context="page content",
        purpose_summaries={"coordinator": "Finance domain", "target": "Legal domain"},
        offline_wikis=[],
        warnings=[],
        history=[],
    )
    assert "Finance domain" in prompt
    assert "Wiki scopes:" in prompt
