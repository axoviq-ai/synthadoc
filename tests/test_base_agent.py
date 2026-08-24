# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for BaseAgent and the structural invariant that all LLM agents inherit from it."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from synthadoc.agents._base import BaseAgent
from synthadoc.providers.base import LLMProvider


# ── BaseAgent construction ────────────────────────────────────────────────────

class _ConcreteAgent(BaseAgent):
    """Minimal concrete subclass used for construction and run() tests."""
    async def _run(self, *args, **kwargs):
        return []


def test_base_agent_stores_provider():
    provider = MagicMock(spec=LLMProvider)
    agent = _ConcreteAgent(provider)
    assert agent._provider is provider


def test_base_agent_cfg_defaults_to_none():
    provider = MagicMock(spec=LLMProvider)
    agent = _ConcreteAgent(provider)
    assert agent._cfg is None


def test_base_agent_stores_cfg():
    provider = MagicMock(spec=LLMProvider)
    cfg = MagicMock()
    agent = _ConcreteAgent(provider, cfg)
    assert agent._cfg is cfg


def test_base_agent_cfg_keyword_arg():
    """cfg may be passed as a keyword argument."""
    provider = MagicMock(spec=LLMProvider)
    cfg = MagicMock()
    agent = _ConcreteAgent(provider, cfg=cfg)
    assert agent._cfg is cfg


def test_base_agent_provider_stored_on_subclass():
    """_provider set by BaseAgent.__init__ is accessible on the subclass instance."""
    provider = MagicMock(spec=LLMProvider)

    class AnotherAgent(BaseAgent):
        def __init__(self, provider):
            super().__init__(provider)
            self._extra = "data"

        async def _run(self, *args, **kwargs):  # required by ABC
            return None

    agent = AnotherAgent(provider)
    assert agent._provider is provider
    assert agent._extra == "data"


# ── Structural invariant: all LLM agents inherit BaseAgent ───────────────────

_LLM_AGENTS = [
    ("SummarizeAgent",       "synthadoc.agents.summarize_agent"),
    ("RewriteAgent",         "synthadoc.agents.rewrite_agent"),
    ("SearchDecomposeAgent", "synthadoc.agents.search_decompose_agent"),
    ("ScaffoldAgent",        "synthadoc.agents.scaffold_agent"),
    ("ActionAgent",          "synthadoc.agents.action_agent"),
    ("ContextAgent",         "synthadoc.agents.context_agent"),
    ("QueryAgent",           "synthadoc.agents.query_agent"),
    ("LintAgent",            "synthadoc.agents.lint_agent"),
    ("IngestAgent",          "synthadoc.agents.ingest_agent"),
    ("FaithfulnessAuditAgent", "synthadoc.agents.citation_faithfulness_agent"),
]


@pytest.mark.parametrize("class_name,module_path", _LLM_AGENTS)
def test_llm_agent_inherits_base_agent(class_name, module_path):
    """Every LLM agent must be a subclass of BaseAgent."""
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    assert issubclass(cls, BaseAgent), (
        f"{class_name} must inherit from BaseAgent. "
        "Add `(BaseAgent)` to the class declaration and call `super().__init__(provider[, cfg])`."
    )


def test_skill_agent_exempt():
    """SkillAgent (no LLM) is deliberately exempt from BaseAgent."""
    from synthadoc.agents.skill_agent import SkillAgent
    assert not issubclass(SkillAgent, BaseAgent)


def test_export_utility_not_in_agents_package():
    """The wiki export utility lives in core/, not agents/, and has no BaseAgent dependency."""
    from synthadoc.core.export import ExportAgent
    assert not issubclass(ExportAgent, BaseAgent)


# ── run() / _run() / _safe_default() pattern ─────────────────────────────────

def test_run_delegates_to_run_impl():
    """BaseAgent.run() calls _run() and returns its result."""
    provider = MagicMock(spec=LLMProvider)
    agent = _ConcreteAgent(provider)
    result = asyncio.run(agent.run())
    assert result == []


def test_run_returns_safe_default_on_exception():
    """BaseAgent.run() catches _run() exceptions and returns _safe_default()."""
    provider = MagicMock(spec=LLMProvider)

    class _FailingAgent(BaseAgent):
        async def _run(self, *args, **kwargs):
            raise RuntimeError("simulated LLM failure")

    agent = _FailingAgent(provider)
    result = asyncio.run(agent.run())
    assert result is None  # default _safe_default() returns None


def test_safe_default_override():
    """Subclasses can override _safe_default() to return a typed empty result."""
    provider = MagicMock(spec=LLMProvider)

    class _ListAgent(BaseAgent):
        async def _run(self, *args, **kwargs):
            raise ValueError("boom")

        def _safe_default(self):
            return []

    agent = _ListAgent(provider)
    result = asyncio.run(agent.run())
    assert result == []


def test_bare_subclass_raises_type_error_on_instantiation():
    """Subclasses that omit _run() raise TypeError at instantiation (ABC enforcement)."""
    class _BareAgent(BaseAgent):
        pass  # does not override _run

    with pytest.raises(TypeError, match="_run"):
        _BareAgent(MagicMock(spec=LLMProvider))


def test_run_passes_args_to_run_impl():
    """BaseAgent.run(*args, **kwargs) forwards arguments to _run()."""
    provider = MagicMock(spec=LLMProvider)
    received: dict = {}

    class _EchoAgent(BaseAgent):
        async def _run(self, x, y=0):
            received["x"] = x
            received["y"] = y
            return x + y

    agent = _EchoAgent(provider)
    result = asyncio.run(agent.run(3, y=7))
    assert result == 10
    assert received == {"x": 3, "y": 7}


def test_faithfulness_audit_agent_safe_default():
    """FaithfulnessAuditAgent._safe_default() returns []."""
    from unittest.mock import MagicMock
    from synthadoc.agents.citation_faithfulness_agent import FaithfulnessAuditAgent

    provider = MagicMock(spec=LLMProvider)
    store = MagicMock()
    agent = FaithfulnessAuditAgent(provider, wiki_root=MagicMock(), store=store)
    assert agent._safe_default() == []
