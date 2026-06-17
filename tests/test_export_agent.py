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
async def test_graphml_citation_count_from_audit_db(tmp_path):
    from synthadoc.storage.log import AuditDB
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE)
    _write_page(store, "lovelace", "Ada Lovelace", LifecycleState.ACTIVE)
    audit_path = tmp_path / ".synthadoc" / "audit.db"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit = AuditDB(audit_path)
    await audit.init()
    await audit.record_claim_citations("babbage", [
        {"source_file": "src.txt", "line_start": 1, "line_end": 5, "claim_excerpt": "claim 1"},
        {"source_file": "src.txt", "line_start": 6, "line_end": 10, "claim_excerpt": "claim 2"},
        {"source_file": "src.txt", "line_start": 11, "line_end": 15, "claim_excerpt": "claim 3"},
    ])
    agent = ExportAgent(
        store=store, wiki_name="test-wiki",
        audit_db_path=audit_path,
        routing_path=tmp_path / "ROUTING.md",
    )
    result = await agent.export(ExportOptions(format="graphml"))
    # babbage has 3 citations, lovelace has 0
    assert ">3<" in result or "<data key=\"citation_count\">3</data>" in result
    assert "<data key=\"citation_count\">0</data>" in result


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


# ── OKF export tests ───────────────────────────────────────────────────────────

def _write_okf_page(store, slug, title, status, content="", type_=None,
                    resource=None, tags=None, created="2026-05-26", updated=None):
    page = WikiPage(
        title=title, tags=tags or [], content=content, status=status,
        confidence="high", sources=[], created=created, updated=updated,
        orphan=False, type=type_, resource=resource,
    )
    store.write_page(slug, page)


def _parse_frontmatter(text: str) -> dict:
    import yaml
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}


@pytest.mark.asyncio
async def test_okf_export_returns_dict(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Father of computer science.", type_="person")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    assert isinstance(result, dict)
    assert "index.md" in result
    assert "wiki/alan-turing.md" in result


@pytest.mark.asyncio
async def test_okf_concept_file_has_required_type_field(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Father of computer science.", type_="person")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/alan-turing.md"])
    assert fm["type"] == "person"


@pytest.mark.asyncio
async def test_okf_type_defaults_to_concept_when_none(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "old-page", "Old Page", LifecycleState.ACTIVE,
                    content="Some content.", type_=None)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/old-page.md"])
    assert fm["type"] == "concept"


@pytest.mark.asyncio
async def test_okf_description_derived_from_first_sentence(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Father of computer science. Much more detail here.", type_="person")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/alan-turing.md"])
    assert fm["description"] == "Father of computer science."


@pytest.mark.asyncio
async def test_okf_resource_omitted_when_none(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "local-page", "Local Page", LifecycleState.ACTIVE,
                    content="Content.", type_="concept", resource=None)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/local-page.md"])
    assert "resource" not in fm


@pytest.mark.asyncio
async def test_okf_resource_present_for_url_source(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "web-page", "Web Page", LifecycleState.ACTIVE,
                    content="Content.", type_="concept",
                    resource="https://example.com/article")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/web-page.md"])
    assert fm["resource"] == "https://example.com/article"


@pytest.mark.asyncio
async def test_okf_tags_as_comma_string(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Content.", type_="person",
                    tags=["mathematics", "computation"])
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/alan-turing.md"])
    assert fm["tags"] == "mathematics, computation"


@pytest.mark.asyncio
async def test_okf_timestamp_uses_updated_when_present(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Content.", type_="person",
                    created="2026-01-01", updated="2026-05-15")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/alan-turing.md"])
    assert fm["timestamp"] == "2026-05-15"


@pytest.mark.asyncio
async def test_okf_timestamp_falls_back_to_created(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Content.", type_="person",
                    created="2026-01-01", updated=None)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    fm = _parse_frontmatter(result["wiki/alan-turing.md"])
    assert fm["timestamp"] == "2026-01-01"


@pytest.mark.asyncio
async def test_okf_wikilinks_rewritten_to_relative_paths(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="See [[grace-hopper]] for more.", type_="person")
    _write_okf_page(store, "grace-hopper", "Grace Hopper", LifecycleState.ACTIVE,
                    content="Compiler pioneer.", type_="person")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    body = result["wiki/alan-turing.md"].split("---", 2)[2]
    assert "[[grace-hopper]]" not in body
    assert "[Grace Hopper](grace-hopper.md)" in body


@pytest.mark.asyncio
async def test_okf_index_groups_pages_by_type(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Mathematician.", type_="person")
    _write_okf_page(store, "eniac", "ENIAC", LifecycleState.ACTIVE,
                    content="First computer.", type_="technology")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    index = result["index.md"]
    assert "## person" in index
    assert "## technology" in index
    assert "[Alan Turing](wiki/alan-turing.md)" in index
    assert "[ENIAC](wiki/eniac.md)" in index


@pytest.mark.asyncio
async def test_okf_archived_pages_excluded_by_default(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "old-page", "Old Page", LifecycleState.ARCHIVED,
                    content="Retired.", type_="concept")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    assert "wiki/old-page.md" not in result


@pytest.mark.asyncio
async def test_okf_draft_excluded_by_default(tmp_path):
    """Draft pages must not appear in OKF bundle by default — unverified content."""
    store = _make_store(tmp_path)
    _write_okf_page(store, "draft-page", "Draft Page", LifecycleState.DRAFT,
                    content="Unverified.", type_="concept")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    assert "wiki/draft-page.md" not in result


@pytest.mark.asyncio
async def test_okf_stale_excluded_by_default(tmp_path):
    """Stale pages must not appear in OKF bundle by default — source has changed."""
    store = _make_store(tmp_path)
    _write_okf_page(store, "stale-page", "Stale Page", LifecycleState.STALE,
                    content="Outdated.", type_="concept")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    assert "wiki/stale-page.md" not in result


@pytest.mark.asyncio
async def test_okf_contradicted_included_by_default(tmp_path):
    """Contradicted pages must appear in OKF bundle — consumers see status: contradicted."""
    store = _make_store(tmp_path)
    _write_okf_page(store, "conflict-page", "Conflict Page", LifecycleState.CONTRADICTED,
                    content="Conflicting claim.", type_="concept")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    assert "wiki/conflict-page.md" in result
    fm = _parse_frontmatter(result["wiki/conflict-page.md"])
    assert fm["status"] == "contradicted"


@pytest.mark.asyncio
async def test_okf_contradiction_note_appended_to_body(tmp_path):
    """contradiction_note must be appended to body as a blockquote warning."""
    store = _make_store(tmp_path)
    page = WikiPage(
        title="Conflict Page", tags=[], content="Original claim.",
        status=LifecycleState.CONTRADICTED, confidence="low", sources=[],
        created="2026-05-26", orphan=False, type="concept",
        contradiction_note="Source B says the opposite.",
    )
    store.write_page("conflict-page", page)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf"))
    body = result["wiki/conflict-page.md"].split("---", 2)[2]
    assert "Source B says the opposite." in body
    assert "> **Contradiction:**" in body


@pytest.mark.asyncio
async def test_okf_archived_pages_included_with_status_filter(tmp_path):
    store = _make_store(tmp_path)
    _write_okf_page(store, "old-page", "Old Page", LifecycleState.ARCHIVED,
                    content="Retired.", type_="concept")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="okf", status_filter="archived"))
    assert "wiki/old-page.md" in result


# ── OKF helper unit tests ──────────────────────────────────────────────────────

from synthadoc.agents.export_agent import _first_sentence, _rewrite_wikilinks


def test_first_sentence_no_period_returns_truncated():
    """Content with no sentence-ending period returns truncated text."""
    result = _first_sentence("A long description without a period at all")
    assert result == "A long description without a period at all"


def test_first_sentence_skips_headings():
    """Markdown headings are skipped when extracting first sentence."""
    result = _first_sentence("# Section Title\nThe real content here. More follows.")
    assert result == "The real content here."


def test_first_sentence_strips_citation_markers():
    """^[...] citation markers are removed from the extracted sentence."""
    result = _first_sentence("Some content.^[source:1-2] More text.")
    assert "^[" not in result
    assert result == "Some content."


def test_first_sentence_strips_wikilinks():
    """[[wikilinks]] are replaced with display text only in the extracted sentence."""
    result = _first_sentence("Traces to [[alan-turing]]'s 1950 paper. More follows.")
    assert "[[" not in result
    assert "alan-turing" in result


def test_first_sentence_strips_piped_wikilinks():
    """[[slug|display]] keeps only the display text."""
    result = _first_sentence("Developed by [[grace-hopper|Grace Hopper]]. More follows.")
    assert "[[" not in result
    assert "Grace Hopper" in result


def test_rewrite_wikilinks_piped_form():
    """[[slug|display]] must use custom display text, not slug_to_title lookup."""
    result = _rewrite_wikilinks("See [[grace-hopper|Grace]] here.", {"grace-hopper": "Grace Hopper"})
    assert "[Grace](grace-hopper.md)" in result


def test_okf_log_rendered_when_events_present(tmp_path):
    """log.md must appear in OKF bundle when lifecycle events exist."""
    store = _make_store(tmp_path)
    _write_okf_page(store, "alan-turing", "Alan Turing", LifecycleState.ACTIVE,
                    content="Mathematician.", type_="person")
    agent = _agent(tmp_path, store)
    events = [
        {"slug": "alan-turing", "from_state": "draft", "to_state": "active",
         "reason": "lint passed", "timestamp": "2026-05-01T10:00:00"},
    ]
    result = agent._render_okf({"alan-turing": store.read_page("alan-turing")}, events)
    assert "log.md" in result
    assert "alan-turing" in result["log.md"]
    assert "active" in result["log.md"]
