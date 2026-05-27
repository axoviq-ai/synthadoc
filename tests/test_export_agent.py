# tests/test_export_agent.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef, LifecycleState
from synthadoc.agents.export_agent import ExportAgent, ExportOptions


def _make_store(tmp_path: Path) -> WikiStorage:
    store = WikiStorage(tmp_path / "wiki")
    return store


def _write_page(store, slug, title, status, content="", contradiction_note=None, tags=None):
    page = WikiPage(
        title=title, tags=tags or [], content=content, status=status,
        confidence="high", sources=[], created="2026-05-26T00:00:00",
        orphan=False, contradiction_note=contradiction_note,
    )
    store.write_page(slug, page)


def _agent(tmp_path, store):
    return ExportAgent(
        store=store,
        wiki_name="test-wiki",
        audit_db_path=tmp_path / ".synthadoc" / "audit.db",
        routing_path=tmp_path / "ROUTING.md",
    )


@pytest.mark.asyncio
async def test_llms_txt_active_in_pages_section(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "ada-lovelace", "Ada Lovelace", LifecycleState.ACTIVE, "First programmer.")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "## Pages" in result
    assert "[Ada Lovelace](ada-lovelace)" in result


@pytest.mark.asyncio
async def test_llms_txt_contradicted_in_needs_review(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "eniac", "ENIAC", LifecycleState.CONTRADICTED,
                contradiction_note="disputed claim about first computer")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "## Needs Review" in result
    assert "[ENIAC](eniac)" in result
    assert "contradicted" in result


@pytest.mark.asyncio
async def test_llms_txt_stale_in_needs_review(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "vacuum-tubes", "Vacuum Tubes", LifecycleState.STALE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "## Needs Review" in result
    assert "stale" in result


@pytest.mark.asyncio
async def test_llms_txt_archived_omitted(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "old-page", "Old Page", LifecycleState.ARCHIVED)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "old-page" not in result


@pytest.mark.asyncio
async def test_llms_txt_status_active_filter_omits_review_section(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "ada-lovelace", "Ada Lovelace", LifecycleState.ACTIVE, "First programmer.")
    _write_page(store, "eniac", "ENIAC", LifecycleState.CONTRADICTED)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt", status_filter="active"))
    assert "## Pages" in result
    assert "[Ada Lovelace]" in result
    assert "## Needs Review" not in result
    assert "eniac" not in result


@pytest.mark.asyncio
async def test_llms_full_txt_contains_page_content(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE,
                content="Babbage designed the Difference Engine.^[babbage.txt:1-12]")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms-full.txt"))
    assert "# Charles Babbage" in result
    assert "Babbage designed the Difference Engine.^[babbage.txt:1-12]" in result


@pytest.mark.asyncio
async def test_llms_full_txt_has_header_with_count(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "p1", "Page One", LifecycleState.ACTIVE)
    _write_page(store, "p2", "Page Two", LifecycleState.ACTIVE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms-full.txt"))
    assert "2 active" in result


@pytest.mark.asyncio
async def test_empty_wiki_llms_txt(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "# test-wiki" in result


@pytest.mark.asyncio
async def test_empty_wiki_llms_full_txt(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms-full.txt"))
    assert "# test-wiki" in result


@pytest.mark.asyncio
async def test_graphml_has_node_for_each_page(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE)
    _write_page(store, "lovelace", "Ada Lovelace", LifecycleState.ACTIVE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="graphml"))
    assert 'id="babbage"' in result
    assert 'id="lovelace"' in result


@pytest.mark.asyncio
async def test_graphml_node_has_status_attribute(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="graphml"))
    assert "active" in result


@pytest.mark.asyncio
async def test_graphml_node_has_label_key(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="graphml"))
    assert 'attr.name="label"' in result
    assert "Charles Babbage" in result
    # yEd NodeLabel for native label display in yEd
    assert "NodeLabel" in result
    assert 'yfiles.type="nodegraphics"' in result


@pytest.mark.asyncio
async def test_graphml_wikilink_edge_has_wikilink_type(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE,
                content="See also [[lovelace]].")
    _write_page(store, "lovelace", "Ada Lovelace", LifecycleState.ACTIVE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="graphml"))
    assert 'source="babbage"' in result
    assert 'target="lovelace"' in result
    assert "wikilink" in result


@pytest.mark.asyncio
async def test_graphml_routing_branch_on_node(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE)
    routing_path = tmp_path / "ROUTING.md"
    routing_path.write_text("## Pioneers\n- [[babbage]]\n", encoding="utf-8")
    agent = ExportAgent(
        store=store, wiki_name="test-wiki",
        audit_db_path=tmp_path / ".synthadoc" / "audit.db",
        routing_path=routing_path,
    )
    result = await agent.export(ExportOptions(format="graphml"))
    assert "Pioneers" in result


@pytest.mark.asyncio
async def test_graphml_no_self_links(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE,
                content="[[babbage]] is a self-link.")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="graphml"))
    assert 'source="babbage" target="babbage"' not in result


@pytest.mark.asyncio
async def test_graphml_empty_wiki(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="graphml"))
    assert '<?xml version="1.0"' in result
    assert "<graphml" in result


@pytest.mark.asyncio
async def test_json_has_all_six_differentiators(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE,
                content="Babbage designed the Difference Engine.")
    agent = _agent(tmp_path, store)
    import json
    result = json.loads(await agent.export(ExportOptions(format="json")))
    page = result["pages"][0]
    assert "claims" in page                         # differentiator 1
    assert "lifecycle_history" in page              # differentiator 2
    assert "total_compilation_cost_usd" in result   # differentiator 3
    assert "routing" in result                      # differentiator 4
    assert result["wiki"] == "test-wiki"
    assert "exported_at" in result


@pytest.mark.asyncio
async def test_json_status_filter(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "active-page", "Active", LifecycleState.ACTIVE)
    _write_page(store, "stale-page", "Stale", LifecycleState.STALE)
    agent = _agent(tmp_path, store)
    import json
    result = json.loads(await agent.export(ExportOptions(format="json", status_filter="active")))
    slugs = [p["slug"] for p in result["pages"]]
    assert "active-page" in slugs
    assert "stale-page" not in slugs


@pytest.mark.asyncio
async def test_json_page_has_correct_fields(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE,
                content="Content.", tags=["pioneer"])
    agent = _agent(tmp_path, store)
    import json
    result = json.loads(await agent.export(ExportOptions(format="json")))
    page = result["pages"][0]
    assert page["slug"] == "babbage"
    assert page["title"] == "Charles Babbage"
    assert page["status"] == "active"
    assert page["tags"] == ["pioneer"]
    assert "content" in page
    assert "sources" in page
    assert "lint_warnings" in page
    assert page["ingest_cost_usd"] == 0.0
    assert page["ingest_tokens"] == 0


@pytest.mark.asyncio
async def test_json_empty_wiki(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    import json
    result = json.loads(await agent.export(ExportOptions(format="json")))
    assert result["page_count"] == 0
    assert result["pages"] == []


@pytest.mark.asyncio
async def test_json_unknown_format_raises(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    with pytest.raises(ValueError, match="Unknown format"):
        await agent.export(ExportOptions(format="bogus"))


@pytest.mark.asyncio
async def test_json_date_object_created_serializes(tmp_path):
    """yaml.safe_load converts bare YAML dates to datetime.date — must not blow up json.dumps."""
    import datetime, json
    store = _make_store(tmp_path)
    page = WikiPage(
        title="Date Page", tags=[], content="", status=LifecycleState.ACTIVE,
        confidence="high", sources=[], created=datetime.date(2026, 5, 26),
        orphan=False,
    )
    store.write_page("date-page", page)
    agent = _agent(tmp_path, store)
    result = json.loads(await agent.export(ExportOptions(format="json")))
    assert result["pages"][0]["created"] == "2026-05-26"


@pytest.mark.asyncio
async def test_json_page_ingest_cost_aggregates_from_audit_db(tmp_path):
    from synthadoc.storage.log import AuditDB
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE)
    _write_page(store, "lovelace", "Ada Lovelace", LifecycleState.ACTIVE)
    audit_path = tmp_path / ".synthadoc" / "audit.db"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit = AuditDB(audit_path)
    await audit.init()
    # Two source files contributed to babbage, one to lovelace
    await audit.record_ingest("h1", 100, "src1.txt", "babbage", tokens=200, cost_usd=0.001)
    await audit.record_ingest("h2", 200, "src2.txt", "babbage", tokens=300, cost_usd=0.002)
    await audit.record_ingest("h3", 150, "src3.txt", "lovelace", tokens=100, cost_usd=0.0005)
    agent = ExportAgent(
        store=store, wiki_name="test-wiki",
        audit_db_path=audit_path,
        routing_path=tmp_path / "ROUTING.md",
    )
    import json
    result = json.loads(await agent.export(ExportOptions(format="json")))
    pages_by_slug = {p["slug"]: p for p in result["pages"]}
    assert pages_by_slug["babbage"]["ingest_tokens"] == 500
    assert abs(pages_by_slug["babbage"]["ingest_cost_usd"] - 0.003) < 1e-9
    assert pages_by_slug["lovelace"]["ingest_tokens"] == 100
    assert abs(pages_by_slug["lovelace"]["ingest_cost_usd"] - 0.0005) < 1e-9


@pytest.mark.asyncio
async def test_json_date_object_ingested_serializes(tmp_path):
    """yaml.safe_load coerces bare YAML dates to datetime.date — SourceRef.ingested must not blow up json.dumps."""
    import datetime, json
    from synthadoc.storage.wiki import SourceRef
    store = _make_store(tmp_path)
    page = WikiPage(
        title="Source Page", tags=[], content="", status=LifecycleState.ACTIVE,
        confidence="high",
        sources=[SourceRef(file="doc.pdf", hash="abc", size=100, ingested=datetime.date(2026, 5, 26))],
        orphan=False,
    )
    store.write_page("source-page", page)
    agent = _agent(tmp_path, store)
    result = json.loads(await agent.export(ExportOptions(format="json")))
    assert result["pages"][0]["sources"][0]["ingested"] == "2026-05-26"
