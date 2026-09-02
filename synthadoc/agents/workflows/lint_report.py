# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""LintReportWorkflow — run a full lint pass and surface the complete report."""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_get_lint_report,
    tool_run_lint,
)

if TYPE_CHECKING:
    pass

_log = __import__("logging").getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a wiki maintenance agent. Your task is to run a full lint pass and
show the user a complete lint report when it finishes.

## Tool reference

### run_lint
Run a full wiki lint pass and wait for it to complete. Blocks until done.
Input:  {}
Output: {"status": "success"|"failed"|"timeout", "message": str} | {"error": str}

### get_lint_report
Read the full lint state from the audit DB and page frontmatter.
No arguments needed.
Input:  {}
Output: {
  "last_run": {
    "timestamp": str, "dangling_removed": int, "orphans": int,
    "contradictions_resolved": int, "contradictions_flagged": int
  },
  "contradicted_pages": [{"slug": str, "since": str}],
  "adversarial_warnings": [{"slug": str, "count": int}],
  "orphan_slugs": [str],
  "broken_citations": int,
  "broken_citation_pages": [{"slug": str, "count": int}]
}

## Tool-call wire format

Emit EXACTLY this JSON object (no markdown fences, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}

When you have a final message for the user, respond with plain text only (no JSON).

## Workflow steps

1. Call run_lint with no arguments. Blocks until the lint job finishes.
   - If it returns {"error": ...}: write a plain-text error message and STOP.
   - If it returns {"status": "failed"|"timeout", ...}: write a plain-text error and STOP.
2. Call get_lint_report with no arguments.
3. Write a plain-text report using this structure:

   ### Lint Report (use the timestamp from last_run, or today's date if missing)

   **Summary**
   - Dangling links removed: N  (omit this line if dangling_removed == 0)
   - Orphan pages: N
   - Contradictions: N resolved, N flagged
   - Broken citations: N  (omit this line if broken_citations == 0)

   **Contradicted Pages**
   List each as "- slug  (since YYYY-MM-DD)".
   If none: "(none)"

   **Adversarial Warnings**
   List each as "- [[slug]]  (N warning(s))".
   If none: "(none)"

   **Orphan Pages**
   List each slug as a bullet.
   If none: "(none)"

   **Broken Citations**
   List each as "- [[slug]]  (N broken citation(s))".
   If none: "(none)"

Plain text ends the workflow. Use it ONLY in step 3 or on error. All
intermediate steps must be tool calls, not prose.
"""


class LintReportWorkflow(AgenticWorkflow):
    """Run a full lint pass then surface the complete report in one shot."""

    NAME = "lint-report"
    DESCRIPTION = "Run a full lint pass and surface the complete report."

    MATCH_RE = re.compile(
        r"^(please\s+)?\brun\b.{0,20}\blint\b"
        r"|^(can|could|would)\s+(you\s+)?(please\s+)?\brun\b.{0,20}\blint\b",
        re.IGNORECASE,
    )

    # CLI providers (claude-code, opencode) refuse the JSON wire-format
    # tool-call loop in _SYSTEM_PROMPT — they correctly identify the
    # {"tool_call": ...} instruction pattern as a prompt injection attempt.
    # This workflow opts into a Python-driven alternative (run_for_cli_provider)
    # that drives the same two-step sequence directly from Python.
    # No LLM reasoning call is needed because the workflow is fully read-only
    # and deterministic: run lint → read report → format output.
    # The same tool functions (tool_run_lint, tool_get_lint_report) are reused
    # directly so behaviour is identical to what the system prompt instructs
    # the LLM to do on the Anthropic-API path.
    SUPPORTS_CLI_PROVIDER: bool = True

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "run_lint":        functools.partial(tool_run_lint, ctx),
            "get_lint_report": functools.partial(tool_get_lint_report, ctx),
        }

    # ── CLI provider path ─────────────────────────────────────────────────────

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: Python-driven lint + report (read-only, no LLM).

        Why this path exists
        --------------------
        CLI providers (claude-code, opencode) receive the system prompt's JSON
        wire-format instruction block ({"tool_call": ...} protocol) and correctly
        flag it as a prompt injection attempt.  Rather than asking them to act as
        a subordinate LLM agent, this path drives the same two-step sequence
        directly from Python.

        No LLM reasoning call is needed because this workflow is fully
        deterministic and read-only: run lint → read the lint report → format
        the output.  The report format mirrors the structure defined in the
        system prompt (step 3), so output is identical on both provider paths.

        Steps (mirrors system prompt §steps 1-3)
        -----------------------------------------
        1. tool_run_lint      — run a full wiki lint pass; wait for it to finish.
                                Early-exit on error or failure.
        2. tool_get_lint_report — read the lint state from the audit DB.
        3. Format a plain-text report following the system prompt §step 3 layout:
             ### Lint Report (timestamp)
             Summary block (dangling, orphans, contradictions, broken citations)
             Contradicted Pages / Adversarial Warnings / Orphan Pages / Broken Citations

        The ``provider`` and ``question`` arguments are accepted for interface
        compatibility but unused — no LLM call is needed for a read-only
        sequential workflow.
        """
        import datetime

        # ── Step 1: run lint ──────────────────────────────────────────────────
        lint_result = await tool_run_lint(ctx)
        lint_error = lint_result.get("error")
        lint_status = lint_result.get("status", "")
        if lint_error or lint_status in ("failed", "timeout"):
            msg = (
                f"Lint failed: "
                f"{lint_error or lint_result.get('message', 'unknown error')}"
            )
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── Step 2: read report ───────────────────────────────────────────────
        report = await tool_get_lint_report(ctx)
        last_run: dict = report.get("last_run") or {}

        # ── Step 3: format report (mirrors system prompt §step 3) ─────────────
        # Timestamp: use last_run["timestamp"] when available; fall back to today.
        ts = (last_run.get("timestamp") or str(datetime.date.today()))[:10]

        dangling: int = last_run.get("dangling_removed", 0)
        orphans: int = last_run.get("orphans", 0)
        contradictions_resolved: int = last_run.get("contradictions_resolved", 0)
        contradictions_flagged: int = last_run.get("contradictions_flagged", 0)
        broken_citations: int = report.get("broken_citations", 0)

        parts: list[str] = [f"### Lint Report ({ts})\n"]

        # Summary block — omit "Dangling links removed" and "Broken citations"
        # when they are zero (mirrors the system prompt "omit if 0" instructions).
        summary_lines: list[str] = ["**Summary**"]
        if dangling:
            summary_lines.append(f"- Dangling links removed: {dangling}")
        summary_lines.append(f"- Orphan pages: {orphans}")
        summary_lines.append(
            f"- Contradictions: {contradictions_resolved} resolved, "
            f"{contradictions_flagged} flagged"
        )
        if broken_citations:
            summary_lines.append(f"- Broken citations: {broken_citations}")
        parts.append("\n".join(summary_lines))

        # Contradicted pages
        contradicted: list[dict] = report.get("contradicted_pages", [])
        parts.append("\n**Contradicted Pages**")
        if contradicted:
            for item in contradicted:
                since = item.get("since", "")
                since_label = f"  (since {since})" if since else ""
                parts.append(f"- {item['slug']}{since_label}")
        else:
            parts.append("(none)")

        # Adversarial warnings
        warned: list[dict] = report.get("adversarial_warnings", [])
        parts.append("\n**Adversarial Warnings**")
        if warned:
            for item in warned:
                n = item.get("count", 0)
                label = "warning" if n == 1 else "warnings"
                parts.append(f"- [[{item['slug']}]]  ({n} {label})")
        else:
            parts.append("(none)")

        # Orphan pages
        orphan_slugs: list[str] = report.get("orphan_slugs", [])
        parts.append("\n**Orphan Pages**")
        if orphan_slugs:
            for slug in orphan_slugs:
                parts.append(f"- {slug}")
        else:
            parts.append("(none)")

        # Broken citations
        broken_citation_pages: list[dict] = report.get("broken_citation_pages", [])
        parts.append("\n**Broken Citations**")
        if broken_citation_pages:
            for item in broken_citation_pages:
                n = item.get("count", 0)
                label = "citation" if n == 1 else "citations"
                parts.append(f"- [[{item['slug']}]]  ({n} broken {label})")
        else:
            parts.append("(none)")

        text = "\n".join(parts)
        yield {"event": "token", "data": {"text": text}}
        yield {"event": "final_text", "data": {"text": text}}
