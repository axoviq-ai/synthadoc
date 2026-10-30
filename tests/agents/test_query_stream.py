# tests/agents/test_query_stream.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock
from synthadoc.agents.query_agent import QueryAgent
from synthadoc.providers.base import Message
from synthadoc.storage.wiki import WikiStorage
from synthadoc.storage.search import HybridSearch


async def _collect_stream(agent, question):
    events = []
    async for evt in agent.run_stream(question):
        events.append(evt)
    return events


def _make_streaming_agent(tmp_wiki, tokens=("Answer", " here"), answer_full="Answer here",
                          stream_input_tokens=0, stream_output_tokens=0):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = MagicMock()
    # Explicitly set integer defaults so query_agent.py reads real ints, not MagicMocks.
    provider.last_stream_input_tokens = stream_input_tokens
    provider.last_stream_output_tokens = stream_output_tokens
    provider.complete = AsyncMock(return_value=MagicMock(
        text='["what is AI?"]', input_tokens=10, output_tokens=5
    ))
    async def _stream(*a, **kw):
        for t in tokens:
            yield t
    provider.complete_stream = _stream
    return store, search, provider


@pytest.mark.asyncio
async def test_run_stream_emits_status_events(tmp_wiki):
    """run_stream() must emit status:retrieving then status:synthesizing."""
    store, search, provider = _make_streaming_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    types = [e["event"] for e in events]
    assert "status" in types
    status_events = [e for e in events if e["event"] == "status"]
    phases = [e["data"]["phase"] for e in status_events]
    assert "retrieving" in phases
    assert "synthesizing" in phases


@pytest.mark.asyncio
async def test_run_stream_emits_token_events(tmp_wiki):
    """run_stream() must emit token events for each yielded chunk."""
    store, search, provider = _make_streaming_agent(tmp_wiki, tokens=("Hello", " World"))
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    token_events = [e for e in events if e["event"] == "token"]
    assert len(token_events) == 2
    assert token_events[0]["data"]["text"] == "Hello"
    assert token_events[1]["data"]["text"] == " World"


@pytest.mark.asyncio
async def test_run_stream_emits_done_with_hints(tmp_wiki):
    """run_stream() must emit a done event with next_hints list."""
    store, search, provider = _make_streaming_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1
    assert "next_hints" in done_events[0]["data"]
    assert isinstance(done_events[0]["data"]["next_hints"], list)


@pytest.mark.asyncio
async def test_run_stream_emits_citations(tmp_wiki):
    """run_stream() must emit a citations event after tokens."""
    store, search, provider = _make_streaming_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    citation_events = [e for e in events if e["event"] == "citations"]
    assert len(citation_events) == 1
    assert "citations" in citation_events[0]["data"]


@pytest.mark.asyncio
async def test_run_stream_event_structure(tmp_wiki):
    """Every event from run_stream must have 'event' and 'data' keys."""
    store, search, provider = _make_streaming_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    for evt in events:
        assert "event" in evt, f"missing 'event' key in {evt}"
        assert "data" in evt, f"missing 'data' key in {evt}"

@pytest.mark.asyncio
async def test_run_stream_gap_emits_gap_event(tmp_wiki):
    """When gap is detected (low BM25 score + threshold), run_stream emits a gap event."""
    from synthadoc.storage.search import SearchResult

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = MagicMock()
    # decompose call + SearchDecomposeAgent call (for suggested searches)
    provider.complete = AsyncMock(side_effect=[
        MagicMock(text='["quantum error correction"]', input_tokens=10, output_tokens=5),
        MagicMock(text='["quantum computing", "error correction"]', input_tokens=10, output_tokens=5),
    ])

    async def _stream(*a, **kw):
        yield "Sorry, not enough info."
    provider.complete_stream = _stream

    agent = QueryAgent(
        provider=provider, store=store, search=search,
        gap_score_threshold=10.0,  # very high threshold -> gap always triggered
    )
    events = await _collect_stream(agent, "quantum error correction")
    gap_events = [e for e in events if e["event"] == "gap"]
    assert len(gap_events) == 1, "gap event must be emitted when knowledge gap detected"
    assert "suggested_searches" in gap_events[0]["data"]
    assert isinstance(gap_events[0]["data"]["suggested_searches"], list)


@pytest.mark.asyncio
async def test_run_stream_purpose_pinned_in_synthesis(tmp_wiki):
    """When purpose.md exists, synthesis prompt must include the Wiki Scope preamble."""
    (tmp_wiki / "wiki" / "purpose.md").write_text(
        "---\ntitle: Purpose\n---\nThis wiki covers enterprise software engineering.\n"
        "Include: architecture, design patterns.\nExclude: personal projects.",
        encoding="utf-8",
    )
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=MagicMock(
        text='["what is dependency injection?"]', input_tokens=10, output_tokens=5,
    ))
    captured: list[dict] = []
    async def _stream(messages, **kw):
        captured.append({"messages": messages})
        yield "Answer here"
    provider.complete_stream = _stream

    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    await _collect_stream(agent, "What is dependency injection?")

    assert captured, "complete_stream was not called"
    synthesis_content = captured[0]["messages"][0].content
    assert "Wiki Scope (purpose.md)" in synthesis_content
    assert "enterprise software engineering" in synthesis_content


@pytest.mark.asyncio
async def test_run_stream_no_purpose_no_preamble(tmp_wiki):
    """When purpose.md is absent, synthesis prompt must not contain the Wiki Scope preamble."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=MagicMock(
        text='["what is caching?"]', input_tokens=10, output_tokens=5,
    ))
    captured: list[dict] = []
    async def _stream(messages, **kw):
        captured.append({"messages": messages})
        yield "Answer here"
    provider.complete_stream = _stream

    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    await _collect_stream(agent, "What is caching?")

    assert captured
    synthesis_content = captured[0]["messages"][0].content
    assert "### Wiki Scope (purpose.md)" not in synthesis_content


@pytest.mark.asyncio
async def test_run_stream_system_knowledge_in_synthesis(tmp_wiki):
    """When the question contains a Synthadoc keyword (e.g. 'ingest'), the synthesis
    prompt must include a 'Synthadoc Help' section."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=MagicMock(
        text='["what file types can I ingest?"]', input_tokens=10, output_tokens=5,
    ))
    captured: list[dict] = []
    async def _stream(messages, **kw):
        captured.append({"messages": messages})
        yield "You can ingest PDF and DOCX files."
    provider.complete_stream = _stream

    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    await _collect_stream(agent, "What file types can I ingest?")

    assert captured
    synthesis_content = captured[0]["messages"][0].content
    assert "Synthadoc Help" in synthesis_content


@pytest.mark.asyncio
async def test_run_stream_system_knowledge_suppresses_gap(tmp_wiki):
    """When system knowledge matches, no gap event should be emitted even at very high threshold."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=MagicMock(
        text='["what file types can I ingest?"]', input_tokens=10, output_tokens=5,
    ))
    async def _stream(*a, **kw):
        yield "You can ingest PDF files."
    provider.complete_stream = _stream

    # Very high threshold that would normally force a gap on an empty wiki
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=999.0)
    events = await _collect_stream(agent, "What file types can I ingest?")

    gap_events = [e for e in events if e["event"] == "gap"]
    assert len(gap_events) == 0, "system knowledge match must suppress gap event"


@pytest.mark.asyncio
async def test_run_stream_done_event_includes_token_counts(tmp_wiki):
    """done event must carry tokens_used, input_tokens, output_tokens from the provider."""
    store, search, provider = _make_streaming_agent(
        tmp_wiki, stream_input_tokens=150, stream_output_tokens=60
    )
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1
    data = done_events[0]["data"]
    assert data["input_tokens"] == 150
    assert data["output_tokens"] == 60
    assert data["tokens_used"] == 210


@pytest.mark.asyncio
async def test_run_stream_done_event_tokens_zero_when_provider_unsupported(tmp_wiki):
    """done event must carry tokens_used=0 when the provider does not report streaming usage."""
    store, search, provider = _make_streaming_agent(tmp_wiki)  # default: 0/0
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    done = [e for e in events if e["event"] == "done"][0]["data"]
    assert done["tokens_used"] == 0
    assert done["input_tokens"] == 0
    assert done["output_tokens"] == 0


@pytest.mark.asyncio
async def test_run_stream_sends_the_answer_with_title_links_pointed_at_slugs(tmp_wiki):
    """[[Title]] citations name no file; the stream ends with the text linked by slug."""
    from synthadoc.storage.wiki import WikiPage
    store, search, provider = _make_streaming_agent(
        tmp_wiki, tokens=("Zuse designed Plankalkül ", "([[konrad-zuse-z3-computer]])."))
    store.write_page("konrad-zuse", WikiPage(
        title="Konrad Zuse Z3 Computer", tags=[], content="Zuse designed Plankalkül in 1945.",
        status="active", confidence="high", sources=[]))
    provider.complete = AsyncMock(return_value=MagicMock(
        text='["Who designed Plankalkül?"]', input_tokens=10, output_tokens=5))
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "Who designed Plankalkül?")
    answers = [e for e in events if e["event"] == "answer"]
    assert answers == [{"event": "answer",
                        "data": {"text": "Zuse designed Plankalkül ([[konrad-zuse]])."}}]
    names = [e["event"] for e in events]
    assert names.index("answer") < names.index("citations")


@pytest.mark.asyncio
async def test_run_stream_sends_no_answer_event_when_links_are_already_slugs(tmp_wiki):
    store, search, provider = _make_streaming_agent(tmp_wiki, tokens=("See ", "[[ai-overview]]."))
    agent = QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=0.0)
    events = await _collect_stream(agent, "What is AI?")
    assert not [e for e in events if e["event"] == "answer"]


_LONG_CITED = ("Quantum error correction spreads one logical qubit over many physical qubits. " * 12
               + "See [[quantum-computing]].")      # > 800 chars, one citation: Guard C would suppress


def _gap_agent_streaming(tmp_wiki, tokens):
    store, search, provider = _make_streaming_agent(tmp_wiki, tokens=tokens)
    return QueryAgent(provider=provider, store=store, search=search, gap_score_threshold=2.0), provider


@pytest.mark.asyncio
async def test_run_stream_keeps_a_gap_the_llm_declares_in_gap_mode(tmp_wiki):
    """Gap mode asks the LLM to start with [GAP] when the pages do not answer the
    question; a long, cited answer must not let Guard C overrule that verdict."""
    agent, _ = _gap_agent_streaming(tmp_wiki, tokens=("[GAP]\n", _LONG_CITED))
    events = await _collect_stream(agent, "quantum error correction")
    assert [e for e in events if e["event"] == "gap"]
    shown = "".join(e["data"]["text"] for e in events if e["event"] in ("token", "answer"))
    assert "[GAP]" not in shown


@pytest.mark.asyncio
async def test_run_stream_guard_c_still_suppresses_a_gap_when_the_llm_finds_coverage(tmp_wiki):
    """No [GAP]: the LLM found the pages answer the question (Plankalkul on the Zuse page)."""
    agent, _ = _gap_agent_streaming(tmp_wiki, tokens=(_LONG_CITED,))
    events = await _collect_stream(agent, "quantum error correction")
    assert not [e for e in events if e["event"] == "gap"]


@pytest.mark.asyncio
async def test_gap_mode_prompt_asks_for_the_gap_sentinel(tmp_wiki):
    agent, provider = _gap_agent_streaming(tmp_wiki, tokens=("ok",))
    prompts = []
    async def _stream(*a, **kw):
        prompts.append(kw["messages"][0].content)
        yield "ok"
    provider.complete_stream = _stream
    await _collect_stream(agent, "quantum error correction")
    assert "start your reply with [GAP] on its own line" in prompts[0]
