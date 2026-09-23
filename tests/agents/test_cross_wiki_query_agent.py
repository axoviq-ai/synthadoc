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
