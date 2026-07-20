# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for LintAgent truncation warnings (Task 5)."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from synthadoc.agents.lint_agent import LintAgent
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef, LifecycleState


def make_source(hash_val: str, file: str = "doc.pdf") -> SourceRef:
    return SourceRef(file=file, hash=hash_val, size=1000, ingested="2026-01-01")


def make_page(sources=None, content="# Test\n\nContent.", status=LifecycleState.ACTIVE):
    """Helper to create a WikiPage."""
    return WikiPage(
        title="Test",
        tags=[],
        content=content,
        status=status,
        confidence="medium",
        sources=sources or [],
    )


def make_store(tmp_path, pages_dict):
    """Helper to create a WikiStorage and populate it with pages."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    for slug, page in pages_dict.items():
        store.write_page(slug, page)
    return store


def mock_provider():
    """Create a mock LLM provider."""
    provider = AsyncMock()
    return provider


def mock_log_writer():
    """Create a mock log writer."""
    log = MagicMock()
    log.log_lint = MagicMock()
    return log


async def test_lint_warns_truncated_source(tmp_path):
    """lint emits a WARN for pages with truncated=True sources."""
    page = make_page(sources=[SourceRef(
        file="papers/big.pdf", hash="x", size=90000, ingested="2026-01-01", truncated=True
    )])
    store = make_store(tmp_path, {"quantum-computing": page})
    agent = LintAgent(mock_provider(), store, mock_log_writer())
    report = await agent.lint(scope="all", adversarial=False, lifecycle=False)
    warns = [w for w in report.warnings if "truncated" in w.lower()]
    assert len(warns) >= 1
    assert "papers/big.pdf" in warns[0]
    assert "--max-source-chars" in warns[0]


async def test_lint_no_warn_when_not_truncated(tmp_path):
    """lint does not emit a WARN for pages with truncated=False sources."""
    page = make_page(sources=[SourceRef(
        file="papers/small.pdf", hash="x", size=1000, ingested="2026-01-01", truncated=False
    )])
    store = make_store(tmp_path, {"quantum-computing": page})
    agent = LintAgent(mock_provider(), store, mock_log_writer())
    report = await agent.lint(scope="all", adversarial=False, lifecycle=False)
    warns = [w for w in report.warnings if "truncated" in w.lower()]
    assert len(warns) == 0


# ---------------------------------------------------------------------------
# Task 11: _build_graph() — wikilink extraction + Louvain clustering
# ---------------------------------------------------------------------------

def test_build_graph_basic_edges(tmp_path):
    """_build_graph extracts undirected edges from wikilinks (one edge per pair)."""
    pages = {
        "a": make_page(content="links to [[b]] and [[c]]"),
        "b": make_page(content="links to [[a]]"),
        "c": make_page(content="no links"),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    nodes, edges = agent._build_graph()
    slugs = {n["slug"] for n in nodes}
    assert slugs == {"a", "b", "c"}
    # Graph is undirected: check as unordered pairs
    edge_sets = {frozenset((e["from_slug"], e["to_slug"])) for e in edges}
    assert frozenset(("a", "b")) in edge_sets
    assert frozenset(("a", "c")) in edge_sets
    # a↔b is one edge (not two); b→a wikilink and a→b wikilink collapse into one undirected edge
    assert len([e for e in edges if frozenset((e["from_slug"], e["to_slug"])) == frozenset(("a", "b"))]) == 1


def test_build_graph_multi_link_weight(tmp_path):
    """Multiple [[slug]] references to same target accumulate weight."""
    pages = {
        "a": make_page(content="[[b]] and again [[b]]"),
        "b": make_page(content=""),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    nodes, edges = agent._build_graph()
    ab = next(e for e in edges if frozenset((e["from_slug"], e["to_slug"])) == frozenset(("a", "b")))
    assert ab["weight"] == 2


def test_build_graph_empty_wiki(tmp_path):
    """Empty wiki produces empty nodes and edges."""
    store = make_store(tmp_path, {})
    agent = LintAgent(None, store, mock_log_writer())
    nodes, edges = agent._build_graph()
    assert nodes == []
    assert edges == []


def test_build_graph_single_node_no_edges(tmp_path):
    """Single page with no wikilinks — node present, no edges."""
    store = make_store(tmp_path, {"a": make_page(content="no links here")})
    agent = LintAgent(None, store, mock_log_writer())
    nodes, edges = agent._build_graph()
    assert len(nodes) == 1
    assert edges == []


def test_build_graph_self_link_ignored(tmp_path):
    """[[self]] wikilink on a page is ignored."""
    store = make_store(tmp_path, {"a": make_page(content="see [[a]] for details")})
    agent = LintAgent(None, store, mock_log_writer())
    nodes, edges = agent._build_graph()
    assert edges == []


def test_build_graph_cluster_ids_are_integers(tmp_path):
    """All cluster_id values are non-negative integers."""
    store = make_store(tmp_path, {
        "a": make_page(content="[[b]]"),
        "b": make_page(content="[[c]]"),
        "c": make_page(content=""),
    })
    agent = LintAgent(None, store, mock_log_writer())
    nodes, _ = agent._build_graph()
    for n in nodes:
        assert isinstance(n["cluster_id"], int)
        assert n["cluster_id"] >= 0


def test_build_graph_pipe_alias_link_resolved(tmp_path):
    """[[slug|display]] links should produce edges using the slug, not 'slug|display'."""
    pages = {
        "a": make_page(content="see [[b|Page B]] for details"),
        "b": make_page(content=""),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    nodes, edges = agent._build_graph()
    edge_sets = {frozenset((e["from_slug"], e["to_slug"])) for e in edges}
    assert frozenset(("a", "b")) in edge_sets, "pipe-alias link should produce edge a↔b"


def test_build_graph_wikilink_edge_type(tmp_path):
    """Pure wikilink edges get edge_type='wikilink'."""
    pages = {
        "a": make_page(content="see [[b]]"),
        "b": make_page(content=""),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    _, edges = agent._build_graph()
    ab = next(e for e in edges if frozenset((e["from_slug"], e["to_slug"])) == frozenset(("a", "b")))
    assert ab["edge_type"] == "wikilink"


def test_build_graph_co_source_edge(tmp_path):
    """Pages sharing a source hash produce one undirected co_source edge with +2 weight per shared hash."""
    src = make_source("sha256abc")
    pages = {
        "a": make_page(content="no links", sources=[src]),
        "b": make_page(content="no links", sources=[src]),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    _, edges = agent._build_graph()
    # Single undirected co-source edge (not two directed edges)
    ab_edges = [e for e in edges if frozenset((e["from_slug"], e["to_slug"])) == frozenset(("a", "b"))]
    assert len(ab_edges) == 1, "exactly one co-source edge between a and b expected"
    edge = ab_edges[0]
    assert edge["weight"] == 2  # 1 shared source × 2
    assert edge["edge_type"] == "co_source"


def test_build_graph_mixed_edge(tmp_path):
    """Wikilink + shared source hash produces edge_type='mixed' with accumulated weight."""
    src = make_source("sha256xyz")
    pages = {
        "a": make_page(content="links to [[b]]", sources=[src]),
        "b": make_page(content="", sources=[src]),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    _, edges = agent._build_graph()
    ab = next(e for e in edges if frozenset((e["from_slug"], e["to_slug"])) == frozenset(("a", "b")))
    # wikilink weight=1, co-source weight=2 → total 3
    assert ab["weight"] == 3
    assert ab["edge_type"] == "mixed"


def test_build_graph_co_source_two_shared(tmp_path):
    """Two shared source hashes contribute +4 to co-source weight."""
    pages = {
        "x": make_page(content="", sources=[make_source("h1", "a.pdf"), make_source("h2", "b.pdf")]),
        "y": make_page(content="", sources=[make_source("h1", "a.pdf"), make_source("h2", "b.pdf")]),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    _, edges = agent._build_graph()
    xy = next(e for e in edges if frozenset((e["from_slug"], e["to_slug"])) == frozenset(("x", "y")))
    assert xy["weight"] == 4  # 2 shared sources × 2
    assert xy["edge_type"] == "co_source"


def test_build_graph_excludes_archived_pages(tmp_path):
    """Archived pages must not appear as graph nodes on a full rebuild.

    Regression: before the fix, _build_graph() read all .md files from disk
    without filtering by lifecycle state, so a server restart would re-add
    archived pages to the graph (contradicting the node deletion performed by
    cascade_archive() at archive time).
    """
    pages = {
        "active-page": make_page(content="see [[other-active]]", status=LifecycleState.ACTIVE),
        "other-active": make_page(content="", status=LifecycleState.ACTIVE),
        "archived-page": make_page(content="", status=LifecycleState.ARCHIVED),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    nodes, _ = agent._build_graph()
    slugs = {n["slug"] for n in nodes}
    assert "archived-page" not in slugs
    assert "active-page" in slugs
    assert "other-active" in slugs


def test_build_graph_excludes_draft_pages(tmp_path):
    """Draft pages must not appear in the graph — they are unreviewed content.

    Only active, stale, and contradicted pages belong in the validated knowledge
    network represented by the graph.
    """
    pages = {
        "active-page": make_page(content="see [[draft-page]]", status=LifecycleState.ACTIVE),
        "draft-page": make_page(content="", status=LifecycleState.DRAFT),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    nodes, _ = agent._build_graph()
    slugs = {n["slug"] for n in nodes}
    assert "draft-page" not in slugs
    assert "active-page" in slugs


def test_build_graph_includes_stale_and_contradicted(tmp_path):
    """Stale and contradicted pages are still part of the knowledge network and must appear."""
    pages = {
        "active-page": make_page(content="see [[stale-page]] and [[contradicted-page]]",
                                 status=LifecycleState.ACTIVE),
        "stale-page": make_page(content="", status=LifecycleState.STALE),
        "contradicted-page": make_page(content="", status=LifecycleState.CONTRADICTED),
    }
    store = make_store(tmp_path, pages)
    agent = LintAgent(None, store, mock_log_writer())
    nodes, _ = agent._build_graph()
    slugs = {n["slug"] for n in nodes}
    assert "stale-page" in slugs
    assert "contradicted-page" in slugs
