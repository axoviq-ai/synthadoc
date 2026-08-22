# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""ScaffoldWorkflow — regenerate core wiki scaffold files interactively."""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_confirm,
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

### confirm
Send a confirmation card to the UI and wait up to 120 seconds for the user to
approve or decline.  Times out as declined.
Input:  {"message": str, "yes_label": str, "no_label": str}
Output: {"confirmed": bool}

### run_scaffold
Enqueue a scaffold job for the given domain, wait for it to complete, and
return the outcome.
Input:  {"domain": str}
Output: {"status": "success", "domain": str, "categories_updated": int,
         "routing_regenerated": bool}
     or {"status": "failed"|"timeout", "message": str}
     or {"error": str}

## Tool-call wire format

Emit EXACTLY this JSON object (no markdown fences, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}

When you have no more tool calls to make, produce a plain-text summary (no JSON).

## Workflow steps

### Phase 1 — Preview
1. Call get_scaffold_preview (no arguments).
   Build a confirmation message that lists:
   - The domain that will be scaffolded
   - Every file that will be overwritten (one per line, relative path)
   - A note that user content above <!-- synthadoc:scaffold --> markers is preserved

### Phase 2 — Confirm
2. Call confirm with the preview message.
   yes_label: "Run scaffold"
   no_label: "Cancel"
   - If confirmed == false: write "Scaffold cancelled by user." STOP.

### Phase 3 — Run
3. Call run_scaffold with the domain returned in step 1.
   - If status == "failed" or "timeout": report the error message and STOP.
   - If "error" key present: report the error and STOP.

### Phase 4 — Report
4. Write a plain-text summary:
   - Domain scaffolded
   - Files written (list)
   - N pages updated with category labels (categories_updated)
   - Whether ROUTING.md was regenerated (routing_regenerated true/false)
   - A reminder: "User-written sections above the scaffold marker were preserved."

## CRITICAL RULE — confirm before run_scaffold

You MUST call confirm (step 2) and receive {"confirmed": true} before calling run_scaffold.
- Calling run_scaffold without first calling confirm is STRICTLY PROHIBITED.
- If confirm returns {"confirmed": false}, write "Scaffold cancelled by user." and STOP.
  Do NOT call run_scaffold under any circumstances when confirmed is false.
- The sequence is always: get_scaffold_preview → confirm → run_scaffold (if confirmed).
  Skipping the confirm step and jumping directly to run_scaffold is WRONG.
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

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "get_scaffold_preview": functools.partial(tool_get_scaffold_preview, ctx),
            "confirm":              functools.partial(tool_confirm, ctx),
            "run_scaffold":         functools.partial(tool_run_scaffold, ctx),
        }
