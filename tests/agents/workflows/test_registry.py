# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for the workflow registry and MATCH_RE class attribute convention."""
from __future__ import annotations

import re


def test_routed_workflows_is_nonempty_list_of_agentic_workflow_subclasses():
    from synthadoc.agents.workflows._base import AgenticWorkflow
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS

    assert isinstance(ROUTED_WORKFLOWS, list)
    assert len(ROUTED_WORKFLOWS) > 0
    for wf_cls in ROUTED_WORKFLOWS:
        assert issubclass(wf_cls, AgenticWorkflow), f"{wf_cls} is not an AgenticWorkflow"


def test_every_routed_workflow_has_compiled_match_re():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS

    for wf_cls in ROUTED_WORKFLOWS:
        assert wf_cls.MATCH_RE is not None, f"{wf_cls.__name__} must define MATCH_RE"
        assert isinstance(wf_cls.MATCH_RE, re.Pattern), (
            f"{wf_cls.__name__}.MATCH_RE must be a compiled re.Pattern"
        )


def test_base_class_match_re_default_is_none():
    from synthadoc.agents.workflows._base import AgenticWorkflow

    assert AgenticWorkflow.MATCH_RE is None


def test_lint_report_workflow_match_re_hits_action_phrases():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow

    match = LintReportWorkflow.MATCH_RE
    assert match.search("run lint and show me the report")
    assert match.search("run lint")
    assert match.search("please run a full lint")


def test_lint_report_workflow_match_re_misses_query_phrases():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow

    match = LintReportWorkflow.MATCH_RE
    assert not match.search("show me my lint report")   # query, not action
    assert not match.search("what is my lint result?")
    assert not match.search("what does lint mean?")


def test_broken_wikilinks_workflow_match_re_hits_action_phrases():
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow

    match = BrokenWikilinksWorkflow.MATCH_RE
    assert match.search("scan for broken wikilinks")
    assert match.search("fix broken links")
    assert match.search("check wikilink integrity")
    assert match.search("find dangling wikilinks")
    assert match.search("dead wikilinks")


def test_broken_wikilinks_workflow_match_re_misses_unrelated_phrases():
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow

    match = BrokenWikilinksWorkflow.MATCH_RE
    assert not match.search("what are wikilinks?")
    assert not match.search("how do I use links?")


def test_registry_loop_routes_lint_question_to_lint_report_workflow():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow

    question = "run lint and show me the lint report"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is LintReportWorkflow


def test_registry_loop_routes_wikilinks_question_to_broken_wikilinks_workflow():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow

    question = "scan for broken wikilinks"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is BrokenWikilinksWorkflow


def test_registry_loop_returns_none_for_unrouted_question():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS

    question = "what does the alan-turing page say about the ACE?"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is None
