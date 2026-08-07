# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tool-call loop runner for agentic workflows.

The LLM protocol expected here:
  - To call a tool: respond with exactly
      {"tool_call": {"name": "<tool_name>", "input": {<kwargs>}}}
  - To end the loop: respond with any plain text (not a tool_call JSON).
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, AsyncGenerator, Awaitable, Callable

from synthadoc.skills.base import Message

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext
    from synthadoc.providers.base import LLMProvider

# Matches {"tool_call": {"name": "<name>", "input": {<flat-or-one-level-nested dict>}}}
_TOOL_CALL_RE = re.compile(
    r'\{\s*"tool_call"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"input"\s*:\s*'
    r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*\}\s*\}',
    re.DOTALL,
)

_CHUNK_SIZE = 40
_MAX_PARSE_RETRIES = 2

_TOOL_LABELS: dict[str, str] = {
    "find_stale_pages": "Checking for stale pages",
    "find_page_source": "Looking up page source",
    "ingest_source": "Starting re-ingest",
    "poll_job": "Checking job status",
    "run_lint": "Running lint check",
    "confirm": "Requesting your confirmation",
}


def _parse_tool_call(text: str) -> tuple[str, dict] | None:
    """Return ``(tool_name, tool_input_dict)`` when *text* contains a tool call, else ``None``."""
    match = _TOOL_CALL_RE.search(text)
    if not match:
        return None
    try:
        tool_input = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None
    return match.group(1), tool_input


async def run_tool_call_loop(
    system_prompt: str,
    initial_message: str,
    tool_fns: dict[str, Callable[..., Awaitable[dict]]],
    provider: "LLMProvider",
    ctx: "WorkflowContext",
    *,
    budget: int = 30,
) -> AsyncGenerator[dict, None]:
    """Drive an LLM tool-call loop and yield SSE event dicts.

    Yielded event shapes (from the generator)::

        {"event": "token",      "data": {"text": str}}
        {"event": "final_text", "data": {"text": str}}

    Side-channel events (dispatched via ctx.send_sse_event, NOT yielded)::

        {"event": "tool_progress", "data": {"tool": str, "message": str}}

    Args:
        system_prompt:   System prompt passed to the provider on every call.
        initial_message: First user message; becomes ``messages[0]``.
        tool_fns:        Map of tool name → async callable.  Each callable
                         receives ``**tool_input`` from the LLM response.
        provider:        An :class:`LLMProvider` instance.
        ctx:             Runtime :class:`WorkflowContext`.
        budget:          Maximum number of tool calls before the loop is
                         forcibly terminated.
    """
    messages: list[Message] = [Message(role="user", content=initial_message)]
    tool_count = 0
    parse_retries = 0

    # Emit immediately so the UI shows activity before the first LLM round-trip.
    await ctx.send_sse_event("tool_progress", {"tool": "_init", "message": "Working on your request..."})

    while True:
        response = await provider.complete(messages, system=system_prompt)
        text = response.text.strip()

        parsed = _parse_tool_call(text)

        # If the response looks like JSON but the regex failed, retry up to the limit.
        if parsed is None and text.startswith("{") and parse_retries < _MAX_PARSE_RETRIES:
            parse_retries += 1
            messages.append(Message(role="assistant", content=text))
            messages.append(
                Message(
                    role="user",
                    content="Please format the tool call as valid JSON: "
                    '{"tool_call": {"name": "<name>", "input": {<kwargs>}}}',
                )
            )
            continue

        parse_retries = 0

        if parsed is not None:
            tool_name, tool_input = parsed
            tool_count += 1

            if tool_count > budget:
                yield {
                    "event": "final_text",
                    "data": {"text": f"Tool call budget of {budget} exceeded."},
                }
                return

            label = _TOOL_LABELS.get(tool_name, f"Calling {tool_name}")
            await ctx.send_sse_event(
                "tool_progress",
                {"tool": tool_name, "message": f"{label}..."},
            )

            if tool_name not in tool_fns:
                tool_result = {"error": f"Unknown tool: {tool_name!r}"}
            else:
                try:
                    tool_result = await tool_fns[tool_name](**tool_input)
                except TypeError as exc:
                    tool_result = {"error": f"Invalid arguments for {tool_name!r}: {exc}"}

            messages.append(Message(role="assistant", content=text))
            messages.append(Message(role="user", content=str(tool_result)))

        else:
            # Plain-text response — stream as token chunks, then emit final_text.
            for i in range(0, max(len(text), 1), _CHUNK_SIZE):
                yield {"event": "token", "data": {"text": text[i : i + _CHUNK_SIZE]}}
            yield {"event": "final_text", "data": {"text": text}}
            return
