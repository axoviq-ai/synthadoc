# synthadoc/agents/workflows/orphan_resolver.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""OrphanResolverWorkflow — agentic closed-loop integration for orphaned wiki pages.

Finds pages with no inbound [[wikilinks]], searches for topically related
candidate pages using 4 progressively broader strategies, proposes and applies
natural link insertions with diff-before-write approval, and verifies
resolution via graph-level recomputation.

Up to 4 strategies per orphan; escalates to tool_notify on exhaustion.
Pages are processed sequentially with an inter-orphan confirm gate.
"""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING

from synthadoc.agents.workflows._base import AgenticWorkflow
from synthadoc.agents.workflows._tools import (
    tool_confirm,
    tool_notify,
    tool_read_page_content,
    tool_propose_and_apply,
)
from synthadoc.agents.workflows.tools.orphan_resolver_tools import (
    tool_find_orphaned_pages,
    tool_estimate_and_confirm,
    tool_search_orphan_candidates,
    tool_verify_orphan_resolved,
)

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_SYSTEM_PROMPT = """\
You are a wiki maintenance agent specialising in resolving orphaned pages.
An orphaned page is an active page with no incoming [[wikilinks]] from other \
active content pages — it is invisible to navigation and unlikely to be cited.

━━━ TOOL-CALL WIRE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Emit EXACTLY this JSON object (no markdown fences, no XML, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}
When delivering a final message for the user, respond with plain text only (no JSON).

━━━ TOOL INVENTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
tool_find_orphaned_pages()
    → {"orphans": [slugs], "count": N}

tool_estimate_and_confirm(orphan_count)
    → {"confirmed": bool, "orphan_count": N, "estimated_usd": float}
    Sends estimate notice AND requests approval in one step.
    Do NOT call tool_confirm separately after this.

tool_search_orphan_candidates(orphan_slug, strategy, exclude_slugs)
    strategy: "title_bm25" | "content_bm25" | "full_title_scan" | "contextual_reasoning"
    exclude_slugs: list of slugs already tried — never returned again
    → For title_bm25 / content_bm25:
        {"candidates": [slug, ...], "strategy": str, "tried_slugs": [...]}
    → For full_title_scan:
        {"candidates": [], "all_page_titles": [{"slug": str, "title": str}, ...],
         "strategy": str, "tried_slugs": [...]}
    → For contextual_reasoning:
        {"candidates": [], "all_page_titles": [...], "orphan_content": str,
         "strategy": str, "tried_slugs": [...]}

tool_read_page_content(slug)
    → {"slug": str, "title": str, "content": str, "status": str, ...}
    → {"error": str} — page not found

tool_propose_and_apply(slug, new_content, strategy_name, rationale)
    → {"applied": bool, "diff_preview": str}
    Shows a unified diff to the user; writes only if approved.
    Call at most ONCE per candidate per attempt.

tool_verify_orphan_resolved(orphan_slug)
    → {"resolved": bool, "linked_by": [slugs]}
    Re-runs graph-level orphan detection. Call AFTER a successful apply.

tool_confirm(message, yes_label, no_label)
    → {"confirmed": bool}
    Use for inter-orphan gate only. Do NOT use after tool_estimate_and_confirm.

tool_notify(message, level)
    → {"sent": True}
    Non-blocking notice — does NOT end the loop. level: "info"|"warning"|"error"

━━━ WORKFLOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Discover orphans
  If the initial message specifies a --slug:
    Call tool_verify_orphan_resolved(orphan_slug=<slug>) immediately.
    • resolved=true  → the page already has inbound links and is NOT an orphan.
                       Respond with plain text (ends loop):
                       "<slug> is not an active orphan page — it already has inbound
                        wikilinks from: <linked_by list>. No action needed."
    • resolved=false → treat this slug as the only orphan. Set orphan count = 1
                       and proceed directly to STEP 3 (skip STEP 2).
  Otherwise call tool_find_orphaned_pages().

STEP 2 — Check for work
  If count == 0: respond with plain text "No active orphaned pages found." (ends loop).

STEP 3 — Cost estimate and approval
  Call tool_estimate_and_confirm(orphan_count=<N>).
  • confirmed=false → respond with plain text "Orphan resolver cancelled." (ends loop).
  • confirmed=true  → proceed immediately to step 4. No prose between steps.

STEP 4 — Per-orphan resolution loop
  Maintain: resolved_list=[], unresolved_list=[], skipped_list=[]

  For each orphan_slug (process one at a time, sequentially):

    tried_slugs = []   ← accumulates across ALL attempts for this orphan

    4a. Side-effect pre-check — before starting the strategy loop:
        Call tool_verify_orphan_resolved(orphan_slug).
        • resolved=true  → another fix already linked this page as a side effect.
                           Add orphan_slug to resolved_list and SKIP to the next
                           orphan (do NOT propose any changes). No strategy needed.
        • resolved=false → proceed to strategy loop below.

    4b. Strategy loop — try each strategy in order, up to 4 attempts:
        Attempt 1 → strategy "title_bm25"
        Attempt 2 → strategy "content_bm25"
        Attempt 3 → strategy "full_title_scan"
        Attempt 4 → strategy "contextual_reasoning"

        i.  Call tool_search_orphan_candidates(orphan_slug, strategy, tried_slugs).
            Update tried_slugs with the returned tried_slugs list.

        ii. Determine candidates:
            • For title_bm25 / content_bm25: use the "candidates" list directly.
            • For full_title_scan / contextual_reasoning: review "all_page_titles"
              (and "orphan_content" when present) and select 2-3 slugs that most
              plausibly have reason to mention the orphan. Use these as candidates.
            • If no candidates can be identified: advance to the next strategy
              IMMEDIATELY — emit ONLY the next tool_search_orphan_candidates tool
              call. NO prose, NO explanation, NO "(Note: …)". Any text here ends
              the workflow permanently.

        iii.For each of the top 2-3 candidates (skip those already in tried_slugs):
              Call tool_read_page_content(candidate_slug).
            Choose the candidate where a [[orphan_slug]] link would be most natural —
            in a related section, an existing "See also" block, or an inline mention.

        iv. Formulate new_content for the chosen candidate, inserting [[orphan_slug]]
            at the chosen natural location. The link MUST be contextually appropriate;
            never add forced or irrelevant links.

        v.  Call tool_propose_and_apply(
              slug=candidate_slug,
              new_content=<revised content with [[orphan_slug]] inserted>,
              strategy_name=f"Strategy {attempt} — {strategy}",
              rationale=<one sentence explaining why this location is natural>
            ).
            • applied=false (user skipped): try the next candidate in this attempt.
              If no more candidates in this attempt, advance to next strategy —
              emit the next tool_search_orphan_candidates call with NO prose.
            • applied=true: proceed to step vi.

        vi. Call tool_verify_orphan_resolved(orphan_slug).
            • resolved=true  → add orphan_slug to resolved_list. BREAK strategy loop.
            • resolved=false → continue to next strategy.

    4c. After 4 strategies exhausted and still orphaned:
        Add orphan_slug to unresolved_list.
        Call tool_notify(level="warning", message=
          f"⚠ Could not auto-resolve orphan '[[{orphan_slug}]]' after 4 strategies.\\n"
          f"Pages considered: {tried_slugs}\\n\\n"
          "Suggested next steps:\\n"
          "  1. Re-run orphan-resolver — the LLM may identify different candidates "
               "or insertion points on a fresh attempt.\\n"
          "  2. Manually add [[" + orphan_slug + "]] to a natural location in one "
               "of the pages above.\\n"
          "  3. If this page is standalone and no longer relevant, archive it:\\n"
          "     synthadoc lifecycle transition --slug " + orphan_slug + " --state archived\\n"
          "  4. If the topic needs a hub page, create one first and re-run orphan-resolver."
        )

    4d. Inter-orphan confirm (if more orphans remain):
        ⚠ MANDATORY — Do NOT output any plain text before calling tool_confirm here.
           Plain text output ends the entire workflow immediately.
        Call tool_confirm(
          f"Continue to next orphan ({next_slug})?",
          yes_label="Continue",
          no_label="Stop"
        ).
        • confirmed=false → add remaining orphans to skipped_list. Break outer loop.

STEP 5 — Final summary (plain text — ends the loop)
  BEFORE writing the summary, audit your lists:
    • Every slug discovered in step 1 MUST appear in exactly one of
      resolved_list, unresolved_list, or skipped_list.
    • If any slug is missing, add it to skipped_list now.
    • len(resolved_list) + len(unresolved_list) + len(skipped_list)
      MUST equal the orphan count from step 1. If they do not match,
      do NOT write the summary — call tool_notify(level="error") with
      the discrepancy and then write the summary with corrected counts.

  Format:
    "Orphan Resolver — Complete

    ✅ Resolved (<N>):
      - <slug> (linked from <page>)
      ...
    ⚠ Unresolved (<N>):
      - <slug> (4 strategies exhausted — see notices above)
      ...
    ⏭ Skipped (<N>):
      - <slug>
      ..."

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Plain text ENDS THE LOOP — use it ONLY for the final summary or cancellations.
• Strategy transitions are SILENT: when advancing to the next strategy because no
  candidates matched, emit only the tool_call JSON — zero prose, zero explanation.
  Writing "(Note: …)" or any natural-language text at that point ends the workflow.
• Links must be contextually natural. Never add [[slug]] in an irrelevant location.
• ALWAYS call tool_verify_orphan_resolved(orphan_slug) at the START of each orphan
  (step 4a pre-check) AND again after every successful apply (step 4b.vi).
• NEVER call tool_propose_and_apply more than once per candidate per attempt.
• When tool_verify_orphan_resolved returns resolved=true, add to resolved_list and BREAK.
• Pass cumulative tried_slugs to every tool_search_orphan_candidates call.
• Do NOT output any plain text before calling tool_confirm between orphans.
• Cap is HARD at 4 strategies per orphan — escalate on the 5th failure.
• EVERY orphan from step 1 must appear in the final summary. Total must match step 1.
"""


class OrphanResolverWorkflow(AgenticWorkflow):
    """Agentic maintenance workflow to integrate orphaned wiki pages."""

    NAME = "orphan-resolver"
    DESCRIPTION = "Find and resolve active orphan pages — active pages with no inbound [[wikilinks]] from other active pages."
    CLI_ARGS = "[--slug SLUG]  (omit to resolve all active orphaned pages)"

    MATCH_RE: re.Pattern = re.compile(
        r"\borphan.{0,20}\bresolv"
        r"|\bresolv.{0,20}\borphan"
        r"|\bfix\s+orphan\w*\b"
        r"|\brun\s+orphan.{0,10}resolver\b"
        r"|\borphan\s+resolver\b",
        re.IGNORECASE,
    )

    def get_tool_budget(self) -> int:
        # 3 setup + 20 orphans × 15 calls (4 attempts × ~3 + confirm) = 303 → 300
        return 300

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str, **_kwargs) -> str:
        slug_match = re.search(r"--slug\s+(\S+)", user_input, re.IGNORECASE)
        if slug_match:
            slug = slug_match.group(1)
            return (
                f"Run the orphan resolver workflow for a single page: {slug}\n"
                f"FIRST: call tool_verify_orphan_resolved(orphan_slug='{slug}') "
                f"to check whether this page is actually an orphan.\n"
                f"• If resolved=true  → it is NOT an orphan; stop with a plain-text "
                f"'not an orphan' message (see STEP 1).\n"
                f"• If resolved=false → it IS an orphan; proceed to STEP 3 with "
                f"orphan_count=1 (skip tool_find_orphaned_pages and STEP 2)."
            )
        return (
            "Run the orphan resolver workflow.\n"
            "Process all orphaned pages found by tool_find_orphaned_pages."
        )

    def get_tool_fns(self, ctx: "WorkflowContext") -> dict:
        p = functools.partial
        return {
            # Orphan-domain tools
            "tool_find_orphaned_pages":       p(tool_find_orphaned_pages, ctx),
            "tool_estimate_and_confirm":      p(tool_estimate_and_confirm, ctx),
            "tool_search_orphan_candidates":  p(tool_search_orphan_candidates, ctx),
            "tool_verify_orphan_resolved":    p(tool_verify_orphan_resolved, ctx),
            # Shared framework tools
            "tool_read_page_content":         p(tool_read_page_content, ctx),
            "tool_propose_and_apply":         p(tool_propose_and_apply, ctx),
            "tool_confirm":                   p(tool_confirm, ctx),
            "tool_notify":                    p(tool_notify, ctx),
        }
