# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import functools
from typing import Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_confirm,
    tool_find_stale_pages,
    tool_ingest_source,
    tool_poll_job,
    tool_run_lint,
)

_SYSTEM_PROMPT = """You are a wiki maintenance agent. You have these tools available:

find_stale_pages — list all stale wiki pages with their source file paths.
  Input: {}
  Output: {"pages": [{"slug": str, "source_path": str|null, "stale_since": str}]}

ingest_source — queue a re-ingest job for one source file.
  Input: {"source_path": str}
  Output: {"job_id": str} | {"error": str}

poll_job — wait for a queued job to complete.
  Input: {"job_id": str, "timeout_seconds": int (default 120)}
  Output: {"status": "success"|"failed"|"timeout", "message": str}

run_lint — queue a lint run.
  Input: {"scope": str (default "all")}
  Output: {"job_id": str} | {"error": str}

confirm — ask the user to confirm before proceeding with a potentially destructive action.
  Input: {"message": str, "yes_label": str (default "Yes"), "no_label": str (default "No")}
  Output: {"confirmed": bool}

To call a tool, respond EXACTLY with this JSON and nothing else:
{"tool_call": {"name": "<tool_name>", "input": <input_dict>}}

When you have a final message for the user, respond with plain text only (no tool_call JSON).
"""


class IngestLintWorkflow(AgenticWorkflow):
    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "find_stale_pages": functools.partial(tool_find_stale_pages, ctx),
            "ingest_source": functools.partial(tool_ingest_source, ctx),
            "poll_job": functools.partial(tool_poll_job, ctx),
            "run_lint": functools.partial(tool_run_lint, ctx),
            "confirm": functools.partial(tool_confirm, ctx),
        }
