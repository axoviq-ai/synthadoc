# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""LintReportWorkflow — run a full lint pass and surface the complete report."""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_get_lint_report,
    tool_run_lint,
)

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """\
You are a wiki maintenance agent. Your task is to run a full lint pass and
show the user a complete lint report when it finishes.

## Tool reference

### run_lint
Run a full wiki lint pass and wait for it to complete. Blocks until done.
Input:  {}
Output: {"status": "success"|"failed"|"timeout", "message": str} | {"error": str}

### get_lint_report
Read the full lint state from the audit DB and page frontmatter.
No arguments needed.
Input:  {}
Output: {
  "last_run": {
    "timestamp": str, "dangling_removed": int, "orphans": int,
    "contradictions_resolved": int, "contradictions_flagged": int
  },
  "contradicted_pages": [{"slug": str, "since": str}],
  "adversarial_warnings": [{"slug": str, "count": int}],
  "orphan_slugs": [str]
}

## Tool-call wire format

Emit EXACTLY this JSON object (no markdown fences, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}

When you have a final message for the user, respond with plain text only (no JSON).

## Workflow steps

1. Call run_lint with no arguments. Blocks until the lint job finishes.
   - If it returns {"error": ...}: write a plain-text error message and STOP.
   - If it returns {"status": "failed"|"timeout", ...}: write a plain-text error and STOP.
2. Call get_lint_report with no arguments.
3. Write a plain-text report using this structure:

   ### Lint Report (use the timestamp from last_run, or today's date if missing)

   **Summary**
   - Dangling links removed: N  (omit this line if dangling_removed == 0)
   - Orphan pages: N
   - Contradictions: N resolved, N flagged

   **Contradicted Pages**
   List each as "- slug  (since YYYY-MM-DD)".
   If none: "(none)"

   **Adversarial Warnings**
   List each as "- [[slug]]  (N warning(s))".
   If none: "(none)"

   **Orphan Pages**
   List each slug as a bullet.
   If none: "(none)"

Plain text ends the workflow. Use it ONLY in step 3 or on error. All
intermediate steps must be tool calls, not prose.
"""


class LintReportWorkflow(AgenticWorkflow):
    """Run a full lint pass then surface the complete report in one shot."""

    NAME = "lint-report"
    DESCRIPTION = "Run a full lint pass and surface the complete report."

    MATCH_RE = re.compile(
        r"^(please\s+)?\brun\b.{0,20}\blint\b"
        r"|^(can|could|would)\s+(you\s+)?(please\s+)?\brun\b.{0,20}\blint\b",
        re.IGNORECASE,
    )

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "run_lint":        functools.partial(tool_run_lint, ctx),
            "get_lint_report": functools.partial(tool_get_lint_report, ctx),
        }
