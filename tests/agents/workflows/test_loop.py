# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows._loop import (
    _parse_all_tool_calls,
    _parse_tool_call,
    run_tool_call_loop,
)
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
    token_events = [e for e in results if e["event"] == "token"]
    assert len(final_events) == 1
    # Budget-exceeded message is sent as token chunks before final_text.
    # Check that "limit" or "budget" appears in either the tokens or final_text.
    full_text = "".join(e["data"]["text"] for e in token_events) + final_events[0]["data"]["text"]
    assert "limit" in full_text.lower() or "budget" in full_text.lower()
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


# ---------------------------------------------------------------------------
# _parse_tool_call — no-match and success paths (lines 46, 51)
# ---------------------------------------------------------------------------

def test_parse_tool_call_returns_none_when_no_pattern_match():
    """Plain text with no tool_call JSON → returns None."""
    assert _parse_tool_call("This is just plain text.") is None
    assert _parse_tool_call("") is None


def test_parse_tool_call_returns_name_and_input_on_valid_call():
    """Well-formed tool call JSON → returns (tool_name, input_dict)."""
    text = '{"tool_call": {"name": "my_tool", "input": {"x": 42}}}'
    result = _parse_tool_call(text)
    assert result is not None
    name, inp = result
    assert name == "my_tool"
    assert inp == {"x": 42}


# ---------------------------------------------------------------------------
# _parse_all_tool_calls — invalid JSON exception path (lines 61-62)
# ---------------------------------------------------------------------------

def test_parse_all_tool_calls_skips_entry_with_invalid_json():
    """When one match has invalid JSON for 'input', it is silently skipped."""
    text = (
        '{"tool_call": {"name": "good_tool", "input": {"a": 1}}}\n'
        '{"tool_call": {"name": "bad_tool", "input": {not_valid_json}}}'
    )
    results = _parse_all_tool_calls(text)
    # Only the valid entry should be returned
    assert len(results) == 1
    assert results[0][0] == "good_tool"


# ---------------------------------------------------------------------------
# run_tool_call_loop — TypeError in tool args (lines 164-165)
# ---------------------------------------------------------------------------

async def test_loop_handles_type_error_in_tool_args():
    """Tool function rejects call due to wrong arg types → error fed back to LLM, loop finishes."""
    ctx, _ = _make_ctx()

    call_count = 0

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # sends unexpected arg 'bad_arg'; strict_tool requires 'required_arg'
            return CompletionResponse(
                text='{"tool_call": {"name": "strict_tool", "input": {"bad_arg": 99}}}',
                input_tokens=5, output_tokens=5,
            )
        return CompletionResponse(text="Fixed.", input_tokens=5, output_tokens=5)

    async def strict_tool(required_arg: int) -> dict:
        return {"ok": required_arg}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="go",
        tool_fns={"strict_tool": strict_tool},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    assert any(e["event"] == "final_text" for e in results)
    assert call_count == 2


# ---------------------------------------------------------------------------
# run_tool_call_loop — multiple non-confirm tool calls in one turn (line 174)
# ---------------------------------------------------------------------------

async def test_loop_handles_multiple_tool_calls_in_one_response():
    """LLM emits two non-confirm tool calls in one turn; both run and combined results returned."""
    ctx, _ = _make_ctx()

    call_count = 0
    tool_a_calls: list = []
    tool_b_calls: list = []

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CompletionResponse(
                text=(
                    '{"tool_call": {"name": "tool_a", "input": {"v": 1}}}\n'
                    '{"tool_call": {"name": "tool_b", "input": {"v": 2}}}'
                ),
                input_tokens=10, output_tokens=10,
            )
        return CompletionResponse(text="Both done.", input_tokens=5, output_tokens=5)

    async def tool_a(v: int) -> dict:
        tool_a_calls.append(v)
        return {"a": v}

    async def tool_b(v: int) -> dict:
        tool_b_calls.append(v)
        return {"b": v}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="run both",
        tool_fns={"tool_a": tool_a, "tool_b": tool_b},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    assert tool_a_calls == [1]
    assert tool_b_calls == [2]
    assert any(e["event"] == "final_text" for e in results)


# ---------------------------------------------------------------------------
# run_tool_call_loop — mandatory-next-tool enforcement
# ---------------------------------------------------------------------------

async def test_loop_enforces_mandatory_next_tool_when_llm_produces_plain_text():
    """When a tool result sets _mandatory_next_tool and the LLM produces plain text,
    the loop injects an enforcement message and retries once, giving the LLM a
    chance to call the required tool."""
    ctx, events = _make_ctx()
    call_count = 0
    confirm_calls: list[str] = []

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # LLM calls scan_tool first
            return CompletionResponse(
                text='{"tool_call": {"name": "scan_tool", "input": {}}}',
                input_tokens=5, output_tokens=5,
            )
        if call_count == 2:
            # LLM (incorrectly) produces plain text instead of calling confirm
            return CompletionResponse(
                text="I found some issues. Here is my report...",
                input_tokens=5, output_tokens=5,
            )
        if call_count == 3:
            # After enforcement injection, LLM calls confirm
            return CompletionResponse(
                text='{"tool_call": {"name": "confirm", "input": {"message": "Fix?"}}}',
                input_tokens=5, output_tokens=5,
            )
        return CompletionResponse(text="Done.", input_tokens=5, output_tokens=5)

    async def scan_tool() -> dict:
        return {
            "has_issues": True,
            "total_broken": 2,
            "_mandatory_next_tool": "confirm",
        }

    async def confirm(message: str, yes_label: str = "Yes", no_label: str = "No") -> dict:
        confirm_calls.append(message)
        return {"confirmed": True}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="scan",
        tool_fns={"scan_tool": scan_tool, "confirm": confirm},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # The loop must have called the LLM at least 3 times (scan → plain text →
    # enforcement injection → confirm → final)
    assert call_count >= 3, f"Expected ≥3 LLM calls, got {call_count}"
    # confirm was eventually called
    assert len(confirm_calls) == 1, f"Expected confirm called once, got {confirm_calls}"
    # The loop ended cleanly
    assert any(e["event"] == "final_text" for e in results)


@pytest.mark.asyncio
async def test_loop_stub_response_exhausted_emits_stub_error():
    """After _MAX_PARSE_RETRIES of stub responses the loop emits the stub-error
    message (covering line 311 — the elif for _STUB_RESPONSES_MSG)."""
    ctx, _ = _make_ctx()
    call_count = 0

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(text="[]", input_tokens=5, output_tokens=5)

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="do something",
        tool_fns={},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    final_events = [e for e in results if e["event"] == "final_text"]
    token_events = [e for e in results if e["event"] == "token"]
    assert len(final_events) == 1
    full_text = "".join(e["data"]["text"] for e in token_events) + final_events[0]["data"]["text"]
    assert "stub" in full_text.lower() or "empty" in full_text.lower()
    assert "⚠" in full_text


@pytest.mark.asyncio
async def test_loop_invoke_xml_format_exhausted_emits_tag_error():
    """After _MAX_PARSE_RETRIES of <invoke name=...> responses the loop emits
    the tag-format terminal error (covering lines 295-296, 311)."""
    ctx, _ = _make_ctx()
    call_count = 0

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(
            text='<invoke name="tool_read_page_content"><arg name="slug">test</arg></invoke>',
            input_tokens=5,
            output_tokens=5,
        )

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="do something",
        tool_fns={},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    final_events = [e for e in results if e["event"] == "final_text"]
    token_events = [e for e in results if e["event"] == "token"]
    assert len(final_events) == 1
    full_text = "".join(e["data"]["text"] for e in token_events) + final_events[0]["data"]["text"]
    assert "<invoke>" in full_text or "invoke" in full_text.lower()
    assert "unsupported" in full_text.lower() or "tag" in full_text.lower()
    # Consumed initial + 2 retries + 1 exhausted = 4 calls total
    assert call_count <= 4


async def test_loop_mandatory_next_tool_exhausted_after_one_retry():
    """If the LLM still produces plain text after the enforcement injection,
    the loop exits to plain text (no infinite retry)."""
    ctx, _ = _make_ctx()
    call_count = 0

    async def _complete(messages, system=None, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CompletionResponse(
                text='{"tool_call": {"name": "scan_tool", "input": {}}}',
                input_tokens=5, output_tokens=5,
            )
        # LLM always produces plain text — even after enforcement
        return CompletionResponse(
            text="I refuse to call confirm.",
            input_tokens=5, output_tokens=5,
        )

    async def scan_tool() -> dict:
        return {"has_issues": True, "_mandatory_next_tool": "confirm"}

    provider = MagicMock()
    provider.complete = _complete

    results = []
    async for event in run_tool_call_loop(
        system_prompt="sys",
        initial_message="scan",
        tool_fns={"scan_tool": scan_tool},
        provider=provider,
        ctx=ctx,
    ):
        results.append(event)

    # After one enforcement retry the loop must still terminate (not loop forever)
    assert any(e["event"] == "final_text" for e in results)
    # call_count should be bounded: scan (1) + plain text (2) + enforcement (3) + final plain text (4)
    assert call_count <= 5, f"Loop did not terminate promptly: {call_count} calls"


# ---------------------------------------------------------------------------
# Native tool-call markup (MiniMax) and robust JSON decoding
# ---------------------------------------------------------------------------

# Shape observed from MiniMax in the contradiction resolver: prose, then native
# markup with the opening '{"' lost, and a page rewrite containing braces.
_MINIMAX_REPLY = (
    'The two new warnings are overstated. Let me use Strategy 1 again.'
    ']<]minimax[>[<tool_call> ]<]minimax[>[<tool_call> ]<]minimax[>['
    'name": "tool_propose_and_apply", "input": {"slug": "transistor-and-microchip", '
    '"new_content": "# Transistor\\n\\nThe \\"tyranny of numbers\\" {braces} here.", '
    '"strategy_name": "Strategy 1 — Content rewrite", "rationale": "Attempt 2"}}}'
)


def test_parse_recovers_minimax_native_tool_call():
    calls = _parse_all_tool_calls(_MINIMAX_REPLY)
    assert len(calls) == 1
    name, tool_input = calls[0]
    assert name == "tool_propose_and_apply"
    assert tool_input["slug"] == "transistor-and-microchip"
    assert "{braces}" in tool_input["new_content"]


def test_parse_wire_format_with_deep_nesting_and_braces_in_strings():
    text = '{"tool_call": {"name": "t", "input": {"a": {"b": {"c": [1, {"d": "}{"}]}}}}}'
    assert _parse_all_tool_calls(text) == [("t", {"a": {"b": {"c": [1, {"d": "}{"}]}}})]


def test_parse_native_markup_with_string_encoded_arguments():
    text = '<tool_call>{"name": "my_tool", "arguments": "{\\"x\\": 1}"}</tool_call>'
    assert _parse_all_tool_calls(text) == [("my_tool", {"x": 1})]


def test_parse_ignores_bare_name_input_in_prose_without_markup():
    text = 'The tool takes "name": "my_tool", "input": {"x": 1} as its arguments.'
    assert _parse_all_tool_calls(text) == []


async def test_loop_executes_minimax_native_tool_call():
    """The MiniMax reply runs the tool instead of being dumped as final text."""
    ctx, events = _make_ctx()
    replies = iter([_MINIMAX_REPLY, "All pages resolved."])

    async def _complete(messages, system=None, temperature=0.0, max_tokens=4096):
        return CompletionResponse(text=next(replies), input_tokens=1, output_tokens=1)

    applied = []

    async def tool_propose_and_apply(**kwargs):
        applied.append(kwargs["slug"])
        return {"status": "applied"}

    provider = MagicMock()
    provider.complete = _complete

    results = [e async for e in run_tool_call_loop(
        system_prompt="s", initial_message="m",
        tool_fns={"tool_propose_and_apply": tool_propose_and_apply},
        provider=provider, ctx=ctx,
    )]

    assert applied == ["transistor-and-microchip"]
    final = [e for e in results if e["event"] == "final_text"]
    assert final[-1]["data"]["text"] == "All pages resolved."
    assert "minimax" not in final[-1]["data"]["text"]


async def test_loop_unrecoverable_native_markup_reports_tag_error_immediately():
    """Native markup that cannot be recovered fails on the first attempt, never dumps raw JSON."""
    ctx, events = _make_ctx()
    broken = 'Fixing now.]<]minimax[>[<tool_call> name": "tool_x", "input": {truncated'
    calls = 0

    async def _complete(messages, system=None, temperature=0.0, max_tokens=4096):
        nonlocal calls
        calls += 1
        return CompletionResponse(text=broken, input_tokens=1, output_tokens=1)

    provider = MagicMock()
    provider.complete = _complete

    results = [e async for e in run_tool_call_loop(
        system_prompt="s", initial_message="m", tool_fns={}, provider=provider, ctx=ctx,
    )]

    assert calls == 1  # no retries — fail fast
    final_text = [e for e in results if e["event"] == "final_text"][-1]["data"]["text"]
    assert "`<tool_call>`" in final_text
    assert "truncated" not in final_text
    retries = [e for e in events if e["data"].get("tool") == "_parse_retry"]
    assert len(retries) == 0  # no format-reminder retries


# ---------------------------------------------------------------------------
# Tier 1 hardening: protocol footer, framed tool results, drift logging
# ---------------------------------------------------------------------------

import json as _json
import logging as _logging

from synthadoc.agents.workflows._loop import _example_call, _protocol_footer, _tool_result_message


async def _run(replies, tool_fns, provider_cfg=None):
    """Run the loop with scripted replies; return (events, systems_seen, messages_seen)."""
    ctx, _ = _make_ctx()
    it = iter(replies)
    systems, msgs = [], []

    async def _complete(messages, system=None, **_kw):
        systems.append(system)
        msgs.append(list(messages))
        return CompletionResponse(text=next(it), input_tokens=1, output_tokens=1)

    provider = MagicMock()
    provider.complete = _complete
    provider._config = provider_cfg
    events = [e async for e in run_tool_call_loop(
        system_prompt="WORKFLOW RULES", initial_message="go", tool_fns=tool_fns,
        provider=provider, ctx=ctx,
    )]
    return events, systems, msgs


async def test_system_prompt_ends_with_protocol_footer_naming_real_tools():
    async def tool_read(slug):
        return {"ok": True}

    _, systems, _ = await _run(["done"], {"tool_read": tool_read})
    system = systems[0]
    assert system.startswith("WORKFLOW RULES")
    footer = system[len("WORKFLOW RULES"):]
    assert "TOOL-CALL PROTOCOL" in footer
    assert "Tool names: tool_read" in footer
    assert "<tool_call>" in footer and "Do NOT use" in footer
    assert '{"tool_call": {"name": "tool_read", "input": {"slug": "alan-turing"}}}' in footer


async def test_tool_result_is_labelled_and_followed_by_format_reminder():
    async def my_tool(x):
        return {"doubled": x * 2}

    _, _, msgs = await _run(
        ['{"tool_call": {"name": "my_tool", "input": {"x": 2}}}', "done"], {"my_tool": my_tool},
    )
    result_msg = msgs[1][-1]
    assert result_msg.role == "user"
    label, body, _, reminder = result_msg.content.split("\n", 3)
    assert label == "Result of my_tool:"
    assert _json.loads(body) == {"doubled": 4}
    assert reminder.startswith('Next: reply with exactly one {"tool_call"')


def test_tool_result_message_lists_all_tools_for_batched_calls():
    text = _tool_result_message([{"tool": "a", "result": {"x": 1}}, {"tool": "b", "result": None}])
    assert text.startswith("Results of a, b:\n")
    assert _json.loads(text.split("\n")[1]) == [
        {"tool": "a", "result": {"x": 1}}, {"tool": "b", "result": None},
    ]


def test_example_call_prefers_slug_tool_then_required_params():
    async def list_pages(scope):
        return {}

    async def read_page(slug, verbose=False):
        return {}

    async def run_lint():
        return {}

    assert _json.loads(_example_call({"list_pages": list_pages, "read_page": read_page})) == {
        "tool_call": {"name": "read_page", "input": {"slug": "alan-turing"}}}
    assert _json.loads(_example_call({"list_pages": list_pages})) == {
        "tool_call": {"name": "list_pages", "input": {"scope": "<scope>"}}}
    assert _json.loads(_example_call({"run_lint": run_lint})) == {
        "tool_call": {"name": "run_lint", "input": {}}}
    assert "<tool_name>" in _protocol_footer({})


async def test_native_format_recovery_is_logged_with_model(caplog):
    cfg = MagicMock(provider="minimax", model="MiniMax-M3")

    async def tool_propose_and_apply(**kwargs):
        return {"status": "applied"}

    with caplog.at_level(_logging.WARNING, logger="synthadoc.agents.workflows._loop"):
        await _run([_MINIMAX_REPLY, "done"], {"tool_propose_and_apply": tool_propose_and_apply}, cfg)
    drift = [r for r in caplog.records if "format drift" in r.getMessage()]
    assert len(drift) == 1
    assert "minimax/MiniMax-M3" in drift[0].getMessage()
    assert "tool_propose_and_apply" in drift[0].getMessage()


async def test_parse_failure_stops_immediately_and_is_logged(caplog):
    """Unrecoverable parse failure stops on the first attempt with an ERROR log — no retries."""
    broken = 'x]<]minimax[>[<tool_call> name": "t", "input": {broken'
    with caplog.at_level(_logging.WARNING, logger="synthadoc.agents.workflows._loop"):
        await _run([broken], {}, MagicMock(provider="minimax", model="MiniMax-M3"))
    retries = [r for r in caplog.records if "parse failure" in r.getMessage()]
    stopped = [r for r in caplog.records if "workflow stopped" in r.getMessage()]
    assert len(retries) == 0  # no format-reminder retries
    assert len(stopped) == 1 and stopped[0].levelno == _logging.ERROR
    assert "minimax/MiniMax-M3" in stopped[0].getMessage()


# ── Replies truncated at max_tokens ───────────────────────────────────────────

_DEGENERATE = "<br>\n\n\n" * 2000   # Claude Haiku 5.5 content-health run, 2026-10-16


async def _run_loop(provider, tool_fns=None, max_tokens=16384):
    ctx, events = _make_ctx()
    results = [e async for e in run_tool_call_loop(
        system_prompt="sys", initial_message="go", tool_fns=tool_fns or {},
        provider=provider, ctx=ctx, max_tokens=max_tokens,
    )]
    return results, events


async def test_truncated_degenerate_reply_is_retried_and_never_shown():
    """A max_tokens reply with no tool call is discarded and retried; the retry's answer is final."""
    replies = [
        CompletionResponse(text=_DEGENERATE, input_tokens=10, output_tokens=16384, truncated=True),
        CompletionResponse(text="All done.", input_tokens=10, output_tokens=5),
    ]
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=replies)

    results, events = await _run_loop(provider)

    finals = [e["data"]["text"] for e in results if e["event"] == "final_text"]
    assert finals == ["All done."]
    assert all("<br>" not in e["data"]["text"] for e in results if e["event"] == "token")
    # The junk is not echoed back to the model; a short placeholder and a nudge are.
    retry_msgs = provider.complete.call_args_list[1].args[0]
    assert "<br>" not in "".join(m.content for m in retry_msgs)
    assert "cut off at the output limit (16384 tokens)" in retry_msgs[-1].content
    assert any(e["data"].get("tool") == "_parse_retry" for e in events)


async def test_truncated_reply_after_retries_shows_token_limit_error():
    """When every attempt is truncated the user gets the workflow_max_tokens hint, not the junk."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=_DEGENERATE, input_tokens=10, output_tokens=4096, truncated=True))

    results, _ = await _run_loop(provider, max_tokens=4096)

    finals = [e["data"]["text"] for e in results if e["event"] == "final_text"]
    assert len(finals) == 1
    assert "<br>" not in finals[0]
    assert "workflow_max_tokens = 8192" in finals[0]
    assert provider.complete.call_count == 3   # first attempt + 2 retries


async def test_truncated_reply_with_complete_tool_call_still_runs_the_tool():
    """Truncation after a complete JSON tool call (trailing junk) does not block the call."""
    tool = AsyncMock(return_value={"ok": True})
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[
        CompletionResponse(text='{"tool_call": {"name": "my_tool", "input": {}}}\n<br>\n<br>',
                           input_tokens=10, output_tokens=16384, truncated=True),
        CompletionResponse(text="Finished.", input_tokens=10, output_tokens=5),
    ])

    results, _ = await _run_loop(provider, tool_fns={"my_tool": tool})

    tool.assert_awaited_once()
    assert [e["data"]["text"] for e in results if e["event"] == "final_text"] == ["Finished."]


async def test_untruncated_plain_text_is_final_on_mock_providers():
    """MagicMock responses (no real truncated attr) keep the plain-text-is-final behaviour."""
    provider = MagicMock()
    resp = MagicMock(text="Summary.", output_tokens=5)
    provider.complete = AsyncMock(return_value=resp)

    results, _ = await _run_loop(provider)

    assert [e["data"]["text"] for e in results if e["event"] == "final_text"] == ["Summary."]


@pytest.mark.parametrize("text,expect_hint", [
    ("Should I go ahead with the remaining six pages?", True),
    ("Content Health Resolver — Complete.", False),
])
async def test_question_ending_names_rerun_hint_so_yes_routes_back(text, expect_hint):
    """A plain-text question ends the workflow; name the rerun hint so 'yes' re-runs it."""
    ctx, _ = _make_ctx()
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(text=text, input_tokens=1, output_tokens=1))
    results = [e async for e in run_tool_call_loop(
        system_prompt="sys", initial_message="go", tool_fns={}, provider=provider, ctx=ctx,
        rerun_hint="Run content health resolver",
    )]
    final = [e["data"]["text"] for e in results if e["event"] == "final_text"][0]
    assert final.startswith(text)
    assert ('"Run content health resolver"** hint chip to continue' in final) is expect_hint
