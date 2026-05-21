# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
import json
from synthadoc.storage.log import AuditDB


@pytest.fixture
async def populated_audit_db(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(3):
        await db.record_ingest(
            source_hash=f"hash{i}", source_size=1000 + i,
            source_path=f"/wiki/raw/doc{i}.pdf", wiki_page=f"page-{i}",
            tokens=500 + i * 100, cost_usd=0.01 * (i + 1),
        )
    await db.record_audit_event("job-1", "ingest_complete", {"pages": 1})
    await db.record_audit_event("job-2", "lint_complete", {"resolved": 0})
    return db


@pytest.mark.asyncio
async def test_list_ingests_returns_records(populated_audit_db):
    records = await populated_audit_db.list_ingests(limit=10)
    assert len(records) == 3
    assert records[0]["source_path"] == "/wiki/raw/doc0.pdf"
    assert "tokens" in records[0]
    assert "cost_usd" in records[0]
    assert "ingested_at" in records[0]


@pytest.mark.asyncio
async def test_list_ingests_respects_limit(populated_audit_db):
    records = await populated_audit_db.list_ingests(limit=2)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_events_returns_records(populated_audit_db):
    events = await populated_audit_db.list_events(limit=10)
    assert len(events) == 2
    assert events[0]["event"] in ("ingest_complete", "lint_complete")


@pytest.mark.asyncio
async def test_cost_summary_aggregates_correctly(populated_audit_db):
    summary = await populated_audit_db.cost_summary(days=30)
    assert summary["total_tokens"] == 500 + 600 + 700
    assert abs(summary["total_cost_usd"] - 0.06) < 0.001
    assert "daily" in summary


def test_audit_history_command_prints_table(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki)])
    assert result.exit_code == 0


def test_audit_history_json_flag(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki), "--json"])
    assert result.exit_code == 0
    # CliRunner mixes stderr into output; strip the [wiki: ...] hint line before parsing JSON
    json_output = "\n".join(
        line for line in result.output.splitlines()
        if not line.startswith("[wiki:")
    ).strip()
    data = json.loads(json_output)
    assert isinstance(data, list)


def test_audit_cost_command(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "cost", "--wiki", str(wiki)])
    assert result.exit_code == 0


def test_audit_events_command(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "events", "--wiki", str(wiki)])
    assert result.exit_code == 0


# ── additional coverage tests ────────────────────────────────────────────────

def _make_wiki(tmp_path):
    """Create a minimal wiki directory structure with an initialised audit.db."""
    import asyncio
    from synthadoc.storage.log import AuditDB

    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()
    db = AuditDB(wiki / ".synthadoc" / "audit.db")

    async def _seed():
        await db.init()
        await db.record_ingest(
            source_hash="abc", source_size=1000,
            source_path="/wiki/raw/paper.pdf", wiki_page="paper",
            tokens=500, cost_usd=0.01,
        )
        await db.record_audit_event("job-x", "ingest_complete", {"pages": 1})
        await db.record_query("What is AI?", sub_questions_count=2, tokens=300, cost_usd=0.005)

    asyncio.run(_seed())
    return wiki


def test_audit_history_with_records_renders_table(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki)])
    assert result.exit_code == 0
    assert "paper.pdf" in result.output


def test_audit_cost_json_flag(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "cost", "--wiki", str(wiki), "--json"])
    assert result.exit_code == 0
    lines = [l for l in result.output.splitlines() if not l.startswith("[wiki:")]
    data = json.loads("\n".join(lines))
    assert "total_tokens" in data


def test_audit_cost_with_data_renders_table(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "cost", "--wiki", str(wiki)])
    assert result.exit_code == 0
    assert "Total tokens" in result.output


def test_audit_queries_command(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "queries", "--wiki", str(wiki)])
    assert result.exit_code == 0
    assert "Query History" in result.output


def test_audit_queries_json_flag(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "queries", "--wiki", str(wiki), "--json"])
    assert result.exit_code == 0
    lines = [l for l in result.output.splitlines() if not l.startswith("[wiki:")]
    data = json.loads("\n".join(lines))
    assert isinstance(data, list)


def test_audit_events_json_flag(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "events", "--wiki", str(wiki), "--json"])
    assert result.exit_code == 0
    lines = [l for l in result.output.splitlines() if not l.startswith("[wiki:")]
    data = json.loads("\n".join(lines))
    assert isinstance(data, list)


def test_audit_events_with_data_renders_table(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = _make_wiki(tmp_path)
    result = runner.invoke(app, ["audit", "events", "--wiki", str(wiki)])
    assert result.exit_code == 0
    assert "Audit Events" in result.output


# ── claim_citations tests ────────────────────────────────────────────────────

import asyncio
from synthadoc.storage.log import AuditDB


@pytest.fixture
def db(tmp_path):
    d = AuditDB(tmp_path / ".synthadoc" / "audit.db")
    asyncio.run(d.init())
    return d


def test_record_claim_citations_stores_rows(db):
    citations = [
        {"source_file": "foo.txt", "line_start": 1, "line_end": 10,
         "claim_excerpt": "First claim here"},
        {"source_file": "foo.txt", "line_start": 20, "line_end": 30,
         "claim_excerpt": "Second claim here"},
    ]
    asyncio.run(db.record_claim_citations("alan-turing", citations))
    rows = asyncio.run(db.list_citations())
    assert len(rows) == 2
    assert rows[0]["page_slug"] == "alan-turing"
    assert rows[0]["source_file"] == "foo.txt"
    assert rows[0]["line_start"] == 1


def test_list_citations_filter_by_page(db):
    asyncio.run(db.record_claim_citations("alan-turing", [
        {"source_file": "a.txt", "line_start": 1, "line_end": 5, "claim_excerpt": "x"}
    ]))
    asyncio.run(db.record_claim_citations("ada-lovelace", [
        {"source_file": "b.txt", "line_start": 1, "line_end": 5, "claim_excerpt": "y"}
    ]))
    rows = asyncio.run(db.list_citations(page_slug="alan-turing"))
    assert len(rows) == 1
    assert rows[0]["page_slug"] == "alan-turing"


def test_list_citations_filter_by_source(db):
    asyncio.run(db.record_claim_citations("alan-turing", [
        {"source_file": "bio.txt", "line_start": 1, "line_end": 5, "claim_excerpt": "x"}
    ]))
    asyncio.run(db.record_claim_citations("alan-turing", [
        {"source_file": "other.txt", "line_start": 1, "line_end": 5, "claim_excerpt": "y"}
    ]))
    rows = asyncio.run(db.list_citations(source_file="bio.txt"))
    assert len(rows) == 1


def test_list_citations_broken_only(db):
    asyncio.run(db.write_event(
        "citation_validation_failed",
        metadata='{"slug": "p", "citation": "^[x.txt:1-2]", "reason": "broken_ref"}'
    ))
    asyncio.run(db.write_event("ingest_started", metadata="{}"))
    rows = asyncio.run(db.list_citations(broken_only=True))
    assert len(rows) == 1
    assert rows[0]["reason"] == "broken_ref"


def test_write_event_stores_event(db):
    asyncio.run(db.write_event("citation_pass4_skipped",
                               metadata='{"slug": "p", "error": "timeout"}'))
    events = asyncio.run(db.list_events(limit=10))
    assert any(e["event"] == "citation_pass4_skipped" for e in events)
