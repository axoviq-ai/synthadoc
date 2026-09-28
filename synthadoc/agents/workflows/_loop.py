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
    "tool_read_page_content":          "Reading page content",
    "tool_run_scoped_lint":            "Running scoped re-lint",
    "tool_propose_and_apply":          "Proposing change",
    "tool_transition_lifecycle_state": "Transitioning lifecycle state",
    "tool_get_wiki_status":            "Checking wiki status",
    "tool_get_contradicted_pages":     "Listing contradicted pages",
    "tool_read_source_content":        "Reading source content",
    "tool_cost_estimate":              "Estimating cost",
}

# Short stub responses some models emit instead of a proper tool call
# (e.g. MiniMax-M2.5 initialising an internal variable and emitting it).
_STUB_RESPONSES: frozenset[str] = frozenset({"[]", "{}", "null", "none", "true", "false", ""})


def _looks_like_tool_attempt(text: str) -> bool:
    """Return True when *text* looks like a failed tool call attempt.

    Covers four failure modes: malformed JSON starting with ``{``, truncated
    JSON with ``{"tool_call"`` prefix, a short stub response (``[]``, ``null``,
    etc.), and an unsupported tag format (``[TOOL_CALL]`` or ``<invoke name=``).
    """
    t = text.lower()
    return (
        text.startswith("{")
        or '{"tool_call"' in text
        or t in _STUB_RESPONSES
        or "[tool_call]" in t
        or "<invoke name=" in t
    )


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


def _parse_all_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Return ALL ``(tool_name, tool_input_dict)`` pairs found in *text*."""
    results = []
    for match in _TOOL_CALL_RE.finditer(text):
        try:
            tool_input = json.loads(match.group(2))
            results.append((match.group(1), tool_input))
        except json.JSONDecodeError:
            pass
    return results


async def run_tool_call_loop(
    system_prompt: str,
    initial_message: str,
    tool_fns: dict[str, Callable[..., Awaitable[dict]]],
    provider: "LLMProvider",
    ctx: "WorkflowContext",
    *,
    budget: int = 30,
    max_tokens: int = 4096,
    rerun_hint: str | None = None,
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
    # Mandatory-next-tool enforcement: set when a tool result contains
    # "_mandatory_next_tool".  If the LLM produces plain text instead of calling
    # that tool, the loop injects a reminder and retries once before giving up.
    _mandatory_next: str | None = None
    _mandatory_retry_done: bool = False

    # Emit immediately so the UI shows activity before the first LLM round-trip.
    await ctx.send_sse_event("tool_progress", {"tool": "_init", "message": "Working on your request..."})

    while True:
        response = await provider.complete(messages, system=system_prompt, max_tokens=max_tokens)
        text = response.text.strip()

        all_calls = _parse_all_tool_calls(text)

        # Retry when the response looks like a tool call attempt but didn't parse.
        # See _looks_like_tool_attempt for the four failure modes it detects.
        if not all_calls and _looks_like_tool_attempt(text) and parse_retries < _MAX_PARSE_RETRIES:
            parse_retries += 1
            _text_lower = text.lower()
            _used_tag_format = "[tool_call]" in _text_lower or "<invoke name=" in _text_lower
            _reason = (
                "used an unsupported tag/XML format instead of JSON"
                if _used_tag_format
                else "may have been cut off by the token limit"
            )
            await ctx.send_sse_event(
                "tool_progress",
                {"tool": "_parse_retry",
                 "message": (
                     f"⚠ Response could not be parsed (attempt {parse_retries}/{_MAX_PARSE_RETRIES}) "
                     f"— {_reason}. "
                     "Retrying with a reminder to use the correct format…"
                 )},
            )
            messages.append(Message(role="assistant", content=text))
            messages.append(
                Message(
                    role="user",
                    content=(
                        "Your previous response could not be parsed as a valid tool call "
                        f"({_reason}). "
                        "Respond with ONLY a single JSON object — no prose, no explanation, "
                        "no [TOOL_CALL] tags, no <invoke> tags, no XML, no markdown fences:\n"
                        '{"tool_call": {"name": "<name>", "input": {<kwargs>}}}'
                    ),
                )
            )
            continue

        parse_retries = 0

        # Mandatory-next-tool enforcement.
        # A previous tool result set "_mandatory_next_tool" — if the LLM produced
        # plain text instead of calling that tool, inject a correction message and
        # retry once.  This catches the common failure where the LLM interprets a
        # "scan for" query as "report findings only" and exits to text without
        # presenting the user confirmation gate.
        if _mandatory_next and not all_calls and not _mandatory_retry_done:
            _mandatory_retry_done = True
            messages.append(Message(role="assistant", content=text))
            messages.append(Message(
                role="user",
                content=(
                    f"WORKFLOW ENFORCEMENT: The previous tool result required you to call "
                    f"`{_mandatory_next}` as your next action. "
                    "Producing plain text here skips user confirmation and is not allowed. "
                    f'You MUST call `{_mandatory_next}` now with the appropriate arguments.'
                ),
            ))
            continue

        # Reset mandatory-next state each LLM turn (whether the LLM complied or not).
        _mandatory_next = None
        _mandatory_retry_done = False

        if all_calls:
            # `confirm` / `tool_confirm` is a blocking user-input gate — it must
            # never run alongside other tool calls in the same batch.  If the LLM
            # mixes confirm with data tools, execute only the data tools now so the
            # LLM has context before asking the user.  If the LLM sends only
            # confirm(s), run just the first.
            _CONFIRM_NAMES = {"confirm", "tool_confirm"}
            has_confirm = any(name in _CONFIRM_NAMES for name, _ in all_calls)
            if has_confirm:
                non_confirm = [(n, inp) for n, inp in all_calls if n not in _CONFIRM_NAMES]
                if non_confirm:
                    # Data tools present alongside confirm: run data tools only.
                    active_calls = non_confirm
                else:
                    # Only confirm(s): execute the first one; discard duplicates.
                    active_calls = all_calls[:1]
            else:
                active_calls = all_calls

            # Execute every tool call found in this response (LLM sometimes batches
            # multiple calls in one turn). Return all results before the next LLM call.
            combined: list[dict] = []
            for tool_name, tool_input in active_calls:
                tool_count += 1
                if tool_count > budget:
                    _continue = (
                        f' Type **yes** or click the **"{rerun_hint}"** hint chip to continue.'
                        if rerun_hint
                        else " Re-run the workflow to continue where it left off."
                    )
                    msg = (
                        f"⚠ The workflow reached its tool-call limit ({budget} calls) "
                        f"before completing all tasks.{_continue}"
                    )
                    for i in range(0, max(len(msg), 1), _CHUNK_SIZE):
                        yield {"event": "token", "data": {"text": msg[i : i + _CHUNK_SIZE]}}
                    yield {"event": "final_text", "data": {"text": msg}}
                    return

                label = _TOOL_LABELS.get(tool_name, f"Calling {tool_name}")
                await ctx.send_sse_event(
                    "tool_progress",
                    {"tool": tool_name, "message": f"{label}..."},
                )

                if tool_name not in tool_fns:
                    tool_result: dict = {"error": f"Unknown tool: {tool_name!r}"}
                else:
                    try:
                        tool_result = await tool_fns[tool_name](**tool_input)
                    except TypeError as exc:
                        tool_result = {"error": f"Invalid arguments for {tool_name!r}: {exc}"}
                # Capture mandatory-next-tool signal for the upcoming LLM turn.
                # The field remains in the result so the LLM also sees it as an
                # inline instruction (two layers of enforcement).
                if isinstance(tool_result, dict):
                    _mn = tool_result.get("_mandatory_next_tool")
                    if _mn:
                        _mandatory_next = _mn
                        _mandatory_retry_done = False
                combined.append({"tool": tool_name, "result": tool_result})

            messages.append(Message(role="assistant", content=text))
            # Single call: return the result dict directly (backward-compatible format).
            # Multiple calls: return the list so the LLM sees all results at once.
            # Use json.dumps (not str()) so the LLM receives standard JSON instead of
            # Python repr — double-quoted keys, null/true/false instead of None/True/False.
            if len(combined) == 1:
                messages.append(Message(
                    role="user",
                    content=json.dumps(combined[0]["result"], ensure_ascii=False, default=str),
                ))
            else:
                messages.append(Message(
                    role="user",
                    content=json.dumps(combined, ensure_ascii=False, default=str),
                ))

        else:
            # Retries exhausted — if this still looks like a failed tool call,
            # emit a user-friendly error instead of raw JSON.
            if _looks_like_tool_attempt(text):
                recommended = max_tokens * 2
                _text_lower = text.lower()
                if "[tool_call]" in _text_lower or "<invoke name=" in _text_lower:
                    _fmt = "`[TOOL_CALL]`" if "[tool_call]" in _text_lower else "`<invoke>`"
                    err = (
                        f"⚠ The workflow could not continue because the model used an "
                        f"unsupported tag format ({_fmt}) for tool calls instead "
                        "of the required JSON wire format.\n\n"
                        "This is a model-specific behaviour — some models (e.g. MiniMax-M2.5) "
                        "default to their own tool-call syntax rather than the JSON protocol "
                        "required for agentic workflows.\n\n"
                        "**Fix options:**\n"
                        "1. Re-run the workflow (a fresh attempt sometimes succeeds — the "
                        "format reminder is injected automatically after each failure).\n"
                        "2. Switch to an Anthropic or OpenAI model for agentic workflows "
                        "(`contradiction-resolver`, `orphan-resolver`, etc.) in "
                        "`[agents]` of your `config.toml`."
                    )
                elif _text_lower in _STUB_RESPONSES:
                    err = (
                        "⚠ The workflow could not continue because the model repeatedly "
                        f"returned an empty or stub response (`{text}`) instead of a tool call.\n\n"
                        "This is a model-specific behaviour — some reasoning models "
                        "(e.g. MiniMax-M2.5) do not reliably follow the JSON wire-format "
                        "tool-call protocol required for agentic workflows.\n\n"
                        "**Fix options:**\n"
                        "1. Re-run the workflow (a fresh attempt sometimes succeeds).\n"
                        "2. Switch to an Anthropic or OpenAI model for agentic workflows "
                        "(`contradiction-resolver`, `orphan-resolver`, etc.) in "
                        "`[agents]` of your `config.toml`."
                    )
                else:
                    err = (
                        "⚠ The workflow could not continue because the model's response was "
                        "repeatedly truncated or malformed.\n\n"
                        "**Likely cause:** the model hit its token limit while generating a "
                        "large tool call (e.g. outputting a full page's content).\n\n"
                        f"**Fix:** increase `workflow_max_tokens` in `[agents]` of your "
                        f"`config.toml` from **{max_tokens}** to **{recommended}** (or higher) "
                        f"and re-run the workflow:\n\n"
                        f"```toml\n[agents]\nworkflow_max_tokens = {recommended}\n```"
                    )
                for i in range(0, max(len(err), 1), _CHUNK_SIZE):
                    yield {"event": "token", "data": {"text": err[i : i + _CHUNK_SIZE]}}
                yield {"event": "final_text", "data": {"text": err}}
                return
            # Plain-text response — stream as token chunks, then emit final_text.
            for i in range(0, max(len(text), 1), _CHUNK_SIZE):
                yield {"event": "token", "data": {"text": text[i : i + _CHUNK_SIZE]}}
            yield {"event": "final_text", "data": {"text": text}}
            return
