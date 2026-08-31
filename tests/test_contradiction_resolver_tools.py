# tests/test_contradiction_resolver_tools.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for the 3 contradiction-specific tools in contradiction_resolver_tools.py."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from synthadoc.storage.wiki import WikiPage, WikiStorage, LifecycleState


def _make_store(tmp_path: Path, pages: dict) -> WikiStorage:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    for slug, page in pages.items():
        store.write_page(slug, page)
    return store


def _contradicted(warnings=None, note=None, sources=None):
    # Use `is None` check so that an explicit empty list means "no warnings"
    return WikiPage(
        title="T", tags=[], content="body",
        status=LifecycleState.CONTRADICTED, confidence="high",
        sources=sources if sources is not None else [],
        lint_warnings=warnings if warnings is not None else [{"claim": "c", "concern": "dubious"}],
        contradiction_note=note,
    )


def _ctx(tmp_path, store):
    ctx = MagicMock()
    ctx.wiki_root = tmp_path
    ctx.store = store
    ctx.send_sse_event = AsyncMock()
    ctx.audit_db = AsyncMock()
    ctx.queue = AsyncMock()
    ctx.session_id = "s"
    return ctx


# ── tool_get_contradicted_pages ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_contradicted_pages_all_returns_only_contradicted(tmp_path):
    pages = {
        "c1": _contradicted(warnings=[{"claim": "x"}]),
        "active1": WikiPage(title="A", tags=[], content="",
                            status=LifecycleState.ACTIVE, confidence="high", sources=[]),
    }
    store = _make_store(tmp_path, pages)
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_get_contradicted_pages
    result = await tool_get_contradicted_pages(ctx, scope="all")
    slugs = [p["slug"] for p in result["pages"]]
    assert "c1" in slugs
    assert "active1" not in slugs


@pytest.mark.asyncio
async def test_get_contradicted_pages_gate_scope(tmp_path):
    pages = {
        "gate": _contradicted(warnings=[{"claim": "x"}], note=None),
        "conflict": _contradicted(warnings=[], note="conflict note"),
    }
    store = _make_store(tmp_path, pages)
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_get_contradicted_pages
    result = await tool_get_contradicted_pages(ctx, scope="gate")
    slugs = [p["slug"] for p in result["pages"]]
    assert "gate" in slugs
    assert "conflict" not in slugs


@pytest.mark.asyncio
async def test_get_contradicted_pages_conflict_scope(tmp_path):
    pages = {
        "gate": _contradicted(warnings=[{"claim": "x"}], note=None),
        "conflict": _contradicted(warnings=[], note="conflict note"),
    }
    store = _make_store(tmp_path, pages)
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_get_contradicted_pages
    result = await tool_get_contradicted_pages(ctx, scope="conflict")
    slugs = [p["slug"] for p in result["pages"]]
    assert "conflict" in slugs
    assert "gate" not in slugs


@pytest.mark.asyncio
async def test_get_contradicted_pages_type_classification(tmp_path):
    pages = {
        "gate": _contradicted(warnings=[{"claim": "x"}], note=None),
        "conflict": _contradicted(warnings=[], note="note"),
        "both": _contradicted(warnings=[{"claim": "x"}], note="note"),
        "unknown": _contradicted(warnings=[], note=None),
    }
    store = _make_store(tmp_path, pages)
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_get_contradicted_pages
    result = await tool_get_contradicted_pages(ctx, scope="all")
    by_slug = {p["slug"]: p["type"] for p in result["pages"]}
    assert by_slug["gate"] == "gate"
    assert by_slug["conflict"] == "conflict"
    assert by_slug["both"] == "both"
    assert by_slug["unknown"] == "unknown"


@pytest.mark.asyncio
async def test_get_contradicted_pages_both_type_included_in_gate_scope(tmp_path):
    """A 'both'-type page (warnings + note) must appear under scope='gate'."""
    pages = {
        "both": _contradicted(warnings=[{"claim": "x"}], note="conflict note"),
        "conflict_only": _contradicted(warnings=[], note="conflict note"),
    }
    store = _make_store(tmp_path, pages)
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_get_contradicted_pages
    result = await tool_get_contradicted_pages(ctx, scope="gate")
    slugs = [p["slug"] for p in result["pages"]]
    assert "both" in slugs, "'both' page must appear under scope='gate'"
    assert "conflict_only" not in slugs


@pytest.mark.asyncio
async def test_get_contradicted_pages_both_type_included_in_conflict_scope(tmp_path):
    """A 'both'-type page (warnings + note) must appear under scope='conflict'."""
    pages = {
        "both": _contradicted(warnings=[{"claim": "x"}], note="conflict note"),
        "gate_only": _contradicted(warnings=[{"claim": "x"}], note=None),
    }
    store = _make_store(tmp_path, pages)
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_get_contradicted_pages
    result = await tool_get_contradicted_pages(ctx, scope="conflict")
    slugs = [p["slug"] for p in result["pages"]]
    assert "both" in slugs, "'both' page must appear under scope='conflict'"
    assert "gate_only" not in slugs


# ── tool_read_source_content ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_source_from_raw_sources(tmp_path):
    from synthadoc.storage.wiki import SourceRef
    (tmp_path / "raw_sources").mkdir()
    (tmp_path / "raw_sources" / "src.txt").write_text("source text", encoding="utf-8")
    page = _contradicted(sources=[SourceRef(file="src.txt", hash="abc", size=11, ingested="2026-01-01")])
    store = _make_store(tmp_path, {"p": page})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    result = await tool_read_source_content(ctx, slug="p")
    assert result["source_text"] == "source text"
    assert result["fallback_used"] == "raw_sources"


@pytest.mark.asyncio
async def test_read_source_fallback_to_note(tmp_path):
    page = _contradicted(note="Source A vs B", sources=[])
    store = _make_store(tmp_path, {"p": page})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    result = await tool_read_source_content(ctx, slug="p")
    assert result["fallback_used"] == "contradiction_note"
    assert "Source A vs B" in result["source_text"]


@pytest.mark.asyncio
async def test_read_source_fallback_none(tmp_path):
    page = _contradicted(note=None, sources=[])
    store = _make_store(tmp_path, {"p": page})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    result = await tool_read_source_content(ctx, slug="p")
    assert result["fallback_used"] == "none"
    assert result["source_text"] == ""


# ── tool_cost_estimate ────────────────────────────────────────────────────────
# tool_cost_estimate now calls tool_confirm internally (via a deferred import
# from _tools.py), so all tests must patch that dependency.

_CONFIRM_PATCH = "synthadoc.agents.workflows._tools.tool_confirm"


@pytest.mark.asyncio
async def test_cost_estimate_positive_values(tmp_path):
    """Returns correct estimate fields and forwards confirmed=True from tool_confirm."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    with patch(_CONFIRM_PATCH, new_callable=AsyncMock,
               return_value={"confirmed": True}):
        from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_cost_estimate
        result = await tool_cost_estimate(ctx, page_count=4)
    assert result["pages"] == 4
    assert result["estimated_tokens"] > 0
    assert result["estimated_usd"] >= 0.0
    assert result["estimated_minutes"] > 0
    assert result["confirmed"] is True


@pytest.mark.asyncio
async def test_cost_estimate_single_page(tmp_path):
    """Scaling: 4-page estimate has more tokens than 1-page estimate."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    with patch(_CONFIRM_PATCH, new_callable=AsyncMock,
               return_value={"confirmed": True}):
        from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_cost_estimate
        one = await tool_cost_estimate(ctx, page_count=1)
        four = await tool_cost_estimate(ctx, page_count=4)
    assert four["estimated_tokens"] > one["estimated_tokens"]


@pytest.mark.asyncio
async def test_cost_estimate_sends_notice_sse(tmp_path):
    """tool_cost_estimate emits a notice SSE event with the formatted estimate."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    with patch(_CONFIRM_PATCH, new_callable=AsyncMock,
               return_value={"confirmed": True}):
        from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_cost_estimate
        await tool_cost_estimate(ctx, page_count=3)
    ctx.send_sse_event.assert_awaited_once()
    event_name, event_data = ctx.send_sse_event.call_args.args
    assert event_name == "notice"
    assert "3" in event_data["text"]  # page count mentioned in notice text


@pytest.mark.asyncio
async def test_cost_estimate_confirmed_false_propagates(tmp_path):
    """When tool_confirm returns confirmed=False, the result reflects that."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    with patch(_CONFIRM_PATCH, new_callable=AsyncMock,
               return_value={"confirmed": False}):
        from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_cost_estimate
        result = await tool_cost_estimate(ctx, page_count=2)
    assert result["confirmed"] is False
    # Estimate fields must still be present even on cancellation
    assert result["pages"] == 2
    assert "estimated_usd" in result


# ── extra coverage: extracted fallback and missing page ──────────────────────

@pytest.mark.asyncio
async def test_read_source_fallback_to_extracted(tmp_path):
    """Covers the .synthadoc/extracted/ fallback path."""
    from synthadoc.storage.wiki import SourceRef
    extracted_dir = tmp_path / ".synthadoc" / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    (extracted_dir / "report.txt").write_text("extracted content", encoding="utf-8")
    # raw_sources/ exists but does NOT contain the file
    (tmp_path / "raw_sources").mkdir()
    page = _contradicted(sources=[SourceRef(file="report.pdf", hash="abc", size=100, ingested="2026-01-01")])
    store = _make_store(tmp_path, {"q": page})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    result = await tool_read_source_content(ctx, slug="q")
    assert result["fallback_used"] == "extracted"
    assert "extracted content" in result["source_text"]


@pytest.mark.asyncio
async def test_read_source_page_not_found(tmp_path):
    """Covers the 'page not found' branch."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    result = await tool_read_source_content(ctx, slug="does-not-exist")
    assert "error" in result


# ── new edge-case coverage ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_source_empty_file_field_is_skipped(tmp_path):
    """Source with empty file= is skipped; falls through to 'none' fallback (line 85)."""
    from synthadoc.storage.wiki import SourceRef
    page = _contradicted(
        note=None,
        sources=[SourceRef(file="", hash="", size=0, ingested="")],
    )
    store = _make_store(tmp_path, {"p": page})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    result = await tool_read_source_content(ctx, slug="p")
    assert result["fallback_used"] == "none"


@pytest.mark.asyncio
async def test_read_source_raw_oserror_falls_through(tmp_path):
    """OSError reading raw_sources file is silently caught; falls through (lines 93-94)."""
    from pathlib import Path
    from unittest.mock import patch as _patch
    from synthadoc.storage.wiki import SourceRef

    raw_dir = tmp_path / "raw_sources"
    raw_dir.mkdir()
    raw_file = raw_dir / "src.txt"
    raw_file.write_text("something", encoding="utf-8")

    page = _contradicted(note=None, sources=[SourceRef(file="src.txt", hash="", size=0, ingested="")])
    store = _make_store(tmp_path, {"p": page})
    ctx = _ctx(tmp_path, store)

    _orig_read = Path.read_text

    def _raise_for_raw(self, *args, **kwargs):
        if self == raw_file:
            raise OSError("Permission denied")
        return _orig_read(self, *args, **kwargs)

    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    with _patch.object(Path, "read_text", _raise_for_raw):
        result = await tool_read_source_content(ctx, slug="p")
    # raw_sources raised OSError, no extracted copy → fallback_used="none"
    assert result["fallback_used"] == "none"


@pytest.mark.asyncio
async def test_read_source_extracted_oserror_falls_through(tmp_path):
    """OSError reading extracted file is silently caught; falls through (lines 105-106)."""
    from pathlib import Path
    from unittest.mock import patch as _patch
    from synthadoc.storage.wiki import SourceRef

    extracted_dir = tmp_path / ".synthadoc" / "extracted"
    extracted_dir.mkdir(parents=True)
    ext_file = extracted_dir / "src.txt"
    ext_file.write_text("extracted content", encoding="utf-8")

    page = _contradicted(note=None, sources=[SourceRef(file="src.txt", hash="", size=0, ingested="")])
    store = _make_store(tmp_path, {"p": page})
    ctx = _ctx(tmp_path, store)

    _orig_read = Path.read_text

    def _raise_for_extracted(self, *args, **kwargs):
        if self == ext_file:
            raise OSError("Permission denied")
        return _orig_read(self, *args, **kwargs)

    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_read_source_content
    with _patch.object(Path, "read_text", _raise_for_extracted):
        result = await tool_read_source_content(ctx, slug="p")
    assert result["fallback_used"] == "none"


@pytest.mark.asyncio
async def test_cost_estimate_sse_error_is_swallowed(tmp_path):
    """Exception from send_sse_event is swallowed; estimate still returns (lines 148-149)."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    ctx.send_sse_event = AsyncMock(side_effect=RuntimeError("SSE down"))
    with patch(_CONFIRM_PATCH, new_callable=AsyncMock, return_value={"confirmed": True}):
        from synthadoc.agents.workflows.tools.contradiction_resolver_tools import tool_cost_estimate
        result = await tool_cost_estimate(ctx, page_count=2)
    assert result["confirmed"] is True
    assert result["pages"] == 2
