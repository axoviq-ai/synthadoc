# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

SseEventFn = Callable[[str, dict], Awaitable[None]]

# ---------------------------------------------------------------------------
# Confirm-gate helpers — used by AgenticWorkflow.build_guarded_tool_fns
# ---------------------------------------------------------------------------

def _make_confirm_gatekeeper(
    original_fn: "Callable[..., Awaitable[dict]]",
    gate_open: "list[bool]",
) -> "Callable[..., Awaitable[dict]]":
    """Wrap a 'confirm' tool so that approval opens the session gate."""
    async def _wrapped(*args: object, **kwargs: object) -> dict:
        result: dict = await original_fn(*args, **kwargs)  # type: ignore[misc]
        if result.get("confirmed"):
            gate_open[0] = True
        return result
    return _wrapped


_DIFF_EXCERPT_LEN = 400  # chars shown per BEFORE / AFTER block


def _build_fallback_confirm_message(
    tool_name: str,
    slug: str,
    issues: list,
    new_content: str,
    ctx: "WorkflowContext",
) -> str:
    """Build an informative fallback confirm message with a before/after diff.

    Shown when a gated tool is called before the LLM has called ``confirm``.
    Extracts the current page content from the store so the user can review
    what will change, even when the LLM skipped the explicit confirm step.
    """
    if not slug:
        return (
            f"Run `{tool_name}`?\n\n"
            "(Tip: call `confirm` with a detailed diff first.)"
        )

    # Try to read current content for the before side of the diff.
    current_content: str | None = None  # None = store unavailable; "" = page empty
    if ctx.store is not None:
        try:
            page = ctx.store.read_page(slug)
            if page is not None:
                current_content = page.content  # may be "" for template pages
        except Exception:
            pass  # store error — fall through to show what we have

    # Build the issues line (e.g. "duplicate_section ×2, thin_section ×1").
    issues_line = ""
    if issues:
        issues_line = f"\nIssues: {', '.join(str(i) for i in issues)}"

    def _excerpt(text: str, label: str) -> str:
        excerpt = text[:_DIFF_EXCERPT_LEN]
        if len(text) > _DIFF_EXCERPT_LEN:
            excerpt += f"\n… ({len(text) - _DIFF_EXCERPT_LEN} more chars)"
        return f"**{label}:**\n```\n{excerpt}\n```"

    # Both sides available and content actually changed → BEFORE / AFTER.
    if current_content and new_content and current_content.strip() != new_content.strip():
        return (
            f"**{slug}** — apply content-health fix?{issues_line}\n\n"
            f"{_excerpt(current_content, 'BEFORE')}\n\n"
            f"{_excerpt(new_content, 'AFTER')}"
        )

    # LLM returned the same content — nothing would change.
    if current_content and new_content and current_content.strip() == new_content.strip():
        return (
            f"**{slug}** — no changes detected.{issues_line}\n\n"
            "The proposed content is identical to the current page.\n"
            "Proceed only if you want a snapshot recorded with no actual edits.\n\n"
            f"{_excerpt(current_content, 'CURRENT CONTENT')}"
        )

    # Current page has no body content — LLM is about to write from scratch.
    if current_content is not None and not current_content and new_content:
        return (
            f"**{slug}** — ⚠️ page currently has no content.{issues_line}\n\n"
            "The LLM generated new content from scratch (the existing page body is empty). "
            "Review carefully before proceeding.\n\n"
            f"{_excerpt(new_content, 'PROPOSED CONTENT')}"
        )

    # Store unavailable or read failed — show only proposed content.
    if new_content:
        return (
            f"**{slug}** — apply content-health fix?{issues_line}\n\n"
            "(Current content could not be read — showing proposed content only.)\n\n"
            f"{_excerpt(new_content, 'PROPOSED CONTENT')}"
        )

    return (
        f"Run `{tool_name}` on **{slug}**?{issues_line}\n\n"
        "(Tip: call `confirm` with a side-by-side diff first.)"
    )


def _make_gated_tool(
    original_fn: "Callable[..., Awaitable[dict]]",
    tool_name: str,
    gate_open: "list[bool]",
    ctx: "WorkflowContext",
    *,
    reset_after_call: bool = False,
) -> "Callable[..., Awaitable[dict]]":
    """Wrap a gated tool to fire a fallback confirm when the gate is not open.

    The fallback fires only if the LLM calls this tool before the session's
    ``confirm`` tool has been called and approved.  Once the gate is open —
    either via the explicit confirm tool or via this fallback — subsequent
    calls to the same tool run without an extra dialog, unless
    ``reset_after_call=True``, in which case the gate is reset to closed after
    each successful call so that every invocation requires a fresh confirm.
    Use ``reset_after_call=True`` for per-item write tools (e.g. one confirm
    per wiki page) and the default for bulk-approve workflows.
    """
    async def _wrapped(*args: object, **kwargs: object) -> dict:
        if not gate_open[0]:
            # Deferred import to avoid circular dependency (_tools imports _base).
            from synthadoc.agents.workflows._tools import (  # noqa: PLC0415
                tool_confirm as _tool_confirm,
            )
            # Build an informative fallback message using available call context.
            slug: str = kwargs.get("slug", args[0] if args else "")  # type: ignore[assignment]
            issues: list = kwargs.get("issues_fixed", [])  # type: ignore[assignment]
            new_content: str = kwargs.get("content", "")  # type: ignore[assignment]
            detail = _build_fallback_confirm_message(tool_name, slug, issues, new_content, ctx)
            fallback = await _tool_confirm(ctx, detail, yes_label="Proceed", no_label="Cancel")
            if not fallback.get("confirmed"):
                return {
                    "status": "cancelled",
                    "message": f"`{tool_name}` cancelled by user.",
                }
            gate_open[0] = True
        result: dict = await original_fn(*args, **kwargs)  # type: ignore[misc]
        if reset_after_call:
            gate_open[0] = False
        return result
    return _wrapped


@dataclass
class WorkflowContext:
    """Runtime context threaded through every agentic workflow."""

    session_id: str
    wiki_root: Path
    queue: "JobQueue | None"  # type: ignore[name-defined]
    store: "WikiStorage | None"  # type: ignore[name-defined]
    audit_db: "AuditDB | None"  # type: ignore[name-defined]
    send_sse_event: SseEventFn
    confirm_registry: dict[str, asyncio.Event]
    confirm_result_registry: dict[str, bool]
    domain: str = ""
    # Cache-invalidation hooks wired up by ActionAgent from the orchestrator.
    # None in tests that don't need cache coherence.
    bump_epoch: "Callable[[], None] | None" = None
    invalidate_search: "Callable[[], None] | None" = None
    # BM25/vector search instance — used by tool_search_orphan_candidates.
    # None in tests that don't need search access.
    search: "HybridSearch | None" = None  # type: ignore[name-defined]
    # True when the active provider is a CodingToolCLIProvider (opencode, claude-code).
    # Used by cost-estimate tools to substitute "Covered by coding tool subscription"
    # for the dollar figure — CLI providers bill via their own subscription, not per-token.
    is_cli_provider: bool = False

    def cost_label(self, usd: float) -> str:
        """Human-readable cost string for a workflow estimate.

        CLI providers (opencode, claude-code) bill via their own subscription,
        so a per-token dollar figure would be misleading.
        """
        if self.is_cli_provider:
            return "Covered by coding tool subscription"
        return f"~${usd:.2f}"


class AgenticWorkflow(ABC):
    """Abstract base class for all agentic workflows.

    Optional class attribute — set on subclasses that need fast-path routing:

        MATCH_RE = re.compile(r"...", re.IGNORECASE)

    When set, ActionAgent's run_gen checks this pattern before calling the LLM
    and routes directly to this workflow on a match.  Workflows without MATCH_RE
    are reached only via LLM intent extraction.
    """

    MATCH_RE: re.Pattern | None = None

    # Set on subclasses that register with the CLI registry.
    # ``NAME`` is the ``--name`` value for ``synthadoc workflow run``.
    # ``DESCRIPTION`` is shown by ``synthadoc workflow list``.
    # ``CLI_ARGS`` is a compact one-line summary of workflow-specific extra
    # arguments forwarded after ``--name NAME`` (e.g. ``[--slug SLUG]``).
    # Leave None for workflows that take no extra arguments.
    NAME: str | None = None
    DESCRIPTION: str | None = None
    CLI_ARGS: str | None = None

    # Hint chip text shown to the user when the workflow ends with incomplete work
    # (budget exhausted, or final summary has skipped / unresolved items).
    # The chip text must match MATCH_RE so clicking it re-triggers the workflow.
    # Leave None for workflows that do not need a "continue" chip.
    RERUN_HINT: str | None = None

    # Declare the names of tools that must not run without prior user approval.
    #
    # ── When to use this (Pattern B) vs. embedding confirm in the tool (Pattern A) ──
    #
    # Pattern A — embed confirm inside the tool function
    #   Use when: the tool itself can compose a concrete, informative confirm
    #   message without any LLM help (e.g. it already holds the list of files
    #   it's about to overwrite).
    #   How: call ``await tool_confirm(ctx, message=...)`` inside the dangerous
    #   tool function.  Leave GATED_TOOLS = frozenset() (the default).
    #   Example: ScaffoldWorkflow / tool_run_scaffold in _tools.py.
    #
    # Pattern B — declarative GATED_TOOLS (this attribute)  ← use this by default
    #   Use when: the confirm message should include data the LLM gathered via
    #   earlier tool calls (e.g. "Found 7 broken links on pages A, B, C").
    #   How:
    #     1. Return a "confirm" entry in get_tool_fns (functools.partial is fine).
    #     2. Declare GATED_TOOLS = frozenset({"my_write_tool"}).
    #   The framework (build_guarded_tool_fns below) then:
    #     • Wraps "confirm" so that confirmed=True opens the session gate.
    #     • Wraps each GATED_TOOLS entry so it fires a fallback dialog if the
    #       LLM skips the confirm step — no write ever happens without approval.
    #     • Once the gate is open, subsequent calls to gated tools run directly.
    #   Examples: BrokenWikilinksWorkflow, IngestLintWorkflow, OrphanResolverWorkflow.
    #
    # Read-only workflows (no wiki writes) do not override this attribute at all —
    # the empty default below is the correct value and build_guarded_tool_fns
    # becomes a no-op when it is empty.
    #
    # See _registry.py module docstring for a summary of both patterns.
    GATED_TOOLS: frozenset[str] = frozenset()  # override only for write workflows

    # Subset of GATED_TOOLS whose gate resets after each successful call,
    # requiring a fresh confirm before every invocation.  Use this for
    # per-item write tools where each change needs individual user approval
    # (e.g. one confirm per wiki page).  Leave empty for bulk-approve
    # workflows where a single opening confirm covers the whole batch.
    GATED_TOOLS_PER_CALL: frozenset[str] = frozenset()

    # Set to True in subclasses that provide a CLI-provider alternative path.
    #
    # Coding-tool CLI providers (claude-code, opencode) are themselves agents
    # with their own identity, tool-calling mechanism, and safety reasoning.
    # They refuse Synthadoc's JSON wire-format tool-call loop as prompt
    # injection.  Workflows that set this flag implement ``run_for_cli_provider``
    # with a deterministic Python-driven gather → execute-with-confirm pattern
    # that avoids fake tools and identity-redefinition entirely.
    #
    # Defaults to False.  Override to True only when ``run_for_cli_provider``
    # is also implemented — ActionAgent checks this flag at runtime.
    SUPPORTS_CLI_PROVIDER: bool = False

    async def run_for_cli_provider(
        self,
        ctx: "WorkflowContext",
        question: str,
        provider: "LLMProvider",  # type: ignore[name-defined]
    ):
        """CLI-provider alternative to the JSON wire-format tool-call loop.

        Called by ActionAgent._run_orchestrate when the configured provider is
        a CodingToolCLIProvider and SUPPORTS_CLI_PROVIDER is True.

        Pattern: Python gathers data and computes fixes deterministically →
        user confirms → Python executes.  Avoids fake tools and identity
        redefinition — the LLM is never asked to pretend to be a different agent.

        This is an async generator — yield SSE event dicts in the same shape as
        the tool-call loop (``{"event": "token", ...}``,
        ``{"event": "tool_progress", ...}``, ``{"event": "final_text", ...}``).

        Subclasses MUST override this method when SUPPORTS_CLI_PROVIDER is True.
        The ``provider`` parameter is available for subclasses that need a single
        factual LLM call (e.g. for summarisation); most implementations will not
        use it.
        """
        raise NotImplementedError(
            f"{type(self).__name__} sets SUPPORTS_CLI_PROVIDER=True "
            "but does not implement run_for_cli_provider()."
        )
        # Make this an async generator — the yield is unreachable at runtime but
        # required so Python treats the coroutine as an async generator (PEP 525).
        if False:  # pragma: no cover
            yield {}  # type: ignore[misc]

    @abstractmethod
    async def build_system_prompt(self) -> str:
        """Return the system prompt for the LLM."""
        ...

    @abstractmethod
    def build_initial_message(self, user_input: str) -> str:
        """Return the first user message sent to the LLM."""
        ...

    @abstractmethod
    def get_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        """Return a mapping of tool name → async callable for this workflow.

        Return plain callables (``functools.partial`` is idiomatic).  Do NOT add
        confirm-gate wrappers here — use Pattern B (declare GATED_TOOLS + include
        a ``"confirm"`` entry) and the framework wires up the protection via
        ``build_guarded_tool_fns``.  See the GATED_TOOLS docstring for when to
        choose Pattern A (embed confirm inside the tool) instead.
        """
        ...

    def build_guarded_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        """Return the tool registry with confirm-gate wrappers applied.

        Called by ActionAgent instead of get_tool_fns.  If GATED_TOOLS is
        empty the result is identical to get_tool_fns(ctx).  Otherwise:

        - The "confirm" tool (if present) is wrapped so that a confirmed=True
          response opens the session gate.
        - Each tool in GATED_TOOLS is wrapped so that it fires a fallback
          confirm dialog when the gate is still closed at call time.
        """
        fns = self.get_tool_fns(ctx)
        if not self.GATED_TOOLS:
            return fns

        gate_open: list[bool] = [False]
        result: dict[str, Callable[..., Awaitable[dict]]] = {}
        for name, fn in fns.items():
            if name == "confirm":
                result[name] = _make_confirm_gatekeeper(fn, gate_open)
            elif name in self.GATED_TOOLS:
                result[name] = _make_gated_tool(
                    fn, name, gate_open, ctx,
                    reset_after_call=(name in self.GATED_TOOLS_PER_CALL),
                )
            else:
                result[name] = fn
        return result

    def get_tool_budget(self) -> int:
        """Maximum tool calls before the loop is forcibly terminated.

        Workflows that process many pages (e.g. ContradictionResolverWorkflow)
        should override this to a higher value.  The default of 30 is suitable
        for single-run workflows like IngestLintWorkflow.
        """
        return 30
