# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Central registry of AgenticWorkflows that participate in fast-path routing.

To add a new workflow with fast-path routing:
  1. Implement AgenticWorkflow in a new module under synthadoc/agents/workflows/.
  2. Set MATCH_RE = re.compile(r"...", re.IGNORECASE) on the class.
  3. Add one import line and one entry in ROUTED_WORKFLOWS below.

No other file needs to change.  ActionAgent reads ROUTED_WORKFLOWS at startup,
derives _ACTION_RE coverage automatically from each workflow's MATCH_RE, and
routes directly to the first matching workflow — no LLM extraction required.
"""
from __future__ import annotations

from synthadoc.agents.workflows._base import AgenticWorkflow
from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
from synthadoc.agents.workflows.lint_report import LintReportWorkflow
from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow

# Ordered list of workflow classes with MATCH_RE fast-path routing.
# First match wins; put more specific patterns before broader ones.
ROUTED_WORKFLOWS: list[type[AgenticWorkflow]] = [
    LintReportWorkflow,
    BrokenWikilinksWorkflow,
    ScaffoldWorkflow,
    IngestLintWorkflow,
]
