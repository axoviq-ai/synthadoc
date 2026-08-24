# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Base class for Tier-1 (single-LLM-call) agents.

All agents that make direct LLM calls without a tool-calling loop must
inherit from ``BaseAgent``.  Agents that run an agentic tool loop inherit
from ``AgenticWorkflow`` instead (see ``agents/workflows/_base.py``).

Non-LLM utility classes (``SkillAgent``, ``ExportAgent``) are exempt and
remain standalone.

Contract
--------
LLM       — bound at construction via ``provider: LLMProvider``; stored as
            ``self._provider``.
Config    — optional ``cfg: Config | None``; stored as ``self._cfg``.
            Agents that expose a typed accessor (e.g. ``self._cfg.ingest``)
            should document their cfg dependency in the class docstring.
Memory    — none; agents are stateless between calls.  Do not store
            conversation history on the instance.
Tools     — none; use ``AgenticWorkflow`` for tool-calling loops.
Prompt    — define system prompts as module-level constants named
            ``_<NAME>_SYSTEM`` (e.g. ``_SUMMARIZE_SYSTEM``).
Entry pt  — ``async def run(...)`` is the preferred public entry-point name
            for new agents.  Legacy names (``summarize``, ``rewrite``,
            ``lint``) are accepted but ``run`` should be used in all new
            implementations.
Errors    — catch ``Exception`` from LLM calls; log with
            ``logger.warning``; return a typed safe default (empty string,
            empty list, etc.) so the caller never needs to handle
            LLM-level failures.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from synthadoc.providers.base import LLMProvider

if TYPE_CHECKING:
    from synthadoc.config import Config


class BaseAgent:
    """Shared infrastructure for Tier-1 agents.

    Subclasses call ``super().__init__(provider[, cfg])`` and add their
    own domain-specific dependencies (``store``, ``wiki_root``, …) as
    additional ``__init__`` parameters.
    """

    def __init__(
        self,
        provider: LLMProvider,
        cfg: "Config | None" = None,
    ) -> None:
        self._provider = provider
        self._cfg = cfg
