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

from synthadoc.agents.content_health_scanner import resolvable_issues
from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import tool_confirm, tool_notify, tool_rollback_last_fix
from synthadoc.agents.workflows.tools.content_health_tools import (
    SEVERITY_ORDER,
    tool_apply_content_health_fix,
    tool_dismiss_content_health_issues,
    tool_find_content_health_issues,
    tool_get_page_content,
    tool_list_content_health_fixes,
    tool_merge_duplicate_sections,
    tool_rollback_content_health_fix,
)
from synthadoc.storage.wiki import LifecycleState, SYSTEM_PAGE_SLUGS

_SYSTEM_PROMPT = """\
You are an agentic workflow executor for Synthadoc wiki maintenance.
Your task is to fix structural content issues on wiki pages — duplicate sections,
empty sections, unclosed code blocks, orphaned headings, and broken list nesting.
Only ACTIVE pages are processed. Thin sections are not part of this workflow: they
need new facts, so the lint report lists them for a human editor.

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

merge_duplicate_sections
  Fix ALL duplicate_section issues on a page in one call, without you rewriting it.
  Python folds every later copy of a duplicated heading into the first one, keeping
  every sentence. The tool shows the user the real diff, waits for approval and
  writes the page itself — do NOT call write_content_health_fix for duplicates.
  Input:  {"slug": str}
  Output: {"status": "success"|"cancelled"|"error", "slug": str, "merged": [str],
           "skipped": [str], "remaining_issues": int, ...}

get_page_content
  Read the raw markdown content and existing issues for a page.
  Input:  {"slug": str}
  Output: {"status": "success"|"error", "slug": str, "title": str, "content": str,
           "issues": [{"type": str, "severity": str, "location": str, "description": str}]}

write_content_health_fix
  Propose a content-health fix. The tool shows the user the real diff between the
  current page and your content, waits for approval, then snapshots and writes.
  You do not write the approval card yourself.
  MANDATORY SEQUENCE (enforced): get_page_content(slug) → write_content_health_fix(slug)
  • You MUST have called get_page_content for this EXACT slug first.
  • The content argument MUST be the get_page_content response with ONLY structural
    fixes applied — never invented or recalled from training.
  • The slug MUST be one returned by find_content_health_issues in this session.
  Input:  {"slug": str, "content": str, "issues_fixed": [str]}
  Output: {"status": "success"|"cancelled"|"error", "slug": str, "snapshot_index": int,
           "remaining_issues": int, "fix_record": dict}
  status="cancelled": the user skipped this page — move on to the next slug.

list_content_health_fixes
  List all pages previously fixed or dismissed by this workflow, sorted newest first.
  action="fixed": content rewritten, pre-fix snapshot saved.
  action="dismissed": issues cleared without editing the page, so there is NO snapshot
  (report it as "dismissed — needs human editing", never as a fix with missing details).
  action="fixed+dismissed": rewritten, then the remaining issues dismissed.
  Input:  {}
  Output: {"fixes": [{"slug": str, "title": str, "action": str, "fixed_at": str,
                      "issues_fixed": [str], "snapshot_index_before": int|null,
                      "dismissed_count": int, "dismissed_types": [str],
                      "dismissed_reason": str}]}   (dismissed_* only when dismissed)

rollback_content_health_fix
  Roll back one page: restores the pre-fix snapshot, or for a dismissal-only record
  undoes the dismissal (issues restored, content unchanged).
  Input:  {"slug": str}
  Output: {"status": "success"|"error", "slug": str, "rolled_back_to_snapshot": int
           (snapshot rollback) | "restored_issues": int (dismissal undone), "message": str}

dismiss_content_health_issues
  Dismiss issues that CANNOT be fixed by a structural change (fixing them would
  require writing new factual prose — prohibited here).
  Clears content_health_issues from frontmatter so the hint chip stops surfacing
  this page. Does NOT modify page content or create a snapshot.
  ALWAYS call notify FIRST to explain the dismissal, then call this tool. The user
  approves each dismissal; status="cancelled" means the issues stay flagged.
  Input:  {"slug": str, "reason": str}
  Output: {"status": "success"|"error", "slug": str, "dismissed_count": int,
           "remaining_issues": int, "reason": str}

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

  3a. DUPLICATES FIRST: if the page's issues include duplicate_section, call
      merge_duplicate_sections(slug). It handles every duplicate on the page,
      including copies with different text, and asks the user itself.
      If it returns remaining_issues=0 or status="cancelled" → page done, next slug.
      Otherwise continue with 3b for the remaining issues.

  3b. Call get_page_content using the EXACT slug string from the pages[] entry.
      Copy the slug character-for-character from the find_content_health_issues
      result — do not alter it in any way.
      If the result has status="error":
      → STOP processing this slug immediately.
      → Do NOT call write_content_health_fix for it.
      → Do NOT invent or generate any content for it.
      → Move on to the next slug in the discovery list.

  3c. DEEP ANALYSIS:
      Read the full content (from the get_page_content result) and all reported
      issues carefully. Compose a rewrite that ONLY fixes structural issues:
        - empty_section: remove the heading (it has no text and no sub-sections)
        - orphaned_heading: turn the stray H1 into an H2 (or a plain line)
        - unclosed_code_block: close the code fence
        - broken_list_nesting: fix the list indentation
      Never add, remove or reword sentences — write_content_health_fix rejects
      any rewrite that loses a sentence. Base the rewrite ENTIRELY on the
      get_page_content result.

  3d. Call write_content_health_fix using the SAME slug from the pages[] entry,
        content=<rewritten content based on get_page_content result>,
        issues_fixed=[<list of "type xN" strings>]
      The user sees the real diff and approves or skips it.
      If status="cancelled" → page skipped, continue to the next slug.
      If status="error", nothing was written: follow its error message
        (usually: leave those issues for 3e) — never retry the same content.
      If remaining_issues > 0: proceed to 3e for those remaining issues.
      Output summary line: "<slug>: N issues fixed. Snapshot saved — say
        'roll back <slug>' to undo."

  3e. DISMISSAL — only for issues that no structural change can fix (fixing them
      would require writing new factual sentences). Duplicate sections are NEVER
      dismissed: merge_duplicate_sections fixes them.
      1. Call notify(level="warning", message="<slug>: N issue(s) cannot be fixed
         automatically. [Explain which issues and why human editing is needed.]")
      2. Call dismiss_content_health_issues(slug=<slug>, reason="<brief reason>").
         The user approves it; status="cancelled" means the issues stay flagged.
      3. Output summary line: "<slug>: N issue(s) dismissed — requires human editing."

  Never ask the user a question in plain text mid-run: plain text ends the workflow.

STEP 4 — Final summary (plain text only):
  "Content Health Resolver — Complete

  ✅ Fixed (N pages):
  - **<slug>**: <issues> → Snapshot saved
  ...
  ⚠️ Dismissed — requires human editing (N pages):
  - **<slug>**: <issue types> → <what a human editor must do>
  ...
  ⏭ Skipped (N pages): <slug>, ..."

  If Fixed (N pages) > 0, append these two lines after the summary above —
  there is nothing to review or undo when nothing was actually written:
    Say 'list content health fixes' to review all changes.
    Say 'roll back <slug>' to undo any individual page.

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NEVER output plain text while work remains — plain text terminates the workflow.
2. NEVER modify factual content — only fix structural/formatting issues.
3. ALWAYS follow the exact per-page sequence: merge_duplicate_sections (if duplicates) →
   get_page_content → write_content_health_fix.
   Skipping get_page_content means you are writing content you invented, not the real page.
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
        when = fix.get("fixed_at") or "unknown time"
        action = fix.get("action", "fixed")
        parts = []
        if action != "dismissed":
            issues = ", ".join(fix.get("issues_fixed") or []) or "issues fixed"
            parts.append(f"fixed: {issues} (pre-fix snapshot #{fix.get('snapshot_index_before')})")
        if action != "fixed":
            types = ", ".join(fix.get("dismissed_types") or []) or "issues"
            parts.append(
                f"dismissed {fix.get('dismissed_count', 0)} {types} — needs human editing"
                + ("" if action == "fixed+dismissed" else " (no snapshot: content unchanged)")
            )
        lines.append(f"- {fix['slug']} — {when} — " + "; ".join(parts))
    return "\n".join(lines)


async def _rollback_with_fallback(ctx: WorkflowContext, slug: str) -> dict:
    """Roll back *slug*'s content-health fix, or its generic last fix if it has none.

    Fast-path routing sends every "roll back X" chat message here (this
    workflow's MATCH_RE claims "roll back"), even when the page was last
    changed by contradiction_resolver / orphan_resolver through
    tool_propose_and_apply.  When there is no content-health fix record but
    the page carries a generic last_fix_record, delegate to
    tool_rollback_last_fix so the user's rollback still happens.
    """
    result = await tool_rollback_content_health_fix(ctx, slug)
    if result.get("status") != "error":
        return result
    page = ctx.store.read_page(slug) if ctx.store is not None else None
    if page is None or page.content_health_fix_record or not page.last_fix_record:
        return result
    fallback = await tool_rollback_last_fix(ctx, slug)
    if "message" not in fallback and fallback.get("error"):
        fallback = dict(fallback, message=fallback["error"])
    return fallback


_DRAFT_RE = re.compile(
    r"^\s*(TODO|FIXME|Expand to\b|Hmm[,.\s]|Wait[,.\s]|I'll\b|I will\b|Let me\b"
    r"|existing content|combine existing|add more content|placeholder)",
    re.IGNORECASE | re.MULTILINE,
)


def _is_draft(text: str) -> bool:
    """Return True if the text contains LLM planning/thinking artifacts."""
    return bool(_DRAFT_RE.search(text))


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

    # Writes are approved inside the tools (Pattern A), from the real diff: see
    # tool_apply_content_health_fix and tool_merge_duplicate_sections. The model
    # never writes the approval card, so it cannot misdescribe a change.

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
        self._intent = intent  # read by the rollback tool at call time
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
                    f"The user wants to roll back the most recent recorded fix for page "
                    f"'{slug}'.\n"
                    f"Call rollback_content_health_fix(slug='{slug}') and report the result "
                    f"as plain text using the TOOL'S OWN wording, not your own paraphrase. "
                    f"This page's last recorded fix may NOT be a content-health fix — "
                    f"rollback_content_health_fix falls back to the page's generic last fix "
                    f"(from the contradiction resolver or orphan resolver) when it has no "
                    f"content-health-specific record. Do not say 'content health fix' unless "
                    f"the tool's own result actually says so.\n"
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
            f"STEP 3: For EACH slug in this exact list — {slug_comma_list}:\n"
            f"  a. if it has duplicate_section issues: merge_duplicate_sections(slug=\"<exact slug>\")\n"
            f"  b. for any remaining issues: get_page_content(slug=\"<exact slug>\")\n"
            f"  c. compose a structural fix\n"
            f"  d. write_content_health_fix(slug=\"<exact slug>\", ...) — the user approves the diff\n\n"
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
                            and resolvable_issues(page.content_health_issues)):
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
            return await tool_apply_content_health_fix(ctx, slug=slug, content=content,
                                                       issues_fixed=issues_fixed)

        async def _rollback(slug: str) -> dict:
            # A rollback the user asked for ("roll back X") runs directly. During a
            # fix run the model must not undo pages on its own, so ask first.
            if getattr(self, "_intent", "fix") != "rollback":
                gate = await tool_confirm(
                    ctx,
                    message=(
                        f"Roll back **{slug}** to the version saved before its content-health "
                        "fix? This replaces the page's current content (or, for a dismissal, "
                        "restores its issues)."
                    ),
                    yes_label="Roll back", no_label="Keep current",
                )
                if not gate.get("confirmed"):
                    return {"status": "cancelled",
                            "message": f"Rollback of '{slug}' cancelled by the user. Do not retry it."}
            return await _rollback_with_fallback(ctx, slug)

        async def _dismiss(slug: str, reason: str) -> dict:
            # Dismissing leaves the text alone but hides the page from the resolver,
            # so the user approves it like any other change.
            page = ctx.store.read_page(slug) if ctx.store is not None else None
            issues = resolvable_issues(page.content_health_issues) if page else []
            listed = "\n".join(f"- {i.get('type')} at '{i.get('location')}'" for i in issues)
            gate = await tool_confirm(
                ctx,
                message=(
                    f"**{slug}** — dismiss {len(issues)} issue(s) for a human editor?\n\n"
                    f"{listed}\n\nReason: {reason}\n\n"
                    "The page text is not changed; the issues stop being offered to this "
                    f"workflow. Say 'roll back {slug}' later to bring them back."
                ),
                yes_label="Dismiss", no_label="Keep flagged",
            )
            if not gate.get("confirmed"):
                return {"status": "cancelled",
                        "message": f"Dismissal of '{slug}' declined by the user; its issues stay flagged."}
            return await tool_dismiss_content_health_issues(ctx, slug, reason)

        async def _merge_duplicates(slug: str) -> dict:
            if found_slugs and slug not in found_slugs:
                return {
                    "status": "error",
                    "error": (
                        f"Workflow violation: '{slug}' was not returned by "
                        "find_content_health_issues. Only process pages from the "
                        "discovery list."
                    ),
                }
            return await tool_merge_duplicate_sections(ctx, slug)

        return {
            "find_content_health_issues": _find_issues,
            "merge_duplicate_sections": _merge_duplicates,
            "get_page_content": _get_content,
            "write_content_health_fix": _write_fix,
            "dismiss_content_health_issues": _dismiss,
            "list_content_health_fixes": functools.partial(tool_list_content_health_fixes, ctx),
            "rollback_content_health_fix": _rollback,
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
        """CLI-provider path: Python-driven gather → merge / LLM analysis → approve diff → write.

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
            result = await _rollback_with_fallback(ctx, rollback_slug)
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
        from synthadoc.agents.content_health_scanner import refresh_wiki_health_issues as _refresh
        yield {"event": "token", "data": {"text": "Scanning pages for content health issues…\n"}}
        _refresh(ctx.store)

        flagged = []
        for slug in ctx.store.list_pages():
            page = ctx.store.read_page(slug)
            if page is None or page.status != LifecycleState.ACTIVE:
                continue
            issues = resolvable_issues(page.content_health_issues)
            if issues:
                top_sev = min(SEVERITY_ORDER.get(i["severity"], 9) for i in issues)
                flagged.append((top_sev, -len(issues), slug, issues))
        flagged.sort()

        # Filter to --slug if given
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        if slug_match:
            requested = slug_match.group(1).lower()
            flagged = [entry for entry in flagged if entry[2] == requested]

        if not flagged:
            yield {"event": "final_text", "data": {"text": "No active pages with content issues found."}}
            return

        counts: dict[str, int] = {}
        for *_, issues in flagged:
            for issue in issues:
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

        # CLI providers (opencode, claude-code) are agentic — they read files,
        # plan before writing, and hallucinate new sections when the issue list
        # is long.  API providers follow the prompt reliably and don't need this
        # guard.  This path is CLI-only, so the cap applies only there.
        _MAX_ISSUES_AUTO_FIX = 6

        for _sev, _count, slug, issues in flagged:
            if slug in SYSTEM_PAGE_SLUGS or slug.endswith("-index") or slug.endswith("-dashboard"):
                yield {"event": "token", "data": {"text": f"⏭ {slug}: skipped (meta/navigation page)\n"}}
                skipped.append(slug)
                continue

            # Duplicates are merged in Python (no LLM), same tool as the API path.
            if any(i["type"] == "duplicate_section" for i in issues):
                merge = await tool_merge_duplicate_sections(ctx, slug)
                if merge.get("status") == "cancelled":
                    skipped.append(slug)
                    yield {"event": "token", "data": {"text": f"⏭ {slug}: skipped.\n"}}
                    continue
                if merge.get("merged"):
                    fixed.append(slug)
                    yield {"event": "token", "data": {"text": (
                        f"✅ {slug}: merged duplicate sections ({', '.join(merge['merged'])}). "
                        f"Snapshot #{merge.get('snapshot_index', '?')} saved.\n"
                    )}}
                page = ctx.store.read_page(slug)
                issues = resolvable_issues(page.content_health_issues) if page else []
                if not issues:
                    continue
            page = ctx.store.read_page(slug)
            if page is None:
                continue

            if len(issues) > _MAX_ISSUES_AUTO_FIX:
                yield {"event": "token", "data": {
                    "text": (
                        f"⏭ {slug}: {len(issues)} issues — too many for "
                        f"safe auto-fix (limit {_MAX_ISSUES_AUTO_FIX}), needs human review.\n"
                    )
                }}
                skipped.append(slug)
                continue
            _counts: dict[tuple, int] = {}
            for _i in issues:
                _k = (_i["type"], _i["severity"])
                _counts[_k] = _counts.get(_k, 0) + 1
            issues_summary = ", ".join(
                f"{t} ({s}){' ×' + str(n) if n > 1 else ''}"
                for (t, s), n in list(_counts.items())[:3]
            )
            yield {"event": "token", "data": {"text": f"\n--- {slug} ---\nIssues: {issues_summary}\n"}}

            _issues_text = "\n".join(
                f"- {i['type']} at '{i['location']}': {i['description']}"
                for i in issues
            )
            prompt = (
                "You are a surgical wiki editor. Your job is MINIMAL targeted fixes only.\n\n"
                "ABSOLUTE RULES — violating any one is a failure:\n"
                "  • Output ONLY final publishable wiki markdown. No reasoning, no planning,\n"
                "    no TODO, no 'Hmm', no 'I'll', no annotations, no commentary.\n"
                "  • Keep EVERY sentence exactly as written. Do not add, remove or reword\n"
                "    sentences; a rewrite that loses a sentence is rejected.\n"
                "  • PRESERVE every heading you are not fixing EXACTLY — same text, same # level.\n"
                "  • PRESERVE the section ORDER exactly as in the original.\n"
                "  • Do NOT add new sections.\n"
                "  • Do NOT read files or use tools — all content is provided below.\n\n"
                "PERMITTED CHANGES (only these, only where the issue list directs):\n"
                "  1. empty_section: delete the empty heading.\n"
                "  2. orphaned_heading: change the stray '# ' heading to '## '.\n"
                "  3. unclosed_code_block: add the missing closing ``` fence.\n"
                "  4. broken_list_nesting: fix the list indentation.\n\n"
                f"Issues to fix:\n{_issues_text}\n\n"
                f"Page content (copy it, apply only the fixes above, output the result):\n\n"
                f"{page.content}\n\n"
                "Your ENTIRE response is the corrected page starting with '# '."
            )
            from synthadoc.skills.base import Message as _Msg
            _resp = await provider.complete([_Msg(role="user", content=prompt)])
            proposed = _extract_md_from_response(_resp.text)

            if _is_draft(proposed):
                yield {"event": "token", "data": {
                    "text": (
                        f"⛔ {slug}: proposed content contains planning notes "
                        f"— skipped to prevent wiki corruption.\n"
                    )
                }}
                skipped.append(slug)
                continue

            result = await tool_apply_content_health_fix(
                ctx, slug=slug, content=proposed, issues_fixed=[i["type"] for i in issues],
            )
            if result["status"] == "success":
                if slug not in fixed:
                    fixed.append(slug)
                yield {"event": "token", "data": {
                    "text": f"✅ {slug}: fixed. Snapshot #{result.get('snapshot_index', '?')} saved.\n"
                }}
            elif result["status"] == "cancelled":
                skipped.append(slug)
                yield {"event": "token", "data": {"text": f"⏭ {slug}: skipped.\n"}}
            else:
                await tool_dismiss_content_health_issues(
                    ctx, slug, reason=f"auto-fix rejected: {result.get('error')}",
                )
                yield {"event": "token", "data": {
                    "text": f"⚠ {slug}: fix rejected, issues dismissed for human review — "
                            f"{result.get('error')}\n"
                }}
                skipped.append(slug)

        final_summary = (
            f"\nContent Health Resolver — Complete\n"
            f"✅ Fixed: {len(fixed)} page(s) — {', '.join(fixed) or 'none'}\n"
            f"⏭ Skipped: {len(skipped)} page(s) — {', '.join(skipped) or 'none'}\n"
        )
        yield {"event": "final_text", "data": {"text": final_summary}}
