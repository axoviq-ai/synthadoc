# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Base class for Tier-1 (single-LLM-call) agents.

All agents that make direct LLM calls without a tool-calling loop must
inherit from ``BaseAgent``.  Agents that run an agentic tool loop inherit
from ``AgenticWorkflow`` instead (see ``agents/workflows/_base.py``).

Non-LLM utility classes (e.g. the wiki export serialiser in
``core/export.py``) live outside the agents package and do not inherit
``BaseAgent`` because they require no LLM provider.

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
Entry pt  — implement ``async def _run(self, ...)`` with the agent logic;
            the public ``run(...)`` is provided by this base class and wraps
            ``_run`` with logging and a safe-default fallback.
Errors    — do NOT catch exceptions inside ``_run``; let them propagate to
            ``run``, which logs the failure and returns ``_safe_default()``.
            Override ``_safe_default`` to return a typed empty result
            (``[]``, ``""``, ``None``, …) appropriate for the agent.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from synthadoc.providers.base import LLMProvider

if TYPE_CHECKING:
    from synthadoc.config import Config

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Shared infrastructure for Tier-1 agents.

    **For new agents:** implement ``_run(self, ...)`` with the core logic
    and override ``_safe_default()`` to return a typed empty result.
    The public ``run(...)`` is provided here — do not override it unless
    error suppression must be bypassed (hard-failure pattern).

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

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Public entry point.  Calls ``_run`` and handles failures.

        On any exception from ``_run``, logs a warning using the subclass
        name and returns ``_safe_default()``.  Callers never need to catch
        LLM-level errors.

        Agents where a ``None`` fallback would cause ``AttributeError`` at
        the call site (callers that access result fields directly) should
        override this method to propagate errors instead of suppressing them.
        """
        try:
            return await self._run(*args, **kwargs)
        except Exception as exc:
            logger.warning("%s.run failed: %s", type(self).__name__, exc)
            return self._safe_default()

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abstractmethod
    async def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Implement agent logic here.  Do not catch exceptions.

        Declared abstract so Python raises ``TypeError`` at instantiation
        time rather than at the first ``run()`` call if a subclass forgets
        to implement it.
        """

    def _safe_default(self) -> Any:
        """Return a typed empty result when ``_run`` raises.

        Override to return the appropriate empty value for the agent's
        return type: ``[]`` for list results, ``""`` for strings, etc.
        Defaults to ``None``.
        """
        return None
