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
Scan pages for broken [[slug]] references.  Returns fuzzy suggestions
(difflib, stdlib) for likely typos.
Input:  {"page_slug": str}   — scan only that one page (single-page mode)
     OR {}                   — scan all active pages (full-wiki mode)
Output: {"has_issues": bool,   — TRUE when broken links were found, FALSE when clean
         "pages": [{"slug": str, "broken_links": [{"ref": str, "suggestion": str|null}]}],
         "scanned": int, "total_broken": int,
         "page_title": str|null}   — display title, present only in single-page mode

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
Run a full lint pass to validate link integrity after fixes are applied. Blocks until done.
Input:  {}
Output: {"status": "success"|"failed"|"timeout", "message": str} | {"error": str}

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
2. Check the "has_issues" field in the result:
   - If has_issues == false (no broken links): write the clean-wiki summary below
     and STOP.  Do NOT call any more tools.
   - If has_issues == true (broken links found): your NEXT action MUST be a confirm
     tool call (step 5).  Do NOT write any plain text yet.  Plain text ends the
     workflow — you may only write plain text AFTER completing all of Phase 2
     (steps 4–9).
     NEVER call apply_link_fixes as the next step — confirm MUST come first.

#### Clean-wiki summary template (only when total_broken == 0)
Single-page mode: "No broken wikilinks found on the <page_title> page."
  Use the page_title value from the find_broken_wikilinks result as the display name.
  If page_title is null, fall back to the slug.
Full-wiki mode:   "No broken wikilinks found across N active pages. Wiki link integrity is clean.
                   Note: Stale/draft pages were excluded from the scan."

### Phase 2 — Fix
4. Build a confirm message listing every affected page, each broken ref, and its fix:
   - If suggestion exists: [[broken-ref]] → [[suggestion]] (fuzzy match)
   - If no suggestion:     [[broken-ref]] → remove link (no similar page found)
   Include at the end: "Stale/draft pages were excluded. Promote them to active
   to include in the scan."
5. Call confirm with the full scope.
   - If declined: report "Re-ingest declined by user." STOP.
6. For each page in pages (one at a time):
   - Build the fixes list from that page's broken_links (the find_broken_wikilinks result).
     For each broken_link entry: new_ref = entry.suggestion.
     Suggestion is a slug string → correct the link. Suggestion is null → remove the link.
     Treat each entry independently — do not use null for a link that has a suggestion.
   - Call apply_link_fixes with page_slug and fixes.
7. Call run_lint (scope="all") to revalidate the wiki. Blocks until done.
8. Call get_page_states with the slugs of all pages that had fixes applied.
9. Write a plain-text summary:
    - N active pages scanned
    - M broken links found and fixed across K pages
    - Per-page: "  • <slug>: N fix(es)" — include pages where changes==0 as no-ops
    - Lint job: pass / fail
    - "Page states after fix:" section — ✓ active, ✗ stale, ○ other
    - Reminder: "Stale/draft pages were excluded from the scan."

## CRITICAL RULES

### apply_link_fixes is MANDATORY for every page with broken links
When find_broken_wikilinks reports total_broken > 0 and the user confirms:
- You MUST call apply_link_fixes for EVERY page listed in the results.
- new_ref=null is a valid, required action — it removes the dead [[link]] markup.
- A link with suggestion=null does NOT mean "nothing to do". It means the fix is removal.
- Skipping apply_link_fixes because a broken link has no fuzzy suggestion is WRONG.
- Do NOT call get_page_states or run_lint before apply_link_fixes has been called
  for every page in the results.

### confirm is MANDATORY before apply_link_fixes
You MUST call confirm (step 5) and receive {"confirmed": true} before calling
apply_link_fixes.  If confirmed is false, write the cancellation message and STOP —
do NOT call apply_link_fixes, run_lint, or get_page_states.

NEVER call apply_link_fixes immediately after find_broken_wikilinks.
The mandatory order is: find_broken_wikilinks → confirm → apply_link_fixes.
If you call apply_link_fixes before confirm, you have made an error.
The tool result's "has_issues" field is the authoritative signal — check it, then
call confirm, then and only then proceed to apply_link_fixes.

### Never exit to plain text while broken links remain unfixed
When find_broken_wikilinks returns total_broken > 0, producing a plain-text response
before completing Phase 2 is WRONG.  The only valid plain-text responses are:
  (a) The clean-wiki summary (only when total_broken == 0).
  (b) "Re-ingest declined by user." (only when confirm returns confirmed=false).
  (c) The final summary at step 9 (only after apply_link_fixes, run_lint, and
      get_page_states have all been called).
Any other plain-text output when broken links exist terminates the workflow without
fixing them — this is a bug.  Always call confirm next after finding broken links.
"""


class BrokenWikilinksWorkflow(AgenticWorkflow):
    """Scan active wiki pages for broken [[wikilinks]] and fix them interactively."""

    NAME = "broken-wikilinks"
    DESCRIPTION = "Scan all pages for broken [[wikilinks]] and fix them interactively."

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

    # Confirm gate — Pattern B (declarative GATED_TOOLS).
    #
    # Declaring a tool name here tells the framework (build_guarded_tool_fns)
    # to protect it automatically:
    #   • The "confirm" tool in get_tool_fns opens the session gate on approval.
    #   • If the LLM calls the gated tool before going through confirm, the
    #     framework fires a fallback dialog so no write happens silently.
    #   • Once the gate is open it stays open for the session — no repeat
    #     dialogs on subsequent calls to the same tool.
    #
    # To add a confirm gate in a new workflow:
    #   1. Include "confirm": functools.partial(tool_confirm, ctx) in get_tool_fns.
    #   2. Declare GATED_TOOLS = frozenset({"your_destructive_tool"}).
    #
    # Use Pattern A instead (embed tool_confirm inside the tool function itself,
    # leave GATED_TOOLS empty) when the confirm message is built programmatically
    # rather than by the LLM.  scaffold.py shows Pattern A.
    #
    # Full contract: AgenticWorkflow.GATED_TOOLS in _base.py.
    GATED_TOOLS: frozenset[str] = frozenset({"apply_link_fixes"})

    # CLI providers (claude-code, opencode) refuse the JSON wire-format tool-call
    # loop in _SYSTEM_PROMPT as prompt injection.  This workflow opts into a
    # Python-driven alternative — no LLM call is needed at all because
    # tool_find_broken_wikilinks already runs difflib internally and returns a
    # "suggestion" field for every broken ref.  The fix algorithm is purely
    # mechanical: suggestion present → rename to suggestion; suggestion null → remove.
    # All tool functions are reused directly from the multi-turn path.
    SUPPORTS_CLI_PROVIDER: bool = True

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        slug_match = re.search(r"--slug\s+(\S+)", user_input, re.IGNORECASE)
        if slug_match:
            slug = slug_match.group(1)
            return (
                f"Scan for broken wikilinks.\n"
                f"Single-page mode: check only the '{slug}' page.\n"
                f"Pass page_slug='{slug}' to find_broken_wikilinks."
            )
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "find_broken_wikilinks": functools.partial(tool_find_broken_wikilinks, ctx),
            "apply_link_fixes":      functools.partial(tool_apply_link_fixes, ctx),
            "confirm":               functools.partial(tool_confirm, ctx),
            "run_lint":              functools.partial(tool_run_lint, ctx),
            "get_page_states":       functools.partial(tool_get_page_states, ctx),
        }

    # ── CLI provider path ─────────────────────────────────────────────────────

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: scan → confirm → apply → lint → page-states → summary.

        Mirrors the system prompt's Phase 1 and Phase 2 sequence but drives all
        steps directly from Python instead of through the JSON wire-format loop.

        Why no LLM call is needed here
        --------------------------------
        tool_find_broken_wikilinks already embeds difflib.get_close_matches
        internally and returns a ``suggestion`` field for every broken ref.
        The fix decision is therefore mechanical:
          • suggestion is a slug string → rename: new_ref = suggestion
          • suggestion is None           → remove: new_ref = None
        No language understanding is required.  This matches BrokenCitationResolverWorkflow
        which similarly computes fixes with difflib from Python.

        Post-apply sequence (MANDATORY per system prompt §Phase 2 steps 7-8)
        -----------------------------------------------------------------------
        run_lint is called unconditionally after all apply_link_fixes calls,
        regardless of individual outcomes.  get_page_states follows immediately
        to populate the "Page states after fix" section of the summary.

        The ``provider`` argument is accepted for interface compatibility but is
        unused — no LLM reasoning step is needed.
        """
        # ── 1. Scan (Phase 1, step 1) ─────────────────────────────────────────
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        page_slug: str | None = slug_match.group(1) if slug_match else None

        scan = await tool_find_broken_wikilinks(ctx, page_slug=page_slug)
        pages: list[dict] = scan.get("pages", [])
        total_broken: int  = scan.get("total_broken", 0)
        scanned: int       = scan.get("scanned", 0)

        if total_broken == 0:
            # Phase 1, step 2 — clean-wiki summary (mirrors system prompt template)
            if page_slug:
                page_title = scan.get("page_title") or page_slug
                msg = f"No broken wikilinks found on the {page_title} page."
            else:
                msg = (
                    f"No broken wikilinks found across {scanned} active pages. "
                    f"Wiki link integrity is clean.\n"
                    f"Note: Stale/draft pages were excluded from the scan."
                )
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 2. Build fix list from suggestion field (no computation needed) ───
        # tool_find_broken_wikilinks already ran difflib; suggestion is the result.
        decisions: list[dict] = []
        for p in pages:
            fixes = [
                {"old_ref": bl["ref"], "new_ref": bl.get("suggestion")}
                for bl in p.get("broken_links", [])
            ]
            if fixes:
                decisions.append({"slug": p["slug"], "fixes": fixes})

        # ── 3. Confirm (Phase 2, steps 4-5) ───────────────────────────────────
        n_pages = len(decisions)
        n_fixes = sum(len(d["fixes"]) for d in decisions)
        confirm_lines: list[str] = [
            f"Found {total_broken} broken wikilink(s) across {len(pages)} page(s). "
            f"Proposed {n_fixes} fix(es) on {n_pages} page(s):\n",
        ]
        for item in decisions:
            confirm_lines.append(f"{item['slug']}:")
            for fix in item["fixes"]:
                if fix["new_ref"]:
                    confirm_lines.append(
                        f"  [[{fix['old_ref']}]]  →  [[{fix['new_ref']}]]"
                    )
                else:
                    confirm_lines.append(
                        f"  [[{fix['old_ref']}]]  →  remove link (no similar page found)"
                    )
        confirm_lines.append(
            "\nStale/draft pages were excluded. "
            "Promote them to active to include in the scan."
        )

        confirmed = await tool_confirm(
            ctx,
            "\n".join(confirm_lines),
            yes_label="Apply fixes",
            no_label="Cancel",
        )
        if not confirmed.get("confirmed"):
            msg = "Cancelled — no links were modified."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 4. Apply (Phase 2, step 6) ────────────────────────────────────────
        # apply_link_fixes is called for EVERY page with broken links — including
        # those where new_ref=null for all fixes — to satisfy the system prompt's
        # "MANDATORY for every page" rule.
        fix_results: dict[str, dict] = {}
        for item in decisions:
            slug = item["slug"]
            await ctx.send_sse_event(
                "tool_progress",
                {"tool": "apply_link_fixes", "message": f"Fixing {slug}..."},
            )
            fix_results[slug] = await tool_apply_link_fixes(
                ctx, page_slug=slug, fixes=item["fixes"]
            )

        # ── 5. Lint + page states (Phase 2, steps 7-8 — MANDATORY) ───────────
        attempted_slugs = [item["slug"] for item in decisions]
        lint_result   = await tool_run_lint(ctx)
        states_result = await tool_get_page_states(ctx, slugs=attempted_slugs)
        state_map: dict[str, str] = {
            p["slug"]: p["state"] for p in states_result.get("pages", [])
        }

        # ── 6. Summary (Phase 2, step 9) ─────────────────────────────────────
        _ICON: dict[str, str] = {"active": "✓", "stale": "✗"}
        lint_status = lint_result.get("status", "unknown")
        lint_ok = lint_status == "success"
        total_changes = sum(
            r.get("changes", 0) for r in fix_results.values()
            if r.get("status") == "success"
        )

        parts: list[str] = ["**Broken Wikilinks — Complete**\n"]
        parts.append(f"{scanned} active page(s) scanned.")
        parts.append(
            f"{total_broken} broken link(s) found; "
            f"{total_changes} fix(es) applied across {len(decisions)} page(s)."
        )
        parts.append(
            f"\n{'✅' if lint_ok else '⚠'} Lint: {lint_status}"
            + (f" — {lint_result['message']}" if lint_result.get("message") else "")
        )

        # Per-page results — include all pages, even where changes==0 (no-ops)
        parts.append("\nPer-page results:")
        for item in decisions:
            slug = item["slug"]
            r = fix_results.get(slug, {})
            if r.get("status") == "success":
                parts.append(f"  • {slug}: {r.get('changes', 0)} fix(es)")
            else:
                parts.append(f"  • {slug}: ⚠ error — {r.get('error', 'unknown')}")

        parts.append("\nPage states after fix:")
        for slug in attempted_slugs:
            state = state_map.get(slug, "unknown")
            parts.append(f"  {_ICON.get(state, '○')} {slug}: {state}")

        parts.append("\nNote: Stale/draft pages were excluded from the scan.")

        summary = "\n".join(parts)
        yield {"event": "token", "data": {"text": summary}}
        yield {"event": "final_text", "data": {"text": summary}}
