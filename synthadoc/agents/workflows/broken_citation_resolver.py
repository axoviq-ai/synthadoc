# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""BrokenCitationResolverWorkflow — agentic closed-loop fix for broken ^[file:L-L] citation markers.

Scans active wiki pages for broken, malformed, or out-of-range source citations.
Proposes targeted fixes per page with fuzzy source-name matching and validates
each fix with a re-scan. Loops until all citations are clean or escalates
unresolvable cases.
"""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Awaitable, Callable

from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext
from synthadoc.agents.workflows._tools import (
    tool_apply_citation_fixes,
    tool_confirm,
    tool_find_broken_citations,
    tool_get_wiki_status,
    tool_notify,
)

if TYPE_CHECKING:
    pass

# Fuzzy-match cutoff for broken_ref citations — defined once so both the
# system prompt (§STEP 4a) and the CLI-provider path use the identical value.
_FUZZY_MATCH_CUTOFF = 0.72

# _SYSTEM_PROMPT embeds _FUZZY_MATCH_CUTOFF via .replace() so the value
# stays in sync with the Python implementation automatically.
_SYSTEM_PROMPT = """\
You are an agentic workflow executor for Synthadoc wiki maintenance.
Your task is to scan all active wiki pages for broken ^[file:L-L] source citation
markers and fix them interactively.

Three failure reasons you will encounter:
- broken_ref: the citation filename is not listed in the page's sources[].
- malformed: the marker syntax is invalid (e.g. missing line numbers, start > end).
- out_of_range: the line_end exceeds the actual length of the extracted source file.

Only ACTIVE pages are scanned. Stale, draft, and archived pages are excluded.

━━━ TOOL-CALL WIRE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Emit EXACTLY this JSON object (no markdown fences, no XML, no prose) to call a tool:
{"tool_call": {"name": "<tool_name>", "input": {<args>}}}
When delivering a final message for the user, respond with plain text only (no JSON).

━━━ TOOL INVENTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

find_broken_citations
  Scan active pages for broken ^[file:L-L] markers.
  Input:  {"page_slug": str}   — single-page re-verification after a fix
       OR {}                   — full-wiki scan
  Output: {
    "pages": [{"slug": str, "title": str|null,
               "issues": [{"citation": str, "reason": "broken_ref"|"malformed"|"out_of_range"}],
               "page_sources": [str]}],
    "total_issues": int,
    "scanned": int
  }

apply_citation_fixes
  Apply citation marker patches to a single page. One call per page.
  The confirm gate fires automatically before the first write.
  Input:  {"page_slug": str,
           "fixes": [{"old_citation": str, "new_citation": str|null}]}
  Output: {"status": "success"|"error", "changes": int, "page": str}
  Note: new_citation=null removes the marker; surrounding prose is preserved.
  Check result["status"] — on error, result["error"] contains the reason.

confirm
  Send a confirmation card to the UI and wait up to 120 seconds.
  Input:  {"message": str, "yes_label": str, "no_label": str}
  Output: {"confirmed": bool}

notify
  Send a non-blocking notice (does NOT terminate the workflow).
  Input:  {"message": str, "level": "info"|"warning"|"error"}
  Output: {"sent": true}

get_wiki_status
  Return live lifecycle counts for all user pages. Call this FIRST in STEP 5
  before any plain-text output.
  Output: {"active": int, "draft": int, "stale": int, "contradicted": int, "archived": int}

━━━ SINGLE-PAGE MODE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When the initial message specifies a page_slug, operate in single-page mode:
- Call find_broken_citations EXACTLY ONCE with that page_slug.
- If total_issues == 0: respond "No broken citations found on '<slug>'." STOP.
- Do NOT call find_broken_citations without a page_slug in single-page mode.
- Do NOT scan the whole wiki.
- STEP 5 summary covers only the specified page.
All other steps (STEP 3-5) apply normally for that one page.

━━━ WORKFLOW STEPS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Discover (full-wiki mode only; skip if a page_slug was given)
  Call find_broken_citations (no arguments) for a full-wiki scan.

STEP 2 — Check for work
  If total_issues == 0: respond with plain text
  "No broken citations found — all ^[file:L-L] markers are valid."
  DO NOT call any more tools.

STEP 3 — Report and confirm
  ⚠ Do NOT output any plain text here. Plain text ends the workflow.
  Call confirm with a summary listing each affected page and its issues:
  "Found <N> broken citation(s) across <M> page(s). Fix them now?

  <page-slug> (<N> issue(s)):
    - ^[old.txt:1-5] — broken_ref (file not in sources)
    - ^[bio.txt] — malformed (invalid syntax)
    ..."

STEP 4 — Per-page fix loop
  For each page from STEP 1 (in the order returned):

  4a. Propose fixes for EACH issue on this page, using this strategy:
      broken_ref: Use difflib.get_close_matches(citation_filename, page_sources, n=1, cutoff=$$FUZZY_CUTOFF$$).
                  If a match is found: propose corrected marker with matched filename; keep same line range.
                  new_citation = "^[matched_filename:start-end]"
                  If no match: propose removal. new_citation = null.
      malformed:  Propose removal. new_citation = null.
      out_of_range: Propose removal. new_citation = null.
                  (Line-range clamping is unsafe without reading the source; removal is the safe default.)

  4b. Call apply_citation_fixes with the proposed fixes for this page.
      The confirm gate fires automatically before the first write — you do not need
      to call confirm yourself before apply_citation_fixes.

  4c. Call find_broken_citations(page_slug=<slug>) to re-verify this page.
      If issues remain and attempt_number < 3:
        - broken_ref on retry: fall back to removal (new_citation=null).
        - Other: diagnose and retry with corrected fixes.
      If attempt_number == 3 and issues remain:
        Call notify(level="warning", message="<slug>: unable to resolve <N> citation(s) after 3 attempts — <diagnosis>")
        Add slug to "unresolved" list and continue to next page.

  4d. Between pages: call confirm("Continue to next page (<next-slug>)?", yes_label="Continue", no_label="Stop")
      If not confirmed: stop. Treat remaining pages as skipped.

STEP 5 — Final summary
  ⚠ Do NOT output any plain text yet.
  FIRST call get_wiki_status() — this fetches live lifecycle counts.
  THEN call find_broken_citations() to get current broken citation count.
  THEN output a single plain-text summary.

  For every citation you fixed or removed, include the before/after detail
  so the user knows exactly what changed and why.  Use this format:

  "Broken Citation Resolver — Complete

  ✅ Fixed (<N> pages):
    - <slug>:
        • ^[old-filename.txt:1-5] (broken_ref — not in sources)
          → renamed to ^[correct-filename.txt:1-5]
        • ^[bad.txt] (malformed — missing line range)
          → removed
    ...
  ⚠ Unresolved (<N> pages):
    - <slug>: <citation> — <reason>; <diagnosis of why no fix was possible>
    ...
  ⏭ Skipped (<N> pages):
    - <slug>
    ...

  Wiki: <active> active, <stale> stale, <contradicted> contradicted
  Remaining broken citations: <N>"

  Rules for the per-citation lines:
  - Show the original broken marker and its reason in parentheses.
  - For a rename: show the new marker after "→ renamed to".
  - For a removal: show "→ removed" and state why (malformed / no close match).
  - Never omit citations from the summary — every issue from STEP 1 must appear.

━━━ CRITICAL RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ALWAYS call get_wiki_status() before outputting the STEP 5 summary.
2. NEVER output plain text while work remains (steps 3 or 4) — plain text ends the workflow.
3. Call apply_citation_fixes for EVERY page with issues after the gate is open.
4. new_citation=null is a valid, required action for malformed and out_of_range issues.
   Skipping apply_citation_fixes because no fuzzy match was found is WRONG — use null.
5. Re-verification (step 4c) uses find_broken_citations(page_slug=slug), not run_lint.
""".replace("$$FUZZY_CUTOFF$$", str(_FUZZY_MATCH_CUTOFF))


class BrokenCitationResolverWorkflow(AgenticWorkflow):
    """Scan active wiki pages for broken ^[file:L-L] source citations and fix them."""

    NAME = "broken-citation-resolver"
    DESCRIPTION = (
        "Scan active wiki pages for broken ^[file:L-L] source citation markers "
        "(broken_ref / malformed / out_of_range) and fix them interactively."
    )

    MATCH_RE = re.compile(
        r"\bbroken\b.{0,25}\bcitations?\b"
        r"|\bcitations?\b.{0,25}\bbroken\b"
        r"|\bfix\b.{0,25}\bcitations?\b"
        r"|\bcitation.{0,10}resolver\b"
        r"|\bbroken.{0,10}ref\b"
        r"|\bmalformed.{0,10}citations?\b",
        re.IGNORECASE,
    )

    # Pattern B confirm gate: the gate wraps apply_citation_fixes so it
    # requires user approval before the first write.
    GATED_TOOLS: frozenset[str] = frozenset({"apply_citation_fixes"})

    # CLI providers (claude-code, opencode) cannot follow the JSON wire-format
    # tool-call loop.  This workflow opts into a Python-driven alternative that
    # uses difflib fuzzy matching to compute fixes deterministically — no LLM
    # reasoning call required — and then asks for user confirmation before writing.
    SUPPORTS_CLI_PROVIDER: bool = True

    async def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_initial_message(self, user_input: str) -> str:
        slug_match = re.search(r"--slug\s+(\S+)", user_input, re.IGNORECASE)
        if slug_match:
            slug = slug_match.group(1)
            return (
                f"Scan for broken citation markers.\n"
                f"⚠ SINGLE-PAGE MODE: check ONLY the '{slug}' page.\n"
                f"Call find_broken_citations with page_slug='{slug}'.\n"
                f"If total_issues == 0, respond with plain text and STOP — "
                f"do NOT call find_broken_citations without a page_slug."
            )
        return user_input

    def get_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        p = functools.partial
        return {
            "find_broken_citations": p(tool_find_broken_citations, ctx),
            "apply_citation_fixes":  p(tool_apply_citation_fixes, ctx),
            "confirm":               p(tool_confirm, ctx),
            "notify":                p(tool_notify, ctx),
            "get_wiki_status":       p(tool_get_wiki_status, ctx),
        }

    def get_tool_budget(self) -> int:
        # Full-wiki scan + per-page: up to 3 fix attempts + 1 re-verify + 1 confirm = 5 calls/page
        # + 3 setup calls + final 2 calls = 5N + 5. At 10 pages: 55 → budget 60.
        return 60

    async def run_for_cli_provider(self, ctx, question, provider):
        """CLI-provider path: pure Python gather → confirm → execute.

        Mirrors the STEP 1-5 algorithm from the system prompt but uses
        difflib.get_close_matches directly so no LLM reasoning call is needed.
        Reuses the same tool functions as the normal loop — tool_find_broken_citations,
        tool_confirm, tool_apply_citation_fixes — to stay consistent with the
        API-provider path.

        Fix algorithm (mirrors system prompt §STEP 4a):
          broken_ref  → difflib.get_close_matches(filename, page_sources, n=1, cutoff=0.72)
                        Matched  : rename to matched filename, keep same line range.
                        No match : remove (new_citation=None).
          malformed   → remove (new_citation=None)
          out_of_range→ remove (new_citation=None)
        """
        import difflib as _difflib

        # ── 1. Gather ─────────────────────────────────────────────────────────
        slug_match = re.search(r"--slug\s+(\S+)", question, re.IGNORECASE)
        page_slug = slug_match.group(1) if slug_match else None

        scan = await tool_find_broken_citations(ctx, page_slug=page_slug)
        pages: list[dict] = scan.get("pages", [])
        total: int = scan.get("total_issues", 0)

        if total == 0:
            scope = f"on '{page_slug}'" if page_slug else "— all ^[file:L-L] markers are valid"
            msg = f"No broken citations found {scope}."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 2. Compute fixes (deterministic) ──────────────────────────────────
        decisions: list[dict] = []

        for p in pages:
            slug = p["slug"]
            sources: list[str] = p.get("page_sources", [])
            issues: list[dict] = p.get("issues", [])
            fixes: list[dict] = []

            for iss in issues:
                citation: str = iss["citation"]   # e.g. "^[wrong.txt:1-5]"
                reason: str = iss["reason"]

                if reason == "broken_ref":
                    # Extract filename: "^[fname:start-end]" → "fname"
                    inner = citation.lstrip("^").lstrip("[").rstrip("]")
                    fname = inner.split(":")[0]
                    matches = _difflib.get_close_matches(fname, sources, n=1, cutoff=_FUZZY_MATCH_CUTOFF)
                    if matches:
                        # Keep the same line range, replace only the filename
                        colon_idx = citation.index(":", len("^["))
                        bracket_end = citation.rindex("]")
                        line_range = citation[colon_idx + 1 : bracket_end]
                        new_citation: str | None = f"^[{matches[0]}:{line_range}]"
                    else:
                        new_citation = None   # no close match → remove
                else:
                    # malformed or out_of_range → always remove
                    new_citation = None

                fixes.append({"old_citation": citation, "new_citation": new_citation})

            if fixes:
                decisions.append({"slug": slug, "fixes": fixes})

        # ── 3. Confirm ────────────────────────────────────────────────────────
        n_pages = len(decisions)
        n_fixes = sum(len(d["fixes"]) for d in decisions)
        confirm_lines: list[str] = [
            f"Found {total} broken citation(s) across {len(pages)} page(s). "
            f"Proposed {n_fixes} fix(es) on {n_pages} page(s):\n",
        ]
        for item in decisions:
            confirm_lines.append(f"{item['slug']}:")
            for fix in item["fixes"]:
                action = f"→ {fix['new_citation']}" if fix["new_citation"] else "→ removed"
                confirm_lines.append(f"  {fix['old_citation']}  {action}")

        confirmed = await tool_confirm(
            ctx,
            "\n".join(confirm_lines),
            yes_label="Apply fixes",
            no_label="Cancel",
        )
        if not confirmed.get("confirmed"):
            msg = "Cancelled — no citations were modified."
            yield {"event": "token", "data": {"text": msg}}
            yield {"event": "final_text", "data": {"text": msg}}
            return

        # ── 4. Execute ────────────────────────────────────────────────────────
        fixed: list[tuple[str, list[dict]]] = []
        failed: list[tuple[str, str]] = []

        for item in decisions:
            slug = item["slug"]
            await ctx.send_sse_event(
                "tool_progress",
                {"tool": "apply_citation_fixes", "message": f"Fixing {slug}..."},
            )
            result = await tool_apply_citation_fixes(ctx, page_slug=slug, fixes=item["fixes"])
            if result.get("status") == "success":
                fixed.append((slug, item["fixes"]))
            else:
                failed.append((slug, result.get("error") or "unknown error"))

        # ── 5. Summary (mirrors system prompt §STEP 5) ────────────────────────
        # Call get_wiki_status first — same requirement as the multi-turn path.
        wiki_status = await tool_get_wiki_status(ctx)

        parts: list[str] = ["**Broken Citation Resolver — Complete**\n"]

        if fixed:
            parts.append(f"✅ Fixed ({len(fixed)} page(s)):")
            for slug, fixes in fixed:
                parts.append(f"  - {slug}:")
                for fix in fixes:
                    old = fix["old_citation"]
                    new = fix["new_citation"]
                    parts.append(f"      {old}  →  {new if new else 'removed'}")

        if failed:
            parts.append(f"\n⚠ Failed ({len(failed)} page(s)):")
            for slug, err in failed:
                parts.append(f"  - {slug}: {err}")

        if not fixed and not failed:
            parts.append("No changes were applied.")

        # Wiki status counts — same footer as the multi-turn path's STEP 5 summary.
        status_str = ", ".join(f"{k}: {v}" for k, v in wiki_status.items()
                               if k not in ("tool", "message"))
        parts.append(f"\nWiki: {status_str}")

        summary = "\n".join(parts)
        yield {"event": "token", "data": {"text": summary}}
        yield {"event": "final_text", "data": {"text": summary}}
