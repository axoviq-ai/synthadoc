# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ContentHealthResolverWorkflow — detect and fix wiki content quality issues.

Heuristic scanner flags pages post-ingest; this workflow loads the flagged
pages, runs LLM deep analysis, presents a side-by-side diff for user approval,
snapshots before each write, and stores a fix_record for later rollback.
"""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import tool_confirm, tool_notify
from synthadoc.agents.workflows.tools.content_health_tools import (
    tool_get_page_content,
    tool_list_content_health_fixes,
    tool_rollback_content_health_fix,
    tool_write_content_health_fix,
)
from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """\
You are an agentic workflow executor for Synthadoc wiki maintenance.
Your task is to fix content quality issues on wiki pages — duplicate sections,
empty sections, thin sections, unclosed code blocks, orphaned headings, and
broken list nesting. Only ACTIVE pages are processed.

━━━ TOOL-CALL WIRE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Emit EXACTLY this JSON object (no markdown fences, no XML, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}
When delivering a final message for the user, respond with plain text only (no JSON).

━━━ TOOL INVENTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

get_page_content
  Read the raw markdown content and existing issues for a page.
  Input:  {"slug": str}
  Output: {"status": "success"|"error", "slug": str, "title": str, "content": str,
           "issues": [{"type": str, "severity": str, "location": str, "description": str}]}

write_content_health_fix
  Apply a content-health fix. A snapshot is taken before writing.
  The confirm gate fires automatically before the first call.
  Input:  {"slug": str, "content": str, "issues_fixed": [str]}
  Output: {"status": "success"|"error", "slug": str, "snapshot_index": int,
           "remaining_issues": int, "fix_record": dict}

list_content_health_fixes
  List all pages previously fixed by this workflow, sorted newest first.
  Input:  {}
  Output: {"fixes": [{"slug": str, "title": str, "fixed_at": str,
                      "issues_fixed": [str], "snapshot_index_before": int}]}

rollback_content_health_fix
  Roll back one page to its pre-fix snapshot.
  Input:  {"slug": str}
  Output: {"status": "success"|"error", "slug": str, "rolled_back_to_snapshot": int,
           "message": str}

confirm
  Send a confirmation card to the UI and wait up to 120 seconds.
  Input:  {"message": str, "yes_label": str, "no_label": str}
  Output: {"confirmed": bool}

notify
  Send a non-blocking notice (does NOT terminate the workflow).
  Input:  {"level": "info"|"warning"|"error", "message": str}
  Output: {}

━━━ WORKFLOW STEPS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Parse the page list from the initial message.
  Sort pages: critical issues first, then high, then medium. Within each
  severity, sort by issue count descending.

STEP 2 — Opening confirm before any work begins.
  Call confirm with:
    "Found N page(s) with content issues (X critical, Y high, Z medium).
    Pages processed highest-severity first. A snapshot is saved before each
    change — say 'list content health fixes' or 'roll back [page]' to undo.
    Ready to begin?"
  yes_label="Begin", no_label="Cancel"
  If not confirmed: output plain-text cancel message and stop.

STEP 3 — Per-page loop:

  3a. Call get_page_content(slug=<slug>).

  3b. DEEP ANALYSIS:
      Read the full content and all reported issues carefully.
      Identify ALL issues including any additional semantic problems.
      Compose a rewrite that ONLY fixes structural issues — never alter
      factual content.

  3c. Call confirm with a SIDE-BY-SIDE DIFF message:
      Show "BEFORE:" with affected sections and "AFTER:" with proposed rewrite.
      List the issue types being addressed.
      yes_label="Approve", no_label="Skip this page"

      If confirmed → proceed to 3d.
      If not confirmed AND user said "stop" → output final summary, stop.
      If not confirmed → skip page (no snapshot, no write), continue to next.

  3d. On approval:
      Call write_content_health_fix(slug=<slug>, content=<rewritten>,
        issues_fixed=[<list of "type xN" strings>])
      If remaining_issues > 0: call notify(level="warning", message=...)
      Output summary line: "<slug>: N issues fixed. Snapshot saved — say
        'roll back <slug>' to undo."

STEP 4 — Final summary (plain text only):
  "Content Health Resolver — Complete

  ✅ Fixed (N pages):
  - **<slug>**: <issues> → Snapshot saved
  ...
  ⏭ Skipped (N pages): <slug>, ...

  Say 'list content health fixes' to review all changes.
  Say 'roll back <slug>' to undo any individual page."

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NEVER output plain text while work remains — plain text terminates the workflow.
2. NEVER modify factual content — only fix structural/formatting issues.
3. ALWAYS call write_content_health_fix after user approves.
"""


class ContentHealthResolverWorkflow(AgenticWorkflow):
    """Detect and fix wiki content quality issues interactively."""

    NAME = "content-health"
    DESCRIPTION = (
        "Scan active wiki pages for content quality issues (duplicate sections, "
        "thin sections, broken markdown) and fix them interactively with "
        "side-by-side diff approval and snapshot rollback."
    )
    CLI_ARGS = "[--slug SLUG]"
    RERUN_HINT = "Run content health resolver"
    SUPPORTS_CLI_PROVIDER = True

    MATCH_RE = re.compile(
        r"\bcontent.?health\b"
        r"|\bfix.{0,20}content\b"
        r"|\bduplicate.{0,20}sections?\b"
        r"|\bcontent.{0,20}issues?\b"
        r"|\bcontent.{0,15}resolver\b",
        re.IGNORECASE,
    )

    GATED_TOOLS: frozenset[str] = frozenset({"write_content_health_fix"})

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "get_page_content": functools.partial(tool_get_page_content, ctx),
            "write_content_health_fix": functools.partial(tool_write_content_health_fix, ctx),
            "list_content_health_fixes": functools.partial(tool_list_content_health_fixes, ctx),
            "rollback_content_health_fix": functools.partial(tool_rollback_content_health_fix, ctx),
            "confirm": functools.partial(tool_confirm, ctx),
            "notify": functools.partial(tool_notify, ctx),
        }

    def get_tool_budget(self) -> int:
        return 200  # large budget — may process many pages

    async def run_for_cli_provider(
        self,
        ctx: "WorkflowContext",
        question: str,
        provider: "LLMProvider",  # type: ignore[name-defined]
    ):
        """CLI-provider path: Python-driven gather → LLM analysis → typer.confirm → write."""
        # Implemented in Task 7.
        raise NotImplementedError(
            "run_for_cli_provider not yet implemented — see Task 7."
        )
        if False:  # pragma: no cover
            yield {}  # type: ignore[misc]
