# synthadoc/agents/workflows/contradiction_resolver.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""ContradictionResolverWorkflow — agentic closed-loop remediation for contradicted pages.

Drives the LLM through a per-page strategy loop: read → propose → confirm → re-lint → activate.
Strategy cap is 3 per page; cap exhaustion triggers an escalation (Strategy 5).
"""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING

from synthadoc.agents.workflows._base import AgenticWorkflow
# Shared framework tools (usable by any workflow)
from synthadoc.agents.workflows._tools import (
    tool_confirm,
    tool_ingest_source,
    tool_notify,
    tool_poll_job,
    tool_read_page_content,
    tool_run_scoped_lint,
    tool_propose_and_apply,
    tool_transition_lifecycle_state,
    tool_get_wiki_status,
)
# Contradiction-domain tools (specific to this workflow)
from synthadoc.agents.workflows.contradiction_resolver_tools import (
    tool_get_contradicted_pages,
    tool_read_source_content,
    tool_cost_estimate,
)

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_SYSTEM_PROMPT = """\
You are a wiki maintenance agent specialising in resolving pages that have been \
marked 'contradicted'. A contradicted page may be:

  • Gate-demoted: adversarial review found ≥ threshold dubious or unsupported claims.
    Signal: lint_warnings list on the page.
  • Source-conflict: ingest detected that a new source contradicts the existing content.
    Signal: contradiction_note frontmatter field.
  • Both: both signals present.
  • Unknown: contradicted state with no lint_warnings and no contradiction_note —
    run a fresh lint to determine whether the contradicted state is stale metadata
    (lint passes → auto-transition to active) or a real issue (lint fails → treat
    as gate-demoted with the fresh warnings).

━━━ TOOL-CALL WIRE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Emit EXACTLY this JSON object (no markdown fences, no XML, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}
When you have a final message for the user, respond with plain text only (no JSON).

━━━ TOOL INVENTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
tool_get_contradicted_pages(scope)     → list contradicted pages (scope: all/gate/conflict)
tool_read_page_content(slug)           → current content + lint_warnings + contradiction_note
tool_read_source_content(slug)         → source text (layered fallback: raw → extracted → note)
tool_propose_and_apply(slug, new_content, strategy_name, rationale)
                                       → shows diff to user, applies if approved
tool_run_scoped_lint(slug)             → re-lint one page; returns {pass, warnings_count, ...}
tool_transition_lifecycle_state(slug, to_state, reason)
                                       → transition page to to_state + lifecycle event
                                         (use to_state="active" to clear contradicted)
tool_get_wiki_status()                 → lifecycle state counts
tool_cost_estimate(page_count)         → shows estimate to user as a notice AND
                                         requests approval in one step; returns
                                         {confirmed, pages, estimated_usd,
                                          estimated_minutes}. Do NOT call
                                         tool_confirm separately after this.
tool_confirm(message, yes_label, no_label)   → prompt user for yes/no decision
                                         (for inter-page decisions only — NOT
                                          for the initial cost-estimate gate)
tool_notify(message, level)            → send a notice to the user WITHOUT ending
                                         the loop. Use for mid-workflow status
                                         messages (e.g. escalation notices after
                                         3 failures). level: "info"|"warning"|"error"
tool_ingest_source(source_path)        → enqueue ingest job; returns job_id
tool_poll_job(job_id, timeout_seconds) → poll until job terminal; returns status dict

━━━ WORKFLOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — List pages
  Call tool_get_contradicted_pages(scope) where scope comes from the initial message
  (all / gate / conflict). If slug is specified, still call get_contradicted_pages
  then filter to that slug.

STEP 2 — Check for work
  If the result has zero pages: respond with plain text "No contradicted pages \
found matching the selected scope." (this ends the loop).

STEP 3 — Cost estimate and approval
  Call tool_cost_estimate(page_count=<N from step 1>).
  This tool sends the estimate to the user AND shows a ConfirmCard in one
  operation — do NOT call tool_confirm separately here.
  After tool_cost_estimate returns, check result["confirmed"]:
    • false → respond with plain text "Contradiction resolver cancelled."
              (this ends the loop — it is the ONLY plain text allowed here)
    • true  → proceed immediately to step 4 with NO plain text output
  Do NOT output any prose or summary between this tool call and step 4.

STEP 4 — Per-page resolution loop
  For each page from step 1:

    4a. Detect type (gate / conflict / both / unknown from tool result).

        Unknown — status is contradicted but no lint_warnings and no contradiction_note:
          i.  Call tool_run_scoped_lint(slug) to get a fresh lint result.
          ii. If lint PASS → the contradicted state is stale metadata; transition:
                call tool_transition_lifecycle_state(slug, to_state="active",
                  reason="resolved: clean lint with no contradiction signals — contradicted state was stale")
              Add slug to the "fixed" list and continue to step 4j.
          iii.If lint FAIL → the page has real issues; treat as gate-demoted using
              the fresh lint_warnings from this lint result and proceed from step 4c
              with Strategy 1.
          Do NOT skip unknown pages without first running tool_run_scoped_lint.

    4b. Read page: call tool_read_page_content(slug).
        If conflict or both: also call tool_read_source_content(slug).

    4c. Select Strategy 1 (content rewrite) as the first attempt.
        Formulate improved content that:
          - For gate-demoted: removes or hedges the specific claims in lint_warnings
          - For conflict: reconciles the source contradiction_note with explicit sourcing hedge
          - For both: addresses both

    4d. Call tool_propose_and_apply(slug, new_content, strategy_name, rationale).
        strategy_name should be one of:
          "Strategy 1 — Content rewrite"
          "Strategy 2 — Web ingest for better grounding"
          "Strategy 3 — Force source re-ingest"
          "Strategy 4 — Cross-page resolution"
          "Strategy 5 — Escalate"

    4e. If not applied (user skipped): mark page as skipped, continue to next page.

    4f. If applied: call tool_run_scoped_lint(slug).

    4g. If lint PASS:
        ⚠ MANDATORY TOOL CALL — you MUST call this before outputting any text:
        tool_transition_lifecycle_state(slug, to_state="active",
            reason=f"resolved by contradiction-resolver — strategy: {strategy_name}, attempt <N>")
        After the tool call succeeds: add slug to your internal "fixed" list, then
        continue to step 4j (next page) or step 5 (final summary) if last page.
        Do NOT output any plain text here — text output ends the entire workflow.

    4h. If lint FAIL (attempt < 3): diagnose the failure, then escalate to the next
        strategy — NEVER use Strategy 1 again after the first attempt fails.

          Attempt 2 — always Strategy 2 or 3 (never Strategy 1):
            • Strategy 2 (Web ingest) — search for current authoritative sources
              to support, replace, or provide grounding for the disputed claims.
              Use this for gate-demoted pages (lint_warnings) where the claims
              need better citation, and for source-conflict pages where a newer
              web source may supersede the contradiction.
            • Strategy 3 (Force re-ingest) — force-reingest the page's source_path
              if source_path is available and the source itself may have updated.
            Choose whichever fits the failure diagnosis; prefer Strategy 2 for
            gate-demoted pages, Strategy 3 for source-conflict pages.

          Attempt 3 — must be a strategy not yet tried:
            • Strategy 4 (Cross-page resolution) — if linked wiki pages contain
              information that can resolve or corroborate the disputed content.
            • The other of Strategy 2 / Strategy 3 if it wasn't used in attempt 2.
            Never return to Strategy 1.

        Repeat from 4c.

    4i. If cap reached (3 failed attempts): Strategy 5 — Escalate.
        Do NOT output plain text (it would end the entire workflow).
        Instead call tool_notify with level="warning":
          message: "⚠ <slug> — unresolved after 3 attempts\n  Diagnosis: <why each strategy failed>\n  Suggested: <concrete next steps for the user>"
        Add slug to your internal "unresolved" list.
        Then continue immediately to step 4j (inter-page confirm).

    4j. Between pages: if more pages remain, call tool_confirm with
        "Continue to next page (<next_slug>)?", yes_label="Continue", no_label="Stop".
        If not confirmed: stop the loop (treat remaining pages as skipped).
        ⚠ MANDATORY — do NOT output any plain text before calling tool_confirm here.
        Text output ends the entire workflow before the confirmation is shown.

STEP 5 — Final summary
  Print a formatted summary:
    "Contradiction Resolver — Complete\\n\\n✅ Fixed (<N>):\\n  ...\\n⚠ Unresolved (<N>):\\n  ...\\n⏭ Skipped (<N>):\\n  ..."

STEP 6 — Ground-truth confirmation
  Call tool_get_wiki_status() and append the lifecycle counts to the summary.
  This is the ground truth — it tells the user whether contradicted pages
  are actually gone.

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Plain text ENDS THE LOOP — use it ONLY for the final summary (step 5/6),
  or when cancelling (steps 2 and 3).
• ALWAYS call tool_run_scoped_lint after every applied change.
• ALWAYS call tool_transition_lifecycle_state AS A TOOL CALL (not in text) when scoped lint passes.
  This call MUST happen before any plain-text output — even a one-line summary ends the workflow.
• NEVER transition to active before scoped lint passes.
• NEVER use Strategy 1 more than once per page. After Strategy 1 fails, always
  escalate to Strategy 2, 3, or 4 — never return to Strategy 1 with "a different
  angle". A different angle is still Strategy 1 and is still forbidden.
• Cap is HARD at 3 attempts per page — escalate on the 4th failure.
• Do NOT call tool_propose_and_apply and tool_confirm in the same tool-call batch.
"""


class ContradictionResolverWorkflow(AgenticWorkflow):
    """Closed-loop agentic remediation for contradicted wiki pages."""

    NAME = "contradiction-resolver"
    DESCRIPTION = "Interactively resolve pages in 'contradicted' state (diff-before-write approval)."
    CLI_ARGS = "[--slug SLUG]  [--type adversarial|source-conflict]"

    MATCH_RE: re.Pattern = re.compile(
        r"\bcontradiction.{0,30}\bresolv"
        r"|\bresolv.{0,30}\bcontradict"
        r"|\bfix\s+contradicted\b"
        r"|\brun\s+contradiction.{0,10}resolver\b"
        r"|\bcontradiction\s+resolver\b",
        re.IGNORECASE,
    )

    def get_tool_budget(self) -> int:
        # Each page requires ~6 tool calls (read, propose, lint, transition, confirm ×2)
        # plus 3 setup calls and 1 final status call.  Allow up to 20 pages with retry
        # headroom: 3 + 20 × 10 + 1 = 204 → round to 200 for a clean limit.
        return 200

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    # Map user-facing --type names to internal scope tokens.
    _TYPE_REMAP: dict[str, str] = {
        "adversarial": "gate",
        "source-conflict": "conflict",
    }

    def build_initial_message(
        self,
        user_input: str,
        **_kwargs,
    ) -> str:
        slug_match = re.search(r"--slug\s+(\S+)", user_input, re.IGNORECASE)
        type_match = re.search(
            r"--type\s+(gate|adversarial|conflict|source-conflict|all)",
            user_input,
            re.IGNORECASE,
        )

        slug = slug_match.group(1) if slug_match else None
        raw_type = type_match.group(1).lower() if type_match else "all"
        scope = self._TYPE_REMAP.get(raw_type, raw_type)

        msg_parts = ["Run the contradiction resolver workflow."]
        msg_parts.append(f"Scope: {scope}")
        if slug:
            msg_parts.append(f"Limit to slug: {slug}")
        return "\n".join(msg_parts)

    def get_tool_fns(self, ctx: "WorkflowContext") -> dict:
        p = functools.partial
        return {
            # Contradiction-domain tools (from contradiction_resolver_tools.py)
            "tool_get_contradicted_pages":     p(tool_get_contradicted_pages, ctx),
            "tool_read_source_content":        p(tool_read_source_content, ctx),
            "tool_cost_estimate":              p(tool_cost_estimate, ctx),
            # Generic framework tools (from _tools.py)
            "tool_read_page_content":          p(tool_read_page_content, ctx),
            "tool_run_scoped_lint":            p(tool_run_scoped_lint, ctx),
            "tool_propose_and_apply":          p(tool_propose_and_apply, ctx),
            "tool_transition_lifecycle_state": p(tool_transition_lifecycle_state, ctx),
            "tool_get_wiki_status":            p(tool_get_wiki_status, ctx),
            # Shared tools (from _tools.py — also used by other workflows)
            "tool_confirm":                    p(tool_confirm, ctx),
            "tool_notify":                     p(tool_notify, ctx),
            "tool_ingest_source":              p(tool_ingest_source, ctx),
            "tool_poll_job":                   p(tool_poll_job, ctx),
        }
