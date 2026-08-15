# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import functools
import re
from typing import Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_confirm,
    tool_find_page_source,
    tool_find_stale_pages,
    tool_get_page_states,
    tool_ingest_source,
    tool_poll_job,
    tool_run_lint,
)

_SYSTEM_PROMPT = """You are a wiki maintenance agent. You have these tools available:

find_stale_pages — list all stale wiki pages with their source file paths.
  Input: {}
  Output: {"pages": [{"slug": str, "source_path": str|null, "stale_since": str}]}

find_page_source — look up the source file path for any wiki page by slug,
  regardless of its current lifecycle state (active, draft, stale, etc.).
  Input: {"slug": str}
  Output: {"slug": str, "source_path": str} | {"error": str}

ingest_source — re-ingest one source file and return the outcome when the job finishes.
  Always force-processes the file even if it hasn't changed.
  Input: {"source_path": str}
  Output: {"status": "success"|"failed"|"timeout", "message": str, "job_id": str} | {"error": str}

poll_job — poll a queued job for its current status.
  Input: {"job_id": str, "timeout_seconds": int (default 240)}
  Output: {"status": "success"|"failed"|"timeout", "message": str}

run_lint — queue a lint run.
  Input: {"scope": str (default "all")}
  Output: {"job_id": str} | {"error": str}

get_page_states — return the current lifecycle state of one or more pages.
  Input: {"slugs": [str, ...]}
  Output: {"pages": [{"slug": str, "state": str}]}
  state is one of: "active", "stale", "draft", "archived", "unknown".
  Call this AFTER lint completes to confirm whether the re-ingest achieved its goal.

confirm — ask the user to confirm before proceeding.
  Input: {"message": str, "yes_label": str (default "Yes"), "no_label": str (default "No")}
  Output: {"confirmed": bool}
  If confirm returns {"confirmed": false}, respond with a brief plain-text message
  acknowledging the cancellation (use the word "cancelled") and stop.

Workflow A — re-ingest ALL stale pages:
1. Call find_stale_pages.
2. Call confirm IMMEDIATELY — list the pages in the message, ask whether to proceed.
   Use the confirm TOOL; never write plain text to ask (that exits the loop).
3. If confirmed, call ingest_source for each page with a valid source_path — one page
   at a time, waiting for each result before calling the next.
4. Call run_lint — MANDATORY even if one or more ingests failed. Returns a job_id.
5. Call poll_job(job_id=<lint_job_id>) to wait for the lint job to complete.
6. Call get_page_states with the slugs of every page you attempted to re-ingest.
7. Plain-text summary of every re-ingest outcome, the lint result (pass/fail), and
   a "Page states after re-ingest" section listing each slug with its current state.
   Use ✓ for active, ✗ for stale, and ○ for draft/archived/unknown.

Workflow B — re-ingest a SPECIFIC page by slug:
1. Call find_page_source(slug=<slug>) to get its source path.
2. Call confirm IMMEDIATELY — include the slug and path in the message.
   Use the confirm TOOL; never write plain text to ask (that exits the loop).
3. If confirmed, call ingest_source(source_path=<path>).
4. Call run_lint — MANDATORY regardless of whether the ingest succeeded. Returns a job_id.
5. Call poll_job(job_id=<lint_job_id>) to wait for the lint job to complete.
6. Call get_page_states(slugs=[<slug>]) to check the page's current lifecycle state.
7. Plain-text summary of the ingest result, the lint result (pass/fail), and the
   final page state. Use ✓ for active, ✗ for stale, ○ for draft/archived/unknown.

CRITICAL RULE: Steps 4→5→6 are REQUIRED after every confirmed ingest_source call.
You MUST call run_lint, then poll_job, then get_page_states — in that order — before
writing any plain-text response. Providing a summary without completing these three
steps is NOT allowed, even if earlier steps encountered errors.

Plain text ends the workflow — use it ONLY in the final summary step or when
confirm returns false. All intermediate steps must be tool calls, not plain text.

To call a tool, respond EXACTLY with this JSON and nothing else:
{"tool_call": {"name": "<tool_name>", "input": <input_dict>}}

When you have a final message for the user, respond with plain text only (no tool_call JSON).
"""


class IngestLintWorkflow(AgenticWorkflow):
    MATCH_RE = re.compile(
        r"\bstale\s+pages?\b"
        r"|\borchestrat"
        r"|\b(guided|agentic)\s+(maintenance\s+)?workflow\b"
        r"|\bre.?ingest\b.{0,60}\bstale\b|\bstale\b.{0,60}\bre.?ingest\b"
        r"|\bre.?ingest\b\s+the\s+[a-z0-9]",
        re.IGNORECASE,
    )

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "find_stale_pages": functools.partial(tool_find_stale_pages, ctx),
            "find_page_source": functools.partial(tool_find_page_source, ctx),
            "ingest_source": functools.partial(tool_ingest_source, ctx),
            "poll_job": functools.partial(tool_poll_job, ctx),
            "run_lint": functools.partial(tool_run_lint, ctx),
            "get_page_states": functools.partial(tool_get_page_states, ctx),
            "confirm": functools.partial(tool_confirm, ctx),
        }
