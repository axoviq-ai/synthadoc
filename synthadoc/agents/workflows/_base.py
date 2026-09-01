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


def _make_gated_tool(
    original_fn: "Callable[..., Awaitable[dict]]",
    tool_name: str,
    gate_open: "list[bool]",
    ctx: "WorkflowContext",
) -> "Callable[..., Awaitable[dict]]":
    """Wrap a gated tool to fire a fallback confirm when the gate is not open.

    The fallback fires only if the LLM calls this tool before the session's
    ``confirm`` tool has been called and approved.  Once the gate is open —
    either via the explicit confirm tool or via this fallback — subsequent
    calls to the same tool run without an extra dialog.
    """
    async def _wrapped(*args: object, **kwargs: object) -> dict:
        if not gate_open[0]:
            # Deferred import to avoid circular dependency (_tools imports _base).
            from synthadoc.agents.workflows._tools import (  # noqa: PLC0415
                tool_confirm as _tool_confirm,
            )
            fallback = await _tool_confirm(
                ctx,
                f"Run `{tool_name}`?\n\n"
                "(Tip: call `confirm` with a detailed summary first so the user "
                "can review all planned changes before anything is applied.)",
                yes_label="Proceed",
                no_label="Cancel",
            )
            if not fallback.get("confirmed"):
                return {
                    "status": "cancelled",
                    "message": f"`{tool_name}` cancelled by user.",
                }
            gate_open[0] = True
        return await original_fn(*args, **kwargs)  # type: ignore[misc]
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
                result[name] = _make_gated_tool(fn, name, gate_open, ctx)
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
