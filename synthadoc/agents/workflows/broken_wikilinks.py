# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""BrokenWikilinksWorkflow — scan active pages for dead [[wikilinks]] and fix them."""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_apply_link_fixes,
    tool_confirm,
    tool_find_broken_wikilinks,
    tool_get_page_states,
    tool_poll_job,
    tool_run_lint,
)

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """\
You are an agentic workflow executor for Synthadoc wiki maintenance.
Your task is to scan all active wiki pages for broken [[wikilinks]] and fix them.

A broken wikilink is a [[slug]] reference in a page's content that points to a page
that does not exist in the wiki.  Only plain [[slug]] links are checked — typed
wikilinks and aliases use a different resolution path and are out of scope here.

Only ACTIVE pages are scanned.  Stale, draft, and archived pages are excluded.
If the user expects a stale or draft page to be included, they must promote it to
active first.

## Tool reference

### find_broken_wikilinks
Scan all active pages for broken [[slug]] references.  Returns fuzzy suggestions
(difflib, stdlib) for likely typos.  No arguments needed.
Input:  {}
Output: {"pages": [{"slug": str, "broken_links": [{"ref": str, "suggestion": str|null}]}],
         "scanned": int, "total_broken": int}

### apply_link_fixes
Apply corrections to a single page.  new_ref=null removes the link, keeping the
display text.  One call per page.
Input:  {"page_slug": str, "fixes": [{"old_ref": str, "new_ref": str|null}]}
Output: {"status": "success"|"error", "changes": int, "page": str}

### confirm
Send a confirmation card to the UI and wait up to 120 seconds for the user to
approve or decline.  Times out as declined.
Input:  {"message": str, "yes_label": str, "no_label": str}
Output: {"confirmed": bool}

### run_lint
Enqueue a full lint pass to validate link integrity after fixes are applied.
Input:  {}
Output: {"job_id": str}

### poll_job
Wait for a job to reach a terminal state.
Input:  {"job_id": str, "timeout_seconds": int}
Output: {"status": "success"|"failed"|"timeout", "message": str}

### get_page_states
Return the current lifecycle state of one or more pages.
Input:  {"slugs": [str]}
Output: {"pages": [{"slug": str, "state": str}]}

## Tool-call wire format

Emit EXACTLY this JSON object (no markdown fences, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}

When you have no more tool calls to make, produce a plain-text summary (no JSON).

## Workflow steps

### Phase 1 — Scan
1. Call find_broken_wikilinks (no arguments).
2. If total_broken == 0:
   Write a plain-text summary: "No broken wikilinks found across N active pages.
   Wiki link integrity is clean."
   Note: "Stale/draft pages were excluded from the scan."
   STOP — do not call any more tools.
3. If total_broken > 0: proceed to Phase 2.

### Phase 2 — Fix
4. Build a confirm message listing every affected page, each broken ref, and its fix:
   - If suggestion exists: [[broken-ref]] → [[suggestion]] (fuzzy match)
   - If no suggestion:     [[broken-ref]] → remove link (no similar page found)
   Include at the end: "Stale/draft pages were excluded. Promote them to active
   to include in the scan."
5. Call confirm with the full scope.
   - If declined: report "Re-ingest declined by user." STOP.
6. For each page in pages (one at a time):
   - Build the fixes list from its broken_links:
     * new_ref = suggestion  (or null if suggestion is null)
   - Call apply_link_fixes with page_slug and fixes.
7. Call run_lint (scope="all") to revalidate the wiki.
8. Call poll_job with the returned job_id (timeout_seconds=300).
9. Call get_page_states with the slugs of all pages that had fixes applied.
10. Write a plain-text summary:
    - N active pages scanned
    - M broken links found and fixed across K pages
    - Per-page: "  • <slug>: N fix(es)" — include pages where changes==0 as no-ops
    - Lint job: pass / fail
    - "Page states after fix:" section — ✓ active, ✗ stale, ○ other
    - Reminder: "Stale/draft pages were excluded from the scan."
"""


class BrokenWikilinksWorkflow(AgenticWorkflow):
    """Scan active wiki pages for broken [[wikilinks]] and fix them interactively."""

    MATCH_RE = re.compile(
        r"\bbroken\b.{0,40}\b(?:wiki\s*links?|links?)\b"
        r"|\b(?:wiki\s*links?|links?)\b.{0,40}\bbroken\b"
        r"|\bfix\b.{0,40}\b(?:dead|dangling|broken)\b.{0,30}\b(?:wiki\s*links?|links?)\b"
        r"|\b(?:dead|dangling)\b.{0,30}\b(?:wiki\s*links?|links?)\b"
        r"|\bscan\b.{0,40}\b(?:wiki\s*links?|links?)\b"
        r"|\bcheck\b.{0,40}\bwiki\s*links?\b"
        r"|\blink\s+integrit",
        re.IGNORECASE,
    )

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "find_broken_wikilinks": functools.partial(tool_find_broken_wikilinks, ctx),
            "apply_link_fixes":      functools.partial(tool_apply_link_fixes, ctx),
            "confirm":               functools.partial(tool_confirm, ctx),
            "run_lint":              functools.partial(tool_run_lint, ctx),
            "poll_job":              functools.partial(tool_poll_job, ctx),
            "get_page_states":       functools.partial(tool_get_page_states, ctx),
        }
