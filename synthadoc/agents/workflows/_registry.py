# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Central registry of AgenticWorkflows that participate in fast-path routing.

To add a new workflow with fast-path routing:
  1. Implement AgenticWorkflow in a new module under synthadoc/agents/workflows/.
  2. Set MATCH_RE = re.compile(r"...", re.IGNORECASE) on the class.
  3. Set NAME and DESCRIPTION on the class to expose it via the CLI.
  4. Add one import line and one entry in ROUTED_WORKFLOWS below.
  5. If the workflow writes to the wiki, add a confirm gate (see below).
     Read-only workflows skip this step — the base-class default is correct.

No other file needs to change.  ActionAgent reads ROUTED_WORKFLOWS at startup,
derives _ACTION_RE coverage automatically from each workflow's MATCH_RE, and
routes directly to the first matching workflow — no LLM extraction required.
CLI_REGISTRY is derived automatically from ROUTED_WORKFLOWS.NAME entries and
drives ``synthadoc workflow list`` and ``synthadoc workflow run --name``.

── Confirm gates (step 5) ───────────────────────────────────────────────────────
Read-only workflows (no wiki writes): nothing to do — ``GATED_TOOLS`` defaults
to ``frozenset()`` on the base class and ``build_guarded_tool_fns`` is a no-op.

Write workflows MUST ask the user to approve before the first write.
Choose the pattern based on who composes the confirm message:

  Pattern A — tool composes its own message (no LLM help needed)
      Use when the dangerous tool already has all the data it needs to write
      a concrete confirm message (e.g. "About to overwrite index.md, purpose.md").
      How: call ``await tool_confirm(ctx, message=...)`` inside the dangerous
      tool function itself.  Leave ``GATED_TOOLS = frozenset()`` (the default).
      Example: ScaffoldWorkflow → tool_run_scaffold in _tools.py.

  Pattern B — LLM composes the message from its scan results  (recommended)
      Use when the confirm message should include data the LLM gathered via
      earlier tool calls (e.g. "Found 7 broken links on pages A, B, C").
      How:
        a. Include ``"confirm": functools.partial(tool_confirm, ctx)`` in
           ``get_tool_fns``.
        b. Declare ``GATED_TOOLS = frozenset({"your_write_tool"})``.
      The framework (AgenticWorkflow.build_guarded_tool_fns in _base.py) then
      wraps "confirm" so approval opens the session gate, and wraps each
      gated tool so it fires a fallback dialog if the LLM skips the confirm
      step — no write ever reaches the wiki without user approval.
      Examples: BrokenWikilinksWorkflow, IngestLintWorkflow, OrphanResolverWorkflow.

Full implementation details: AgenticWorkflow.GATED_TOOLS in _base.py.
────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from synthadoc.agents.workflows._base import AgenticWorkflow
from synthadoc.agents.workflows.broken_citation_resolver import BrokenCitationResolverWorkflow
from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
from synthadoc.agents.workflows.lint_report import LintReportWorkflow
from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow

# Ordered list of workflow classes with MATCH_RE fast-path routing.
# First match wins; put more specific patterns before broader ones.
ROUTED_WORKFLOWS: list[type[AgenticWorkflow]] = [
    LintReportWorkflow,
    BrokenWikilinksWorkflow,
    ScaffoldWorkflow,
    ContradictionResolverWorkflow,   # more specific than IngestLintWorkflow
    BrokenCitationResolverWorkflow,
    OrphanResolverWorkflow,
    IngestLintWorkflow,
]

# Workflows available via ``synthadoc workflow run --name <name>``.
# Populated automatically from ROUTED_WORKFLOWS entries that have NAME set.
CLI_REGISTRY: dict[str, type[AgenticWorkflow]] = {
    wf.NAME: wf
    for wf in ROUTED_WORKFLOWS
    if wf.NAME is not None
}
