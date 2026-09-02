# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""ScaffoldWorkflow — regenerate core wiki scaffold files interactively."""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

_log = __import__("logging").getLogger(__name__)

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_get_scaffold_preview,
    tool_run_scaffold,
)

if TYPE_CHECKING:
    pass

_SYSTEM_PROMPT = """\
You are an agentic workflow executor for Synthadoc wiki maintenance.
Your task is to regenerate the wiki's core scaffold files for the configured domain.

Scaffold rewrites these files every run:
  - wiki/index.md      (categories, domain label, navigation structure)
  - wiki/purpose.md    (mission statement and scope)
  - AGENTS.md / CLAUDE.md / GEMINI.md  (agent coding guidelines)
  - ROUTING.md         (regenerated only if it already exists)

Content above the <!-- synthadoc:scaffold --> marker in index.md and purpose.md
is preserved — user-written sections above that line are never overwritten.

## Tool reference

### get_scaffold_preview
Read the configured domain and list the files that will be overwritten.
No arguments needed.
Input:  {}
Output: {"domain": str, "files_to_overwrite": [str]}

### run_scaffold
Enqueue a scaffold job for the given domain.  The tool automatically shows a
confirmation dialog to the user before writing any files; if the user declines
or the 120-second timeout fires, it returns {"status": "cancelled"} without
touching any files.
Input:  {"domain": str}
Output: {"status": "success", "domain": str, "categories_updated": int,
         "routing_regenerated": bool}
     or {"status": "cancelled", "message": str}
     or {"status": "failed"|"timeout", "message": str}
     or {"error": str}

## Tool-call wire format

Emit EXACTLY this JSON object (no markdown fences, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}

When you have no more tool calls to make, produce a plain-text summary (no JSON).

## Workflow steps

### Phase 1 — Preview
1. Call get_scaffold_preview (no arguments) to learn the domain and file list.

### Phase 2 — Run (confirmation is automatic)
2. Call run_scaffold with the domain returned in step 1.
   run_scaffold shows the user a confirmation dialog automatically before
   writing anything.
   - If status == "cancelled": write "Scaffold cancelled by user." and STOP.
   - If status == "failed" or "timeout": report the error message and STOP.
   - If "error" key present: report the error and STOP.

### Phase 3 — Report
3. Write a plain-text summary:
   - Domain scaffolded
   - Files written (list from get_scaffold_preview)
   - N pages updated with category labels (categories_updated)
   - Whether ROUTING.md was regenerated (routing_regenerated true/false)
   - A note on preservation: index.md has one <!-- synthadoc:scaffold --> marker
     below the title — content above it was preserved. purpose.md has one marker
     per section — each section's user-written content above the marker was kept.
"""


class ScaffoldWorkflow(AgenticWorkflow):
    """Regenerate core wiki scaffold files with a confirm gate before running."""

    NAME = "scaffold"
    DESCRIPTION = "Regenerate core wiki scaffold files (confirm gate before writing)."

    MATCH_RE = re.compile(
        r"^(please\s+)?\brun\b.{0,20}\bscaffold\b"
        r"|^(can|could|would)\s+(you\s+)?(please\s+)?\brun\b.{0,20}\bscaffold\b"
        r"|\b(?:rebuild|regenerate)\b.{0,20}\bscaffold\b",
        re.IGNORECASE,
    )

    # Confirm gate — Pattern A (embedded inside tool_run_scaffold).
    #
    # tool_run_scaffold calls tool_confirm internally — it builds the confirm
    # message from the domain and file list before enqueueing any job.  This
    # means no separate "confirm" tool is needed in the LLM registry, and
    # GATED_TOOLS is left empty (the base-class default).
    #
    # Choose Pattern A when the confirm message is built programmatically.
    # Choose Pattern B (GATED_TOOLS) when the LLM builds the message from
    # scan results — broken_wikilinks.py shows Pattern B with full comments.
    GATED_TOOLS: frozenset[str] = frozenset()

    # CLI providers (claude-code, opencode) refuse the JSON wire-format
    # tool-call loop in _SYSTEM_PROMPT — they correctly identify the
    # {"tool_call": ...} instruction pattern as a prompt injection attempt.
    # This workflow opts into a Python-driven alternative (run_for_cli_provider)
    # that drives the same two-phase sequence directly from Python.
    # No LLM reasoning call is needed because the workflow is fully deterministic:
    # get preview → run scaffold (with embedded confirm) → format summary.
    # Pattern A confirm is preserved — it is embedded inside tool_run_scaffold
    # itself, so the CLI path gets the same user-approval gate for free.
    # The same tool functions (tool_get_scaffold_preview, tool_run_scaffold) are
    # reused directly so behaviour is identical to the Anthropic-API path.
    SUPPORTS_CLI_PROVIDER: bool = True

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "get_scaffold_preview": functools.partial(tool_get_scaffold_preview, ctx),
            "run_scaffold":         functools.partial(tool_run_scaffold, ctx),
        }

    # ── CLI provider path ─────────────────────────────────────────────────────

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: Python-driven scaffold (Pattern A confirm, no LLM).

        Why this path exists
        --------------------
        CLI providers (claude-code, opencode) receive the system prompt's JSON
        wire-format instruction block ({"tool_call": ...} protocol) and correctly
        flag it as a prompt injection attempt.  Rather than asking them to act as
        a subordinate LLM agent, this path drives the same two-phase sequence
        directly from Python.

        No LLM reasoning call is needed because this workflow is fully
        deterministic.  The Pattern A confirm gate is preserved — it is embedded
        inside tool_run_scaffold itself (not a separate "confirm" tool call), so
        the CLI path gets the same user-approval flow as the API path for free.

        Phases (mirrors system prompt §phases 1-3)
        -------------------------------------------
        Phase 1 — Preview:
          tool_get_scaffold_preview  — read domain and list of files to overwrite.

        Phase 2 — Run (Pattern A confirm embedded inside the tool):
          tool_run_scaffold(domain)  — shows a confirm_request SSE to the client;
          if the user declines or the 120-second timeout fires, returns
          {"status": "cancelled"} without touching any files.

        Phase 3 — Report:
          Format a plain-text summary following the system prompt §phase 3 layout.

        The ``provider`` and ``question`` arguments are accepted for interface
        compatibility but are unused — no LLM call is needed.
        """
        # ── Phase 1: preview ──────────────────────────────────────────────────
        preview = await tool_get_scaffold_preview(ctx)
        domain: str = preview.get("domain", "General")
        files_to_overwrite: list[str] = preview.get("files_to_overwrite", [])

        # ── Phase 2: run scaffold (Pattern A confirm is inside the tool) ──────
        result = await tool_run_scaffold(ctx, domain=domain)
        status: str = result.get("status", "")

        if status == "cancelled":
            # Use a standardised cancellation phrase instead of the tool's
            # internal "User declined." / "Confirmation timed out." strings.
            msg = "Scaffold cancelled by user."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        if status in ("failed", "timeout") or result.get("error"):
            msg = (
                f"Scaffold failed: "
                f"{result.get('error') or result.get('message', 'unknown error')}"
            )
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── Phase 3: report (mirrors system prompt §phase 3) ──────────────────
        categories_updated: int = result.get("categories_updated", 0)
        routing_regenerated: bool = result.get("routing_regenerated", False)

        parts: list[str] = [f"**Scaffold — Complete** (domain: {domain})\n"]
        parts.append(f"Domain: {domain}")

        if files_to_overwrite:
            file_lines = "\n".join(f"  • {f}" for f in files_to_overwrite)
            parts.append(f"Files written:\n{file_lines}")
        else:
            parts.append("Files written: (none)")

        cat_label = "page" if categories_updated == 1 else "pages"
        parts.append(
            f"Pages updated with category labels: {categories_updated} {cat_label}"
        )
        routing_label = "Yes" if routing_regenerated else "No"
        parts.append(f"ROUTING.md regenerated: {routing_label}")
        parts.append(
            "\nPreservation note: Content above the <!-- synthadoc:scaffold --> "
            "marker in index.md and purpose.md was preserved — user-written "
            "sections above that line were not overwritten."
        )

        text = "\n".join(parts)
        yield {"event": "token", "data": {"text": text}}
        yield {"event": "final_text", "data": {"text": text}}
