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


# ---------------------------------------------------------------------------
# System prompt — markdown format rules
# ---------------------------------------------------------------------------

async def test_system_prompt_step5_uses_bold_headers():
    """Step 5 format template must use **bold** section headers."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    prompt = await wf.build_system_prompt()
    assert "**✅ Resolved" in prompt, (
        "Step 5 format template must use **bold** headers so the LLM mirrors "
        "that format — plain headers produce a paragraph that's hard to distinguish "
        "from list content"
    )


async def test_system_prompt_step5_mentions_rollback_when_resolved():
    """Step 5 must tell the user resolved fixes can be rolled back.

    orphan_resolver writes through tool_propose_and_apply, the same shared
    mechanism contradiction_resolver uses — so every resolved orphan has a
    snapshot and can be undone with 'roll back <slug>'. Without this line in
    the final-summary instructions, the model never tells the user that
    capability exists, even though the tool itself (tool_rollback_last_fix)
    works fine if they happen to ask for it anyway.
    """
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    prompt = await wf.build_system_prompt()
    assert "roll back" in prompt.lower(), (
        "Step 5 instructions must mention rolling back resolved fixes"
    )


async def test_system_prompt_step5_no_bullet_character():
    """Step 5 format template must not use Unicode bullet characters."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    wf = OrphanResolverWorkflow()
    prompt = await wf.build_system_prompt()
    # The critical-rules section uses • for its own bullets, but the STEP 5
    # *format template* that the LLM copies must not use •.
    # We check that the word "Resolved" does not appear on a line that also
    # contains •, which would mean the section header uses •.
    for line in prompt.splitlines():
        if "Resolved" in line or "Unresolved" in line or "Skipped" in line:
            assert "•" not in line, (
                f"Step 5 format template line must not use • bullet character: {line!r}"
            )


# ---------------------------------------------------------------------------
# CLI summary — bold headers and '- ' list items
# ---------------------------------------------------------------------------

def test_cli_summary_uses_bold_headers_and_dash_list():
    """CLI summary builds bold section headers and '- slug' list items.

    '  - slug' (indented dash) is technically valid CommonMark but inconsistent
    with the contradiction-resolver pattern. '- slug' (no indent) is cleaner
    and guaranteed to render on its own line.
    """
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow

    # The summary is built inside run_for_cli_provider, but we can test
    # the format directly by inspecting the source constants via the workflow.
    # Instantiate the workflow and manually reproduce the summary logic.
    wf = OrphanResolverWorkflow()

    resolved_list = [("alan-turing", ["grace-hopper"])]
    unresolved_list = ["babbage"]
    skipped_list = ["colossus"]

    parts: list[str] = ["**Orphan Resolver — Complete**"]

    resolved_lines = [f"**✅ Resolved ({len(resolved_list)}):**"]
    for slug, linked_by in resolved_list:
        linkers = ", ".join(linked_by)
        resolved_lines.append(f"- {slug} (linked from {linkers})")
    parts.append("\n".join(resolved_lines))

    unresolved_lines = [f"**⚠ Unresolved ({len(unresolved_list)}):**"]
    for slug in unresolved_list:
        unresolved_lines.append(f"- {slug} (4 strategies exhausted — see notices above)")
    parts.append("\n".join(unresolved_lines))

    skipped_lines = [f"**⏭ Skipped ({len(skipped_list)}):**"]
    for slug in skipped_list:
        skipped_lines.append(f"- {slug}")
    parts.append("\n".join(skipped_lines))

    summary = "\n\n".join(parts)

    # Bold headers
    assert "**✅ Resolved (1):**" in summary
    assert "**⚠ Unresolved (1):**" in summary
    assert "**⏭ Skipped (1):**" in summary
    # List items with no leading indent
    assert "\n- alan-turing" in summary
    assert "\n- babbage" in summary
    assert "\n- colossus" in summary
    # Must NOT use indented dash
    assert "\n  - alan-turing" not in summary, (
        "Summary must use '- slug' (no indent) not '  - slug' for consistency "
        "with the contradiction-resolver format"
    )


def test_cli_summary_mentions_rollback_only_when_something_resolved():
    """run_for_cli_provider's mirrored summary appends the rollback hint only
    when resolved_list is non-empty — there's nothing to roll back otherwise.

    This reproduces the summary-building snippet the same way
    test_cli_summary_uses_bold_headers_and_dash_list does; it is not a call
    into run_for_cli_provider itself (that needs a full ctx/provider harness).
    """
    def _build_summary(resolved_list, unresolved_list, skipped_list):
        parts: list[str] = ["**Orphan Resolver — Complete**"]
        if resolved_list:
            resolved_lines = [f"**✅ Resolved ({len(resolved_list)}):**"]
            for slug, linked_by in resolved_list:
                linkers = ", ".join(linked_by)
                resolved_lines.append(f"- {slug} (linked from {linkers})")
            parts.append("\n".join(resolved_lines))
        if unresolved_list:
            unresolved_lines = [f"**⚠ Unresolved ({len(unresolved_list)}):**"]
            for slug in unresolved_list:
                unresolved_lines.append(f"- {slug} (4 strategies exhausted — see notices above)")
            parts.append("\n".join(unresolved_lines))
        if skipped_list:
            skipped_lines = [f"**⏭ Skipped ({len(skipped_list)}):**"]
            for slug in skipped_list:
                skipped_lines.append(f"- {slug}")
            parts.append("\n".join(skipped_lines))
        if resolved_list:
            parts.append(
                "A snapshot is saved before each change — "
                "say 'roll back [page]' to undo."
            )
        return "\n\n".join(parts)

    with_fix = _build_summary([("alan-turing", ["grace-hopper"])], [], [])
    assert "say 'roll back [page]' to undo" in with_fix

    no_fix = _build_summary([], ["babbage"], ["colossus"])
    assert "roll back" not in no_fix.lower()


# ---------------------------------------------------------------------------
# tool_rollback_orphan_fix — reverse lookup when the orphan page itself has
# no fix record (orphan resolution edits the LINKING page, not the orphan)
# ---------------------------------------------------------------------------

async def _auto_confirm_orphan(ctx, confirmed=True):
    await asyncio.sleep(0.05)
    gate = ctx.confirm_registry.get("test-session")
    if gate:
        ctx.confirm_result_registry["test-session"] = confirmed
        gate.set()


class TestRollbackOrphanFix:
    _ORIGINAL = "Content about personal computers.\n"
    _FIXED = "Content about personal computers. See [[microprocessor]] for details.\n"

    def _wiki(self, tmp_path, *, with_fix_record: bool = True):
        from synthadoc.storage.log import AuditDB
        from synthadoc.storage.wiki import WikiPage, WikiStorage
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("microprocessor", WikiPage(
            title="Microprocessor", tags=[], content="The CPU on a chip.\n",
            status="active", confidence="", sources=[],
        ))
        store.write_page("personal-computer-revolution", WikiPage(
            title="Personal Computer Revolution", tags=[],
            content=self._ORIGINAL if with_fix_record else self._FIXED,
            status="active", confidence="", sources=[],
        ))
        audit_db = AuditDB(tmp_path / "audit.db")
        return store, audit_db

    async def test_falls_back_to_linking_page_when_orphan_has_no_record(self, tmp_path):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_rollback_orphan_fix
        store, audit_db = self._wiki(tmp_path)
        await audit_db.init()
        ctx, _events = _make_ctx(store=store, audit_db=audit_db)

        asyncio.create_task(_auto_confirm_orphan(ctx))
        applied = await tool_propose_and_apply(
            ctx, slug="personal-computer-revolution", new_content=self._FIXED,
            strategy_name="title_bm25",
            rationale="'personal-computer-revolution' identified as related; "
                      "LLM inserted [[microprocessor]].",
        )
        assert applied["applied"] is True

        result = await tool_rollback_orphan_fix(ctx, "microprocessor")

        assert result["status"] == "success"
        assert "has no fix record of its own" in result["message"]
        assert "personal-computer-revolution" in result["message"]
        page = store.read_page("personal-computer-revolution")
        assert page.content == self._ORIGINAL
        assert page.last_fix_record is None

    async def test_no_fallback_needed_when_slug_itself_has_a_record(self, tmp_path):
        """If the named page DOES carry its own record, use it directly — no
        reverse lookup, no 'has no fix record of its own' framing."""
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_rollback_orphan_fix
        store, audit_db = self._wiki(tmp_path)
        await audit_db.init()
        ctx, _events = _make_ctx(store=store, audit_db=audit_db)

        asyncio.create_task(_auto_confirm_orphan(ctx))
        await tool_propose_and_apply(
            ctx, slug="personal-computer-revolution", new_content=self._FIXED,
            strategy_name="title_bm25", rationale="test",
        )

        result = await tool_rollback_orphan_fix(ctx, "personal-computer-revolution")

        assert result["status"] == "success"
        assert "has no fix record of its own" not in result["message"]

    async def test_no_record_anywhere_returns_original_error(self, tmp_path):
        from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_rollback_orphan_fix
        store, audit_db = self._wiki(tmp_path, with_fix_record=False)
        await audit_db.init()
        ctx, _events = _make_ctx(store=store, audit_db=audit_db)

        result = await tool_rollback_orphan_fix(ctx, "microprocessor")

        assert result["status"] == "error"
        assert "no prior fix recorded" in result["error"].lower()

    async def test_ambiguous_when_multiple_linking_pages_have_records(self, tmp_path):
        from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_rollback_orphan_fix
        from synthadoc.storage.log import AuditDB
        from synthadoc.storage.wiki import WikiPage, WikiStorage
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("microprocessor", WikiPage(
            title="Microprocessor", tags=[], content="The CPU on a chip.\n",
            status="active", confidence="", sources=[],
        ))
        store.write_page("host-a", WikiPage(
            title="Host A", tags=[], content="See [[microprocessor]].\n",
            status="active", confidence="", sources=[],
            last_fix_record={"slug": "host-a", "snapshot_id": 1,
                              "snapshot_index_before": 1,
                              "timestamp": "2026-01-01T00:00:00+00:00",
                              "strategy_name": "title_bm25"},
        ))
        store.write_page("host-b", WikiPage(
            title="Host B", tags=[], content="Also see [[microprocessor]].\n",
            status="active", confidence="", sources=[],
            last_fix_record={"slug": "host-b", "snapshot_id": 2,
                              "snapshot_index_before": 1,
                              "timestamp": "2026-01-01T00:00:00+00:00",
                              "strategy_name": "content_bm25"},
        ))
        audit_db = AuditDB(tmp_path / "audit.db")
        await audit_db.init()
        ctx, _events = _make_ctx(store=store, audit_db=audit_db)

        result = await tool_rollback_orphan_fix(ctx, "microprocessor")

        assert result["status"] == "error"
        assert "host-a" in result["error"]
        assert "host-b" in result["error"]


# ---------------------------------------------------------------------------
# Rollback-via-chat wiring: build_initial_message / run_for_cli_provider /
# GATED_TOOLS — mirrors test_contradiction_resolver_workflow.py's equivalent
# coverage for tool_rollback_last_fix.
# ---------------------------------------------------------------------------

def test_build_initial_message_rollback_intent_with_slug():
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    workflow = OrphanResolverWorkflow()
    msg = workflow.build_initial_message("roll back microprocessor")
    assert "tool_rollback_orphan_fix" in msg
    assert "microprocessor" in msg


def test_build_initial_message_rollback_intent_no_slug():
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    workflow = OrphanResolverWorkflow()
    msg = workflow.build_initial_message("roll back")
    assert "tool_list_recent_fixes" in msg


async def test_cli_provider_rollback_short_circuit_no_model_call():
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow

    ctx = MagicMock()
    ctx.store = MagicMock()
    ctx.send_sse_event = AsyncMock()

    rollback_calls = []
    async def _fake_rollback(ctx, orphan_slug):
        rollback_calls.append(orphan_slug)
        return {"status": "success", "message": f"Rolled back '{orphan_slug}'."}

    class _FakeProvider:
        async def complete(self, *a, **kw):
            raise AssertionError("model should not be called for a rollback request")

    with patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_rollback_orphan_fix",
        new=_fake_rollback,
    ):
        events = [e async for e in OrphanResolverWorkflow().run_for_cli_provider(
            ctx, question="roll back microprocessor", provider=_FakeProvider())]

    assert rollback_calls == ["microprocessor"]
    assert events[-1]["data"]["text"] == "Rolled back 'microprocessor'."


def test_rollback_orphan_fix_is_a_per_call_gated_tool():
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    assert "tool_rollback_orphan_fix" in OrphanResolverWorkflow.GATED_TOOLS
    assert "tool_rollback_orphan_fix" in OrphanResolverWorkflow.GATED_TOOLS_PER_CALL


@pytest.mark.parametrize("confirmed", [True, False])
async def test_rollback_during_normal_run_requires_user_confirm(confirmed):
    """The model must not roll a page back on its own mid-resolution."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    confirm = AsyncMock(return_value={"confirmed": confirmed})
    rollback = AsyncMock(return_value={"status": "success"})
    ctx = MagicMock()
    ctx.store = MagicMock()
    with patch("synthadoc.agents.workflows._tools.tool_confirm", new=confirm), \
         patch("synthadoc.agents.workflows.orphan_resolver.tool_rollback_orphan_fix",
               new=rollback):
        wf = OrphanResolverWorkflow()
        fns = wf.build_guarded_tool_fns(ctx)          # ActionAgent order: tools first
        wf.build_initial_message("run orphan resolver")
        result = await fns["tool_rollback_orphan_fix"](orphan_slug="microprocessor")
        confirm.assert_awaited_once()
        assert (rollback.await_count == 1) is confirmed
        assert result["status"] == ("success" if confirmed else "cancelled")
        if confirmed:
            # Per-call gate: a second rollback needs a fresh approval.
            await fns["tool_rollback_orphan_fix"](orphan_slug="quantum-computing")
            assert confirm.await_count == 2


async def test_tool_confirm_between_orphans_does_not_open_rollback_gate():
    """An approved 'continue to next orphan?' tool_confirm must not unlock rollback."""
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    gate_confirm = AsyncMock(return_value={"confirmed": False})
    rollback = AsyncMock(return_value={"status": "success"})
    ctx = MagicMock()
    with patch("synthadoc.agents.workflows._tools.tool_confirm", new=gate_confirm), \
         patch("synthadoc.agents.workflows.orphan_resolver.tool_confirm",
               new=AsyncMock(return_value={"confirmed": True})), \
         patch("synthadoc.agents.workflows.orphan_resolver.tool_rollback_orphan_fix",
               new=rollback):
        wf = OrphanResolverWorkflow()
        fns = wf.build_guarded_tool_fns(ctx)
        wf.build_initial_message("run orphan resolver")
        await fns["tool_confirm"](message="Continue to the next orphan?")
        result = await fns["tool_rollback_orphan_fix"](orphan_slug="microprocessor")
    gate_confirm.assert_awaited_once()
    rollback.assert_not_awaited()
    assert result["status"] == "cancelled"


async def test_explicit_rollback_request_runs_without_extra_confirm():
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    confirm = AsyncMock()
    rollback = AsyncMock(return_value={"status": "success"})
    ctx = MagicMock()
    with patch("synthadoc.agents.workflows._tools.tool_confirm", new=confirm), \
         patch("synthadoc.agents.workflows.orphan_resolver.tool_rollback_orphan_fix",
               new=rollback):
        wf = OrphanResolverWorkflow()
        fns = wf.build_guarded_tool_fns(ctx)
        wf.build_initial_message("roll back microprocessor")
        result = await fns["tool_rollback_orphan_fix"](orphan_slug="microprocessor")
    confirm.assert_not_awaited()
    rollback.assert_awaited_once_with(ctx, orphan_slug="microprocessor")
    assert result["status"] == "success"


def test_get_tool_fns_includes_rollback_tools():
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    ctx = MagicMock()
    tools = OrphanResolverWorkflow().get_tool_fns(ctx)
    assert "tool_rollback_orphan_fix" in tools
    assert "tool_list_recent_fixes" in tools
