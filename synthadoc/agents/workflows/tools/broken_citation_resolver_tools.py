# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain-specific tool placeholders for BrokenCitationResolverWorkflow.

All tools needed by this workflow (tool_find_broken_citations,
tool_apply_citation_fixes, tool_confirm, tool_notify, tool_get_wiki_status)
are shared tools in synthadoc.agents.workflows._tools and are registered
directly in BrokenCitationResolverWorkflow.get_tool_fns.

This module is a placeholder consistent with the tools/ directory convention.
Future domain tools (e.g. tool_read_source_excerpt) can be added here
without touching _tools.py.
"""
from __future__ import annotations

__all__: list[str] = []
