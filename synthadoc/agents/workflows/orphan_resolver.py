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

_log = __import__("logging").getLogger(__name__)

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

    # CLI providers (claude-code, opencode) refuse the JSON wire-format tool-call
    # loop in _SYSTEM_PROMPT — they correctly identify it as a prompt injection
    # attempt.  This workflow opts into a Python-driven alternative that mirrors
    # all 4 strategies from the multi-turn path:
    #
    #   Strategy 1 — title_bm25:        BM25 (Python) on page titles.
    #   Strategy 2 — content_bm25:      BM25 (Python) on page bodies.
    #   Strategy 3 — full_title_scan:   LLM selects from the full page-title list.
    #   Strategy 4 — contextual_reasoning: LLM selects using orphan content + titles.
    #
    # For strategies 1-2 the tool returns a ranked candidates list (pure Python,
    # no LLM).  For strategies 3-4 the tool returns all_page_titles; a bounded
    # LLM call (_cli_select_candidates) picks the 2-3 best slugs — this is a
    # factual selection task with no tool registry, so CLI providers accept it.
    # A second bounded LLM call (_cli_insert_link) then edits the chosen page
    # to insert [[orphan_slug]] at the most natural location.
    #
    # All tool functions (propose_and_apply, verify_orphan_resolved, etc.) are
    # reused unchanged from the multi-turn path.
    SUPPORTS_CLI_PROVIDER: bool = True

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

    # ── CLI provider path ─────────────────────────────────────────────────────

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: all 4 strategies → bounded LLM calls → propose-and-apply.

        Mirrors the system prompt's STEP 1-5 sequence but replaces the multi-turn
        JSON tool-call loop with direct Python calls to the same tool functions,
        plus bounded LLM calls for candidate selection and link insertion.

        Why bounded LLM calls are needed here (unlike IngestLintWorkflow)
        -------------------------------------------------------------------
        Picking the right candidate page and finding a contextually natural
        insertion point for [[orphan_slug]] requires genuine language understanding.
        The LLM calls are scoped to factual editing/selection tasks with no tool
        registry and no identity redefinition, so CLI providers accept them.

        Four strategies per orphan (mirrors the multi-turn path exactly)
        ------------------------------------------------------------------
          1. title_bm25          — BM25 on page titles (Python, no LLM for selection).
          2. content_bm25        — BM25 on page bodies (Python, no LLM for selection).
          3. full_title_scan     — LLM selects from all page titles (_cli_select_candidates).
          4. contextual_reasoning — LLM selects using orphan content + all page titles.
        For each strategy, up to 3 candidate pages are tried via _cli_insert_link
        (bounded LLM edit) + tool_propose_and_apply (diff-before-write) +
        tool_verify_orphan_resolved (graph-level check).
        """
        # ── 1. Discover orphans (mirrors STEP 1) ──────────────────────────────
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        page_slug: str | None = slug_match.group(1) if slug_match else None

        if page_slug:
            # Single-orphan path: verify first (system prompt §STEP 1 --slug branch)
            pre = await tool_verify_orphan_resolved(ctx, orphan_slug=page_slug)
            if pre.get("resolved"):
                linked_by = ", ".join(pre.get("linked_by") or []) or "unknown"
                msg = (
                    f"'{page_slug}' is not an active orphan page — it already has "
                    f"inbound wikilinks from: {linked_by}. No action needed."
                )
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "final_text", "data": {"text": msg}}
                return
            orphans: list[str] = [page_slug]
        else:
            result = await tool_find_orphaned_pages(ctx)
            orphans = result.get("orphans", [])
            if not orphans:
                msg = "No active orphaned pages found."
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "final_text", "data": {"text": msg}}
                return

        # ── 2. Cost estimate + approval (mirrors STEP 3) ──────────────────────
        estimate = await tool_estimate_and_confirm(ctx, orphan_count=len(orphans))
        if not estimate.get("confirmed"):
            msg = "Orphan resolver cancelled."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 3. Per-orphan resolution loop (mirrors STEP 4) ───────────────────
        resolved_list:   list[tuple[str, list[str]]] = []  # (slug, linked_by)
        unresolved_list: list[str] = []
        skipped_list:    list[str] = []

        for i, orphan_slug in enumerate(orphans):
            await ctx.send_sse_event(
                "tool_progress",
                {"tool": "_resolve_orphan", "message": f"Resolving orphan: {orphan_slug}..."},
            )

            # 3a. Side-effect pre-check — another fix may have already linked this page
            pre_check = await tool_verify_orphan_resolved(ctx, orphan_slug=orphan_slug)
            if pre_check.get("resolved"):
                resolved_list.append((orphan_slug, pre_check.get("linked_by") or []))
            else:
                # 3b. BM25 search + LLM insertion (see _cli_resolve_orphan)
                status = await self._cli_resolve_orphan(ctx, orphan_slug, provider)
                if status == "resolved":
                    verify = await tool_verify_orphan_resolved(ctx, orphan_slug=orphan_slug)
                    resolved_list.append((orphan_slug, verify.get("linked_by") or []))
                else:
                    await tool_notify(
                        ctx,
                        message=(
                            f"⚠ Could not auto-resolve orphan '{orphan_slug}' after 4 strategies.\n\n"
                            f"Next steps:\n"
                            f"  1. Re-run orphan-resolver — a fresh attempt may identify different candidates.\n"
                            f"  2. Manually add [[{orphan_slug}]] to a related page where it fits naturally.\n"
                            f"  3. If this page is standalone and no longer relevant, archive it:\n"
                            f"     synthadoc lifecycle transition --slug {orphan_slug} --state archived\n"
                            f"  4. If the topic needs a hub page, create one first and re-run orphan-resolver."
                        ),
                        level="warning",
                    )
                    unresolved_list.append(orphan_slug)

            # 3c. Inter-orphan confirm gate (mirrors system prompt §STEP 4d)
            if i < len(orphans) - 1:
                next_slug = orphans[i + 1]
                cont = await tool_confirm(
                    ctx,
                    f"Continue to next orphan ({next_slug})?",
                    yes_label="Continue",
                    no_label="Stop",
                )
                if not cont.get("confirmed"):
                    skipped_list.extend(orphans[i + 1:])
                    break

        # ── 4. Final summary (mirrors STEP 5) ────────────────────────────────
        parts: list[str] = ["**Orphan Resolver — Complete**\n"]

        if resolved_list:
            parts.append(f"✅ Resolved ({len(resolved_list)}):")
            for slug, linked_by in resolved_list:
                linkers = ", ".join(linked_by) if linked_by else "unknown"
                parts.append(f"  - {slug} (linked from {linkers})")

        if unresolved_list:
            parts.append(f"\n⚠ Unresolved ({len(unresolved_list)}):")
            for slug in unresolved_list:
                parts.append(
                    f"  - {slug} (4 strategies exhausted — see notices above)"
                )

        if skipped_list:
            parts.append(f"\n⏭ Skipped ({len(skipped_list)}):")
            for slug in skipped_list:
                parts.append(f"  - {slug}")

        summary = "\n".join(parts)
        yield {"event": "token", "data": {"text": summary}}
        yield {"event": "final_text", "data": {"text": summary}}

    async def _cli_resolve_orphan(
        self,
        ctx,
        orphan_slug: str,
        provider,
    ) -> str:
        """Try to resolve one orphan via all 4 strategies + bounded LLM link insertion.

        Mirrors the multi-turn path's strategy loop exactly:
          1. title_bm25          — BM25 on page titles (Python, candidates list direct)
          2. content_bm25        — BM25 on page bodies (Python, candidates list direct)
          3. full_title_scan     — LLM selects from all_page_titles (_cli_select_candidates)
          4. contextual_reasoning — LLM selects using orphan content + all_page_titles

        For each strategy, up to 3 candidate pages are tried:
          - _cli_insert_link: bounded LLM call to edit the candidate page
          - wikilink safety guard: reject rewrites that drop existing [[links]]
          - tool_propose_and_apply: diff-before-write approval
          - tool_verify_orphan_resolved: graph-level confirmation

        Returns "resolved" when the graph confirms resolution, "unresolved" otherwise.
        """
        tried_slugs: list[str] = []

        # Read orphan content upfront — needed for LLM calls in all strategies,
        # especially strategy 4 (contextual_reasoning).
        orphan_info = await tool_read_page_content(ctx, slug=orphan_slug)
        orphan_content: str = orphan_info.get("content", "")

        _STRATEGY_LABELS = {
            "title_bm25":          "Strategy 1 — title BM25 + LLM link insertion",
            "content_bm25":        "Strategy 2 — content BM25 + LLM link insertion",
            "full_title_scan":     "Strategy 3 — full title scan + LLM selection",
            "contextual_reasoning":"Strategy 4 — contextual reasoning + LLM selection",
        }

        for strategy in ("title_bm25", "content_bm25", "full_title_scan", "contextual_reasoning"):
            await ctx.send_sse_event(
                "tool_progress",
                {"tool": "_resolve_orphan",
                 "message": f"[{orphan_slug}] Trying {strategy}..."},
            )

            result = await tool_search_orphan_candidates(
                ctx, orphan_slug=orphan_slug, strategy=strategy,
                exclude_slugs=tried_slugs,
            )
            tried_slugs = result.get("tried_slugs", tried_slugs)

            # Strategies 1-2: tool returns a ranked candidates list directly.
            # Strategies 3-4: tool returns all_page_titles; LLM selects best slugs.
            if strategy in ("title_bm25", "content_bm25"):
                candidates: list[str] = result.get("candidates", [])[:3]
            else:
                all_page_titles = result.get("all_page_titles", [])
                if not all_page_titles:
                    continue  # no pages in wiki; skip strategy
                candidates = await self._cli_select_candidates(
                    provider,
                    orphan_slug=orphan_slug,
                    orphan_content=orphan_content,
                    all_page_titles=all_page_titles,
                    exclude_slugs=tried_slugs,
                )

            if not candidates:
                continue  # this strategy found nothing; try the next one

            # Try each candidate selected by this strategy
            for candidate_slug in candidates:
                # Track the candidate immediately so future strategy searches won't
                # re-suggest it (tool_search_orphan_candidates uses exclude_slugs).
                if candidate_slug not in tried_slugs:
                    tried_slugs.append(candidate_slug)

                await ctx.send_sse_event(
                    "tool_progress",
                    {"tool": "_cli_insert_link",
                     "message": f"Trying candidate: {candidate_slug}..."},
                )

                candidate_info = await tool_read_page_content(ctx, slug=candidate_slug)
                if "error" in candidate_info:
                    continue
                candidate_content: str = candidate_info.get("content", "")

                # Bounded LLM call: insert [[orphan_slug]] naturally into candidate
                new_content = await self._cli_insert_link(
                    provider, orphan_slug, orphan_content,
                    candidate_slug, candidate_content,
                )

                # Skip if the LLM failed or returned unchanged content
                if new_content is None or new_content == candidate_content:
                    continue

                # Safety guard: reject rewrites that drop existing [[wikilinks]].
                # Inserting one link must never silently orphan other pages by
                # removing their only inbound reference.
                def _wikilink_slugs(text: str) -> set[str]:
                    return {
                        m.split("|")[0].strip().lower()
                        for m in re.findall(r"\[\[([^\]]+)\]\]", text)
                    }

                removed_slugs = _wikilink_slugs(candidate_content) - _wikilink_slugs(new_content)
                if removed_slugs:
                    _log.warning(
                        "Skipping candidate %s for orphan %s: "
                        "LLM removed wikilinks %s from rewrite",
                        candidate_slug, orphan_slug, removed_slugs,
                    )
                    await ctx.send_sse_event(
                        "tool_progress",
                        {"tool": "_cli_insert_link",
                         "message": (
                             f"Skipped {candidate_slug}: rewrite removed existing link(s) "
                             f"{{{', '.join(sorted(removed_slugs))}}} — trying next candidate"
                         )},
                    )
                    continue

                # Show diff; apply only if the user approves
                apply_result = await tool_propose_and_apply(
                    ctx,
                    slug=candidate_slug,
                    new_content=new_content,
                    strategy_name=_STRATEGY_LABELS[strategy],
                    rationale=(
                        f"'{candidate_slug}' identified as a related active page via "
                        f"{strategy}; LLM inserted [[{orphan_slug}]] at the most "
                        f"natural location."
                    ),
                )

                if not apply_result.get("applied"):
                    continue  # user rejected this candidate; try the next

                # Graph-level re-check: does the orphan now have an inbound link?
                verify = await tool_verify_orphan_resolved(ctx, orphan_slug=orphan_slug)
                if verify.get("resolved"):
                    return "resolved"

                # Applied but graph-level check still fails (link format mismatch?).
                await tool_notify(
                    ctx,
                    message=(
                        f"Applied link to '{candidate_slug}' but graph-level verification "
                        f"still shows '{orphan_slug}' as orphaned — the link format may "
                        f"not match the slug exactly. Trying next candidate."
                    ),
                    level="warning",
                )

        return "unresolved"

    async def _cli_select_candidates(
        self,
        provider,
        orphan_slug: str,
        orphan_content: str,
        all_page_titles: list[dict],
        exclude_slugs: list[str] | None = None,
        max_candidates: int = 3,
    ) -> list[str]:
        """Bounded LLM call: select the best candidate slugs from a full page-title list.

        Used for strategies 3 (full_title_scan) and 4 (contextual_reasoning) where
        tool_search_orphan_candidates returns all_page_titles instead of a ranked list.
        The LLM selects the 2-3 pages most likely to have reason to mention the orphan.

        The call uses a neutral, factual system prompt (no tool registry, no identity
        redefinition) — CLI providers accept it without safety objections.

        Returns a validated list of slug strings from all_page_titles that are not
        in exclude_slugs.  Empty list if no good candidates or on LLM failure.
        """
        import json
        from synthadoc.providers.base import Message  # local to avoid circular import

        excluded: set[str] = set(exclude_slugs or [])
        # Filter to eligible pages and cap the list to avoid token overflow
        eligible = [
            item for item in all_page_titles
            if item.get("slug") and item["slug"] not in excluded
        ][:200]

        if not eligible:
            return []

        title_lines = "\n".join(
            f"  {item['slug']}: {item.get('title', item['slug'])}"
            for item in eligible
        )

        _SYSTEM = (
            "You are a wiki editor selecting candidate pages for link integration.\n\n"
            f"An orphaned wiki page needs to be linked from other pages to become "
            "discoverable in the knowledge graph.\n\n"
            "Your task: from the list of wiki pages below, select up to 3 pages most "
            "likely to have reason to mention the orphan topic — pages whose existing "
            "content would naturally reference or benefit from a link to this topic.\n\n"
            "Output ONLY a JSON array of slug strings (the left-hand identifiers from "
            "the list), with no explanation, no preamble, no markdown fences. Example:\n"
            '["slug-one", "slug-two"]\n\n'
            "If no page is a plausible fit, output an empty array: []"
        )

        orphan_preview = orphan_content[:1500] if orphan_content else "(no content available)"
        user_msg = (
            f"Orphan page slug: {orphan_slug}\n"
            f"Orphan page content (excerpt):\n{orphan_preview}\n\n"
            f"Wiki pages to choose from:\n{title_lines}"
        )

        try:
            response = await provider.complete(
                [Message(role="user", content=user_msg)],
                system=_SYSTEM,
            )
            raw = response.text.strip()
            # Strip markdown code fences — CLI providers occasionally add them
            if raw.startswith("```"):
                lines = raw.split("\n")
                start = 1
                end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
                raw = "\n".join(lines[start:end]).strip()

            selected = json.loads(raw)
            if not isinstance(selected, list):
                return []

            # Validate: keep only real slugs from the eligible set
            valid_slugs: set[str] = {item["slug"] for item in eligible}
            return [
                s for s in selected
                if isinstance(s, str) and s in valid_slugs
            ][:max_candidates]
        except Exception as exc:  # noqa: BLE001
            _log.warning("CLI candidate selection failed for %s: %s", orphan_slug, exc)
            return []

    async def _cli_insert_link(
        self,
        provider,
        orphan_slug: str,
        orphan_content: str,
        candidate_slug: str,
        candidate_content: str,
    ) -> str | None:
        """Single bounded LLM call: insert [[orphan_slug]] naturally into the candidate page.

        The system prompt is deliberately neutral — no tool registry, no wire-format
        instructions, no identity redefinition — so CLI providers accept it without
        triggering their safety reasoning.

        Returns the revised candidate page markdown, or None on failure.
        """
        from synthadoc.providers.base import Message  # local to avoid circular import

        _SYSTEM = (
            "You are a wiki editor. Your task is to integrate an orphaned wiki page "
            "into the knowledge graph by adding a natural [[wikilink]] to it from "
            "a related page.\n\n"
            "Rules for inserting the link:\n"
            f"  - Insert [[{orphan_slug}]] at the most contextually appropriate location\n"
            "  - Preferred locations: inside a related section alongside thematically "
            "similar content, or in an existing 'See also' section\n"
            "  - Do NOT create a 'See also' section if one does not already exist\n"
            "  - The link must be natural and topically relevant — never forced or "
            "irrelevant to the surrounding prose\n"
            "  - Preserve all existing content, structure, headings, and formatting exactly\n"
            "  - CRITICAL — wikilinks: every [[...]] that already exists in the "
            "candidate page MUST appear verbatim in your output. Do NOT remove, "
            "rename, or reformat any existing [[link]]. You may ONLY add the new "
            f"[[{orphan_slug}]] link — nothing else about the existing wikilinks changes.\n"
            "  - Return ONLY the revised page content (markdown) — "
            "no explanation, no preamble, no code fences"
        )

        user_msg = (
            f"Orphan page slug: {orphan_slug}\n\n"
            f"Orphan page content (for context):\n{orphan_content[:2000]}\n\n"
            f"---\n\n"
            f"Candidate page to modify (slug: {candidate_slug}):\n{candidate_content}"
        )

        try:
            response = await provider.complete(
                [Message(role="user", content=user_msg)],
                system=_SYSTEM,
            )
            revised = response.text.strip()
            # Strip markdown code fences — CLI providers occasionally add them
            if revised.startswith("```"):
                lines = revised.split("\n")
                start = 1
                end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
                revised = "\n".join(lines[start:end]).strip()
            return revised if revised else None
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "CLI link insertion failed for %s → %s: %s", orphan_slug, candidate_slug, exc
            )
            return None
