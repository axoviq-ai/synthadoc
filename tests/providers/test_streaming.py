# tests/providers/test_streaming.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.providers.base import LLMProvider, Message


@pytest.mark.asyncio
async def test_base_provider_complete_stream_not_implemented():
    """complete_stream must raise NotImplementedError on base class."""
    class _Concrete(LLMProvider):
        async def complete(self, messages, system=None, temperature=0.0, max_tokens=4096):
            pass
    provider = _Concrete()
    with pytest.raises(NotImplementedError):
        async for _ in provider.complete_stream([Message(role="user", content="hi")]):
            break


@pytest.mark.asyncio
async def test_openai_provider_complete_stream_yields_tokens():
    """OpenAIProvider.complete_stream must yield token strings."""
    from synthadoc.providers.openai import OpenAIProvider
    from synthadoc.config import AgentConfig

    cfg = AgentConfig(provider="openai", model="gpt-4o-mini")
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._config = cfg
    provider._timeout = None
    provider._extra_body = {}

    chunk1 = MagicMock(); chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
    chunk2 = MagicMock(); chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]
    chunk3 = MagicMock(); chunk3.choices = [MagicMock(delta=MagicMock(content=None))]

    async def _fake_create(*a, **kw):
        async def _gen():
            for c in [chunk1, chunk2, chunk3]:
                yield c
        return _gen()

    mock_client = MagicMock()
    mock_client.chat.completions.create = _fake_create
    provider._client = mock_client

    tokens = []
    async for tok in provider.complete_stream([Message(role="user", content="hi")]):
        tokens.append(tok)
    assert tokens == ["Hello", " world"]


@pytest.mark.asyncio
async def test_openai_provider_complete_stream_strips_think_blocks():
    """complete_stream detects reasoning model via <think> and falls back to complete()."""
    from synthadoc.providers.openai import OpenAIProvider
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.config import AgentConfig

    cfg = AgentConfig(provider="openai", model="minimax/MiniMax-M2.5")
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._config = cfg
    provider._timeout = None
    provider._extra_body = {}

    # Simulate MiniMax streaming: think block split across tokens
    raw_tokens = ["<think>", "some reasoning", "</think>", "\n\nThe answer is 42."]
    chunks = []
    for t in raw_tokens:
        c = MagicMock()
        c.choices = [MagicMock(delta=MagicMock(content=t))]
        chunks.append(c)

    async def _fake_create(*a, **kw):
        async def _gen():
            for c in chunks:
                yield c
        return _gen()

    mock_client = MagicMock()
    mock_client.chat.completions.create = _fake_create
    provider._client = mock_client

    # complete() fallback returns the authoritative full answer
    provider.complete = AsyncMock(
        return_value=CompletionResponse(text="The answer is 42.", input_tokens=0, output_tokens=0)
    )

    tokens = []
    async for tok in provider.complete_stream([Message(role="user", content="hi")]):
        tokens.append(tok)
    combined = "".join(tokens)
    assert "think" not in combined.lower()
    assert "some reasoning" not in combined
    assert "42" in combined
    provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_openai_provider_complete_stream_strips_inline_think_blocks():
    """complete_stream fallback gives the full correct answer despite streaming truncation.

    MiniMax M2.5 may generate a shorter answer via streaming than via complete().
    The fallback to complete() ensures the full command is returned.
    """
    from synthadoc.providers.openai import OpenAIProvider
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.config import AgentConfig

    cfg = AgentConfig(provider="openai", model="minimax/MiniMax-M2.5")
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._config = cfg
    provider._timeout = None
    provider._extra_body = {}

    # Streaming only produces "synthadoc" (truncated) — complete() gives the full answer
    raw_tokens = ["<think>initial reasoning</think>", "synthadoc"]
    chunks = []
    for t in raw_tokens:
        c = MagicMock()
        c.choices = [MagicMock(delta=MagicMock(content=t))]
        chunks.append(c)

    async def _fake_create(*a, **kw):
        async def _gen():
            for c in chunks:
                yield c
        return _gen()

    mock_client = MagicMock()
    mock_client.chat.completions.create = _fake_create
    provider._client = mock_client

    provider.complete = AsyncMock(
        return_value=CompletionResponse(
            text="synthadoc schedule remove <schedule-id>",
            input_tokens=0, output_tokens=0,
        )
    )

    tokens = []
    async for tok in provider.complete_stream([Message(role="user", content="hi")]):
        tokens.append(tok)
    combined = "".join(tokens)
    assert "think" not in combined.lower()
    assert "synthadoc schedule remove <schedule-id>" in combined
    provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_anthropic_provider_complete_stream_yields_tokens():
    """AnthropicProvider.complete_stream must yield token strings."""
    from synthadoc.providers.anthropic import AnthropicProvider
    from synthadoc.config import AgentConfig

    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._config = cfg

    event1 = MagicMock(); event1.type = "content_block_delta"; event1.delta = MagicMock(type="text_delta", text="Hi")
    event2 = MagicMock(); event2.type = "content_block_delta"; event2.delta = MagicMock(type="text_delta", text=" there")
    event3 = MagicMock(); event3.type = "message_stop"

    class _FakeStream:
        def __init__(self):
            self._events = [event1, event2, event3]
            self._idx = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        def __aiter__(self): return self
        async def __anext__(self):
            if self._idx >= len(self._events):
                raise StopAsyncIteration
            e = self._events[self._idx]; self._idx += 1; return e

    provider._client = MagicMock()
    provider._client.messages.stream = MagicMock(return_value=_FakeStream())

    tokens = []
    async for tok in provider.complete_stream([Message(role="user", content="hi")]):
        tokens.append(tok)
    assert tokens == ["Hi", " there"]


@pytest.mark.asyncio
async def test_ollama_provider_complete_stream_yields_tokens():
    """OllamaProvider.complete_stream must yield token strings."""
    from synthadoc.providers.ollama import OllamaProvider
    from synthadoc.config import AgentConfig
    import json

    cfg = AgentConfig(provider="ollama", model="llama3")
    provider = OllamaProvider(config=cfg)

    lines = [
        json.dumps({"message": {"content": "Tok1"}, "done": False}),
        json.dumps({"message": {"content": "Tok2"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    async def _aiter_lines():
        for line in lines:
            yield line

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = _aiter_lines
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_response)

    with patch("synthadoc.providers.ollama.httpx.AsyncClient", return_value=mock_client):
        tokens = []
        async for tok in provider.complete_stream([Message(role="user", content="hi")]):
            tokens.append(tok)
    assert tokens == ["Tok1", "Tok2"]
