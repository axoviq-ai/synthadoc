# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock
from synthadoc.providers.base import CompletionResponse


def _make_provider(text: str):
    p = MagicMock()
    p.complete = AsyncMock(return_value=CompletionResponse(
        text=text, input_tokens=50, output_tokens=20,
    ))
    return p


@pytest.mark.asyncio
async def test_summarize_produces_summary():
    from synthadoc.agents.summarize_agent import SummarizeAgent
    provider = _make_provider(
        "User asked about Alan Turing's early work. Assistant explained computability theory."
    )
    messages = [
        {"role": "user", "content": "What was Turing's early work?"},
        {"role": "assistant", "content": "Turing's early work focused on computability theory..."},
    ]
    agent = SummarizeAgent(provider)
    result = await agent.summarize(messages)
    assert "Turing" in result
    provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_summarize_empty_messages_returns_empty_without_llm_call():
    from synthadoc.agents.summarize_agent import SummarizeAgent
    provider = MagicMock()
    provider.complete = AsyncMock()
    agent = SummarizeAgent(provider)
    result = await agent.summarize([])
    assert result == ""
    provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_summarize_llm_error_returns_empty():
    from synthadoc.agents.summarize_agent import SummarizeAgent
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    agent = SummarizeAgent(provider)
    result = await agent.summarize(messages)
    assert result == ""


@pytest.mark.asyncio
async def test_summarize_formats_conversation_correctly():
    """Verify the conversation is formatted as Role: content lines."""
    from synthadoc.agents.summarize_agent import SummarizeAgent
    provider = _make_provider("Summary text.")
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    agent = SummarizeAgent(provider)
    await agent.summarize(messages)
    call_args = provider.complete.call_args
    prompt_content = call_args.kwargs["messages"][0].content
    assert "User: Hello" in prompt_content
    assert "Assistant: Hi there" in prompt_content
