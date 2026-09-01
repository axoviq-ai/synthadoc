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
from synthadoc.agents.workflows.tools.contradiction_resolver_tools import (
    tool_get_contradicted_pages,
    tool_read_source_content,
    tool_cost_estimate,
)

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

# Content revision rules for Strategy 1 — defined here once so both the
# multi-turn system prompt (§STEP 4c) and the CLI-provider single-call rewrite
# path (_cli_rewrite_page) share the same guidance without duplication.
_STRATEGY_1_RULES = (
    "Formulate improved content that:\n"
    "  - For gate-demoted: removes or hedges the specific claims in lint_warnings\n"
    "  - For conflict: reconciles the source contradiction_note with explicit sourcing hedge\n"
    "  - For both: addresses both\n"
    "  Preserve all headings, structure, and non-disputed content."
)

# _SYSTEM_PROMPT cannot be an f-string because it contains literal `{}` in the
# JSON tool-call wire-format examples.  Instead, $$STRATEGY_1$$ is replaced at
# module load time with _STRATEGY_1_RULES (indented to match step-4c context).
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
        $$STRATEGY_1$$

    4d. Call tool_propose_and_apply(slug, new_content, strategy_name, rationale).
        strategy_name should be one of:
          "Strategy 1 — Content rewrite"
          "Strategy 2 — Web ingest for better grounding"
          "Strategy 3 — Force source re-ingest"
          "Strategy 4 — Cross-page resolution"
          "Strategy 5 — Escalate"

    4e. If not applied (user skipped): mark page as skipped, continue to next page.

    4f. If applied: call tool_run_scoped_lint(slug).

    4g. If lint PASS (tool result contains pass: True):
        ⚠ STOP — do NOT call tool_propose_and_apply again.
        pass: True is the ONLY field that determines pass/fail.
        warnings_count may be non-zero even on a passing result — the linter
        records soft informational notes on a passing page; this is expected
        and does NOT mean another rewrite is needed.
        ⚠ MANDATORY TOOL CALL — you MUST call this before outputting any text:
        tool_transition_lifecycle_state(slug, to_state="active",
            reason=f"resolved by contradiction-resolver — strategy: {strategy_name}, attempt <N>")
        After the tool call succeeds: add slug to your internal "fixed" list, then
        continue to step 4j (next page) or step 5 (final summary) if last page.
        Do NOT output any plain text here — text output ends the entire workflow.

    4h. If lint FAIL (attempt < 4): diagnose the failure, then select the next strategy.
        Prefer Strategy 2, 3, or 4 when they could reasonably address the failure.
        Strategy 1 (content rewrite) may be reused only after other options are
        exhausted or clearly inapplicable.

          Attempt 2 — prefer Strategy 2 or 3; use Strategy 1 only if both are clearly
            inapplicable (no source_path, web ingest irrelevant for the specific failure):
            • Strategy 2 (Web ingest) — preferred for gate-demoted pages; search for
              current authoritative sources to support, replace, or ground disputed claims.
            • Strategy 3 (Force re-ingest) — preferred for source-conflict pages when
              source_path is available and the source itself may have updated.

          Attempt 3 — use a strategy not yet tried; Strategy 1 (second use) is allowed
            only if strategies 2, 3, and 4 have all been tried or clearly ruled out:
            • Strategy 4 (Cross-page resolution) — if linked wiki pages contain
              information that can resolve or corroborate the disputed content.
            • The other of Strategy 2 / Strategy 3 if it wasn't used in attempt 2.
            • Strategy 1 (second use) — only if 2, 3, and 4 are all exhausted. Target
              different specific claims than attempt 1, or use stronger hedging and
              explicit source attribution for each disputed claim.

          Attempt 4 — any remaining untried strategy; if all others have been tried,
            reuse Strategy 1 with a substantially different approach: target different
            claims, restructure the affected section, or add explicit per-claim citations.

        Repeat from 4c.

    4i. If cap reached (4 failed attempts): Strategy 5 — Escalate.
        Do NOT output plain text (it would end the entire workflow).
        Instead call tool_notify with level="warning":
          message: "⚠ <slug> — unresolved after 4 attempts\n  Diagnosis: <why each strategy failed>\n  Suggested: <concrete next steps for the user>"
        Add slug to your internal "unresolved" list.
        Then continue immediately to step 4j (inter-page confirm).

    4j. Between pages: if more pages remain, call tool_confirm with
        "Continue to next page (<next_slug>)?", yes_label="Continue", no_label="Stop".
        If not confirmed: stop the loop (treat remaining pages as skipped).
        ⚠ MANDATORY — do NOT output any plain text before calling tool_confirm here.
        Text output ends the entire workflow before the confirmation is shown.

STEP 5 — Final summary (tool call FIRST, then plain text)
  ⚠ Do NOT output any plain text yet.
  FIRST call tool_get_wiki_status() — this fetches live lifecycle counts.
  THEN output a single plain-text summary combining per-page outcomes and
  the live counts returned by tool_get_wiki_status():
    "Contradiction Resolver — Complete\n\n✅ Fixed (<N>):\n  ...\n⚠ Unresolved (<N>):\n  ...\n⏭ Skipped (<N>):\n  ...\n\nWiki status (live): <key: value, ...>"
  This plain-text output ends the loop — it must be your very last action.

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Plain text ENDS THE LOOP — use it ONLY for the final summary (step 5),
  or when cancelling (steps 2 and 3).
• ALWAYS call tool_get_wiki_status() before outputting the step 5 summary —
  never output any plain text before this tool call returns.
• ALWAYS call tool_run_scoped_lint after every applied change.
• When tool_run_scoped_lint returns pass: True — IMMEDIATELY call
  tool_transition_lifecycle_state. Do NOT call tool_propose_and_apply again.
  pass: True is final. warnings_count may still be non-zero; that is normal
  and must NEVER trigger another rewrite attempt.
• ALWAYS call tool_transition_lifecycle_state AS A TOOL CALL (not in text) when scoped lint passes.
  This call MUST happen before any plain-text output — even a one-line summary ends the workflow.
• NEVER transition to active before scoped lint passes.
• Call tool_propose_and_apply at most ONCE per attempt. After calling it
  (whether the user approves or skips), move to the next step immediately —
  never call tool_propose_and_apply again within the same attempt.
• Prefer Strategy 2, 3, or 4 when they could reasonably address the failure.
  Strategy 1 (content rewrite) may be reused, but only after considering whether
  web ingest, re-ingest, or cross-page resolution is a better fit for the specific
  root cause. Do not reflexively reuse Strategy 1 when another approach targets
  the actual problem. Strategy 1 may be used at most twice per page.
• Cap is HARD at 4 attempts per page — escalate on the 5th failure.
• Do NOT call tool_propose_and_apply and tool_confirm in the same tool-call batch.
""".replace(
    # Embed _STRATEGY_1_RULES (indented 8 spaces to match step-4c context).
    "        $$STRATEGY_1$$",
    "\n".join("        " + line for line in _STRATEGY_1_RULES.splitlines()),
)


_log = __import__("logging").getLogger(__name__)


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

    # CLI providers (claude-code, opencode) cannot follow the JSON wire-format
    # tool-call loop.  This workflow opts into a Python-driven alternative:
    # gather + cost-gate → single LLM rewrite call per page → propose-and-apply
    # (diff-before-write) → scoped lint → lifecycle transition.
    # The LLM call is a factual bounded request ("here is the page; fix it") that
    # CLI providers accept without safety objections.
    SUPPORTS_CLI_PROVIDER: bool = True

    def get_tool_budget(self) -> int:
        # Each page requires ~8 tool calls (read, propose, lint, transition, confirm ×2)
        # with 4-attempt retry headroom.  Allow up to 20 pages:
        # 3 setup + 20 × 12 + 1 final = 244 → round to 250.
        return 250

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

    # ── CLI provider path ─────────────────────────────────────────────────────

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: Python-orchestrated gather → rewrite → confirm → lint → activate.

        Mirrors the normal workflow's STEP 1-5 sequence but replaces the JSON
        wire-format tool-call loop with direct Python calls to the same tool
        functions.  The only LLM call is a bounded rewrite request per page
        ("here is the page and its contradiction signals; revise it") — no fake
        tools, no identity redefinition.

        Limitation vs. the Anthropic-API path: only Strategy 1 (content rewrite)
        is attempted, with no retry loop.  Pages that fail scoped lint after the
        rewrite are marked unresolved; the summary directs the user to run the
        full resolver (with provider=anthropic) for those pages.
        """
        # ── 1. Parse flags (same logic as build_initial_message) ──────────────
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        type_match = re.search(
            r"--type\s+(gate|adversarial|conflict|source-conflict|all)",
            question,
            re.IGNORECASE,
        )
        page_slug = slug_match.group(1) if slug_match else None
        raw_type = (type_match.group(1).lower() if type_match else "all")
        scope = self._TYPE_REMAP.get(raw_type, raw_type)

        # ── 2. Gather contradicted pages ──────────────────────────────────────
        all_pages_result = await tool_get_contradicted_pages(ctx, scope=scope)
        pages: list[dict] = all_pages_result.get("pages", [])
        if page_slug:
            pages = [p for p in pages if p["slug"] == page_slug]

        if not pages:
            scope_label = f"scope={scope}" + (f", slug={page_slug}" if page_slug else "")
            msg = f"No contradicted pages found ({scope_label})."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 3. Cost estimate + approval ───────────────────────────────────────
        estimate = await tool_cost_estimate(ctx, page_count=len(pages))
        if not estimate.get("confirmed"):
            msg = "Contradiction resolver cancelled."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 4. Per-page resolution loop ───────────────────────────────────────
        fixed: list[str] = []
        unresolved: list[tuple[str, str]] = []   # (slug, reason)
        skipped: list[str] = []

        for i, page_info in enumerate(pages):
            slug = page_info["slug"]
            page_type = page_info["type"]

            await ctx.send_sse_event(
                "tool_progress",
                {"tool": "_resolve", "message": f"Resolving {slug} ({page_type})..."},
            )

            # 4a. Unknown type: run lint first to determine whether state is stale
            if page_type == "unknown":
                lint_result = await tool_run_scoped_lint(ctx, slug=slug)
                if lint_result.get("pass"):
                    # Stale metadata — no rewrite needed; transition directly
                    await tool_transition_lifecycle_state(
                        ctx, slug=slug, to_state="active",
                        reason=(
                            "resolved: clean lint with no contradiction signals "
                            "— contradicted state was stale metadata"
                        ),
                    )
                    fixed.append(slug)
                    # Still need to confirm between pages below
                else:
                    # Real issue — treat as gate-demoted and fall through to rewrite
                    page_type = "gate"

            if page_type != "unknown" or slug not in fixed:
                # 4b. Read page content (and source for conflict/both types)
                page_content = await tool_read_page_content(ctx, slug=slug)
                source_text: str | None = None
                if page_type in ("conflict", "both"):
                    source_result = await tool_read_source_content(ctx, slug=slug)
                    source_text = source_result.get("source_text") or None

                # 4c. Single LLM rewrite call
                rewrite = await self._cli_rewrite_page(
                    provider, slug, page_content, source_text, page_type
                )

                if rewrite is None:
                    await tool_notify(
                        ctx,
                        message=f"⚠ {slug} — could not generate a rewrite; skipping",
                        level="warning",
                    )
                    unresolved.append((slug, "LLM rewrite failed"))
                else:
                    # 4d. Show diff and ask for approval (reuses propose_and_apply as-is)
                    apply_result = await tool_propose_and_apply(
                        ctx,
                        slug=slug,
                        new_content=rewrite,
                        strategy_name="Strategy 1 — Content rewrite",
                        rationale=(
                            f"Resolved {page_type} contradiction via single-pass content rewrite "
                            f"(CLI provider path — Strategy 1 only)"
                        ),
                    )

                    if not apply_result.get("applied"):
                        skipped.append(slug)
                    else:
                        # 4e. Re-lint after applying the change
                        lint_result = await tool_run_scoped_lint(ctx, slug=slug)
                        if lint_result.get("pass"):
                            await tool_transition_lifecycle_state(
                                ctx, slug=slug, to_state="active",
                                reason=(
                                    "resolved by contradiction-resolver "
                                    "— CLI provider path, Strategy 1 (content rewrite)"
                                ),
                            )
                            fixed.append(slug)
                        else:
                            wc = lint_result.get("warnings_count", "?")
                            await tool_notify(
                                ctx,
                                message=(
                                    f"⚠ {slug} — rewrite applied but lint still failing "
                                    f"({wc} warning(s)); page remains contradicted. "
                                    f"Run the full resolver with provider=anthropic for "
                                    f"multi-strategy retry."
                                ),
                                level="warning",
                            )
                            unresolved.append((slug, f"lint still failing ({wc} warnings)"))

            # 4f. Confirm before next page
            if i < len(pages) - 1:
                next_slug = pages[i + 1]["slug"]
                cont = await tool_confirm(
                    ctx,
                    f"Continue to next page ({next_slug})?",
                    yes_label="Continue",
                    no_label="Stop",
                )
                if not cont.get("confirmed"):
                    skipped.extend(p["slug"] for p in pages[i + 1:])
                    break

        # ── 5. Final summary ──────────────────────────────────────────────────
        wiki_status = await tool_get_wiki_status(ctx)

        parts: list[str] = ["**Contradiction Resolver — Complete**\n"]

        if fixed:
            parts.append(f"✅ Fixed ({len(fixed)}):")
            for s in fixed:
                parts.append(f"  - {s}")

        if unresolved:
            parts.append(f"\n⚠ Unresolved ({len(unresolved)}):")
            for s, reason in unresolved:
                parts.append(f"  - {s}: {reason}")
            parts.append(
                "\n  Tip: run the full resolver with provider=anthropic for "
                "multi-strategy retry on unresolved pages."
            )

        if skipped:
            parts.append(f"\n⏭ Skipped ({len(skipped)}):")
            for s in skipped:
                parts.append(f"  - {s}")

        status_str = ", ".join(f"{k}: {v}" for k, v in wiki_status.items()
                               if k not in ("tool", "message"))
        parts.append(f"\nWiki status (live): {status_str}")

        summary = "\n".join(parts)
        yield {"event": "token", "data": {"text": summary}}
        yield {"event": "final_text", "data": {"text": summary}}

    async def _cli_rewrite_page(
        self,
        provider,
        slug: str,
        page_content: dict,
        source_text: str | None,
        page_type: str,
    ) -> str | None:
        """Call the provider once with a factual rewrite request.

        Returns the revised markdown string, or None on failure.
        The system prompt is deliberately neutral — no tool registry, no identity
        redefinition — so CLI providers (claude-code, opencode) accept it without
        triggering their safety reasoning.
        """
        from synthadoc.providers.base import Message  # local to avoid circular import

        content = page_content.get("content", "")
        lint_warnings: list[str] = page_content.get("lint_warnings") or []
        contradiction_note: str | None = page_content.get("contradiction_note")

        # Build the problem description
        problem_parts: list[str] = []
        if lint_warnings:
            problem_parts.append("Lint warnings (dubious or unsupported claims to fix):")
            for w in lint_warnings:
                problem_parts.append(f"  - {w}")
        if contradiction_note:
            problem_parts.append(f"Contradiction note: {contradiction_note}")
        if not problem_parts:
            problem_parts.append(
                "(No specific signals recorded. Apply conservative hedging to "
                "any claims that lack explicit sourcing.)"
            )

        source_block = ""
        if source_text:
            source_block = f"\n\nSource text (use to ground your revision):\n{source_text[:4000]}"

        # Reuse _STRATEGY_1_RULES (the same rules embedded in _SYSTEM_PROMPT §STEP 4c)
        # so the content guidance is defined exactly once at module level.
        _SYSTEM = (
            "You are a wiki editor. Apply Strategy 1 — Content rewrite — to resolve "
            "the contradicted wiki page provided.\n\n"
            "Revision rules:\n"
            + _STRATEGY_1_RULES
            + "\n\nReturn ONLY the revised markdown — no explanation, no preamble, no code fences."
        )

        user_msg = (
            f"Wiki page slug: {slug}\n"
            f"Contradiction type: {page_type}\n\n"
            f"Contradiction signals:\n"
            + "\n".join(problem_parts)
            + f"\n\nCurrent page content:\n{content}"
            + source_block
        )

        try:
            response = await provider.complete(
                [Message(role="user", content=user_msg)],
                system=_SYSTEM,
            )
            revised = response.text.strip()
            # Strip markdown fences — CLI providers occasionally wrap output despite instructions
            if revised.startswith("```"):
                lines = revised.split("\n")
                start = 1
                end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
                revised = "\n".join(lines[start:end]).strip()
            return revised if revised else None
        except Exception as exc:  # noqa: BLE001
            _log.warning("CLI rewrite failed for %s: %s", slug, exc)
            return None
