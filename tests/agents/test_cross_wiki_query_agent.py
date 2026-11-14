# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.agents.cross_wiki_query_agent import CrossWikiQueryAgent, _get_question_parts

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
    """ActionAgent.detect() → classify() confirms a genuine action →
    cross_wiki_skipped, routed to local."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    with patch("synthadoc.agents.cross_wiki_query_agent.ActionAgent") as MockAction:
        action_inst = MagicMock()
        action_inst.detect.return_value = True
        action_inst.classify = AsyncMock(return_value="lint")
        action_inst.run = AsyncMock()
        MockAction.return_value = action_inst
        result = await agent.run("run lint")
    assert result.cross_wiki_skipped is True
    action_inst.run.assert_not_called()  # the action's real side effects must never fire

@pytest.mark.asyncio
@pytest.mark.parametrize("question,action_type", [
    ("re-ingest stale pages", "orchestrate"),
    ("Run lint and report", "lint"),
])
async def test_detected_operation_under_cross_wiki_tells_user_to_disable_it(question, action_type):
    """No detected operation — not just agentic workflows (orchestrate), but
    also plain actions like lint — may actually run while cross-wiki search is
    enabled. Running it would silently fire real side effects (a lint job
    genuinely starts) when the user asked expecting a wiki-chat answer, with no
    indication their request was redirected. Tell the user cross-wiki mode
    itself is what's in the way, and never dispatch the action. Issue #524."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    with patch("synthadoc.agents.cross_wiki_query_agent.ActionAgent") as MockAction:
        action_inst = MagicMock()
        action_inst.detect.return_value = True
        action_inst.classify = AsyncMock(return_value=action_type)
        action_inst.run = AsyncMock()
        MockAction.return_value = action_inst
        result = await agent.run(question)
    assert result.cross_wiki_skipped is True
    assert "cross-wiki" in result.answer.lower()
    assert "turn off" in result.answer.lower() or "disable" in result.answer.lower()
    action_inst.run.assert_not_called()  # the action's real side effects must never fire

@pytest.mark.asyncio
async def test_detect_false_positive_falls_through_to_normal_cross_wiki_search():
    """detect()'s fast regex pre-check has known false positives — e.g. "how do
    I roll back a Kubernetes deployment?" matches the literal "roll back"
    substring even though it isn't a synthadoc action. classify()'s LLM
    extraction must correctly return None for it, and the query must fall
    through to normal cross-wiki search instead of being blocked."""
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "k8s-rollback", "title": "Kubernetes Rollback",
                   "score": 3.0, "content": "kubectl rollout undo deployment/foo"}],
        "purpose_summary": "DevOps domain",
        "routing_warning": "",
    }
    provider = _make_provider(answer="Use kubectl rollout undo.")
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    with patch("synthadoc.agents.cross_wiki_query_agent.ActionAgent") as MockAction, \
         patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        action_inst = MagicMock()
        action_inst.detect.return_value = True
        action_inst.classify = AsyncMock(return_value=None)
        action_inst.run = AsyncMock()
        MockAction.return_value = action_inst
        result = await agent.run("How do I roll back a Kubernetes deployment?")
    assert result.cross_wiki_skipped is False
    assert result.answer == "Use kubectl rollout undo."
    action_inst.run.assert_not_called()

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


def test_merge_results_interleaves_wikis_by_rank_not_raw_score():
    """BM25 scores are not comparable across wikis: each wiki's best page comes
    first, whatever its score, and a wiki's own order is kept."""
    agent = CrossWikiQueryAgent(provider=_make_provider(), registry=REGISTRY, own_wiki_name="coordinator")
    raw_results = [
        {"pages": [{"slug": "a1", "score": 40.0}, {"slug": "a2", "score": 35.0}, {"slug": "a3", "score": 30.0}]},
        {"pages": [{"slug": "b1", "score": 0.0}, {"slug": "b2", "score": 3.0}]},   # b1: embedding-only hit
    ]
    pages, offline, _ = agent._merge_results([("a", "u"), ("b", "u")], raw_results)
    assert [p["slug"] for p in pages] == ["a1", "b1", "a2", "b2", "a3"]
    assert [p["wiki_name"] for p in pages][:2] == ["a", "b"]
    assert offline == []


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
    """_fetch_retrieve posts to /retrieve and returns a _RetrieveResponse."""
    import httpx
    import respx
    from synthadoc.agents.cross_wiki_query_agent import CrossWikiQueryAgent, _RetrieveResponse
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    response_data = {
        "wiki_name": "target",
        "pages": [{"slug": "p", "title": "P", "score": 1.0, "content": "c"}],
        "purpose_summary": "Legal",
        "routing_warning": "",
    }
    with respx.mock:
        respx.post("http://127.0.0.1:7071/retrieve").mock(
            return_value=httpx.Response(200, json=response_data)
        )
        result = await agent._fetch_retrieve(
            "http://127.0.0.1:7071", "what is leverage?", ["what is leverage?"]
        )

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


# ---------------------------------------------------------------------------
# CJK translation for cross-wiki retrieval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cjk_query_triggers_translation_before_retrieve():
    """A Chinese question is translated to English before fan-out to /retrieve."""
    translate_calls = []

    async def _fake_translate(provider, question):
        translate_calls.append(question)
        return "How does von Neumann architecture influence LLM training?"

    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    retrieve_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "von-neumann", "title": "Von Neumann", "score": 3.0, "content": "vn content"}],
        "purpose_summary": "Computing history",
        "routing_warning": "",
    }

    chinese_q = "冯·诺依曼架构对当今大型语言模型的大规模训练和运行有什么影响？"

    with patch("synthadoc.agents.cross_wiki_query_agent.translate_for_retrieval", side_effect=_fake_translate):
        with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)) as mock_fetch:
            result = await agent.run(chinese_q)

    assert translate_calls == [chinese_q], "translate_for_retrieval must be called with the original CJK question"
    # The translated English question was passed to decompose / fetch
    fetch_question = mock_fetch.call_args[0][1]  # positional arg: question
    assert fetch_question == chinese_q  # original preserved for synthesis


@pytest.mark.asyncio
async def test_ascii_query_skips_translation():
    """An ASCII question bypasses translation entirely."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    retrieve_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "p1", "title": "P1", "score": 2.0, "content": "content"}],
        "purpose_summary": "",
        "routing_warning": "",
    }

    with patch("synthadoc.agents.cross_wiki_query_agent.translate_for_retrieval") as mock_tr:
        with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
            await agent.run("what is leverage?")

    mock_tr.assert_not_called()


@pytest.mark.asyncio
async def test_on_wikis_selected_called_with_wiki_names():
    """on_wikis_selected callback receives actual wiki names after _wiki_pick."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    retrieve_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "p1", "title": "P1", "score": 2.0, "content": "content"}],
        "purpose_summary": "",
        "routing_warning": "",
    }
    received: list[list[str]] = []

    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        await agent.run("what is leverage?", on_wikis_selected=received.append)

    assert len(received) == 1
    assert isinstance(received[0], list)
    assert "coordinator" in received[0]


@pytest.mark.asyncio
async def test_on_wikis_selected_called_empty_on_action_detected():
    """on_wikis_selected fires with [] when the action-detected fast path triggers."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    received: list[list[str]] = []
    with patch("synthadoc.agents.cross_wiki_query_agent.ActionAgent") as MockAction:
        action_inst = MagicMock()
        action_inst.detect.return_value = True
        action_inst.classify = AsyncMock(return_value="lint")
        MockAction.return_value = action_inst
        await agent.run("run lint", on_wikis_selected=received.append)

    assert received == [[]]


@pytest.mark.asyncio
async def test_classify_error_falls_through_to_search():
    """If classify() raises, the question falls through to normal cross-wiki search (no 500)."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    retrieve_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "k8s", "title": "Kubernetes", "score": 3.0, "content": "rollback info"}],
        "purpose_summary": "",
        "routing_warning": "",
    }
    with patch("synthadoc.agents.cross_wiki_query_agent.ActionAgent") as MockAction:
        action_inst = MagicMock()
        action_inst.detect.return_value = True
        action_inst.classify = AsyncMock(side_effect=RuntimeError("provider timeout"))
        MockAction.return_value = action_inst
        with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
            result = await agent.run("how do I roll back a Kubernetes deployment?")

    assert result.knowledge_gap is False
    assert result.cross_wiki_skipped is False


@pytest.mark.asyncio
async def test_synthesis_error_returns_graceful_result():
    """If synthesis LLM call raises, returns a graceful 200 result (no 500)."""
    provider = _make_provider()
    provider.complete = AsyncMock(side_effect=RuntimeError("synthesis timeout"))
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    retrieve_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "k8s", "title": "Kubernetes", "score": 3.0, "content": "rollback info"}],
        "purpose_summary": "",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        result = await agent.run("how do I roll back a Kubernetes deployment?")

    assert result.knowledge_gap is True
    assert "provider error" in result.answer.lower() or "synthesis" in result.answer.lower()


@pytest.mark.asyncio
async def test_cross_wiki_no_pages_triggers_gap_with_suggested_searches():
    """When all wikis return empty pages, knowledge_gap is True and suggested_searches is populated."""
    provider = _make_provider()
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    empty_resp = {"wiki_name": "coordinator", "pages": [], "purpose_summary": "Finance", "routing_warning": ""}
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=empty_resp)):
        with patch("synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
                   AsyncMock(return_value=["how to calculate conversion ratio", "conversion metrics"])):
            result = await agent.run("what is the conversion ratio?")
    assert result.knowledge_gap is True
    assert len(result.suggested_searches) == 2
    assert "how to calculate conversion ratio" in result.suggested_searches


@pytest.mark.asyncio
async def test_cross_wiki_gap_sentinel_triggers_knowledge_gap_and_suggestions():
    """When pages are retrieved but LLM signals [GAP], knowledge_gap is True and [GAP] is stripped."""
    provider = _make_provider(answer="[GAP]\nThe provided pages do not contain information on this topic.")
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "misc", "title": "Miscellaneous", "score": 1.2, "content": "general text"}],
        "purpose_summary": "Legal domain",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        with patch("synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
                   AsyncMock(return_value=["quantum error correction docs"])):
            result = await agent.run("what is quantum error correction?")
    assert result.knowledge_gap is True
    assert not result.answer.startswith("[GAP]")
    assert "The provided pages do not contain" in result.answer
    assert result.suggested_searches == ["quantum error correction docs"]


@pytest.mark.asyncio
async def test_cross_wiki_empty_title_does_not_cause_irrelevant_citation():
    """A retrieved page with an empty title must not cause an irrelevant citation to be included during a gap."""
    provider = _make_provider(answer="[GAP]\nI do not have information about this topic.")
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [
            {"slug": "unrelated-page", "title": "", "score": 0.5, "content": "unrelated content"},
        ],
        "purpose_summary": "Legal domain",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        with patch("synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
                   AsyncMock(return_value=["search query"])):
            result = await agent.run("what is quantum entanglement?")
    assert result.knowledge_gap is True
    assert result.citations == []


@pytest.mark.asyncio
async def test_cross_wiki_multiple_low_score_pages_triggers_gap():
    """Multiple (>=3) pages with low BM25 scores trigger a knowledge gap when the answer is not substantial."""
    provider = _make_provider(answer="I could not find relevant details in the provided pages.")
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [
            {"slug": "page-1", "title": "Page 1", "score": 0.8, "content": "thin content"},
            {"slug": "page-2", "title": "Page 2", "score": 0.5, "content": "thin content"},
            {"slug": "page-3", "title": "Page 3", "score": 0.3, "content": "thin content"},
        ],
        "purpose_summary": "Legal domain",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        with patch("synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
                   AsyncMock(return_value=["enrich topic"])):
            result = await agent.run("what is topic X?")
    assert result.knowledge_gap is True
    assert result.suggested_searches == ["enrich topic"]


@pytest.mark.asyncio
async def test_cross_wiki_multiple_low_score_pages_guard_c_suppresses_gap():
    """Guard C suppresses knowledge gap when multiple low-score pages yield a substantial, cited answer."""
    long_answer = (
        "According to [[target::page-1]] and [[target::page-2]], this topic is explained in detail. "
        + ("Here is extensive verified context explaining every relevant aspect of this concept. " * 6)
    )
    assert len(long_answer) > 300
    provider = _make_provider(answer=long_answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [
            {"slug": "page-1", "title": "Page 1", "score": 0.8, "content": "content"},
            {"slug": "page-2", "title": "Page 2", "score": 0.5, "content": "content"},
            {"slug": "page-3", "title": "Page 3", "score": 0.3, "content": "content"},
        ],
        "purpose_summary": "Legal domain",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        result = await agent.run("what is topic X?")
    assert result.knowledge_gap is False
    assert result.suggested_searches == []


@pytest.mark.asyncio
async def test_cross_wiki_concise_multi_wiki_answer_low_bm25_no_gap():
    """A concise, correctly answered multi-wiki query with low BM25 scores (< 2.0) must not trigger a false gap."""
    answer = (
        "The leverage ratio is debt divided by equity [[coordinator::leverage]]. "
        "To deploy, run make build and kubectl apply [[target::deployment-runbook]]."
    )
    assert len(answer) < 300  # concise answer that would fail Guard C's 300-char threshold
    provider = _make_provider(answer=answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    coord_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "leverage", "title": "Leverage", "score": 1.38, "content": "leverage content"}],
        "purpose_summary": "Finance",
        "routing_warning": "",
    }
    target_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "deployment-runbook", "title": "Deployment Runbook", "score": 1.45, "content": "deploy content"}],
        "purpose_summary": "DevOps",
        "routing_warning": "",
    }

    async def _mock_fetch(base_url, question, sub_questions):
        if "127.0.0.1:7070" in base_url:
            return coord_resp
        return target_resp

    with patch.object(agent, "_fetch_retrieve", side_effect=_mock_fetch):
        result = await agent.run("What is the leverage ratio and how do I deploy the application?")

    assert result.knowledge_gap is False
    assert result.suggested_searches == []
    assert "coordinator::leverage" in result.citations
    assert "target::deployment-runbook" in result.citations


@pytest.mark.asyncio
async def test_cross_wiki_concise_single_domain_answer_low_bm25_no_gap():
    """A concise single-domain answer citing one retrieved page with low BM25 score (< 2.0) must not trigger a false gap."""
    answer = "To roll back, run kubectl rollout undo deployment/app [[target::deployment-runbook]]."
    assert len(answer) < 300
    provider = _make_provider(answer=answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "deployment-runbook", "title": "Deployment Runbook", "score": 1.4, "content": "rollback content"}],
        "purpose_summary": "DevOps",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        result = await agent.run("How do I roll back a Kubernetes deployment?")
    assert result.knowledge_gap is False
    assert result.suggested_searches == []
    assert "target::deployment-runbook" in result.citations


@pytest.mark.asyncio
async def test_cross_wiki_maintainer_reproduction_irrelevant_citations_negative_statement_triggers_gap():
    """Reproduces maintainer scenario: irrelevant retrieved pages cited in a negative statement must trigger knowledge gap."""
    answer = (
        "The provided pages from [[history-of-computing::Alan Turing]] and [[history-of-computing::Grace Hopper]] "
        "do not contain information about leverage ratio or deploying applications."
    )
    provider = _make_provider(answer=answer)
    registry = {"history-of-computing": {"port": 7070}}
    agent = CrossWikiQueryAgent(provider=provider, registry=registry, own_wiki_name="history-of-computing")

    retrieve_resp = {
        "wiki_name": "history-of-computing",
        "pages": [
            {"slug": "alan-turing", "title": "Alan Turing", "score": 1.1, "content": "computing history and turing machines"},
            {"slug": "grace-hopper", "title": "Grace Hopper", "score": 1.0, "content": "compiler history and cobol"},
        ],
        "purpose_summary": "Computing history",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        with patch(
            "synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
            AsyncMock(return_value=["how to calculate leverage ratio", "how to deploy applications"]),
        ):
            result = await agent.run("What is the leverage ratio and how do I deploy the application?")

    assert result.knowledge_gap is True
    assert len(result.suggested_searches) == 2
    assert "how to calculate leverage ratio" in result.suggested_searches
    assert "history-of-computing::alan-turing" in result.citations
    assert "history-of-computing::grace-hopper" in result.citations


@pytest.mark.asyncio
async def test_cross_wiki_partial_answer_triggers_gap_with_suggestions():
    """When a multi-part question is only partially answered, knowledge gap is triggered and suggestions are generated."""
    answer = (
        "The leverage ratio is debt divided by equity [[coordinator::leverage]]. "
        "However, the provided pages do not contain information about deploying applications."
    )
    provider = _make_provider(answer=answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    coord_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "leverage", "title": "Leverage", "score": 1.5, "content": "leverage is debt divided by equity"}],
        "purpose_summary": "Finance domain",
        "routing_warning": "",
    }
    target_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "history", "title": "History", "score": 0.5, "content": "history content"}],
        "purpose_summary": "General domain",
        "routing_warning": "",
    }

    async def _mock_fetch(base_url, question, sub_questions):
        if "127.0.0.1:7070" in base_url:
            return coord_resp
        return target_resp

    with patch.object(agent, "_fetch_retrieve", side_effect=_mock_fetch):
        with patch(
            "synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
            AsyncMock(return_value=["application deployment guide"]),
        ):
            result = await agent.run("What is the leverage ratio and how do I deploy the application?")

    assert result.knowledge_gap is True
    assert result.suggested_searches == ["application deployment guide"]
    assert "coordinator::leverage" in result.citations


@pytest.mark.asyncio
async def test_cross_wiki_partial_answer_passes_only_missing_question_to_decompose():
    """When a query is partially answered, SearchDecomposeAgent must receive only the uncovered question part."""
    answer = (
        "The leverage ratio is debt divided by equity [[coordinator::leverage]]. "
        "However, the provided pages do not contain information about deploying applications."
    )
    provider = _make_provider(answer=answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    coord_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "leverage", "title": "Leverage", "score": 1.5, "content": "leverage is debt divided by equity"}],
        "purpose_summary": "Finance domain",
        "routing_warning": "",
    }
    target_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "history", "title": "History", "score": 0.5, "content": "history content"}],
        "purpose_summary": "General domain",
        "routing_warning": "",
    }

    async def _mock_fetch(base_url, question, sub_questions):
        if "127.0.0.1:7070" in base_url:
            return coord_resp
        return target_resp

    with patch.object(agent, "_fetch_retrieve", side_effect=_mock_fetch):
        with patch(
            "synthadoc.agents.cross_wiki_query_agent.SearchDecomposeAgent.run",
            AsyncMock(return_value=["application deployment guide"]),
        ) as mock_decomp:
            result = await agent.run("What is the leverage ratio and how do I deploy the application?")

    assert result.knowledge_gap is True
    assert result.suggested_searches == ["application deployment guide"]
    assert "coordinator::leverage" in result.citations
    mock_decomp.assert_called_once()
    decomp_query_arg = mock_decomp.call_args[0][0]
    assert "deploy" in decomp_query_arg
    assert "leverage" not in decomp_query_arg
    assert decomp_query_arg == "how do I deploy the application"


@pytest.mark.asyncio
async def test_cross_wiki_peer_wiki_negative_admission_does_not_trigger_gap():
    """A valid answer from one wiki is not classified as a gap merely because another wiki lacks the information."""
    answer = (
        "The coordinator wiki does not contain deployment documentation. "
        "According to [[target::deployment-runbook]], you can roll back a Kubernetes deployment "
        "by running kubectl rollout undo deployment/app."
    )
    assert len(answer) < 300  # concise answer that would fail Guard C
    provider = _make_provider(answer=answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")

    coord_resp = {
        "wiki_name": "coordinator",
        "pages": [{"slug": "finance-summary", "title": "Finance Summary", "score": 0.2, "content": "financial statements"}],
        "purpose_summary": "Finance domain",
        "routing_warning": "",
    }
    target_resp = {
        "wiki_name": "target",
        "pages": [{"slug": "deployment-runbook", "title": "Deployment Runbook", "score": 1.4, "content": "Kubernetes deployment rollback kubectl rollout undo"}],
        "purpose_summary": "DevOps domain",
        "routing_warning": "",
    }

    async def _mock_fetch(base_url, question, sub_questions):
        if "127.0.0.1:7070" in base_url:
            return coord_resp
        return target_resp

    with patch.object(agent, "_fetch_retrieve", side_effect=_mock_fetch):
        result = await agent.run("How do I roll back a Kubernetes deployment?")

    assert result.knowledge_gap is False
    assert result.suggested_searches == []
    assert "target::deployment-runbook" in result.citations


@pytest.mark.asyncio
async def test_cross_wiki_title_only_citation_still_covers_terms_no_gap():
    """GitHub #545: a page cited only in "wiki::title" form (never "wiki::slug"
    or a [[bracket]] form) must still count toward term coverage.

    cited_page_objs had a dead branch comparing "wiki::title" against
    matching_cited_pages — a list that only ever holds "wiki::slug" strings
    (matching_cited_pages always stores the slug form regardless of which
    citation style actually matched). That branch could never fire. This
    pins the behavior the fix must preserve: a page that's only identifiable
    via its title-qualified citation is still pulled into cited_text (via
    matching_cited_pages's slug-based membership, and independently via the
    bare-title check), so its content satisfies term coverage and no
    knowledge gap is raised.
    """
    answer = "According to target::Quantum Thermostat Configuration Guide, this works great."
    assert len(answer) < 300  # concise answer that would fail Guard C
    provider = _make_provider(answer=answer)
    agent = CrossWikiQueryAgent(provider=provider, registry=REGISTRY, own_wiki_name="coordinator")
    retrieve_resp = {
        "wiki_name": "target",
        "pages": [{
            "slug": "quantum-thermostat-guide",
            "title": "Quantum Thermostat Configuration Guide",
            "score": 0.5,
            "content": "This guide explains how quantum thermostats are configured for optimal performance.",
        }],
        "purpose_summary": "Engineering domain",
        "routing_warning": "",
    }
    with patch.object(agent, "_fetch_retrieve", AsyncMock(return_value=retrieve_resp)):
        result = await agent.run("How are quantum thermostats configured?")

    assert result.knowledge_gap is False
    assert result.suggested_searches == []


class TestGetQuestionParts:
    """GitHub #544: splitting on "and" can orphan a grammatical-subject-less
    fragment (e.g. "growth projections" from "...revenue figures and growth
    projections?"), whose terms are unlikely to appear in cited_text — causing
    a false knowledge-gap callout even when the answer is fully covered.
    """

    def test_short_trailing_fragment_falls_back_to_whole_question(self):
        question = "What are the revenue figures and growth projections?"
        # "growth projections" (2 words) is discarded as too short to carry
        # its own grammatical subject, leaving only 1 valid part — below the
        # 2-part minimum — so the whole original question is used instead of
        # the orphaned fragment.
        assert _get_question_parts(question) == [question]

    def test_two_sufficiently_long_parts_still_split(self):
        question = "What is the leverage ratio and how do I deploy the application?"
        assert _get_question_parts(question) == [
            "What is the leverage ratio",
            "how do I deploy the application",
        ]

    def test_short_leading_fragment_also_falls_back(self):
        question = "Costs and how does the revenue recognition process work?"
        assert _get_question_parts(question) == [question]

    def test_no_conjunction_returns_whole_question(self):
        question = "What is the deployment process?"
        assert _get_question_parts(question) == [question]

    def test_sub_questions_bypass_conjunction_splitting(self):
        sub_questions = ["revenue figures", "growth projections"]
        assert _get_question_parts(
            "What are the revenue figures and growth projections?", sub_questions
        ) == sub_questions

    def test_three_parts_two_valid_one_short_keeps_only_valid(self):
        question = "What is the leverage ratio and how do I deploy it and costs?"
        # "costs?" (1 word) is discarded; the other two parts (5+ words each)
        # meet the minimum and 2 valid parts is enough to split rather than
        # fall back.
        assert _get_question_parts(question) == [
            "What is the leverage ratio",
            "how do I deploy it",
        ]
