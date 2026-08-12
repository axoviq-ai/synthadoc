# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Central registry of AgenticWorkflows that participate in fast-path routing.

To add a new workflow with fast-path routing:
  1. Implement AgenticWorkflow in a new module under synthadoc/agents/workflows/.
  2. Set MATCH_RE = re.compile(r"...", re.IGNORECASE) on the class.
  3. Add one import line and one entry in ROUTED_WORKFLOWS below.

No other file needs to change.  ActionAgent reads ROUTED_WORKFLOWS at startup
and builds both the fast-path loop and the _ACTION_RE gate from it automatically.
"""
from __future__ import annotations

from synthadoc.agents.workflows._base import AgenticWorkflow
from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
from synthadoc.agents.workflows.lint_report import LintReportWorkflow

# Ordered list of workflow classes with MATCH_RE fast-path routing.
# First match wins; put more specific patterns before broader ones.
ROUTED_WORKFLOWS: list[type[AgenticWorkflow]] = [
    LintReportWorkflow,
    BrokenWikilinksWorkflow,
]
