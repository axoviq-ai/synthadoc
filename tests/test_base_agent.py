# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for BaseAgent and the structural invariant that all LLM agents inherit from it."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synthadoc.agents._base import BaseAgent
from synthadoc.providers.base import LLMProvider


# ── BaseAgent construction ────────────────────────────────────────────────────

class _ConcreteAgent(BaseAgent):
    """Minimal concrete subclass used for construction tests."""
    async def run(self):
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
    ("FaithfulnessAuditAgent", "synthadoc.agents.citation_faithfulness"),
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


def test_export_agent_exempt():
    """ExportAgent (no LLM) is deliberately exempt from BaseAgent."""
    from synthadoc.agents.export_agent import ExportAgent
    assert not issubclass(ExportAgent, BaseAgent)
