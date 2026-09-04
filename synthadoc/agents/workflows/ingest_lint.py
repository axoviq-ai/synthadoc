# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import functools
import re
from typing import Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_confirm,
    tool_find_page_source,
    tool_find_stale_pages,
    tool_get_page_states,
    tool_ingest_source,
    tool_run_lint,
)

_log = __import__("logging").getLogger(__name__)

_SYSTEM_PROMPT = """You are a wiki maintenance agent. You have these tools available:

find_stale_pages — list all stale wiki pages with their source file paths.
  Input: {}
  Output: {"pages": [{"slug": str, "source_path": str|null, "stale_since": str}]}

find_page_source — look up the source file path for any wiki page by slug,
  regardless of its current lifecycle state (active, draft, stale, etc.).
  Input: {"slug": str}
  Output: {"slug": str, "source_path": str} | {"error": str}

ingest_source — re-ingest one source file and return the outcome when the job finishes.
  Always force-processes the file even if it hasn't changed.
  Input: {"source_path": str}
  Output: {"status": "success"|"failed"|"timeout", "message": str, "job_id": str} | {"error": str}

run_lint — run a full wiki lint check and wait for it to complete.
  Input: {"scope": str (default "all")}
  Output: {"status": "success"|"failed"|"timeout", "message": str} | {"error": str}

get_page_states — return the current lifecycle state of one or more pages.
  Input: {"slugs": [str, ...]}
  Output: {"pages": [{"slug": str, "state": str}]}
  state is one of: "active", "stale", "draft", "archived", "unknown".
  Call this AFTER lint completes to confirm whether the re-ingest achieved its goal.

confirm — ask the user to confirm before proceeding.
  Input: {"message": str, "yes_label": str (default "Yes"), "no_label": str (default "No")}
  Output: {"confirmed": bool}
  If confirm returns {"confirmed": false}, respond with a brief plain-text message
  acknowledging the cancellation (use the word "cancelled") and stop.

Workflow A — re-ingest ALL stale pages:
1. Call find_stale_pages.
2. Call confirm IMMEDIATELY — list the pages in the message, ask whether to proceed.
   Use the confirm TOOL; never write plain text to ask (that exits the loop).
3. If confirmed, call ingest_source for each page with a valid source_path — one page
   at a time, waiting for each result before calling the next.
4. Call run_lint — MANDATORY even if one or more ingests failed. Blocks until done.
5. Call get_page_states with the slugs of every page you attempted to re-ingest.
6. Plain-text summary of every re-ingest outcome, the lint result (pass/fail), and
   a "Page states after re-ingest" section listing each slug with its current state.
   Use ✓ for active, ✗ for stale, and ○ for draft/archived/unknown.

Workflow B — re-ingest a SPECIFIC page by slug:
1. Call find_page_source(slug=<slug>) to get its source path.
2. Call confirm IMMEDIATELY — include the slug and path in the message.
   Use the confirm TOOL; never write plain text to ask (that exits the loop).
3. If confirmed, call ingest_source(source_path=<path>).
4. Call run_lint — MANDATORY regardless of whether the ingest succeeded. Blocks until done.
5. Call get_page_states(slugs=[<slug>]) to check the page's current lifecycle state.
6. Plain-text summary of the ingest result, the lint result (pass/fail), and the
   final page state. Use ✓ for active, ✗ for stale, ○ for draft/archived/unknown.

CRITICAL RULE: Steps 4→5 are REQUIRED after every confirmed ingest_source call.
You MUST call run_lint, then get_page_states — in that order — before
writing any plain-text response. Providing a summary without completing these two
steps is NOT allowed, even if earlier steps encountered errors.

Plain text ends the workflow — use it ONLY in the final summary step or when
confirm returns false. All intermediate steps must be tool calls, not plain text.

To call a tool, respond EXACTLY with this JSON and nothing else:
{"tool_call": {"name": "<tool_name>", "input": <input_dict>}}

When you have a final message for the user, respond with plain text only (no tool_call JSON).
"""


class IngestLintWorkflow(AgenticWorkflow):
    """Re-ingest stale pages (bulk) or any specific page by slug, then run lint."""

    NAME = "ingest-lint"
    DESCRIPTION = "Re-ingest stale pages (bulk) or any page by slug, then run lint."
    CLI_ARGS = "[--slug SLUG]  (omit to re-ingest all stale pages)"

    MATCH_RE = re.compile(
        r"\bstale\s+pages?\b"
        r"|\borchestrat"
        r"|\b(guided|agentic)\s+(maintenance\s+)?workflow\b"
        r"|\bre.?ingest\b.{0,60}\bstale\b|\bstale\b.{0,60}\bre.?ingest\b"
        r"|\bre.?ingest\b\s+the\s+[a-z0-9]",
        re.IGNORECASE,
    )

    # Confirm gate — Pattern B (declarative GATED_TOOLS).
    # ingest_source is gated: the framework requires a "confirm" call before
    # it will run and fires a fallback dialog if the LLM skips that step.
    # See broken_wikilinks.py for a detailed explanation of the pattern, or
    # AgenticWorkflow.GATED_TOOLS in _base.py for the full contract.
    GATED_TOOLS: frozenset[str] = frozenset({"ingest_source"})

    # CLI providers (claude-code, opencode) refuse to follow the JSON wire-format
    # tool-call loop in _SYSTEM_PROMPT — they correctly identify the
    # {"tool_call": ...} instruction pattern as a prompt injection attempt.
    # This workflow opts into a Python-driven alternative (run_for_cli_provider)
    # that drives Workflow A and Workflow B deterministically from Python,
    # with no LLM reasoning call required at all.  The same tool functions
    # (tool_find_stale_pages, tool_find_page_source, tool_ingest_source,
    # tool_run_lint, tool_get_page_states, tool_confirm) are reused directly
    # so behaviour is identical to what the system prompt instructs the LLM
    # to do on the Anthropic-API path.
    SUPPORTS_CLI_PROVIDER: bool = True

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        return user_input

    def get_tool_fns(self, ctx: WorkflowContext) -> dict[str, Callable[..., Awaitable[dict]]]:
        return {
            "find_stale_pages": functools.partial(tool_find_stale_pages, ctx),
            "find_page_source": functools.partial(tool_find_page_source, ctx),
            "ingest_source":    functools.partial(tool_ingest_source, ctx),
            "run_lint":         functools.partial(tool_run_lint, ctx),
            "get_page_states":  functools.partial(tool_get_page_states, ctx),
            "confirm":          functools.partial(tool_confirm, ctx),
        }

    # ── CLI provider path ─────────────────────────────────────────────────────

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: Python-driven Workflow A (all stale) or B (single slug).

        Why this path exists
        --------------------
        CLI providers (claude-code, opencode) receive the system prompt's JSON
        wire-format instruction block ({"tool_call": ...} protocol) and correctly
        flag it as a prompt injection attempt.  Rather than asking them to act as
        a subordinate LLM agent, this path drives the same two workflows directly
        from Python — no LLM reasoning call is needed because both workflows are
        fully deterministic: the fix algorithm is always "find stale pages → confirm
        → ingest each → run lint → check states".

        Workflow A (no --slug flag): mirrors system prompt §"Workflow A".
          1. tool_find_stale_pages  — discover what needs re-ingesting.
          2. tool_confirm           — show page list, wait for approval.
          3. tool_ingest_source     — one call per page (skips pages with no source).
          4. tool_run_lint          — MANDATORY regardless of individual ingest outcomes.
          5. tool_get_page_states   — verify final state of every attempted slug.
          6. Plain-text summary.

        Workflow B (--slug SLUG): mirrors system prompt §"Workflow B".
          1. tool_find_page_source  — look up source path for the slug.
          2. tool_confirm           — show slug + path, wait for approval.
          3. tool_ingest_source     — re-ingest the one page.
          4. tool_run_lint          — MANDATORY regardless of ingest outcome.
          5. tool_get_page_states   — verify final state of the slug.
          6. Plain-text summary.

        All tool functions are the same instances used by the multi-turn API path,
        so caching, queue handling, and SSE progress events work identically.
        The ``provider`` argument is accepted for interface compatibility but is
        unused — unlike ContradictionResolverWorkflow, no LLM rewrite call is needed.
        """
        # ── 1. Detect mode: explicit --slug flag OR natural language "re-ingest the <slug>" ──
        # The explicit flag is used by the workflow CLI and by users who know the convention.
        # The natural language fallback handles queries issued by the Graph UI
        # (e.g. "Re-ingest the alan-turing page") and matches the last arm of MATCH_RE
        # (r"\bre.?ingest\b\s+the\s+[a-z0-9]").  The API-provider path handles this
        # naturally via LLM understanding; the CLI path must parse it explicitly.
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        if not slug_match:
            # Capture slug token after "re-ingest the " — stops at space or "page" suffix.
            # Slug chars: lowercase letters, digits, hyphens, underscores.
            slug_match = re.search(
                r"\bre.?ingest\b\s+the\s+([a-z0-9][a-z0-9_-]*)",
                question,
                re.IGNORECASE,
            )
        page_slug: str | None = slug_match.group(1).lower() if slug_match else None

        # Accumulates ingest outcomes keyed by slug (status, message).
        # Pages with no source_path record {"status": "skipped"} instead of calling
        # tool_ingest_source, mirroring the LLM path's "valid source_path" guard.
        ingest_results: dict[str, dict] = {}
        attempted_slugs: list[str] = []

        if page_slug:
            # ── Workflow B: single page by slug ──────────────────────────────
            source_result = await tool_find_page_source(ctx, slug=page_slug)
            if "error" in source_result:
                msg = f"Cannot re-ingest '{page_slug}': {source_result['error']}"
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "final_text", "data": {"text": msg}}
                return

            source_path = source_result["source_path"]

            confirmed = await tool_confirm(
                ctx,
                f"Re-ingest page '{page_slug}'?\n  Source: {source_path}",
                yes_label="Re-ingest",
                no_label="Cancel",
            )
            if not confirmed.get("confirmed"):
                msg = "Cancelled — no pages were re-ingested."
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "final_text", "data": {"text": msg}}
                return

            ingest_results[page_slug] = await tool_ingest_source(ctx, source_path=source_path)
            attempted_slugs = [page_slug]

        else:
            # ── Workflow A: all stale pages ───────────────────────────────────
            scan = await tool_find_stale_pages(ctx)
            pages: list[dict] = scan.get("pages", [])

            if not pages:
                msg = "No stale pages found — nothing to re-ingest."
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "final_text", "data": {"text": msg}}
                return

            # Build confirm message that lists every page and its source path,
            # mirroring the system prompt §step 2 instruction ("list the pages
            # in the message").  Pages with no source_path are shown explicitly
            # so the user knows they will be skipped.
            confirm_lines: list[str] = [
                f"Found {len(pages)} stale page(s). Re-ingest all?\n",
            ]
            for p in pages:
                src = p.get("source_path") or "(no source path — will be skipped)"
                stale_since = p.get("stale_since", "")
                since_label = f"  stale since {stale_since}" if stale_since else ""
                confirm_lines.append(f"  • {p['slug']}: {src}{since_label}")

            confirmed = await tool_confirm(
                ctx,
                "\n".join(confirm_lines),
                yes_label="Re-ingest all",
                no_label="Cancel",
            )
            if not confirmed.get("confirmed"):
                msg = "Cancelled — no pages were re-ingested."
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "final_text", "data": {"text": msg}}
                return

            for p in pages:
                slug = p["slug"]
                source_path = p.get("source_path")
                attempted_slugs.append(slug)
                if not source_path:
                    # No source path recorded — skip without calling ingest.
                    # Matches the "valid source_path" guard in system prompt §step 3.
                    ingest_results[slug] = {
                        "status": "skipped",
                        "message": "no source_path recorded",
                    }
                else:
                    ingest_results[slug] = await tool_ingest_source(
                        ctx, source_path=source_path
                    )

        # ── Mandatory post-ingest sequence: lint → page states (both workflows) ──
        # System prompt marks steps 4-5 as REQUIRED after every confirmed ingest:
        # "Call run_lint — MANDATORY even if one or more ingests failed."
        lint_result = await tool_run_lint(ctx)
        states_result = await tool_get_page_states(ctx, slugs=attempted_slugs)
        state_map: dict[str, str] = {
            p["slug"]: p["state"] for p in states_result.get("pages", [])
        }

        # ── Summary (mirrors system prompt §step 6) ───────────────────────────
        # State icons from the system prompt: ✓ active, ✗ stale, ○ everything else.
        _ICON: dict[str, str] = {"active": "✓", "stale": "✗"}

        lint_status = lint_result.get("status", "unknown")
        lint_ok = lint_status == "success"

        mode_label = f"slug={page_slug}" if page_slug else "all stale pages"
        parts: list[str] = [f"**Ingest & Lint — Complete** ({mode_label})\n"]
        parts.append(
            f"{'✅' if lint_ok else '⚠'} Lint: {lint_status}"
            + (f" — {lint_result['message']}" if lint_result.get("message") else "")
        )
        parts.append("\n**Page states after re-ingest:**")
        for slug in attempted_slugs:
            result = ingest_results.get(slug, {})
            # tool_ingest_source may return {"error": msg} (validation/file-not-found)
            # rather than {"status": ...}; treat that as an error outcome so the
            # summary clearly signals the failure (and live tests can detect it).
            ingest_status = result.get("status") or ("error" if result.get("error") else "?")
            state = state_map.get(slug, "unknown")
            icon = _ICON.get(state, "○")
            if ingest_status == "skipped":
                parts.append(f"  ○ {slug} — skipped (no source path)")
            elif result.get("error"):
                parts.append(
                    f"  ✗ {slug}: error — {result['error']}"
                )
            else:
                parts.append(
                    f"  {icon} {slug}: ingest={ingest_status}, state={state}"
                )

        summary = "\n".join(parts)
        yield {"event": "token", "data": {"text": summary}}
        yield {"event": "final_text", "data": {"text": summary}}
