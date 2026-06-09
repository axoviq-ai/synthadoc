# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock
from synthadoc.providers.base import CompletionResponse


def _make_provider(text: str):
    p = MagicMock()
    p.complete = AsyncMock(return_value=CompletionResponse(
        text=text, input_tokens=10, output_tokens=5,
    ))
    return p


@pytest.mark.asyncio
async def test_rewrite_no_history_returns_unchanged_without_llm_call():
    from synthadoc.agents.rewrite_agent import RewriteAgent
    provider = _make_provider("should not be called")
    agent = RewriteAgent(provider)
    result = await agent.rewrite("What was Alan Turing's contribution to computing?", [])
    assert result == "What was Alan Turing's contribution to computing?"
    provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_rewrite_followup_with_history_calls_llm():
    from synthadoc.agents.rewrite_agent import RewriteAgent
    provider = _make_provider("What was Alan Turing's later work in computing after World War II?")
    history = [
        {"role": "user", "content": "What was Alan Turing's early work?"},
        {"role": "assistant", "content": "Turing's early work focused on computability theory..."},
    ]
    agent = RewriteAgent(provider)
    result = await agent.rewrite("what about his later work?", history)
    assert result == "What was Alan Turing's later work in computing after World War II?"
    provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_rewrite_llm_error_falls_back_to_original():
    from synthadoc.agents.rewrite_agent import RewriteAgent
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    history = [
        {"role": "user", "content": "some question"},
        {"role": "assistant", "content": "some answer"},
    ]
    agent = RewriteAgent(provider)
    result = await agent.rewrite("what about it?", history)
    assert result == "what about it?"


@pytest.mark.asyncio
async def test_rewrite_empty_llm_response_falls_back_to_original():
    from synthadoc.agents.rewrite_agent import RewriteAgent
    provider = _make_provider("   ")  # whitespace only
    history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    agent = RewriteAgent(provider)
    result = await agent.rewrite("follow up?", history)
    assert result == "follow up?"
