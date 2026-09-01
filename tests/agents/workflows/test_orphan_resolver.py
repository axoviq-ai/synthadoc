# tests/agents/workflows/test_orphan_resolver.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Unit tests for the orphan-resolver workflow and its domain tools."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synthadoc.agents.workflows._base import WorkflowContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(store=None, search=None, audit_db=None, queue=None):
    events = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="test-session",
        wiki_root=Path("/wiki"),
        queue=queue,
        store=store,
        audit_db=audit_db,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
        search=search,
    )
    return ctx, events


# ---------------------------------------------------------------------------
# Task 2: WorkflowContext.search field
# ---------------------------------------------------------------------------

def test_workflow_context_search_field():
    """WorkflowContext accepts a search= kwarg and exposes it."""
    mock_search = MagicMock()
    ctx, _ = _make_ctx(search=mock_search)
    assert ctx.search is mock_search


def test_workflow_context_search_field_defaults_none():
    """WorkflowContext.search defaults to None when omitted."""
    events = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="s",
        wiki_root=Path("/wiki"),
        queue=None,
        store=None,
        audit_db=None,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    assert ctx.search is None


# ---------------------------------------------------------------------------
# Task 3: tool_find_orphaned_pages + tool_verify_orphan_resolved
# ---------------------------------------------------------------------------

def _make_wiki_store(pages: dict[str, tuple[str, str]]) -> MagicMock:
    """Build a mock WikiStorage from {slug: (status, content)} pairs."""
    store = MagicMock()
    page_slugs = list(pages.keys())
    store.list_pages.return_value = page_slugs

    def _read(slug):
        if slug not in pages:
            return None
        status, content = pages[slug]
        p = MagicMock()
        p.status = status
        p.content = content
        p.orphan = False
        return p

    store.read_page.side_effect = _read
    return store


async def test_find_orphaned_pages_empty():
    """No active pages → empty orphans list."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({})
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    assert result == {"orphans": [], "count": 0}


async def test_find_orphaned_pages_returns_slugs():
    """Page with no inbound links is returned as orphan; page with link is not."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({
        "alpha": ("active", "This page mentions [[beta]]."),
        "beta":  ("active", "No links here."),
        "gamma": ("active", "Links to [[alpha]]."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    # gamma links to alpha, alpha links to beta — only beta has no inbound link
    # Wait: alpha→beta, gamma→alpha. beta has inbound from alpha. gamma has inbound from none.
    # Correct: gamma is orphan (no page links to gamma), beta is not orphan (alpha links to beta)
    # Actually: referenced = {beta, alpha}. Not referenced = {gamma}.
    assert "gamma" in result["orphans"]
    assert "beta" not in result["orphans"]
    assert result["count"] == len(result["orphans"])


async def test_find_orphaned_pages_excludes_non_active():
    """Draft and archived pages are not included in orphan check."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({
        "active-page": ("active", "No links."),
        "draft-page":  ("draft", "No links."),
        "archived":    ("archived", "No links."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    slugs = result["orphans"]
    assert "draft-page" not in slugs
    assert "archived" not in slugs


async def test_verify_orphan_resolved_true():
    """Orphan is resolved when another page now links to it."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved
    store = _make_wiki_store({
        "orphan-page": ("active", "Content."),
        "linker":      ("active", "See [[orphan-page]] for details."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_verify_orphan_resolved(ctx, "orphan-page")
    assert result["resolved"] is True
    assert "linker" in result["linked_by"]


async def test_verify_orphan_resolved_false():
    """Orphan is still unresolved when no page links to it."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved
    store = _make_wiki_store({
        "orphan-page": ("active", "Content."),
        "other":       ("active", "Nothing relevant."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_verify_orphan_resolved(ctx, "orphan-page")
    assert result["resolved"] is False
    assert result["linked_by"] == []


# ---------------------------------------------------------------------------
# Task 4: tool_search_orphan_candidates
# ---------------------------------------------------------------------------

def _make_search_mock(results: list[tuple[str, float]]) -> MagicMock:
    """Build a mock HybridSearch returning given (slug, score) pairs."""
    search = MagicMock()
    mock_results = []
    for slug, score in results:
        r = MagicMock()
        r.slug = slug
        r.score = score
        mock_results.append(r)
    search.bm25_search.return_value = mock_results
    return search


async def test_search_candidates_title_bm25():
    """title_bm25 calls bm25_search with slug-derived terms and returns candidates."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    search = _make_search_mock([("page-a", 0.9), ("page-b", 0.7)])
    store = _make_wiki_store({
        "orphan-topic": ("active", "Content."),
        "page-a": ("active", "Related."),
        "page-b": ("active", "Related."),
    })
    ctx, _ = _make_ctx(store=store, search=search)
    result = await tool_search_orphan_candidates(ctx, "orphan-topic", "title_bm25", [])
    assert result["strategy"] == "title_bm25"
    assert "page-a" in result["candidates"]
    assert "page-b" in result["candidates"]
    search.bm25_search.assert_called_once()
    # Slug "orphan-topic" → terms ["orphan", "topic"]
    call_args = search.bm25_search.call_args[0][0]
    assert "orphan" in call_args
    assert "topic" in call_args


async def test_search_candidates_content_bm25():
    """content_bm25 uses first-paragraph terms from the orphan page."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    search = _make_search_mock([("candidate", 0.8)])
    store = _make_wiki_store({
        "orphan": ("active", "This page discusses quantum computing in detail."),
        "candidate": ("active", "Quantum topics."),
    })
    ctx, _ = _make_ctx(store=store, search=search)
    result = await tool_search_orphan_candidates(ctx, "orphan", "content_bm25", [])
    assert result["strategy"] == "content_bm25"
    assert "candidate" in result["candidates"]
    # Terms from first paragraph passed to bm25_search
    call_terms = search.bm25_search.call_args[0][0]
    assert len(call_terms) > 0


async def test_search_candidates_full_title_scan():
    """full_title_scan returns all active page titles; no BM25 call."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    store = _make_wiki_store({
        "orphan":    ("active", "Content."),
        "page-one":  ("active", "Content."),
        "page-two":  ("active", "Content."),
        "archived":  ("archived", "Content."),
    })
    ctx, _ = _make_ctx(store=store, search=None)
    result = await tool_search_orphan_candidates(ctx, "orphan", "full_title_scan", [])
    assert result["strategy"] == "full_title_scan"
    assert result["candidates"] == []
    slugs = [p["slug"] for p in result["all_page_titles"]]
    assert "page-one" in slugs
    assert "page-two" in slugs
    assert "orphan" not in slugs       # self excluded
    assert "archived" not in slugs     # non-active excluded


async def test_search_candidates_contextual_reasoning():
    """contextual_reasoning returns all titles AND the orphan's full body."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    store = _make_wiki_store({
        "orphan":  ("active", "Full orphan body text here."),
        "other":   ("active", "Other content."),
    })
    ctx, _ = _make_ctx(store=store, search=None)
    result = await tool_search_orphan_candidates(ctx, "orphan", "contextual_reasoning", [])
    assert result["strategy"] == "contextual_reasoning"
    assert "orphan_content" in result
    assert "Full orphan body" in result["orphan_content"]
    assert result["candidates"] == []


async def test_search_candidates_excludes_tried_slugs():
    """exclude_slugs prevents already-tried candidates from appearing."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    search = _make_search_mock([("tried", 0.9), ("fresh", 0.7)])
    store = _make_wiki_store({
        "orphan": ("active", "Content."),
        "tried":  ("active", "Content."),
        "fresh":  ("active", "Content."),
    })
    ctx, _ = _make_ctx(store=store, search=search)
    result = await tool_search_orphan_candidates(
        ctx, "orphan", "title_bm25", ["tried"]
    )
    assert "tried" not in result["candidates"]
    assert "fresh" in result["candidates"]


async def test_search_candidates_empty_when_no_search():
    """title_bm25 returns empty candidates when ctx.search is None."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    ctx, _ = _make_ctx(store=MagicMock(), search=None)
    result = await tool_search_orphan_candidates(ctx, "orphan", "title_bm25", [])
    assert result["candidates"] == []
    assert "error" in result


async def test_search_candidates_unknown_strategy():
    """Unknown strategy returns empty candidates with an error key."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    ctx, _ = _make_ctx(store=MagicMock(), search=MagicMock())
    result = await tool_search_orphan_candidates(ctx, "orphan", "laser_scan", [])
    assert result["candidates"] == []
    assert "error" in result


# ---------------------------------------------------------------------------
# Task 5: tool_estimate_and_confirm
# ---------------------------------------------------------------------------

async def test_cost_estimate_confirm_confirmed():
    """Confirmed cost estimate returns confirmed=True and cost metadata."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_estimate_and_confirm

    async def _confirm_yes(ctx, message, yes_label="Yes", no_label="No", **_):
        return {"confirmed": True}

    with patch(
        "synthadoc.agents.workflows.tools.orphan_resolver_tools.tool_confirm",
        side_effect=_confirm_yes,
    ):
        ctx, _ = _make_ctx()
        result = await tool_estimate_and_confirm(ctx, orphan_count=5)

    assert result["confirmed"] is True
    assert result["orphan_count"] == 5
    assert "estimated_usd" in result
    assert result["estimated_usd"] > 0


async def test_cost_estimate_confirm_cancelled():
    """Declined cost estimate returns confirmed=False."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_estimate_and_confirm

    async def _confirm_no(ctx, message, yes_label="Yes", no_label="No", **_):
        return {"confirmed": False}

    with patch(
        "synthadoc.agents.workflows.tools.orphan_resolver_tools.tool_confirm",
        side_effect=_confirm_no,
    ):
        ctx, _ = _make_ctx()
        result = await tool_estimate_and_confirm(ctx, orphan_count=3)

    assert result["confirmed"] is False


async def test_cost_estimate_message_contains_count():
    """Estimate message shown to user contains the orphan count."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_estimate_and_confirm

    captured_messages = []

    async def _capture_and_confirm(ctx, message, yes_label="Yes", no_label="No", **_):
        captured_messages.append(message)
        return {"confirmed": True}

    with patch(
        "synthadoc.agents.workflows.tools.orphan_resolver_tools.tool_confirm",
        side_effect=_capture_and_confirm,
    ):
        ctx, _ = _make_ctx()
        await tool_estimate_and_confirm(ctx, orphan_count=7)

    assert captured_messages
    assert "7" in captured_messages[0]


# ---------------------------------------------------------------------------
# Task 6: OrphanResolverWorkflow
# ---------------------------------------------------------------------------

import re as _re


@pytest.mark.parametrize("phrase", [
    "run orphan resolver",
    "Run Orphan Resolver",
    "orphan resolver",
    "fix orphaned pages",
    "resolve orphan",
    "orphan resolving",
])
def test_match_re_phrases(phrase):
    """MATCH_RE routes well-known CLI/UI trigger phrases."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    assert OrphanResolverWorkflow.MATCH_RE.search(phrase), (
        f"MATCH_RE did not match: {phrase!r}"
    )


def test_match_re_does_not_match_unrelated():
    """MATCH_RE does not fire on generic wiki queries."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    for phrase in ["run lint report", "show wiki status", "ingest stale pages"]:
        assert not OrphanResolverWorkflow.MATCH_RE.search(phrase), (
            f"MATCH_RE incorrectly matched: {phrase!r}"
        )


def test_orphan_chip_matches_workflow_match_re():
    """The UI hint chip text routes directly to OrphanResolverWorkflow."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    chip = "Run orphan resolver"
    assert OrphanResolverWorkflow.MATCH_RE.search(chip)


def test_build_initial_message_no_slug():
    """Without --slug, initial message runs on all orphans."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    msg = wf.build_initial_message("run orphan resolver")
    assert "all orphaned" in msg.lower() or "all" in msg.lower()
    assert "--slug" not in msg


def test_build_initial_message_with_slug():
    """With --slug, initial message targets the specific slug."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    msg = wf.build_initial_message("run orphan resolver --slug my-page")
    assert "my-page" in msg


def test_get_tool_budget():
    """Tool budget is at least 100 (allows meaningful multi-page run)."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    assert wf.get_tool_budget() >= 100


async def test_get_tool_fns_contains_domain_tools():
    """get_tool_fns returns all expected domain and shared tool keys."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    ctx, _ = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    expected = {
        "tool_find_orphaned_pages",
        "tool_estimate_and_confirm",
        "tool_search_orphan_candidates",
        "tool_verify_orphan_resolved",
        "tool_read_page_content",
        "tool_propose_and_apply",
        "tool_confirm",
        "tool_notify",
    }
    assert expected.issubset(set(fns.keys())), (
        f"Missing tools: {expected - set(fns.keys())}"
    )


async def test_build_system_prompt_contains_tool_inventory():
    """System prompt lists all domain tool names."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    prompt = await wf.build_system_prompt()
    for tool in [
        "tool_find_orphaned_pages",
        "tool_search_orphan_candidates",
        "tool_verify_orphan_resolved",
        "tool_estimate_and_confirm",
    ]:
        assert tool in prompt, f"System prompt missing tool: {tool}"


async def test_build_system_prompt_contains_strategies():
    """System prompt mentions all 4 strategy names."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    prompt = await wf.build_system_prompt()
    for strategy in ["title_bm25", "content_bm25", "full_title_scan", "contextual_reasoning"]:
        assert strategy in prompt, f"System prompt missing strategy: {strategy}"


# ---------------------------------------------------------------------------
# Task 7: Registry + CLI
# ---------------------------------------------------------------------------

def test_orphan_resolver_in_registry():
    """OrphanResolverWorkflow is registered in ROUTED_WORKFLOWS."""
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    assert OrphanResolverWorkflow in ROUTED_WORKFLOWS


def test_orphan_resolver_in_cli_registry():
    """'orphan-resolver' appears in CLI_REGISTRY."""
    from synthadoc.agents.workflows._registry import CLI_REGISTRY
    assert "orphan-resolver" in CLI_REGISTRY


def test_orphan_resolver_cli_query():
    """workflow.py _WORKFLOW_QUERIES maps 'orphan-resolver' to a trigger phrase."""
    from synthadoc.cli.main import app  # noqa: F401  (resolves circular import)
    from synthadoc.cli.workflow import _WORKFLOW_QUERIES
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    assert "orphan-resolver" in _WORKFLOW_QUERIES
    phrase = _WORKFLOW_QUERIES["orphan-resolver"]
    assert OrphanResolverWorkflow.MATCH_RE.search(phrase), (
        f"Query phrase {phrase!r} does not match MATCH_RE"
    )


# ---------------------------------------------------------------------------
# Task 8: WebUI — WikiStorage + HintEngine + hints.json
# ---------------------------------------------------------------------------

def test_count_orphan_active_pages_zero(tmp_path):
    """No pages → count is 0."""
    from synthadoc.storage.wiki import WikiStorage
    store = WikiStorage(tmp_path)
    assert store.count_orphan_active_pages() == 0


def test_count_orphan_active_pages_counts_active_only(tmp_path):
    """Only active pages with orphan=true are counted; others excluded."""
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    store = WikiStorage(tmp_path)

    active_orphan = WikiPage(
        title="Orphan", tags=[], content="Body.", status="active",
        confidence="", sources=[], created="2026-01-01", orphan=True,
    )
    active_normal = WikiPage(
        title="Normal", tags=[], content="Body.", status="active",
        confidence="", sources=[], created="2026-01-01", orphan=False,
    )
    draft_orphan = WikiPage(
        title="Draft", tags=[], content="Body.", status="draft",
        confidence="", sources=[], created="2026-01-01", orphan=True,
    )
    store.write_page("active-orphan", active_orphan)
    store.write_page("active-normal", active_normal)
    store.write_page("draft-orphan", draft_orphan)

    assert store.count_orphan_active_pages() == 1


def test_initial_hints_orphan_priority():
    """orphan > 0 in context → 'Run orphan resolver' chip appears."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "HEALTH_CHECK", context={"contradicted": 0, "stale": 0, "orphan": 3}
    )
    assert "Run orphan resolver" in hints


def test_initial_hints_orphan_below_contradiction():
    """contradiction chip appears before orphan chip."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "HEALTH_CHECK",
        context={"contradicted": 2, "stale": 0, "orphan": 1},
    )
    assert hints.index("Run contradiction resolver") < hints.index("Run orphan resolver")


def test_initial_hints_orphan_below_stale():
    """stale chip appears before orphan chip."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "HEALTH_CHECK",
        context={"contradicted": 0, "stale": 1, "orphan": 2},
    )
    assert hints.index("Re-ingest stale pages") < hints.index("Run orphan resolver")


def test_initial_hints_no_orphan_chip_when_zero():
    """No orphan chip when orphan count is 0."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "POWER_USER", context={"contradicted": 0, "stale": 0, "orphan": 0}
    )
    assert "Run orphan resolver" not in hints


def test_initial_hints_orphan_power_user():
    """'Run orphan resolver' chip appears in POWER_USER mode when orphan > 0."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "POWER_USER", context={"contradicted": 0, "stale": 0, "orphan": 1}
    )
    assert "Run orphan resolver" in hints


# ---------------------------------------------------------------------------
# Retry-loop contract (system prompt + tool-level verification)
# ---------------------------------------------------------------------------

async def test_verify_returns_false_causes_strategy_advance():
    """tool_verify_orphan_resolved returning resolved=false means retry is needed.

    The orphan resolver loop advances to the next strategy whenever verify
    returns resolved=false. This test confirms that the tool correctly returns
    false when no link exists — i.e. the tool provides the right signal for
    strategy advancement.
    """
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import (
        tool_verify_orphan_resolved,
        tool_search_orphan_candidates,
    )
    store = _make_wiki_store({
        "orphan-slug": ("active", "Content with no inbound links."),
        "candidate-a": ("active", "Talks about unrelated stuff."),
    })
    ctx, _ = _make_ctx(store=store)

    # After strategy 1 fails: verify still returns unresolved
    result = await tool_verify_orphan_resolved(ctx, "orphan-slug")
    assert result["resolved"] is False

    # Strategy 2 (content_bm25) call succeeds structurally
    ctx2, _ = _make_ctx(store=store, search=_make_search_mock([("candidate-a", 0.9)]))
    candidates = await tool_search_orphan_candidates(ctx2, "orphan-slug", "content_bm25")
    assert candidates["strategy"] == "content_bm25"


async def test_verify_returns_true_breaks_retry():
    """tool_verify_orphan_resolved returning resolved=true signals completion.

    After a successful link insertion the tool returns resolved=true and
    linked_by lists the linking page — the LLM breaks the strategy loop.
    """
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved

    store = _make_wiki_store({
        "orphan-slug": ("active", "About orphan topic."),
        "linker-page": ("active", "See [[orphan-slug]] for details."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_verify_orphan_resolved(ctx, "orphan-slug")
    assert result["resolved"] is True
    assert "linker-page" in result["linked_by"]


async def test_all_strategies_return_empty_candidates():
    """All 4 strategies can return empty candidate lists.

    When all strategies return no candidates the LLM must call tool_notify.
    This test confirms the empty-candidate path is structurally valid for
    every strategy name.
    """
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    store = _make_wiki_store({"orphan-slug": ("active", "Niche content.")})

    for strategy in ("title_bm25", "content_bm25", "full_title_scan", "contextual_reasoning"):
        # Use search mock that returns no results for BM25 strategies
        search = _make_search_mock([])
        ctx, _ = _make_ctx(store=store, search=search)
        result = await tool_search_orphan_candidates(
            ctx, "orphan-slug", strategy, exclude_slugs=["orphan-slug"]
        )
        # full_title_scan / contextual_reasoning return all_page_titles even when empty
        # BM25 strategies return candidates list
        assert "strategy" in result
        assert result["strategy"] == strategy


def test_escalation_system_prompt_contains_rerun_hint():
    """System prompt escalation template includes the re-run suggestion (step 1)."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    # _SYSTEM_PROMPT is the class-level constant; build_system_prompt uses it
    prompt_const = wf._SYSTEM_PROMPT if hasattr(wf, "_SYSTEM_PROMPT") else ""
    # Fallback: get it from the source
    import synthadoc.agents.workflows.orphan_resolver as _mod
    src = _mod.__file__
    import pathlib
    text = pathlib.Path(src).read_text(encoding="utf-8")
    assert "Re-run orphan-resolver" in text or "re-run orphan-resolver" in text.lower(), (
        "Escalation template missing re-run suggestion"
    )


def test_escalation_system_prompt_contains_tried_slugs():
    """System prompt escalation template references tried_slugs (candidate list)."""
    import pathlib
    import synthadoc.agents.workflows.orphan_resolver as _mod
    text = pathlib.Path(_mod.__file__).read_text(encoding="utf-8")
    assert "tried_slugs" in text, (
        "Escalation template must list tried_slugs so the user sees which candidates were considered"
    )


def test_inter_orphan_confirm_in_system_prompt():
    """System prompt mandates tool_confirm between orphans (not after the last)."""
    import pathlib
    import synthadoc.agents.workflows.orphan_resolver as _mod
    text = pathlib.Path(_mod.__file__).read_text(encoding="utf-8")
    # The prompt must explicitly describe the inter-orphan confirm gate
    assert "Inter-orphan confirm" in text or "inter-orphan" in text.lower() or (
        "tool_confirm" in text and "more orphans remain" in text.lower()
    ), "System prompt must describe the inter-orphan tool_confirm gate"


# ---------------------------------------------------------------------------
# Additional edge-case coverage for orphan_resolver_tools.py
# ---------------------------------------------------------------------------

async def test_find_orphaned_pages_store_is_none():
    """tool_find_orphaned_pages returns empty result when ctx.store is None (line 70)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    ctx, _ = _make_ctx(store=None)
    result = await tool_find_orphaned_pages(ctx)
    assert result == {"orphans": [], "count": 0}


async def test_verify_orphan_resolved_store_is_none():
    """tool_verify_orphan_resolved returns unresolved when ctx.store is None (line 93)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved
    ctx, _ = _make_ctx(store=None)
    result = await tool_verify_orphan_resolved(ctx, "some-slug")
    assert result == {"resolved": False, "linked_by": []}


async def test_verify_orphan_resolved_slug_not_in_active_pages():
    """Slug absent from active pages → resolved=False (line 102)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved
    # "active-page" is active; "ghost" is not in the store at all
    store = _make_wiki_store({"active-page": ("active", "Some content.")})
    ctx, _ = _make_ctx(store=store)
    result = await tool_verify_orphan_resolved(ctx, "ghost")
    assert result == {"resolved": False, "linked_by": []}


async def test_build_page_text_dicts_skips_none_page():
    """_build_page_text_dicts skips slugs when read_page() returns None (line 46)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = MagicMock()
    store.list_pages.return_value = ["ghost-slug", "real-slug"]

    def _read(slug):
        if slug == "ghost-slug":
            return None  # triggers the `continue` on line 46
        p = MagicMock()
        p.status = "active"
        p.content = "Real content."
        p.orphan = False
        return p

    store.read_page.side_effect = _read
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    # ghost-slug was skipped; real-slug is active and has no inbound links → orphan
    assert "ghost-slug" not in result["orphans"]
    assert "real-slug" in result["orphans"]


async def test_build_page_text_dicts_includes_contradicted_in_link_graph():
    """Contradicted pages contribute to all_page_texts (line 51) so their links count."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({
        "orphan": ("active", "No links."),
        "linker": ("contradicted", "See [[orphan]] for more."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    # The contradicted page links to "orphan" — orphan must NOT be in the orphan list
    assert "orphan" not in result["orphans"]


async def test_search_candidates_content_bm25_no_search():
    """content_bm25 with ctx.search=None returns error result (line 212)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    store = _make_wiki_store({"orphan": ("active", "Content about quantum computing.")})
    ctx, _ = _make_ctx(store=store, search=None)
    result = await tool_search_orphan_candidates(ctx, "orphan", "content_bm25", [])
    assert result["candidates"] == []
    assert "error" in result


async def test_search_candidates_content_bm25_empty_page_content():
    """content_bm25 with a page that has no content returns empty candidates (line 216)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    search = _make_search_mock([("other", 0.9)])
    store = _make_wiki_store({
        "orphan": ("active", ""),   # empty content
        "other":  ("active", "Content."),
    })
    ctx, _ = _make_ctx(store=store, search=search)
    result = await tool_search_orphan_candidates(ctx, "orphan", "content_bm25", [])
    assert result["strategy"] == "content_bm25"
    assert result["candidates"] == []


async def test_search_candidates_full_title_scan_no_store():
    """full_title_scan with ctx.store=None returns error result (line 231)."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_search_orphan_candidates
    ctx, _ = _make_ctx(store=None, search=None)
    result = await tool_search_orphan_candidates(ctx, "orphan", "full_title_scan", [])
    assert result["candidates"] == []
    assert "error" in result


def test_initial_hints_broken_wikilinks_chip():
    """'Scan for broken wikilinks' chip appears when broken_wikilinks > 0 (hint_engine line 281)."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "HEALTH_CHECK", context={"contradicted": 0, "stale": 0, "orphan": 0, "broken_wikilinks": 1}
    )
    assert "Scan for broken wikilinks" in hints


def test_initial_hints_broken_citations_chip():
    """'Fix broken citations' chip appears when broken_citations > 0 (hint_engine line 283)."""
    from synthadoc.agents.hint_engine import HintEngine
    hints = HintEngine.initial_hints(
        "HEALTH_CHECK", context={"contradicted": 0, "stale": 0, "orphan": 0, "broken_citations": 1}
    )
    assert "Fix broken citations" in hints
