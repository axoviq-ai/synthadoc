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
    tool_dismiss_content_health_issues,
    tool_find_content_health_issues,
    tool_get_page_content,
    tool_list_content_health_fixes,
    tool_rollback_content_health_fix,
    tool_write_content_health_fix,
)
from synthadoc.storage.wiki import LifecycleState, SYSTEM_PAGE_SLUGS

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

dismiss_content_health_issues
  Dismiss issues that CANNOT be fixed by this workflow (e.g. all remaining
  issues are 'thin_section' which require adding factual prose — prohibited here).
  Clears content_health_issues from frontmatter so the hint chip stops surfacing
  this page. Does NOT modify page content or create a snapshot.
  ALWAYS call notify FIRST to explain the dismissal, then call this tool.
  Input:  {"slug": str, "reason": str}
  Output: {"status": "success"|"error", "slug": str, "dismissed_count": int,
           "remaining_issues": int, "reason": str}

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
    Pages to process: <list every slug from pages[] here, comma-separated>.
    Processing highest-severity pages first. A snapshot is saved before each
    change — say 'list content health fixes' or 'roll back [page]' to undo."
  Then proceed immediately to STEP 3.

STEP 3 — Per-page loop.
  Iterate ONLY over the slug values in the pages[] array returned by
  find_content_health_issues. Do NOT use any slug that was not in that array.
  Do NOT invent, guess, or recall slugs from training knowledge.

  For EACH slug in pages[] (in order):

  3a. Call get_page_content using the EXACT slug string from the pages[] entry.
      Copy the slug character-for-character from the find_content_health_issues
      result — do not alter it in any way.
      If the result has status="error":
      → STOP processing this slug immediately.
      → Do NOT call write_content_health_fix for it.
      → Do NOT invent or generate any content for it.
      → Move on to the next slug in the discovery list.

  3b. DEEP ANALYSIS:
      Read the full content (from the get_page_content result) and all reported
      issues carefully. Compose a rewrite that ONLY fixes structural issues —
      never alter factual content. Base your rewrite ENTIRELY on the content
      returned by get_page_content — do not add information from other sources.

  3c. Call confirm with a SIDE-BY-SIDE DIFF message:
      message should contain ONLY:
        - "BEFORE:" with the affected sections (current state from get_page_content)
        - "AFTER:" with the proposed rewrite of those sections
        - A line listing the issue types being addressed
      Do NOT include "yes_label" or "no_label" text in the message field —
      those are separate JSON fields in the tool call: yes_label="Approve", no_label="Skip this page".

      If confirmed → proceed to 3d.
      If not confirmed AND user said "stop" → output final summary, stop.
      If not confirmed → skip page (no snapshot, no write), continue to next.

  3d. On approval:
      Call write_content_health_fix using the SAME slug from the pages[] entry,
        content=<rewritten content based on get_page_content result>,
        issues_fixed=[<list of "type xN" strings>]
      If remaining_issues > 0 and ALL remaining issues are unfixable (e.g. thin_section):
        proceed to 3e for those remaining issues.
      Else if remaining_issues > 0: call notify(level="warning", message=...)
      Output summary line: "<slug>: N issues fixed. Snapshot saved — say
        'roll back <slug>' to undo."

  3e. DISMISSAL — when ALL issues on a page (or all REMAINING issues after 3d) are
      structurally unfixable by this workflow (all are 'thin_section', or fixing them
      would require inventing factual content):
      1. Call notify(level="warning", message="<slug>: N issue(s) cannot be fixed
         automatically. [Explain what type they are and why human editing is needed.
         Tell the user exactly which sections need expanding and by how many words.]")
      2. Call dismiss_content_health_issues(slug=<slug>,
           reason="<brief reason, e.g. 'all issues are thin_section requiring human editing'>")
      3. Output summary line: "<slug>: N issue(s) dismissed — requires human editing."

      When to use 3e (NEVER write invented content instead):
      - All issues are type 'thin_section'
      - Fixing any issue would require adding new factual sentences
      - Any issue cannot be resolved by structural reformatting alone

STEP 4 — Final summary (plain text only):
  "Content Health Resolver — Complete

  ✅ Fixed (N pages):
  - **<slug>**: <issues> → Snapshot saved
  ...
  ⚠️ Dismissed — requires human editing (N pages):
  - **<slug>**: <issue types> → A human editor must expand these sections
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
6. ONLY use slugs from the pages[] array in the find_content_health_issues result.
   This means: iterate over result["pages"], take result["pages"][i]["slug"], and use
   THAT STRING — character for character — as the slug argument in every subsequent
   tool call. Do NOT substitute a slug from your training knowledge, from memory, or
   from any other source. If you do not have a find_content_health_issues result yet,
   call that tool first before calling any other tool.
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


def _section_excerpt(content: str, issues: list[dict], max_chars: int = 800) -> str:
    """Return a diff excerpt focused on the sections referenced by issues.

    Extracts each affected heading and its body from *content*, separated by
    '---' dividers.  Falls back to a plain head-truncation when no heading
    locations are present (e.g. unclosed_code_block, broken_list_nesting).
    """
    target_headings = {
        i.get("location", "")
        for i in issues
        if i.get("location") and not i["location"].startswith("line ")
    }
    if not target_headings:
        return content[:max_chars] + ("..." if len(content) > max_chars else "")

    lines = content.splitlines(keepends=True)
    captured: list[str] = []
    total = 0
    i = 0
    while i < len(lines) and total < max_chars:
        m = re.match(r"^(#{1,6})\s+(.*)", lines[i].rstrip())
        if m and m.group(2).strip() in target_headings:
            level = len(m.group(1))
            j = i + 1
            while j < len(lines):
                nm = re.match(r"^(#{1,6})\s", lines[j].rstrip())
                if nm and len(nm.group(1)) <= level:
                    break
                j += 1
            block = "".join(lines[i:j]).rstrip()
            captured.append(block)
            total += len(block)
            i = j
        else:
            i += 1

    if not captured:
        return content[:max_chars] + ("..." if len(content) > max_chars else "")

    result = "\n\n---\n\n".join(captured)
    return result[:max_chars] + ("..." if len(result) > max_chars else "")


def _extract_md_from_response(text: str) -> str:
    """Strip tool-call artifacts and narrative from a CLI provider response.

    opencode/claude-code may include shell command output and a summary
    sentence before or after the rewritten markdown.  Find the first H1
    heading and return everything from there to the last non-empty line.
    """
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"^# \S", ln)), None)
    if start is None:
        return text.strip()
    end = len(lines)
    while end > start and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end])


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
        prediscovered = getattr(self, "_prediscovered_slugs", [])
        if not prediscovered:
            return (
                "Run the content health resolver workflow.\n"
                "FIRST: call find_content_health_issues(slug='') to discover all ACTIVE pages "
                "with content quality issues. If total=0: stop with a plain-text "
                "'No active pages with content health issues found.' message.\n"
                "Otherwise proceed through STEP 2 (opening notify) and STEP 3 (per-page loop) "
                "WITHOUT STOPPING mid-task.\n"
                "IMPORTANT: Do NOT pause to ask 'Would you like me to continue?' — plain text "
                "exits the workflow permanently. Produce plain text ONLY for the FINAL summary (STEP 4)."
            )
        # The pages with content health issues have already been identified by Python.
        # Give the LLM the EXACT slug strings upfront so it never needs to guess.
        slug_bullet_list = "\n".join(f"  • {s}" for s in prediscovered)
        slug_comma_list = ", ".join(prediscovered)
        return (
            f"Run the content health resolver workflow.\n\n"
            f"These {len(prediscovered)} page(s) have content health issues in this wiki:\n"
            f"{slug_bullet_list}\n\n"
            f"STEP 1: Call find_content_health_issues(slug='') to get full issue details.\n\n"
            f"STEP 2: Call notify with a summary that lists exactly: {slug_comma_list}\n\n"
            f"STEP 3: For EACH slug in this exact list — {slug_comma_list} — call:\n"
            f"  a. get_page_content(slug=\"<exact slug from list above>\")\n"
            f"  b. compose a structural fix\n"
            f"  c. confirm with BEFORE/AFTER diff\n"
            f"  d. write_content_health_fix(slug=\"<exact slug>\", ...)\n\n"
            f"CRITICAL: The ONLY valid slug values are: {slug_comma_list}\n"
            f"Do NOT call any tool with a slug not in that list.\n"
            f"Do NOT pause mid-task. Plain text ONLY in the final summary."
        )

    def build_guarded_tool_fns(self, ctx: WorkflowContext) -> dict:
        """Pre-discover pages before the LLM loop starts.

        Stores verified slugs on the instance so that:
        • get_tool_fns can pre-populate found_slugs (enforcement guard)
        • build_initial_message can name the exact slugs upfront (prompt anchor)

        The LLM still calls find_content_health_issues for issue details, but
        found_slugs is already seeded so invented slugs are rejected even if the
        model ignores the tool result.
        """
        import logging as _log
        _logger = _log.getLogger(__name__)
        self._prediscovered_slugs: list[str] = []
        if ctx.store is not None:
            for slug in sorted(ctx.store.list_pages()):
                if slug in SYSTEM_PAGE_SLUGS:
                    continue
                try:
                    page = ctx.store.read_page(slug)
                    if (page is not None
                            and page.status == LifecycleState.ACTIVE
                            and page.content_health_issues):
                        self._prediscovered_slugs.append(slug)
                except Exception as exc:
                    _logger.debug("content-health pre-discovery: skip %r — %s", slug, exc)
        _logger.debug(
            "content-health pre-discovery: %d page(s) found: %s",
            len(self._prediscovered_slugs), self._prediscovered_slugs,
        )
        return super().build_guarded_tool_fns(ctx)

    def get_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        # Track which slugs are legitimate (found by find_content_health_issues)
        # and which have been read via get_page_content.  write_content_health_fix
        # is blocked at the function level for any slug not in both sets, so the
        # LLM cannot write invented content even if it skips the workflow steps.
        #
        # Pre-seed found_slugs from the Python-level pre-discovery so that the
        # enforcement guard works even if the LLM never calls find_content_health_issues.
        found_slugs: set[str] = set(getattr(self, "_prediscovered_slugs", []))
        read_slugs: set[str] = set()

        async def _find_issues(slug: str = "") -> dict:
            result = await tool_find_content_health_issues(ctx, slug)
            if result.get("status") == "success" and ctx.store is not None:
                # Verify each returned slug is still readable right now.
                # Filters out any page that was deleted between list_pages() and
                # this call (race-condition window), and populates found_slugs
                # with only confirmed-readable slugs.
                verified: list[dict] = []
                import logging as _logging
                _log = _logging.getLogger(__name__)
                for page in result.get("pages", []):
                    page_slug = page["slug"]
                    try:
                        page_obj = ctx.store.read_page(page_slug)
                        if page_obj is not None:
                            found_slugs.add(page_slug)
                            verified.append(page)
                        else:
                            _log.warning(
                                "content-health: find_content_health_issues returned slug %r "
                                "but read_page returned None — excluding from work list",
                                page_slug,
                            )
                    except Exception as exc:
                        _log.warning(
                            "content-health: could not verify slug %r — excluding: %s",
                            page_slug, exc,
                        )
                result = dict(result)
                result["pages"] = verified
                result["total"] = len(verified)
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
            "dismiss_content_health_issues": functools.partial(tool_dismiss_content_health_issues, ctx),
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

        # Always run a fresh scan so the workflow finds issues even when lint
        # has not yet run and frontmatter flags are absent or stale.
        from dataclasses import asdict as _asdict
        from synthadoc.agents.content_health_scanner import scan_page as _scan_page
        yield {"event": "token", "data": {"text": "Scanning pages for content health issues…\n"}}
        for _slug in ctx.store.list_pages():
            _page = ctx.store.read_page(_slug)
            if _page is None or _page.status != LifecycleState.ACTIVE:
                continue
            _new = [_asdict(i) for i in _scan_page(_slug, _page.content or "")]
            if _new != (_page.content_health_issues or []):
                _page.content_health_issues = _new
                ctx.store.write_page(_slug, _page)

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
            _counts: dict[tuple, int] = {}
            for _i in page.content_health_issues:
                _k = (_i["type"], _i["severity"])
                _counts[_k] = _counts.get(_k, 0) + 1
            issues_summary = ", ".join(
                f"{t} ({s}){' ×' + str(n) if n > 1 else ''}"
                for (t, s), n in list(_counts.items())[:3]
            )
            yield {"event": "token", "data": {"text": f"\n--- {slug} ---\nIssues: {issues_summary}\n"}}

            prompt = (
                "You are a wiki editor. The full page content is provided below.\n"
                "Do NOT read any files or use any tools — all content is already here.\n"
                "Do NOT include explanations, commentary, or summaries.\n\n"
                f"Page slug: {slug}\n\n"
                f"Current content:\n\n{page.content}\n\n"
                f"Structural issues to fix: {page.content_health_issues}\n\n"
                "Rewrite the page to fix ONLY these structural issues "
                "(remove duplicate sections, expand thin/empty sections). "
                "Do NOT change factual content. "
                "Output ONLY the complete corrected markdown, starting with '# '."
            )
            from synthadoc.skills.base import Message as _Msg
            _resp = await provider.complete([_Msg(role="user", content=prompt)])
            proposed = _extract_md_from_response(_resp.text)

            # For small fixes (≤3 issues) show the affected sections side-by-side;
            # for large rewrites the LLM restructures the page so section names
            # no longer align — fall back to plain head-truncation of each version.
            _max = 800
            if len(page.content_health_issues) <= 3:
                before_excerpt = _section_excerpt(page.content, page.content_health_issues, _max)
                after_excerpt = _section_excerpt(proposed, page.content_health_issues, _max)
            else:
                before_excerpt = page.content[:_max] + ("..." if len(page.content) > _max else "")
                after_excerpt = proposed[:_max] + ("..." if len(proposed) > _max else "")
            diff_msg = (
                f"**{slug}** — {issues_summary}\n\n"
                f"**BEFORE** ({len(page.content)} chars):\n```\n{before_excerpt}\n```\n\n"
                f"**AFTER** ({len(proposed)} chars):\n```\n{after_excerpt}\n```"
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
