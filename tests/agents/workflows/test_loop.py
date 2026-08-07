# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows._loop import _parse_tool_call, run_tool_call_loop
from synthadoc.providers.base import CompletionResponse


def _make_ctx():
    events = []

    async def _send(event, data):
        events.append({"event": event, "data": data})

    ctx = WorkflowContext(
        session_id="test-session",
        wiki_root=Path("/tmp/wiki"),
        queue=None,
        store=None,
        audit_db=None,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    return ctx, events


async def test_loop_emits_final_text_when_no_tool_call():
    """Plain-text response → loop yields token chunks then final_text."""
    ctx, events = _make_ctx()
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=CompletionResponse(
            text="Here is my answer.", input_tokens=10, output_tokens=5
        )
    )

    results = []
    async for event in run_tool_call_loop(
        system_prompt="You are helpful.",
        initial_message="What is 2+2?",
        tool_fns={},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    final_events = [e for e in results if e["event"] == "final_text"]
    assert len(final_events) == 1
    assert final_events[0]["data"]["text"] == "Here is my answer."
    # At least one token event should have been emitted
    token_events = [e for e in results if e["event"] == "token"]
    assert len(token_events) >= 1
    # provider was called exactly once
    assert provider.complete.call_count == 1


async def test_loop_executes_tool_and_continues():
    """Tool call JSON → tool executed → loop continues → plain text → final_text."""
    ctx, events = _make_ctx()

    call_count = 0

    async def _complete(messages, system=None, temperature=0.0, max_tokens=4096):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CompletionResponse(
                text='{"tool_call": {"name": "my_tool", "input": {"x": 1}}}',
                input_tokens=10,
                output_tokens=10,
            )
        return CompletionResponse(text="Done!", input_tokens=10, output_tokens=5)

    tool_calls = []

    async def my_tool(x):
        tool_calls.append(x)
        return {"result": x * 2}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="You are helpful.",
        initial_message="Do something.",
        tool_fns={"my_tool": my_tool},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # Tool was called with x=1
    assert tool_calls == [1]

    # tool_progress events: one initial "_init" event + one per tool call
    tool_progress_events = [e for e in events if e["event"] == "tool_progress"]
    assert len(tool_progress_events) >= 2
    per_tool = [e for e in tool_progress_events if e["data"]["tool"] == "my_tool"]
    assert len(per_tool) == 1

    # Final text is from the second LLM response
    final_events = [e for e in results if e["event"] == "final_text"]
    assert len(final_events) == 1
    assert final_events[0]["data"]["text"] == "Done!"


def test_parse_tool_call_returns_none_for_invalid_json_input():
    """Regex matches but json.loads fails → _parse_tool_call returns None."""
    # Unquoted key fools the JSON parser but satisfies the regex char-class
    text = '{"tool_call": {"name": "bad_tool", "input": {unquoted: value}}}'
    result = _parse_tool_call(text)
    assert result is None


async def test_loop_retries_on_malformed_json_then_emits_plain_text():
    """Response starts with '{' but regex fails → loop retries, eventually emits final_text."""
    ctx, events = _make_ctx()

    call_count = 0

    async def _complete(messages, system=None, temperature=0.0, max_tokens=4096):
        nonlocal call_count
        call_count += 1
        # Always return a malformed tool-call-looking blob that starts with '{'
        # but does not match the regex (missing "input" key).
        return CompletionResponse(
            text='{"tool_call": {"name": "broken"}}',
            input_tokens=5,
            output_tokens=5,
        )

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="You are helpful.",
        initial_message="Do something.",
        tool_fns={},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # After _MAX_PARSE_RETRIES the loop gives up and emits the text as final_text
    final_events = [e for e in results if e["event"] == "final_text"]
    assert len(final_events) == 1
    # provider.complete was called initial + 2 retries + 1 final = 4 total
    assert call_count <= 4


async def test_loop_stops_at_budget():
    """Provider always returns a tool call → budget guard fires → final_text contains 'budget'."""
    ctx, events = _make_ctx()

    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=CompletionResponse(
            text='{"tool_call": {"name": "infinite_tool", "input": {}}}',
            input_tokens=10,
            output_tokens=10,
        )
    )

    async def infinite_tool():
        return {"ok": True}

    results = []
    async for event in run_tool_call_loop(
        system_prompt="You are helpful.",
        initial_message="Run forever.",
        tool_fns={"infinite_tool": infinite_tool},
        provider=provider,
        ctx=ctx,
        budget=3,
    ):
        results.append(event)

    final_events = [e for e in results if e["event"] == "final_text"]
    assert len(final_events) == 1
    assert "budget" in final_events[0]["data"]["text"].lower()
    # provider.complete should be called at most budget+1 times
    assert provider.complete.call_count <= 4


@pytest.mark.asyncio
async def test_loop_returns_error_for_unknown_tool():
    """LLM calling a non-existent tool returns an error dict, stream continues normally."""
    ctx, _ = _make_ctx()

    call_count = 0

    async def _provider_complete(messages, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CompletionResponse(
                text='{"tool_call": {"name": "ghost_tool", "input": {}}}',
                input_tokens=5, output_tokens=5,
            )
        return CompletionResponse(text="Done.", input_tokens=5, output_tokens=5)

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=_provider_complete)

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="go",
        tool_fns={},  # empty — ghost_tool not registered
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # Stream must not crash — it must emit a final_text
    assert any(e["event"] == "final_text" for e in results)
    # The error must have been fed back to the LLM (second LLM call happened)
    assert call_count == 2


async def test_loop_confirm_batched_with_data_tool_runs_data_tool_first():
    """If confirm is batched with a data tool, only the data tool runs; LLM then calls confirm."""
    ctx, events = _make_ctx()

    call_count = 0

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # LLM incorrectly batches a data tool with confirm
            return CompletionResponse(
                text=(
                    '{"tool_call": {"name": "data_tool", "input": {"v": 1}}}\n'
                    '{"tool_call": {"name": "confirm", "input": {"message": "ok?"}}}'
                ),
                input_tokens=10, output_tokens=10,
            )
        if call_count == 2:
            # Second turn: LLM now calls confirm alone
            return CompletionResponse(
                text='{"tool_call": {"name": "confirm", "input": {"message": "ok?"}}}',
                input_tokens=10, output_tokens=10,
            )
        return CompletionResponse(text="All done.", input_tokens=5, output_tokens=5)

    data_calls: list[int] = []
    confirm_calls: list[str] = []

    async def data_tool(v):
        data_calls.append(v)
        return {"value": v}

    async def confirm(message, yes_label="Yes", no_label="No"):
        confirm_calls.append(message)
        return {"confirmed": True}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="go",
        tool_fns={"data_tool": data_tool, "confirm": confirm},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # data_tool ran exactly once (not skipped)
    assert data_calls == [1]
    # confirm ran exactly once (in its own turn, not alongside data_tool)
    assert len(confirm_calls) == 1
    assert any(e["event"] == "final_text" for e in results)


async def test_loop_confirm_not_duplicated_when_batched_twice():
    """If LLM emits two confirm calls in one response, only the first is executed."""
    ctx, events = _make_ctx()

    call_count = 0
    confirm_calls: list[str] = []

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # LLM (mistakenly) emits confirm twice
            return CompletionResponse(
                text=(
                    '{"tool_call": {"name": "confirm", "input": {"message": "first"}}}\n'
                    '{"tool_call": {"name": "confirm", "input": {"message": "second"}}}'
                ),
                input_tokens=10, output_tokens=10,
            )
        return CompletionResponse(text="Done.", input_tokens=5, output_tokens=5)

    async def confirm(message, yes_label="Yes", no_label="No"):
        confirm_calls.append(message)
        return {"confirmed": True}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="go",
        tool_fns={"confirm": confirm},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # Only the first confirm ran; the second was discarded
    assert confirm_calls == ["first"]
    assert any(e["event"] == "final_text" for e in results)
