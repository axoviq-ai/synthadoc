# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""ScaffoldWorkflow — regenerate core wiki scaffold files interactively."""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_get_scaffold_preview,
    tool_run_scaffold,
)

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """\
You are an agentic workflow executor for Synthadoc wiki maintenance.
Your task is to regenerate the wiki's core scaffold files for the configured domain.

Scaffold rewrites these files every run:
  - wiki/index.md      (categories, domain label, navigation structure)
  - wiki/purpose.md    (mission statement and scope)
  - AGENTS.md / CLAUDE.md / GEMINI.md  (agent coding guidelines)
  - ROUTING.md         (regenerated only if it already exists)

Content above the <!-- synthadoc:scaffold --> marker in index.md and purpose.md
is preserved — user-written sections above that line are never overwritten.

## Tool reference

### get_scaffold_preview
Read the configured domain and list the files that will be overwritten.
No arguments needed.
Input:  {}
Output: {"domain": str, "files_to_overwrite": [str]}

### run_scaffold
Enqueue a scaffold job for the given domain.  The tool automatically shows a
confirmation dialog to the user before writing any files; if the user declines
or the 120-second timeout fires, it returns {"status": "cancelled"} without
touching any files.
Input:  {"domain": str}
Output: {"status": "success", "domain": str, "categories_updated": int,
         "routing_regenerated": bool}
     or {"status": "cancelled", "message": str}
     or {"status": "failed"|"timeout", "message": str}
     or {"error": str}

## Tool-call wire format

Emit EXACTLY this JSON object (no markdown fences, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}

When you have no more tool calls to make, produce a plain-text summary (no JSON).

## Workflow steps

### Phase 1 — Preview
1. Call get_scaffold_preview (no arguments) to learn the domain and file list.

### Phase 2 — Run (confirmation is automatic)
2. Call run_scaffold with the domain returned in step 1.
   run_scaffold shows the user a confirmation dialog automatically before
   writing anything.
   - If status == "cancelled": write "Scaffold cancelled by user." and STOP.
   - If status == "failed" or "timeout": report the error message and STOP.
   - If "error" key present: report the error and STOP.

### Phase 3 — Report
3. Write a plain-text summary:
   - Domain scaffolded
   - Files written (list from get_scaffold_preview)
   - N pages updated with category labels (categories_updated)
   - Whether ROUTING.md was regenerated (routing_regenerated true/false)
   - A note on preservation: index.md has one <!-- synthadoc:scaffold --> marker
     below the title — content above it was preserved. purpose.md has one marker
     per section — each section's user-written content above the marker was kept.
"""


class ScaffoldWorkflow(AgenticWorkflow):
    """Regenerate core wiki scaffold files with a confirm gate before running."""

    NAME = "scaffold"
    DESCRIPTION = "Regenerate core wiki scaffold files (confirm gate before writing)."

    MATCH_RE = re.compile(
        r"^(please\s+)?\brun\b.{0,20}\bscaffold\b"
        r"|^(can|could|would)\s+(you\s+)?(please\s+)?\brun\b.{0,20}\bscaffold\b"
        r"|\b(?:rebuild|regenerate)\b.{0,20}\bscaffold\b",
        re.IGNORECASE,
    )

    # Confirm gate — Pattern A (embedded inside tool_run_scaffold).
    #
    # tool_run_scaffold calls tool_confirm internally — it builds the confirm
    # message from the domain and file list before enqueueing any job.  This
    # means no separate "confirm" tool is needed in the LLM registry, and
    # GATED_TOOLS is left empty (the base-class default).
    #
    # Choose Pattern A when the confirm message is built programmatically.
    # Choose Pattern B (GATED_TOOLS) when the LLM builds the message from
    # scan results — broken_wikilinks.py shows Pattern B with full comments.
    GATED_TOOLS: frozenset[str] = frozenset()

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "get_scaffold_preview": functools.partial(tool_get_scaffold_preview, ctx),
            "run_scaffold":         functools.partial(tool_run_scaffold, ctx),
        }
