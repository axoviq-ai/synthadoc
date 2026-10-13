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
from typing import Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import tool_confirm, tool_notify
from synthadoc.agents.workflows.tools.content_health_tools import (
    tool_find_content_health_issues,
    tool_get_page_content,
    tool_list_content_health_fixes,
    tool_rollback_content_health_fix,
    tool_write_content_health_fix,
)
from synthadoc.storage.wiki import LifecycleState

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

find_content_health_issues
  Discover all ACTIVE wiki pages that have content health issues.
  Call this FIRST (STEP 1) to build the work list.
  Input:  {"slug": str}  — omit slug (or pass "") to scan the whole wiki
  Output: {"status": "success"|"error", "total": int,
           "pages": [{"slug": str, "title": str, "issue_count": int,
                      "top_severity": str, "issues": [...]}]}
  Pages are pre-sorted: critical first, then by issue count descending.

get_page_content
  Read the raw markdown content and existing issues for a page.
  Input:  {"slug": str}
  Output: {"status": "success"|"error", "slug": str, "title": str, "content": str,
           "issues": [{"type": str, "severity": str, "location": str, "description": str}]}

write_content_health_fix
  Apply a content-health fix. A snapshot is taken before writing.
  MANDATORY SEQUENCE (enforced): get_page_content(slug) → confirm → write_content_health_fix(slug)
  • You MUST have called get_page_content for this EXACT slug first.
  • The content argument MUST be the get_page_content response with ONLY structural
    fixes applied — never invented or recalled from training.
  • You MUST call confirm with a side-by-side diff BEFORE every call to this tool.
  • The slug MUST be one returned by find_content_health_issues in this session.
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

STEP 1 — Discover pages with issues.
  Call find_content_health_issues (pass slug="" to scan the whole wiki, or
  the specific slug if one was requested).
  The tool returns pages pre-sorted: critical first, then by issue count.
  If total=0: output plain text "No active pages with content health issues found." and stop.

STEP 2 — Opening summary before any work begins.
  Call notify with level="info" and message:
    "Found N page(s) with content issues (X critical, Y high, Z medium).
    Processing highest-severity pages first. A snapshot is saved before each
    change — say 'list content health fixes' or 'roll back [page]' to undo."
  Then proceed immediately to STEP 3.

STEP 3 — Per-page loop:

  3a. Call get_page_content(slug=<slug>).
      If the result has status="error": the page cannot be read.
      → STOP processing this slug immediately.
      → Do NOT call write_content_health_fix for it.
      → Do NOT invent or generate any content for it.
      → Move on to the next slug in the discovery list.

  3b. DEEP ANALYSIS:
      Read the full content and all reported issues carefully.
      Identify ALL issues including any additional semantic problems.
      Compose a rewrite that ONLY fixes structural issues — never alter
      factual content.

  3c. Call confirm with a SIDE-BY-SIDE DIFF message:
      message should contain ONLY:
        - "BEFORE:" with the affected sections (current state)
        - "AFTER:" with the proposed rewrite of those sections
        - A line listing the issue types being addressed
      Do NOT include "yes_label" or "no_label" text in the message field —
      those are separate JSON fields in the tool call: yes_label="Approve", no_label="Skip this page".

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
3. ALWAYS follow the exact per-page sequence: get_page_content → confirm → write_content_health_fix.
   Skipping get_page_content means you are writing content you invented, not the real page.
   Skipping confirm means the user cannot review changes before they are applied.
4. NEVER call write_content_health_fix with a slug that was not returned by
   find_content_health_issues. Only process pages from the discovery list.
5. NEVER invent or guess page content. The content you pass to write_content_health_fix
   MUST come from the get_page_content response for that exact slug — with ONLY the
   structural issues corrected, nothing else changed.
"""


def _format_fix_list(fixes: list[dict]) -> str:
    """Render tool_list_content_health_fixes() output as plain text."""
    if not fixes:
        return "No content health fixes have been recorded yet."
    lines = [f"Content health fixes ({len(fixes)}):"]
    for fix in fixes:
        issues = ", ".join(fix.get("issues_fixed") or []) or "issues fixed"
        lines.append(
            f"- {fix['slug']} — {fix.get('fixed_at') or 'unknown time'} — {issues} "
            f"(pre-fix snapshot #{fix.get('snapshot_index_before')})"
        )
    return "\n".join(lines)


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
        r"|\bcontent.{0,15}resolver\b"
        r"|\broll\s*back\b",
        re.IGNORECASE,
    )

    GATED_TOOLS: frozenset[str] = frozenset({"write_content_health_fix"})
    GATED_TOOLS_PER_CALL: frozenset[str] = frozenset({"write_content_health_fix"})

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    _LIST_RE = re.compile(r"\blist\b", re.IGNORECASE)
    _ROLLBACK_BARE_RE = re.compile(r"\broll\s*back\b", re.IGNORECASE)
    _ROLLBACK_RE = re.compile(r"\broll\s*back\b\s+(\S+)", re.IGNORECASE)

    @classmethod
    def _parse_intent(cls, user_input: str) -> tuple[str, str | None]:
        """Classify a request as ("list", None), ("rollback", slug | None) or ("fix", None).

        Shared by the API path (build_initial_message) and the CLI-provider path
        (run_for_cli_provider) so both honour the same list / roll back intents.
        """
        # "list content health fixes" → show fix history, not find new issues
        if cls._LIST_RE.search(user_input):
            return "list", None
        # "roll back SLUG" or bare "roll back" → restore a page's pre-fix snapshot
        if cls._ROLLBACK_BARE_RE.search(user_input):
            match = cls._ROLLBACK_RE.search(user_input)
            return "rollback", match.group(1).rstrip(".,;") if match else None
        return "fix", None

    def build_initial_message(self, user_input: str) -> str:
        intent, slug = self._parse_intent(user_input)
        if intent == "list":
            return (
                "The user wants to see which pages have been fixed by the content health resolver.\n"
                "Call list_content_health_fixes() and present the results as a formatted plain-text list.\n"
                "If the fixes list is empty: output 'No content health fixes have been recorded yet.'\n"
                "Output plain text only — no JSON, no tool calls after the list is printed."
            )
        if intent == "rollback":
            if slug:
                return (
                    f"The user wants to roll back the content health fix for page '{slug}'.\n"
                    f"Call rollback_content_health_fix(slug='{slug}') and report the result as plain text.\n"
                    "Output plain text only — do not call any other tools."
                )
            # "roll back" without a specific slug → list fixes so user can choose
            return (
                "The user wants to roll back a content health fix but did not specify which page.\n"
                "Call list_content_health_fixes() and present the results, then ask the user "
                "which page to roll back.\n"
                "Output plain text only."
            )
        # Single-page targeted run
        slug_match = re.search(r"--slug\s+(\S+)", user_input, re.IGNORECASE)
        if slug_match:
            slug = slug_match.group(1)
            return (
                f"Run the content health resolver for a single page: {slug}\n"
                f"FIRST: call find_content_health_issues(slug='{slug}') to check "
                f"whether this page has any issues. If total=0: stop with a plain-text "
                f"'No issues found for {slug}' message. Otherwise proceed to STEP 2."
            )
        return (
            "Run the content health resolver workflow.\n"
            "FIRST: call find_content_health_issues(slug='') to discover all ACTIVE pages "
            "with content quality issues. If total=0: stop with a plain-text "
            "'No active pages with content health issues found.' message.\n"
            "Otherwise proceed through STEP 2 (opening confirm) and STEP 3 (per-page loop) "
            "WITHOUT STOPPING mid-task.\n"
            "IMPORTANT: Do NOT pause to ask 'Would you like me to continue?' — plain text "
            "exits the workflow permanently. Produce plain text ONLY for the FINAL summary (STEP 4)."
        )

    def get_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        # Track which slugs are legitimate (found by find_content_health_issues)
        # and which have been read via get_page_content.  write_content_health_fix
        # is blocked at the function level for any slug not in both sets, so the
        # LLM cannot write invented content even if it skips the workflow steps.
        found_slugs: set[str] = set()
        read_slugs: set[str] = set()

        async def _find_issues(slug: str = "") -> dict:
            result = await tool_find_content_health_issues(ctx, slug)
            if result.get("status") == "success":
                for page in result.get("pages", []):
                    found_slugs.add(page["slug"])
            return result

        async def _get_content(slug: str) -> dict:
            # Reject slugs that were never returned by find_content_health_issues.
            # This catches the case where the LLM invents a slug from imagination
            # rather than using the actual discovery results.
            if found_slugs and slug not in found_slugs:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "content-health: LLM requested get_page_content(%r) but that slug "
                    "was not in the discovery results. Valid slugs: %s",
                    slug, sorted(found_slugs),
                )
                return {
                    "status": "error",
                    "error": (
                        f"'{slug}' was not returned by find_content_health_issues. "
                        "Only use slugs from the discovery results."
                    ),
                    "action": (
                        "Do NOT invent page slugs. Re-read the find_content_health_issues "
                        "result and use only the slugs listed there."
                    ),
                    "valid_slugs": sorted(found_slugs),
                }
            result = await tool_get_page_content(ctx, slug)
            if result.get("status") == "success":
                read_slugs.add(slug)
            else:
                result["action"] = (
                    f"Skip '{slug}' entirely. "
                    "Do NOT call write_content_health_fix for this slug. "
                    "Continue to the next slug in the discovery list."
                )
            return result

        async def _write_fix(slug: str, content: str, issues_fixed: list) -> dict:
            if slug not in read_slugs:
                return {
                    "status": "error",
                    "error": (
                        f"Workflow violation: get_page_content('{slug}') must be called "
                        "before write_content_health_fix. Call get_page_content now."
                    ),
                }
            if found_slugs and slug not in found_slugs:
                return {
                    "status": "error",
                    "error": (
                        f"Workflow violation: '{slug}' was not returned by "
                        "find_content_health_issues. Only process pages from the "
                        "discovery list."
                    ),
                }
            return await tool_write_content_health_fix(ctx, slug=slug, content=content,
                                                       issues_fixed=issues_fixed)

        return {
            "find_content_health_issues": _find_issues,
            "get_page_content": _get_content,
            "write_content_health_fix": _write_fix,
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
        """CLI-provider path: Python-driven gather → LLM analysis → tool_confirm → write.

        Called server-side when the provider is a CodingToolCLIProvider (claude-code,
        opencode).  All output and confirmations go through SSE events so they reach
        the HTTP stream; typer is not used here.
        """
        if ctx.store is None:
            yield {"event": "final_text", "data": {"text": "No wiki store available."}}
            return

        # "list" / "roll back" intents need no LLM — answer them directly instead
        # of starting a new scan-and-fix session.
        intent, rollback_slug = self._parse_intent(question)
        if intent == "rollback" and rollback_slug:
            result = await tool_rollback_content_health_fix(ctx, rollback_slug)
            text = result.get("message") or f"Rollback of '{rollback_slug}' failed."
            yield {"event": "final_text", "data": {"text": text}}
            return
        if intent in ("list", "rollback"):
            listing = await tool_list_content_health_fixes(ctx)
            text = _format_fix_list(listing.get("fixes", []))
            if intent == "rollback" and listing.get("fixes"):
                text += "\nSay 'roll back <slug>' to restore one of these pages."
            yield {"event": "final_text", "data": {"text": text}}
            return

        _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        flagged = []
        for slug in ctx.store.list_pages():
            page = ctx.store.read_page(slug)
            if page is None or page.status != LifecycleState.ACTIVE or not page.content_health_issues:
                continue
            top_sev = min(_SEVERITY_ORDER.get(i["severity"], 9) for i in page.content_health_issues)
            flagged.append((top_sev, -len(page.content_health_issues), slug, page))
        flagged.sort()

        # Filter to --slug if given
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        if slug_match:
            requested = slug_match.group(1).lower()
            flagged = [(s, c, sl, pg) for s, c, sl, pg in flagged if sl == requested]

        if not flagged:
            yield {"event": "final_text", "data": {"text": "No active pages with content issues found."}}
            return

        counts: dict[str, int] = {}
        for _, _, _, pg in flagged:
            for issue in pg.content_health_issues:
                counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1

        summary_parts = [f"{v} {k}" for k, v in sorted(counts.items())]
        opening_msg = (
            f"Found {len(flagged)} page(s) with content issues "
            f"({', '.join(summary_parts)}).\n"
            "A snapshot is saved before each change — say 'roll back [page]' to undo.\n"
            "Ready to begin?"
        )
        gate = await tool_confirm(ctx, message=opening_msg, yes_label="Begin", no_label="Cancel")
        if not gate.get("confirmed"):
            yield {"event": "final_text", "data": {"text": "Content health resolver cancelled."}}
            return

        fixed: list[str] = []
        skipped: list[str] = []

        for _sev, _count, slug, page in flagged:
            issues_summary = ", ".join(
                f"{i['type']} ({i['severity']})" for i in page.content_health_issues[:3]
            )
            yield {"event": "token", "data": {"text": f"\n--- {slug} ---\nIssues: {issues_summary}\n"}}

            prompt = (
                f"Wiki page '{slug}':\n\n{page.content}\n\n"
                f"Detected issues: {page.content_health_issues}\n\n"
                "Rewrite ONLY the affected sections to fix these structural issues. "
                "Do NOT change factual content. Return ONLY the complete rewritten page markdown."
            )
            proposed = await provider.complete(prompt)

            before_excerpt = page.content[:400] + ("..." if len(page.content) > 400 else "")
            after_excerpt = proposed[:400] + ("..." if len(proposed) > 400 else "")
            diff_msg = (
                f"**{slug}** — {issues_summary}\n\n"
                f"**BEFORE:**\n```\n{before_excerpt}\n```\n\n"
                f"**AFTER:**\n```\n{after_excerpt}\n```"
            )
            gate = await tool_confirm(ctx, message=diff_msg, yes_label="Approve", no_label="Skip this page")
            if gate.get("confirmed"):
                result = await tool_write_content_health_fix(
                    ctx, slug=slug, content=proposed,
                    issues_fixed=[i["type"] for i in page.content_health_issues],
                )
                if result["status"] == "success":
                    snapshot_idx = result.get("snapshot_index", "?")
                    fixed.append(slug)
                    yield {"event": "token", "data": {
                        "text": f"✅ {slug}: fixed. Snapshot #{snapshot_idx} saved.\n"
                    }}
                else:
                    yield {"event": "token", "data": {
                        "text": f"⚠ {slug}: write failed — {result.get('error')}\n"
                    }}
            else:
                skipped.append(slug)
                yield {"event": "token", "data": {"text": f"⏭ {slug}: skipped.\n"}}

        final_summary = (
            f"\nContent Health Resolver — Complete\n"
            f"✅ Fixed: {len(fixed)} page(s) — {', '.join(fixed) or 'none'}\n"
            f"⏭ Skipped: {len(skipped)} page(s) — {', '.join(skipped) or 'none'}\n"
        )
        yield {"event": "final_text", "data": {"text": final_summary}}
