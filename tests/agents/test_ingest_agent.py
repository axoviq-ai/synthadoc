# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import hashlib
import pytest
import aiosqlite
from unittest.mock import AsyncMock
from synthadoc.agents.ingest_agent import IngestAgent, IngestResult, _slugify, _coerce_str_list, _parse_json_response, _strip_leading_frontmatter
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.log import LogWriter, AuditDB
from synthadoc.core.cache import CacheManager


# --- _slugify unit tests ---

def test_slugify_ascii():
    assert _slugify("Alan Turing") == "alan-turing"

def test_slugify_accented():
    assert _slugify("Café au Lait") == "cafe-au-lait"

def test_slugify_chinese():
    slug = _slugify("人工智能")
    assert slug == "人工智能"
    assert len(slug) > 0

def test_slugify_mixed_cjk_ascii():
    slug = _slugify("AI 人工智能 History")
    assert "人工智能" in slug
    assert "ai" in slug
    assert "history" in slug

def test_slugify_pure_symbols_returns_hash():
    slug = _slugify("!!! ???")
    assert slug.startswith("page-")
    assert len(slug) > 5


# --- _parse_json_response unit tests ---

def test_parse_json_response_returns_dict():
    result = _parse_json_response('{"entities": ["AI"], "tags": ["ml"]}')
    assert result == {"entities": ["AI"], "tags": ["ml"]}


def test_parse_json_response_unwraps_top_level_array():
    """LLM sometimes returns a JSON array wrapping the dict — unwrap first element."""
    result = _parse_json_response('[{"entities": ["AI"], "tags": ["ml"]}]')
    assert result == {"entities": ["AI"], "tags": ["ml"]}


def test_parse_json_response_empty_array_returns_empty_dict():
    result = _parse_json_response("[]")
    assert result == {}


def test_parse_json_response_non_dict_array_returns_empty_dict():
    """Array of non-dict elements should fall through to brace extraction."""
    result = _parse_json_response('["a", "b"]')
    assert isinstance(result, dict)


def test_parse_json_response_handles_markdown_fence():
    result = _parse_json_response('```json\n{"entities": ["BERT"]}\n```')
    assert result["entities"] == ["BERT"]


def test_parse_json_response_invalid_json_in_code_fence_falls_through():
    """If code fence contains invalid JSON, the except branch is hit and we fall through."""
    result = _parse_json_response("```json\n{bad: 'json'}\n```")
    assert isinstance(result, dict)


def test_coerce_str_list_with_non_string_non_dict_item():
    """Non-str, non-dict items (e.g. integers) reach the else branch and are str()-converted."""
    result = _coerce_str_list([42, "valid"])
    assert "42" in result
    assert "valid" in result


@pytest.fixture
def mock_provider():
    """Provider that cycles: entity response, then decision response (repeating)."""
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["AI","safety"],"concepts":["alignment"],"tags":["ai"]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"ai-safety","update_content":""}',
        input_tokens=100, output_tokens=50,
    )
    # side_effect as iterator: entity, decision, entity, decision, ...
    import itertools
    p.complete.side_effect = itertools.cycle([_entity, _decision])
    return p


@pytest.mark.asyncio
async def test_ingest_creates_page(tmp_wiki, mock_provider, cache):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# AI Safety\nAlignment is important.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))
    assert isinstance(result, IngestResult)
    assert not result.skipped
    assert result.pages_created


@pytest.mark.asyncio
async def test_ingest_skips_duplicate(tmp_wiki, mock_provider, cache):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "dup.md"
    source.write_text("# Duplicate\nContent.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    await agent.ingest(str(source))
    result2 = await agent.ingest(str(source))
    assert result2.skipped is True


@pytest.mark.asyncio
async def test_ingest_nonexistent_path_raises(tmp_wiki, mock_provider, cache):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    with pytest.raises(FileNotFoundError):
        await agent.ingest("/tmp/does-not-exist-abc123.pdf")


@pytest.mark.asyncio
async def test_ingest_zero_byte_file_raises(tmp_wiki, mock_provider, cache):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    empty = tmp_wiki / "raw_sources" / "empty.md"
    empty.write_bytes(b"")
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    with pytest.raises(ValueError, match="empty"):
        await agent.ingest(str(empty))


@pytest.mark.asyncio
async def test_force_busts_cache(tmp_wiki, mock_provider, cache):
    """force=True must call the LLM even when a cached response exists."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "bust.md"
    source.write_text("# Force bust test\nContent.", encoding="utf-8")

    import itertools
    _entity = CompletionResponse(text='{"entities":[],"concepts":[],"tags":[]}',
                                 input_tokens=100, output_tokens=50)
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"force-bust-test","update_content":""}',
        input_tokens=100, output_tokens=50)
    mock_provider.complete.side_effect = itertools.cycle([_entity, _decision])

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)

    # First ingest — populates cache; 2 LLM calls (extract + decision)
    await agent.ingest(str(source))
    calls_after_first = mock_provider.complete.call_count

    # Second ingest without force — should use cache, no new LLM calls
    await agent.ingest(str(source), force=True)  # force=True skips dedup
    # Without bust_cache the count would stay the same; with bust_cache it increases
    await agent.ingest(str(source), force=True, bust_cache=True)
    assert mock_provider.complete.call_count > calls_after_first


@pytest.mark.asyncio
async def test_new_page_appended_to_index(tmp_wiki, mock_provider, cache):
    """New pages created by ingest must be appended to index.md under 'Recently Added'."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    index_content = (
        "---\ntitle: Index\ntags: [index]\nstatus: active\nconfidence: high\n"
        "created: '2026-01-01'\nsources: []\n---\n\n# Index\n\n## People\n"
    )
    (tmp_wiki / "wiki" / "index.md").write_text(index_content, encoding="utf-8")

    source = tmp_wiki / "raw_sources" / "new_topic.md"
    source.write_text("# New Topic\nBrand new content.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert result.pages_created
    index_text = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    slug = result.pages_created[0]
    # New page must appear in index.md under 'Recently Added'
    assert f"[[{slug}]]" in index_text
    assert "## Recently Added" in index_text


@pytest.mark.asyncio
async def test_ingest_flags_contradiction(tmp_wiki, cache):
    """When LLM returns action='flag', the target page status becomes 'contradicted'."""
    from unittest.mock import AsyncMock
    p = AsyncMock()
    import itertools
    _entity = CompletionResponse(
        text='{"entities":["compiler","Grace Hopper"],"concepts":[],"tags":["history"]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"flag","target":"grace-hopper","new_slug":"","update_content":""}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    # Create the target page
    from synthadoc.storage.wiki import WikiPage
    store.write_page("grace-hopper", WikiPage(
        title="Grace Hopper", tags=["biography"], content="# Grace Hopper\n\nFirst compiler.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "controversy.md"
    source.write_text("A-0 was a loader, not a compiler. FORTRAN was the first.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "grace-hopper" in result.pages_flagged
    page = store.read_page("grace-hopper")
    assert page.status == "contradicted"


@pytest.mark.asyncio
async def test_ingest_flag_ignores_skip_slugs(tmp_wiki, cache):
    """LLM targeting a skip slug (e.g. 'index') with action='flag' must be silently ignored."""
    from unittest.mock import AsyncMock
    import itertools
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    from synthadoc.storage.wiki import WikiPage
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["index"],"concepts":[],"tags":[]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"flag","target":"index","new_slug":"","update_content":""}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("index", WikiPage(
        title="Index", tags=[], content="# Index\n\nWiki root.",
        status="active", confidence="high", sources=[],
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "rewrite.md"
    source.write_text("Completely different index content.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "index" not in result.pages_flagged
    page = store.read_page("index")
    assert page.status == "active", "skip slugs must never be set to contradicted"


@pytest.mark.asyncio
async def test_ingest_updates_existing_page(tmp_wiki, cache):
    """When LLM returns action='update', content is appended to the target page."""
    from unittest.mock import AsyncMock
    p = AsyncMock()
    import itertools
    _entity = CompletionResponse(
        text='{"entities":["Alan Turing","Enigma"],"concepts":[],"tags":["history"]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"update","target":"alan-turing","new_slug":"","update_content":"## Enigma\\n\\nNew detail."}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    from synthadoc.storage.wiki import WikiPage
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"], content="# Alan Turing\n\nMathematician.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "enigma.md"
    source.write_text("Turing broke Enigma at Bletchley Park.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    assert "Enigma" in page.content
    assert "New detail." in page.content


# ── OKF type + resource fields ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_populates_okf_type(tmp_wiki, cache):
    """type field from analysis LLM response is written to the created page."""
    from unittest.mock import AsyncMock
    import itertools
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["Alan Turing"],"tags":["biography"],"type":"person","relevant":true}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"alan-turing","update_content":"","page_content":"# Alan Turing\\n\\nBiography."}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "turing.md"
    source.write_text("# Alan Turing\nBritish mathematician.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert result.pages_created
    page = store.read_page(result.pages_created[0])
    assert page is not None
    assert page.type == "person"


@pytest.mark.asyncio
async def test_ingest_resource_set_for_url_source(tmp_wiki, cache):
    """resource field is auto-populated from the source URL when ingesting a URL."""
    from unittest.mock import AsyncMock, patch
    import itertools
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["Python"],"tags":["programming"],"type":"technology","relevant":true}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"python-lang","update_content":"","page_content":"# Python\\n\\nA programming language."}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    from synthadoc.skills.base import ExtractedContent
    mock_extracted = ExtractedContent(
        text="Python is a programming language.",
        source_path="https://example.com/python",
        metadata={},
    )

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
                        wiki_root=tmp_wiki)
    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted), \
         patch.object(agent._skill_agent, "detect_skill") as mock_detect:
        from synthadoc.skills.base import SkillMeta
        mock_detect.return_value = SkillMeta(name="url", description="URL skill")
        result = await agent.ingest("https://example.com/python")

    assert result.pages_created
    page = store.read_page(result.pages_created[0])
    assert page is not None
    assert page.resource == "https://example.com/python"


@pytest.mark.asyncio
async def test_force_reingest_backfills_okf_fields(tmp_wiki, cache):
    """Force re-ingest of an existing page backfills type/resource when they are absent."""
    from unittest.mock import AsyncMock
    import itertools
    p = AsyncMock()
    _entity_with_type = CompletionResponse(
        text='{"entities":["Alan Turing"],"tags":["biography"],"type":"person","relevant":true}',
        input_tokens=100, output_tokens=50,
    )
    _decision_update = CompletionResponse(
        text='{"action":"update","target":"alan-turing","new_slug":"","update_content":"## Extra\\n\\nMore info."}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity_with_type, _decision_update])

    store = WikiStorage(tmp_wiki / "wiki")
    # Pre-existing page with no type (simulates page created before v0.9.0)
    from synthadoc.storage.wiki import WikiPage
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"], content="# Alan Turing\n\nMathematician.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    assert store.read_page("alan-turing").type is None

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "turing.md"
    source.write_text("Alan Turing biography.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source), force=True)

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    assert page.type == "person"


@pytest.mark.asyncio
async def test_update_action_stamps_updated_field(tmp_wiki, cache):
    """Re-ingesting an existing page via update action sets the updated field to today."""
    from unittest.mock import AsyncMock
    import itertools
    from datetime import date
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["Alan Turing"],"tags":["biography"],"type":"person","relevant":true}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"update","target":"alan-turing","new_slug":"","update_content":"## Extra\\n\\nMore info."}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"], content="# Alan Turing\n\nMathematician.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    assert store.read_page("alan-turing").updated is None

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "turing-extra.md"
    source.write_text("More about Turing.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source), force=True)

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    assert page.updated == date.today().isoformat()


@pytest.mark.asyncio
async def test_create_action_leaves_updated_none(tmp_wiki, mock_provider, cache):
    """Initial ingest (create action) must NOT set the updated field."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "new.md"
    source.write_text("# New Topic\nSome brand new content.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert result.pages_created
    page = store.read_page(result.pages_created[0])
    assert page is not None
    assert page.updated is None


@pytest.mark.asyncio
async def test_ingest_resource_none_for_local_file(tmp_wiki, mock_provider, cache):
    """resource field is None for local file sources."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "local.md"
    source.write_text("# Local Doc\nSome local content.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert result.pages_created
    page = store.read_page(result.pages_created[0])
    assert page is not None
    assert page.resource is None


@pytest.mark.asyncio
async def test_ingest_hash_size_mismatch_warns_and_proceeds(tmp_wiki, mock_provider, caplog, cache):
    """Hash match + size differs → log warning, treat as new source (not a skip)."""
    import logging
    from synthadoc.storage.log import AuditDB

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    source = tmp_wiki / "raw_sources" / "collision.md"
    source.write_text("# Collision test", encoding="utf-8")

    content = source.read_bytes()
    src_hash = hashlib.sha256(content).hexdigest()
    # Insert a record with the same hash but a different size (simulated collision)
    async with aiosqlite.connect(str(audit._path)) as db:
        await db.execute(
            "INSERT INTO ingests (source_hash, source_size, source_path, wiki_page, "
            "tokens, cost_usd, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (src_hash, len(content) + 999, "old.md", "old-page", 0, 0.0, "2026-01-01T00:00:00Z")
        )
        await db.commit()

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    with caplog.at_level(logging.WARNING):
        result = await agent.ingest(str(source))
    assert not result.skipped
    assert any("collision" in r.message.lower() or "size" in r.message.lower()
               for r in caplog.records)


@pytest.mark.asyncio
async def test_purpose_md_filters_out_of_scope_source(tmp_wiki, mock_provider, cache):
    """When purpose.md is present and LLM returns action=skip, result is skipped."""
    import itertools
    from synthadoc.providers.base import CompletionResponse

    (tmp_wiki / "wiki" / "purpose.md").write_text(
        "This wiki covers AI and machine learning only.", encoding="utf-8")

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta Recipes\nHow to make carbonara.", encoding="utf-8")

    entity_resp = CompletionResponse(
        text='{"entities":["pasta"],"concepts":["cooking"],"tags":["food"]}',
        input_tokens=50, output_tokens=20)
    skip_resp = CompletionResponse(
        text='{"reasoning":"Out of scope","action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=50, output_tokens=20)
    mock_provider.complete.side_effect = itertools.cycle([entity_resp, skip_resp])

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
                        wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.skipped
    assert "scope" in result.skip_reason.lower()


@pytest.mark.asyncio
async def test_skip_records_ingest_in_audit_db(tmp_wiki, mock_provider, cache):
    """action=skip must still call record_ingest so the audit DB hash stays current.

    Without this, a subsequent lint run will see the audit hash != disk hash and
    mark the page stale even though nothing actually changed.
    """
    import itertools
    from synthadoc.providers.base import CompletionResponse

    (tmp_wiki / "wiki" / "purpose.md").write_text(
        "This wiki covers AI only.", encoding="utf-8")

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta Recipes\nHow to make carbonara.", encoding="utf-8")

    entity_resp = CompletionResponse(
        text='{"entities":["pasta"],"concepts":["cooking"],"tags":["food"]}',
        input_tokens=10, output_tokens=5)
    skip_resp = CompletionResponse(
        text='{"reasoning":"Out of scope","action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=10, output_tokens=5)
    mock_provider.complete.side_effect = itertools.cycle([entity_resp, skip_resp])

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
                        wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.skipped

    # Audit DB must have a record for this source so future lint won't fire stale.
    record = await audit.find_by_source_path(str(source))
    assert record is not None, "skip action must still write an audit record"
    import hashlib
    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["source_hash"] == expected_hash, \
        "audit record must store the current file hash so lint stale-check passes"


@pytest.mark.asyncio
async def test_purpose_md_absent_does_not_break_ingest(tmp_wiki, mock_provider, cache):
    """No purpose.md — ingest proceeds normally."""
    assert not (tmp_wiki / "wiki" / "purpose.md").exists()
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# AI Safety\nAlignment research.", encoding="utf-8")
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert not result.skipped


# --- _strip_leading_frontmatter unit tests ---

def test_strip_leading_frontmatter_no_frontmatter():
    content = "# My Page\n\nSome content."
    assert _strip_leading_frontmatter(content) == content


def test_strip_leading_frontmatter_with_frontmatter():
    content = "---\ntitle: Capex Policy\nstatus: active\n---\n\n# Capex Policy\n\nContent here."
    result = _strip_leading_frontmatter(content)
    assert result.startswith("# Capex Policy")
    assert "---" not in result.split("\n")[0]
    assert "status: active" not in result


def test_strip_leading_frontmatter_empty_frontmatter():
    content = "---\n---\n\n# Empty FM\n\nBody text."
    result = _strip_leading_frontmatter(content)
    assert result.startswith("# Empty FM")


def test_strip_leading_frontmatter_passthrough_no_closing():
    """A lone opening --- with no closing --- is returned unchanged."""
    content = "---\nno closing\n# Title"
    result = _strip_leading_frontmatter(content)
    assert result == content


@pytest.mark.asyncio
async def test_ingest_strips_llm_frontmatter_from_page_content(tmp_wiki, cache):
    """LLM returning page_content with a leading ---...--- block must not produce double-frontmatter."""
    import itertools

    page_content_with_fm = (
        "---\ntitle: Capex Policy\nstatus: active\n---\n\n"
        "# Capex Policy\n\nMainline content about capex methodology."
    )
    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["CAPEX"],"tags":["finance"],"summary":"Capex policy.","relevant":true}',
        input_tokens=50, output_tokens=20,
    )
    decision_resp = CompletionResponse(
        text=(
            '{"action":"create","new_slug":"capex-policy",'
            f'"page_content":{__import__("json").dumps(page_content_with_fm)},'
            '"update_content":"","target":""}'
        ),
        input_tokens=100, output_tokens=50,
    )
    provider.complete.side_effect = itertools.cycle([entity_resp, decision_resp])

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "capex.md"
    source.write_text("Capex policy document content.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))
    assert result.pages_created

    slug = result.pages_created[0]
    page = store.read_page(slug)
    assert page is not None
    # Body must not contain a YAML block — double-frontmatter would put "---" near the top
    body_lines = page.content.splitlines()
    assert not any(line.strip() == "---" for line in body_lines[:5]), (
        "Double-frontmatter detected: page body starts with a YAML block"
    )
    assert "# Capex Policy" in page.content


def test_init_wiki_creates_purpose_md(tmp_path):
    from synthadoc.cli._init import init_wiki
    init_wiki(tmp_path, domain="AI Research")
    purpose = tmp_path / "wiki" / "purpose.md"
    assert purpose.exists()
    text = purpose.read_text(encoding="utf-8")
    assert "AI Research" in text


@pytest.mark.asyncio
async def test_overview_md_created_after_ingest(tmp_wiki, cache):
    """overview.md must be written after a successful page creation."""
    import itertools
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"AI safety research.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"New topic","action":"create","target":"","new_slug":"ai-safety","update_content":""}',
        input_tokens=50, output_tokens=20)
    overview_resp = CompletionResponse(
        text="This wiki covers AI safety research.\n\nKey themes include alignment.",
        input_tokens=50, output_tokens=30)
    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [entity_resp, decision_resp, overview_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "ai.md"
    source.write_text("# AI Safety\nAlignment is important.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.pages_created
    overview = tmp_wiki / "wiki" / "overview.md"
    assert overview.exists(), "overview.md should be created after page creation"
    text = overview.read_text(encoding="utf-8")
    assert "overview" in text.lower() or "wiki" in text.lower()
    assert "status: active" in text, "overview.md must use status: active, not status: auto"
    assert "confidence: high" in text, "overview.md must include confidence: high"
    assert "created:" in text, "overview.md must include a created date"


@pytest.mark.asyncio
async def test_overview_md_not_written_on_skip(tmp_wiki, cache):
    """overview.md must NOT be written when ingest is skipped."""
    import itertools
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":[],"tags":[],"summary":"Out of scope.","relevant":false}',
        input_tokens=10, output_tokens=5)
    skip_resp = CompletionResponse(
        text='{"action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=10, output_tokens=5)
    provider.complete = AsyncMock(side_effect=itertools.cycle([entity_resp, skip_resp]))

    (tmp_wiki / "wiki" / "purpose.md").write_text("AI only.", encoding="utf-8")
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta\nHow to cook.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    await agent.ingest(str(source))
    assert not (tmp_wiki / "wiki" / "overview.md").exists()


@pytest.mark.asyncio
async def test_ingest_title_uses_h1_from_generated_body(tmp_wiki, cache):
    """WikiPage.title must be derived from the H1 in the LLM-generated body,
    not from the source filename or its frontmatter title field."""
    import itertools

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["water"],"tags":["infrastructure"],"summary":"Water market overview.","relevant":true}',
        input_tokens=50, output_tokens=20)
    # LLM generates body with a proper H1 different from the filename-derived title
    decision_resp = CompletionResponse(
        text=(
            '{"reasoning":"New topic","action":"create","target":"",'
            '"new_slug":"water-infrastructure-market",'
            '"update_content":"",'
            '"page_content":"# Water Infrastructure Market\\n\\nThis page covers the market."}'
        ),
        input_tokens=50, output_tokens=40)
    # overview response
    overview_resp = CompletionResponse(
        text="This wiki covers water infrastructure.",
        input_tokens=20, output_tokens=10)
    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [entity_resp, decision_resp, overview_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    # Filename would derive title "02 Water Infrastructure Market" without the fix
    source = tmp_wiki / "raw_sources" / "02_water_infrastructure_market.md"
    source.write_text("# 02 Water Infrastructure Market\nMarket content.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.pages_created

    slug = result.pages_created[0]
    page = store.read_page(slug)
    assert page is not None
    assert page.title == "Water Infrastructure Market", (
        f"Expected H1-derived title 'Water Infrastructure Market', got '{page.title}'"
    )


def test_decision_prompt_contains_entity_profile_rule():
    """_DECISION_PROMPT must include the entity-profile rule so company profiles always create new pages."""
    from synthadoc.agents.ingest_agent import _DECISION_PROMPT
    assert "ENTITY PROFILE" in _DECISION_PROMPT, (
        "_DECISION_PROMPT must contain RULE 2b (entity profile must create)"
    )
    assert "action='create'" in _DECISION_PROMPT or "action=\"create\"" in _DECISION_PROMPT
    # Confirm the rule covers named companies
    assert "company" in _DECISION_PROMPT.lower()


def test_append_source_ref_deduplicates():
    """_append_source_ref must not add a duplicate (file, hash) entry and must
    compact any duplicates already present from prior --force runs."""
    from synthadoc.agents.ingest_agent import _append_source_ref
    from synthadoc.storage.wiki import SourceRef, WikiPage

    dup = SourceRef(file="/a/b.md", hash="abc123", size=100, ingested="2026-07-04")
    # Pre-load page with 3 identical entries (simulates 3 prior --force runs)
    page = WikiPage(title="T", tags=[], content="", status="draft", confidence="medium",
                    sources=[dup, dup, dup])
    # Appending the same ref should compact to 1 and not add a 4th
    _append_source_ref(page, SourceRef(file="/a/b.md", hash="abc123", size=100, ingested="2026-07-05"))
    assert len(page.sources) == 1

    # Different hash on same file → allowed (genuinely updated source)
    _append_source_ref(page, SourceRef(file="/a/b.md", hash="deadbeef", size=200, ingested="2026-07-05"))
    assert len(page.sources) == 2


def test_append_source_ref_clears_truncated_on_reingest():
    """Re-ingesting the same (file, hash) with truncated=False must clear the stale flag.

    URL sources always produce the same hash (derived from the URL, not content),
    so a re-ingest with a higher max_source_chars must update the existing entry
    rather than being silently dropped.
    """
    from synthadoc.agents.ingest_agent import _append_source_ref
    from synthadoc.storage.wiki import SourceRef, WikiPage

    url = "https://example.com/page"
    url_hash = "hash-from-url"
    page = WikiPage(title="T", tags=[], content="", status="draft", confidence="medium",
                    sources=[SourceRef(file=url, hash=url_hash, size=100, ingested="2026-07-01", truncated=True)])

    # Re-ingest with higher limit — same (file, hash), truncated=False
    _append_source_ref(page, SourceRef(file=url, hash=url_hash, size=100, ingested="2026-07-13", truncated=False))

    assert len(page.sources) == 1
    assert page.sources[0].truncated is False
    assert page.sources[0].ingested == "2026-07-13"


@pytest.mark.asyncio
async def test_analyse_returns_structured_result(tmp_wiki, cache):
    """_analyse() returns entities, tags, and a summary string."""
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"This source discusses AI safety.","relevant":true}',
        input_tokens=50, output_tokens=20))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent._analyse("AI safety content here", bust_cache=True)
    assert "entities" in result
    assert "summary" in result
    assert isinstance(result["summary"], str)


@pytest.mark.asyncio
async def test_analyse_is_cached_on_second_call(tmp_wiki, cache):
    """Second call with same text must hit cache with 0 additional LLM calls."""
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    call_count = 0

    async def counting_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(
            text='{"entities":["X"],"tags":[],"summary":"Test.","relevant":true}',
            input_tokens=10, output_tokens=5)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=counting_complete)

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    await agent._analyse("some text", bust_cache=False)
    first_calls = call_count
    await agent._analyse("some text", bust_cache=False)
    assert call_count == first_calls  # second call hits cache


@pytest.mark.asyncio
async def test_ingest_uses_page_content_for_new_pages(tmp_wiki, cache):
    """When decision includes page_content, new page body uses it (not raw source text)."""
    import itertools
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    analyse_resp = CompletionResponse(
        text='{"entities":["Ada Lovelace"],"tags":["computing"],"summary":"Ada Lovelace was the first programmer.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new topic","action":"create","target":"","new_slug":"ada-lovelace",'
             '"update_content":"","page_content":"# Ada Lovelace\\n\\nAda Lovelace (1815-1852) '
             'is widely regarded as the first computer programmer. She collaborated with '
             '[[charles-babbage]] on the [[analytical-engine]]."}',
        input_tokens=80, output_tokens=40)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=itertools.cycle([analyse_resp, decision_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "ada.md"
    source.write_text("Ada Lovelace raw text", encoding="utf-8")

    from unittest.mock import patch
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert "ada-lovelace" in result.pages_created
    page = store.read_page("ada-lovelace")
    assert "[[charles-babbage]]" in page.content
    assert "[[analytical-engine]]" in page.content
    assert "Ada Lovelace raw text" not in page.content  # raw text not used


@pytest.mark.asyncio
async def test_ingest_preserves_wikilinks_in_update_content(tmp_wiki, cache):
    """update_content from decision is written to page verbatim — [[wikilinks]] preserved."""
    import itertools
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", "# Alan Turing\n\nFounder of computer science.", {})

    analyse_resp = CompletionResponse(
        text='{"entities":["Turing","Enigma"],"tags":["cryptography"],"summary":"Turing broke Enigma.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"adds info","action":"update","target":"alan-turing",'
             '"new_slug":"","update_content":"## Enigma\\n\\nTuring led the team that broke '
             'the [[enigma]] cipher at [[bletchley-park]].","page_content":""}',
        input_tokens=80, output_tokens=40)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=itertools.cycle([analyse_resp, decision_resp]))

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "enigma.md"
    source.write_text("Turing broke Enigma at Bletchley Park.", encoding="utf-8")

    from unittest.mock import patch
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    assert "[[enigma]]" in page.content
    assert "[[bletchley-park]]" in page.content


# ── _coerce_str_list ──────────────────────────────────────────────────────────

def test_coerce_str_list_plain_strings_unchanged():
    assert _coerce_str_list(["AI", "Canada"]) == ["AI", "Canada"]


def test_coerce_str_list_dict_entities_extracted():
    """Some LLMs return entities as dicts with a 'name' field."""
    result = _coerce_str_list([
        {"name": "Canada", "type": "location"},
        {"name": "Llama 3", "type": "model"},
    ])
    assert result == ["Canada", "Llama 3"]


def test_coerce_str_list_mixed_str_and_dict():
    result = _coerce_str_list(["AI", {"name": "OpenAI", "type": "org"}, "safety"])
    assert result == ["AI", "OpenAI", "safety"]


def test_coerce_str_list_fallback_fields():
    """Falls back to 'value', 'label', 'text' if 'name' is absent."""
    assert _coerce_str_list([{"value": "machine learning"}]) == ["machine learning"]
    assert _coerce_str_list([{"label": "NLP"}]) == ["NLP"]
    assert _coerce_str_list([{"text": "deep learning"}]) == ["deep learning"]


def test_coerce_str_list_drops_empty_strings():
    assert _coerce_str_list(["", "AI", "  "]) == ["AI"]


def test_coerce_str_list_non_list_input_returns_empty():
    assert _coerce_str_list(None) == []
    assert _coerce_str_list("not a list") == []
    assert _coerce_str_list(42) == []


@pytest.mark.asyncio
async def test_analyse_coerces_dict_entities_to_strings(tmp_wiki, cache):
    """_analyse() must return entities as strings even if the LLM returns dicts."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"entities":[{"name":"Canada","type":"location"},{"name":"Gardening"}],'
             '"tags":[{"name":"plants"}],"summary":"Canadian gardening.","relevant":true}',
        input_tokens=40, output_tokens=15))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent._analyse("Canadian gardening content", bust_cache=True)

    assert all(isinstance(e, str) for e in result["entities"]), \
        f"entities must all be strings, got: {result['entities']}"
    assert all(isinstance(t, str) for t in result["tags"]), \
        f"tags must all be strings, got: {result['tags']}"
    assert "Canada" in result["entities"]
    assert "plants" in result["tags"]


@pytest.mark.asyncio
async def test_ingest_vision_path_extracts_text_from_image(tmp_wiki, cache):
    """ImageSkill returns extracted text; IngestAgent ingests it and accounts for vision tokens."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["CPU","architecture"],"tags":["hardware"],"summary":"CPU diagram.","relevant":true}',
        input_tokens=40, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"cpu-architecture","update_content":""}',
        input_tokens=50, output_tokens=25)
    provider.complete = AsyncMock(side_effect=itertools.cycle([entity_resp, decision_resp]))
    provider.supports_vision = True

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    img_path = tmp_wiki / "raw_sources" / "diagram.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # ImageSkill now returns populated text + token counts in metadata
    from synthadoc.skills.base import ExtractedContent
    fake_extracted = ExtractedContent(
        text="A diagram showing a CPU architecture.",
        source_path=str(img_path),
        metadata={"tokens_input": 30, "tokens_output": 15},
    )

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", AsyncMock(return_value=fake_extracted)):
        with patch.object(IngestAgent, "_update_overview", AsyncMock()):
            result = await agent.ingest(str(img_path))

    assert not result.skipped
    assert result.pages_created
    # Vision tokens surfaced by the skill are tracked in the ingest result
    assert result.input_tokens >= 30
    assert result.output_tokens >= 15


@pytest.mark.asyncio
async def test_ingest_slug_collision_appends_as_update(tmp_wiki, cache):
    """When the target slug already exists for a 'create' action, content is appended instead."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.storage.wiki import WikiPage

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["Turing"],"tags":["history"],"summary":"About Turing.","relevant":true}',
        input_tokens=50, output_tokens=20)
    # LLM tries to create "alan-turing" but that slug already exists
    decision_resp = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"alan-turing","update_content":"","page_content":"# Alan Turing\\n\\nExtra facts."}',
        input_tokens=50, output_tokens=25)
    provider.complete = AsyncMock(side_effect=itertools.cycle([entity_resp, decision_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"],
        content="# Alan Turing\n\nOriginal content.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "turing2.md"
    source.write_text("More facts about Alan Turing.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    # Must be recorded as an update, not a new creation (original content preserved)
    assert "alan-turing" in result.pages_updated
    assert "alan-turing" not in result.pages_created
    page = store.read_page("alan-turing")
    assert "Original content." in page.content


@pytest.mark.asyncio
async def test_no_extractable_text_produces_skip(tmp_wiki, mock_provider, cache):
    """Empty extracted text on a create action skips with skip_reason='no extractable text'."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "blank.md"
    source.write_text("some bytes so it passes the size check", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    fake_extracted = ExtractedContent(text="", source_path=str(source), metadata={})
    with patch.object(agent._skill_agent, "extract", AsyncMock(return_value=fake_extracted)):
        result = await agent.ingest(str(source))

    assert result.skipped is True
    assert result.skip_reason == "no extractable text"


@pytest.mark.asyncio
async def test_youtube_has_summary_uses_skill_body(tmp_wiki, mock_provider, cache):
    """When has_summary=True, page body must equal extracted.text, not LLM page_content."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    skill_text = (
        "## Executive Summary\n\n"
        "A video about computing history.\n"
        "- Topic: Hollerith machine\n"
        "- Topic: Early programmers\n"
        "Key takeaway: computing began with mechanical tabulation.\n\n"
        "## Transcript\n\n"
        "[0:00] Hello world. [0:02] This is a test."
    )
    mock_extracted = ExtractedContent(
        text=skill_text,
        source_path="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        metadata={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                  "video_id": "dQw4w9WgXcQ", "has_summary": True},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.pages_created or result.pages_updated
    slug = (result.pages_created + result.pages_updated)[0]
    page = store.read_page(slug)
    assert page is not None
    assert "## Executive Summary" in page.content
    assert "## Transcript" in page.content
    assert "[0:00]" in page.content


@pytest.mark.asyncio
async def test_youtube_no_summary_falls_back_to_existing_flow(tmp_wiki, mock_provider, cache):
    """Without has_summary, page creation uses the existing LLM synthesis flow."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    mock_extracted = ExtractedContent(
        text="[0:00] Hello world. [0:02] This is a test.",
        source_path="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        metadata={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                  "video_id": "dQw4w9WgXcQ"},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.pages_created or result.pages_updated


@pytest.mark.asyncio
async def test_youtube_rerun_same_url_is_skipped(tmp_wiki, mock_provider, cache):
    """Re-ingesting the same YouTube URL must be skipped (deduped by URL hash)."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    url = "https://www.youtube.com/watch?v=O5nskjZ_GoI"
    mock_extracted = ExtractedContent(
        text="[0:00] Hello world.",
        source_path=url,
        metadata={"url": url, "video_id": "O5nskjZ_GoI"},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        first = await agent.ingest(url)
        second = await agent.ingest(url)

    assert not first.skipped, "first ingest must create or update a page"
    assert first.pages_created or first.pages_updated
    assert second.skipped, "second ingest of same URL must be skipped"
    assert second.skip_reason == "already ingested"


@pytest.mark.asyncio
async def test_youtube_rerun_allowed_after_page_deleted(tmp_wiki, mock_provider, cache):
    """Re-ingesting a URL must succeed (not be skipped) if the wiki page was deleted."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    url = "https://www.youtube.com/watch?v=O5nskjZ_GoI"
    mock_extracted = ExtractedContent(
        text="[0:00] Hello world.",
        source_path=url,
        metadata={"url": url, "video_id": "O5nskjZ_GoI"},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        first = await agent.ingest(url)

    assert first.pages_created, "first ingest must create a page"
    slug = first.pages_created[0]

    # Simulate user deleting the page from the UI
    (tmp_wiki / "wiki" / f"{slug}.md").unlink()

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        third = await agent.ingest(url)

    assert not third.skipped, "re-ingest after page deletion must not be skipped"


# ── SourceRef.size regression: content length vs. URL byte length ─────────────

@pytest.mark.asyncio
async def test_url_source_ref_size_is_content_length_not_url_length(tmp_wiki, mock_provider, cache):
    """SourceRef.size stores extracted-text char count, not the URL byte length.

    Regression: before the fix, URL sources stored len(url.encode()) in
    SourceRef.size (e.g. 58 for a 58-char URL), causing the lint report to show
    'source exceeded limit (58 chars)' and suggest '--max-source-chars 116'
    — both meaningless. After the fix, size equals the actual content length.
    """
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    url = "https://example.com/quantum-surface-code-article"  # 49 chars
    # Build content that exceeds the default 32 000-char limit so truncated=True.
    content = "quantum " * 5000  # 40 000 chars
    mock_extracted = ExtractedContent(
        text=content,
        source_path=url,
        metadata={},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest(url)

    assert result.pages_created, "ingest must create a page"
    page = store.read_page(result.pages_created[0])
    assert page is not None
    src = page.sources[0]
    assert src.truncated is True, "content exceeded 32 000-char default limit"
    # size must be the content char count, not the URL byte count (49).
    assert src.size == len(content), (
        f"expected size={len(content)}, got {src.size} "
        f"(URL is {len(url)} bytes — if size==URL length, the fix regressed)"
    )


# ── CJK (Chinese / Japanese / Korean) coverage ───────────────────────────────

@pytest.mark.asyncio
async def test_ingest_cjk_source_creates_page(tmp_wiki, cache):
    """Source file with Chinese content → page created with CJK slug and content preserved."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "量子计算.md"
    source.write_text(
        "# 量子计算\n量子计算是利用量子力学原理进行信息处理的技术。量子比特可以同时处于0和1的叠加态。",
        encoding="utf-8",
    )
    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["量子计算","量子比特"],"concepts":["量子叠加"],"tags":["量子计算","技术"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"新主题","action":"create","target":"","new_slug":"量子计算","update_content":"","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert not result.skipped
    assert result.pages_created
    page = store.read_page("量子计算")
    assert page is not None
    assert "量子" in page.content
    assert "量子计算" in page.title or "量子计算" in result.pages_created[0]


@pytest.mark.asyncio
async def test_ingest_cjk_page_update_appends_content(tmp_wiki, cache):
    """Ingest with action=update appends a CJK section to an existing CJK page."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("人工智能", WikiPage(
        title="人工智能", tags=["技术"],
        content="# 人工智能\n人工智能是模拟人类思维的技术。",
        status="active", confidence="medium", sources=[],
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "ml-update.md"
    source.write_text("机器学习是人工智能的重要子领域。", encoding="utf-8")

    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["机器学习","人工智能"],"concepts":["监督学习"],"tags":["人工智能"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"补充信息","action":"update","target":"人工智能","new_slug":"","update_content":"## 机器学习\\n机器学习是人工智能的重要分支，包括监督学习和无监督学习。","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "人工智能" in result.pages_updated
    page = store.read_page("人工智能")
    assert "机器学习" in page.content
    assert "人工智能" in page.content   # original content preserved


@pytest.mark.asyncio
async def test_ingest_cjk_tags_stored_in_page(tmp_wiki, cache):
    """CJK tags from the entity extraction response are stored in the created WikiPage."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "深度学习.md"
    source.write_text("深度学习通过多层神经网络学习数据特征。", encoding="utf-8")

    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["深度学习","神经网络"],"concepts":["反向传播"],"tags":["深度学习","机器学习","人工智能"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"新主题","action":"create","target":"","new_slug":"深度学习","update_content":"","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    await agent.ingest(str(source))

    page = store.read_page("深度学习")
    assert page is not None
    assert "深度学习" in page.tags or "机器学习" in page.tags


@pytest.mark.asyncio
async def test_ingest_adds_slug_to_routing(tmp_wiki, cache):
    """After a CREATE action, IngestAgent places the new slug in ROUTING.md."""
    from synthadoc.core.routing import RoutingIndex

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    routing_path = tmp_wiki / "ROUTING.md"
    RoutingIndex({"People": ["alan-turing"]}).save(routing_path)

    source = tmp_wiki / "raw_sources" / "grace-hopper.md"
    source.write_text("Grace Hopper pioneered compiler development.", encoding="utf-8")

    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(
            text='{"entities":["Grace Hopper"],"concepts":["compiler"],"tags":["computing"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"new topic","action":"create","target":"","new_slug":"grace-hopper","update_content":"","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
        # Pass 4: citation annotation — body falls back to raw text (no page_content given)
        CompletionResponse(
            text="# Grace Hopper\n\nGrace Hopper pioneered compiler development. ^[grace-hopper.md:1-1]",
            input_tokens=20, output_tokens=10,
        ),
        CompletionResponse(text="People", input_tokens=10, output_tokens=5),
        CompletionResponse(text="Overview text.", input_tokens=10, output_tokens=5),
    ]

    agent = IngestAgent(
        provider=provider, store=store, search=search,
        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
        wiki_root=tmp_wiki, routing_path=routing_path,
    )
    result = await agent.ingest(str(source))

    assert "grace-hopper" in result.pages_created
    content = routing_path.read_text()
    assert "[[grace-hopper]]" in content


@pytest.mark.asyncio
async def test_ingest_no_routing_path_skips_routing(tmp_wiki, cache):
    """When routing_path is not set, IngestAgent creates pages without touching routing."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "ada-lovelace.md"
    source.write_text("Ada Lovelace wrote the first algorithm.", encoding="utf-8")

    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["Ada Lovelace"],"concepts":["algorithm"],"tags":["computing"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"new topic","action":"create","target":"","new_slug":"ada-lovelace","update_content":"","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])

    agent = IngestAgent(
        provider=provider, store=store, search=search,
        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
        wiki_root=tmp_wiki,
    )
    result = await agent.ingest(str(source))

    assert "ada-lovelace" in result.pages_created
    # Provider was called for analysis + decision + Pass 4 citation + overview (not branch pick)
    assert provider.complete.call_count == 4


# ── Pass 4: citation annotation ───────────────────────────────────────────────

async def _make_agent_async(tmp_wiki, provider):
    """Async helper: build a fully-wired IngestAgent with wiki_root set."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await audit.init()
    await cache.init()
    return store, audit, IngestAgent(
        provider=provider, store=store, search=search,
        log_writer=log, audit_db=audit, cache=cache,
        max_pages=15, wiki_root=tmp_wiki,
    )


@pytest.fixture
async def db(tmp_wiki):
    """Return an initialised AuditDB for the tmp_wiki."""
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    return audit


@pytest.mark.asyncio
async def test_pass4_annotates_page_content(tmp_wiki):
    """Pass 4 LLM call annotates page_content with ^[source:L-L] markers on CREATE."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    analyse_resp = CompletionResponse(
        text='{"entities":["Ada Lovelace"],"tags":["computing"],"summary":"Ada Lovelace was the first programmer.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new topic","action":"create","target":"","new_slug":"ada-lovelace",'
             '"update_content":"","page_content":"# Ada Lovelace\\n\\nAda Lovelace was the first programmer."}',
        input_tokens=80, output_tokens=40)
    citation_resp = CompletionResponse(
        text="# Ada Lovelace\n\nAda Lovelace was the first programmer. ^[ada.md:1-2]",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Wiki overview.", input_tokens=10, output_tokens=5)

    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, citation_resp, overview_resp]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    source = tmp_wiki / "raw_sources" / "ada.md"
    source.write_text("Ada Lovelace was the first programmer.", encoding="utf-8")

    result = await agent.ingest(str(source))

    assert result.pages_created
    slug = result.pages_created[0]
    page = store.read_page(slug)
    assert page is not None
    assert "^[" in page.content, f"Expected citation marker in page content, got: {page.content!r}"


@pytest.mark.asyncio
async def test_pass4_failure_does_not_fail_ingest(tmp_wiki):
    """If Pass 4 raises an exception, ingest still succeeds and records citation_pass4_skipped."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    call_count = 0

    async def flaky_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        responses = [
            # analyse
            CompletionResponse(
                text='{"entities":["AI"],"tags":["ml"],"summary":"AI topic.","relevant":true}',
                input_tokens=50, output_tokens=20),
            # decision
            CompletionResponse(
                text='{"reasoning":"new","action":"create","target":"","new_slug":"ai-topic","update_content":"","page_content":"# AI\\n\\nArtificial intelligence."}',
                input_tokens=80, output_tokens=40),
        ]
        if call_count <= 2:
            return responses[call_count - 1]
        # Pass 4 call: raise an exception
        raise RuntimeError("LLM unavailable")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=flaky_complete)

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    source = tmp_wiki / "raw_sources" / "ai.md"
    source.write_text("Artificial intelligence is a broad field.", encoding="utf-8")

    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert not result.skipped
    assert result.pages_created

    events = await audit.list_events()
    assert any(e["event"] == "citation_pass4_skipped" for e in events), \
        f"Expected citation_pass4_skipped event, got: {[e['event'] for e in events]}"


@pytest.mark.asyncio
async def test_pass4_only_annotates_update_content(tmp_wiki):
    """For an UPDATE action, only the new update_content is annotated; existing body unchanged."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    analyse_resp = CompletionResponse(
        text='{"entities":["Alan Turing"],"tags":["history"],"summary":"Turing info.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"adds info","action":"update","target":"alan-turing",'
             '"new_slug":"","update_content":"## Enigma\\n\\nTuring broke Enigma.","page_content":""}',
        input_tokens=80, output_tokens=40)
    citation_resp = CompletionResponse(
        text="## Enigma\n\nTuring broke Enigma. ^[enigma.md:1-1]",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Wiki overview.", input_tokens=10, output_tokens=5)

    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, citation_resp, overview_resp]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    original_body = "# Alan Turing\n\nMathematician and computer scientist."
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"],
        content=original_body,
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))

    source = tmp_wiki / "raw_sources" / "enigma.md"
    source.write_text("Turing broke the Enigma cipher.", encoding="utf-8")

    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    # Original body must be unchanged
    assert original_body in page.content
    # The new update section has the citation marker
    assert "^[" in page.content, f"Expected citation in page, got: {page.content!r}"


@pytest.mark.asyncio
async def test_sidecar_written_for_pdf(tmp_wiki):
    """After ingesting a PDF source with page_boundaries, .synthadoc/extracted/<name>.txt is created."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.base import ExtractedContent

    provider = AsyncMock()
    analyse_resp = CompletionResponse(
        text='{"entities":["PDF"],"tags":["test"],"summary":"PDF content.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new","action":"create","target":"","new_slug":"pdf-doc","update_content":"","page_content":"# PDF Doc\\n\\nContent from PDF."}',
        input_tokens=80, output_tokens=40)
    citation_resp = CompletionResponse(
        text="# PDF Doc\n\nContent from PDF. ^[sample.pdf:1-3]",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Overview.", input_tokens=10, output_tokens=5)
    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, citation_resp, overview_resp]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)

    pdf_path = tmp_wiki / "raw_sources" / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content for testing purposes")

    fake_extracted = ExtractedContent(
        text="PDF content here.\nPage two content.",
        source_path=str(pdf_path),
        metadata={"page_boundaries": {1: 1, 2: 2}},
    )

    with patch.object(agent._skill_agent, "extract", AsyncMock(return_value=fake_extracted)):
        with patch.object(IngestAgent, "_update_overview", AsyncMock()):
            result = await agent.ingest(str(pdf_path))

    txt_file = tmp_wiki / ".synthadoc" / "extracted" / "sample.txt"
    assert txt_file.exists(), f"Expected sidecar txt at {txt_file}"
    assert "PDF content here" in txt_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_sidecar_pagemap_written_for_pdf(tmp_wiki):
    """After ingesting a PDF, .synthadoc/extracted/<name>.pdf.pagemap exists and is valid JSON."""
    import itertools
    import json
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.base import ExtractedContent

    provider = AsyncMock()
    analyse_resp = CompletionResponse(
        text='{"entities":["PDF"],"tags":["test"],"summary":"PDF content.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new","action":"create","target":"","new_slug":"mypdf","update_content":"","page_content":"# MyPDF\\n\\nContent."}',
        input_tokens=80, output_tokens=40)
    citation_resp = CompletionResponse(
        text="# MyPDF\n\nContent. ^[mypdf.pdf:1-2]",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Overview.", input_tokens=10, output_tokens=5)
    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, citation_resp, overview_resp]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)

    pdf_path = tmp_wiki / "raw_sources" / "mypdf.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 content")

    page_boundaries = {1: 1, 2: 5, 3: 10}
    fake_extracted = ExtractedContent(
        text="Page 1 content.\nPage 2 content.\nPage 3 content.",
        source_path=str(pdf_path),
        metadata={"page_boundaries": page_boundaries},
    )

    with patch.object(agent._skill_agent, "extract", AsyncMock(return_value=fake_extracted)):
        with patch.object(IngestAgent, "_update_overview", AsyncMock()):
            result = await agent.ingest(str(pdf_path))

    pagemap_file = tmp_wiki / ".synthadoc" / "extracted" / "mypdf.pdf.pagemap"
    assert pagemap_file.exists(), f"Expected pagemap at {pagemap_file}"
    data = json.loads(pagemap_file.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert len(data) == 3


@pytest.mark.asyncio
async def test_sidecar_not_written_for_txt_source(tmp_wiki):
    """For a .txt source (no page_boundaries), no sidecar files are written."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=itertools.cycle([
        CompletionResponse(
            text='{"entities":["text"],"tags":["test"],"summary":"Text content.","relevant":true}',
            input_tokens=50, output_tokens=20),
        CompletionResponse(
            text='{"reasoning":"new","action":"create","target":"","new_slug":"text-doc","update_content":"","page_content":"# Text Doc\\n\\nContent."}',
            input_tokens=80, output_tokens=40),
        CompletionResponse(
            text="# Text Doc\n\nContent. ^[notes.txt:1-1]",
            input_tokens=30, output_tokens=15),
        CompletionResponse(text="Overview.", input_tokens=10, output_tokens=5),
    ]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)

    source = tmp_wiki / "raw_sources" / "notes.txt"
    source.write_text("This is plain text content.", encoding="utf-8")

    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    extracted_dir = tmp_wiki / ".synthadoc" / "extracted"
    sidecar_txt = extracted_dir / "notes.txt"
    sidecar_pagemap = extracted_dir / "notes.pdf.pagemap"
    # No extracted/ dir at all, or no sidecar files
    assert not sidecar_txt.exists() or not (extracted_dir / "notes.pdf.pagemap").exists(), \
        "Sidecar files must NOT be written for plain-text sources without page_boundaries"
    assert not sidecar_pagemap.exists(), "pagemap must not exist for non-PDF sources"


@pytest.mark.asyncio
async def test_pass4_result_recorded_in_claim_citations(tmp_wiki, db, cache):
    """After successful Pass 4, claim_citations rows are written to AuditDB."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    analyse_resp = CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"AI research.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new","action":"create","target":"","new_slug":"ai-research",'
             '"update_content":"","page_content":"# AI Research\\n\\nNeural networks are powerful."}',
        input_tokens=80, output_tokens=40)
    # Return annotated content with a citation marker using the source filename
    citation_resp = CompletionResponse(
        text="# AI Research\n\nNeural networks are powerful. ^[research.md:1-3]",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Overview.", input_tokens=10, output_tokens=5)
    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, citation_resp, overview_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")

    agent = IngestAgent(
        provider=provider, store=store, search=search,
        log_writer=log, audit_db=db, cache=cache,
        max_pages=15, wiki_root=tmp_wiki,
    )

    source = tmp_wiki / "raw_sources" / "research.md"
    source.write_text("Neural networks are powerful tools.", encoding="utf-8")

    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert result.pages_created
    citations = await db.list_citations()
    assert len(citations) > 0, "Expected citation rows in claim_citations after Pass 4"
    assert citations[0]["source_file"] == "research.md"
    assert citations[0]["line_start"] == 1
    assert citations[0]["line_end"] == 3


@pytest.mark.asyncio
async def test_pass4_no_citations_logs_warning(tmp_wiki, caplog):
    """Pass 4 with no ^[filename:L-L] markers must log a WARNING and emit
    citation_pass4_no_markers audit event."""
    import itertools
    import logging
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    # Responses: analysis → decision → Pass 4 (section returned UNCHANGED, no markers) → overview
    analyse_resp = CompletionResponse(
        text='{"entities":["Plan"],"tags":["planning"],"summary":"A plan.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new plan","action":"create","target":"","new_slug":"plan",'
             '"update_content":"","page_content":"# Plan\\n\\nSome plan content here."}',
        input_tokens=80, output_tokens=40)
    # Pass 4 returns the section UNCHANGED — no citations added
    pass4_resp = CompletionResponse(
        text="# Plan\n\nSome plan content here.",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Wiki overview.", input_tokens=10, output_tokens=5)

    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, pass4_resp, overview_resp]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    source = tmp_wiki / "raw_sources" / "plan.md"
    source.write_text("line 1\nline 2\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="synthadoc.agents.ingest_agent"):
        with patch.object(IngestAgent, "_update_overview", AsyncMock()):
            await agent.ingest(str(source))

    # Check that a WARNING was logged about zero citations
    warning_records = [
        r for r in caplog.records
        if "citation_pass4_no_markers" in r.message or "produced no" in r.message
    ]
    assert warning_records, (
        f"Expected a WARNING about 0 citations. Got records: "
        f"{[(r.levelname, r.message) for r in caplog.records]}"
    )

    # Audit event must be recorded
    events = await audit.list_events()
    citation_events = [e for e in events if e["event"] == "citation_pass4_no_markers"]
    assert citation_events, (
        f"Expected citation_pass4_no_markers audit event. Got events: "
        f"{[e['event'] for e in events]}"
    )


@pytest.mark.asyncio
async def test_pass4_with_citation_does_not_warn(tmp_wiki, caplog):
    """When Pass 4 produces at least one ^[filename:L-L] marker, no warning is emitted."""
    import itertools
    import logging
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    analyse_resp = CompletionResponse(
        text='{"entities":["Plan2"],"tags":["planning"],"summary":"Another plan.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new plan","action":"create","target":"","new_slug":"plan2",'
             '"update_content":"","page_content":"# Plan 2\\n\\nSome plan content."}',
        input_tokens=80, output_tokens=40)
    # Pass 4 returns body WITH a citation marker
    pass4_resp = CompletionResponse(
        text="# Plan 2\n\nSome plan content.^[plan2.md:1-2]",
        input_tokens=30, output_tokens=15)
    overview_resp = CompletionResponse(
        text="Wiki overview.", input_tokens=10, output_tokens=5)

    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [analyse_resp, decision_resp, pass4_resp, overview_resp]))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    source = tmp_wiki / "raw_sources" / "plan2.md"
    source.write_text("line 1\nline 2\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="synthadoc.agents.ingest_agent"):
        with patch.object(IngestAgent, "_update_overview", AsyncMock()):
            await agent.ingest(str(source))

    # Check that NO WARNING was logged about zero citations
    warning_msgs = [
        r.message for r in caplog.records
        if ("citation_pass4_no_markers" in r.message or "produced no" in r.message)
        and r.levelno >= logging.WARNING
    ]
    assert not warning_msgs, (
        f"Unexpected citation warning: {warning_msgs}. "
        f"Full log records: {[(r.levelname, r.message) for r in caplog.records]}"
    )


# ── Bug A: sanity check ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pass4_sanity_check_tolerates_heading_reformat(tmp_wiki):
    """Bug A fix: LLM changing ## to # must NOT fail the sanity check."""
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    section = "## CAPEX Classification\n\nContent with many words here."
    lm_return = "# CAPEX Classification\n\nContent with many words here.^[file.md:1-2]"

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=lm_return, input_tokens=10, output_tokens=10
    ))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    annotated, citations = await agent._annotate_citations(
        section, "line 1\nline 2\n", "file.md"
    )
    assert citations, f"Expected citations but got empty list. Annotated: {annotated!r}"


@pytest.mark.asyncio
async def test_pass4_sanity_check_rejects_too_short_response(tmp_wiki):
    """Bug A fix: response shorter than 80% of section → skipped with audit event."""
    import json as _json
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    section = "## Section\n\n" + "A word. " * 40  # long section
    lm_return = '{"error": "json"}'  # very short

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=lm_return, input_tokens=10, output_tokens=10
    ))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    annotated, citations = await agent._annotate_citations(
        section, "line 1\nline 2\n", "file.md"
    )
    assert annotated == section
    assert citations == []
    events = await audit.list_events()
    skipped = [
        e for e in events
        if e["event"] == "citation_pass4_skipped"
        and _json.loads(e.get("metadata") or "{}").get("error") == "response_too_short"
    ]
    assert skipped, f"Expected citation_pass4_skipped with response_too_short, got: {events}"


# ── Bug B: case-sensitive filename ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pass4_case_insensitive_filename_match(tmp_wiki):
    """Bug B fix: LLM returning FILENAME.MD (uppercase) must still produce citations."""
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    section = "# Section\n\nSome content."
    lm_return = "# Section\n\nSome content.^[FILE.MD:1-2]"

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=lm_return, input_tokens=10, output_tokens=10
    ))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    annotated, citations = await agent._annotate_citations(
        section, "line 1\nline 2\n", "file.md"
    )
    assert citations, f"Expected citations for uppercase FILENAME match, got: {citations}"


# ── Bug C: line-based truncation ──────────────────────────────────────────────

def test_pass4_numbered_source_truncates_by_lines():
    """Bug C fix: numbered source must be truncated by line count, not character count."""
    from synthadoc.agents.ingest_agent import _MAX_CITATION_LINES

    lines = [f"Line {i}: content" for i in range(_MAX_CITATION_LINES + 50)]
    source_text = "\n".join(lines)

    numbered = "\n".join(
        f"{i+1}: {line}"
        for i, line in enumerate(source_text.splitlines()[:_MAX_CITATION_LINES])
    )
    numbered_lines = numbered.splitlines()
    assert len(numbered_lines) <= _MAX_CITATION_LINES
    for ln in numbered_lines:
        assert ":" in ln  # format is "N: content"


# ── Bug D: empty source_text audit event ─────────────────────────────────────

@pytest.mark.asyncio
async def test_pass4_empty_source_text_emits_audit_event(tmp_wiki):
    """Bug D fix: empty source_text must emit citation_pass4_skipped audit event."""
    import json as _json
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text="", input_tokens=0, output_tokens=0
    ))

    store, audit, agent = await _make_agent_async(tmp_wiki, provider)
    annotated, citations = await agent._annotate_citations(
        "# Section\n\nContent.", "", "file.md"
    )

    assert citations == []
    events = await audit.list_events()
    assert any(
        e["event"] == "citation_pass4_skipped"
        and _json.loads(e.get("metadata") or "{}").get("error") == "empty_source_text"
        for e in events
    ), f"Expected empty_source_text audit event, got: {events}"


# ── Bug E: bust_cache propagation ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pass4_bust_cache_bypasses_annotation_cache(tmp_wiki):
    """Bug E fix: bust_cache=True must bypass the annotation cache."""
    from synthadoc.providers.base import CompletionResponse

    section = "# Section\n\nSome content."
    source = "line 1\nline 2\n"
    call_count = {"n": 0}

    class CountingProvider:
        async def complete(self, messages, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return CompletionResponse(text=section, input_tokens=10, output_tokens=10)
            return CompletionResponse(
                text=section + "^[file.md:1-2]", input_tokens=10, output_tokens=10
            )

    store, audit, agent = await _make_agent_async(tmp_wiki, CountingProvider())

    # First call: no citations → not cached (Bug F fix)
    _, c1 = await agent._annotate_citations(section, source, "file.md", bust_cache=False)
    assert c1 == []

    # Second call with bust_cache=True: must call LLM again
    _, c2 = await agent._annotate_citations(section, source, "file.md", bust_cache=True)
    assert c2, f"Expected citations on second call with bust_cache=True, got: {c2}"
    assert call_count["n"] == 2, f"Expected 2 LLM calls, got {call_count['n']}"


# ── Bug F: zero-citation results not cached ────────────────────────────────────

@pytest.mark.asyncio
async def test_pass4_zero_citation_result_not_cached(tmp_wiki):
    """Bug F fix: a 0-citation result must NOT be cached; next call retries the LLM."""
    from synthadoc.providers.base import CompletionResponse

    section = "# Section\n\nSome content."
    source = "line 1\nline 2\n"
    call_count = {"n": 0}

    class CountingProvider:
        async def complete(self, messages, **kw):
            call_count["n"] += 1
            return CompletionResponse(text=section, input_tokens=10, output_tokens=10)

    store, audit, agent = await _make_agent_async(tmp_wiki, CountingProvider())

    await agent._annotate_citations(section, source, "file.md")
    await agent._annotate_citations(section, source, "file.md")

    assert call_count["n"] == 2, (
        f"0-citation result was cached — second call did not reach LLM. "
        f"LLM calls: {call_count['n']}"
    )


# --- _backfill_okf_fields unit tests ---

def test_backfill_sets_type_when_absent():
    """type is set from analysis when the page has no type attribute (pre-v0.9.0 page)."""
    from synthadoc.agents.ingest_agent import _backfill_okf_fields
    page = WikiPage(title="T", tags=[], content="", status="active", confidence="high", sources=[])
    del page.__dict__["type"]   # simulate page loaded before type field existed
    _backfill_okf_fields(page, {"type": "concept"}, "paper.pdf")
    assert page.type == "concept"


def test_backfill_does_not_overwrite_existing_type():
    """type is not changed when the page already has a type value."""
    from synthadoc.agents.ingest_agent import _backfill_okf_fields
    page = WikiPage(title="T", tags=[], content="", status="active", confidence="high",
                    sources=[], type="person")
    _backfill_okf_fields(page, {"type": "concept"}, "paper.pdf")
    assert page.type == "person"


def test_backfill_sets_resource_for_url_source():
    """resource is set to the URL when the page has no resource and source is a URL."""
    from synthadoc.agents.ingest_agent import _backfill_okf_fields
    page = WikiPage(title="T", tags=[], content="", status="active", confidence="high", sources=[])
    del page.__dict__["resource"]   # simulate page loaded before resource field existed
    _backfill_okf_fields(page, {}, "https://example.com/article")
    assert page.resource == "https://example.com/article"


def test_backfill_does_not_set_resource_for_file_source():
    """resource is not set when the source is a local file path."""
    from synthadoc.agents.ingest_agent import _backfill_okf_fields
    page = WikiPage(title="T", tags=[], content="", status="active", confidence="high", sources=[])
    _backfill_okf_fields(page, {}, "/path/to/paper.pdf")
    assert page.resource is None


def test_backfill_tolerates_page_missing_both_fields():
    """No AttributeError when both type and resource are absent from the page object."""
    from synthadoc.agents.ingest_agent import _backfill_okf_fields
    page = WikiPage(title="T", tags=[], content="", status="active", confidence="high", sources=[])
    del page.__dict__["type"]
    del page.__dict__["resource"]
    _backfill_okf_fields(page, {"type": "technology"}, "https://example.com/chip")
    assert page.type == "technology"
    assert page.resource == "https://example.com/chip"


# --- Active page protection contract ---

@pytest.mark.asyncio
async def test_decision_prompt_includes_page_status(tmp_wiki, cache):
    """The decision prompt must include status= for each candidate page so the LLM
    can apply the RULE 1b active-page-protection contract."""
    import itertools
    from unittest.mock import AsyncMock, call
    from synthadoc.providers.base import CompletionResponse

    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["CAPEX"],"concepts":[],"tags":["finance"],"relevant":true}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"capex","update_content":"","page_content":"# CAPEX\\n\\nContent."}',
        input_tokens=100, output_tokens=50,
    )
    _citation = CompletionResponse(text="# CAPEX\n\nContent.", input_tokens=10, output_tokens=5)
    _overview = CompletionResponse(text="Overview.", input_tokens=10, output_tokens=5)
    p.complete.side_effect = itertools.cycle([_entity, _decision, _citation, _overview])

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("finance-plan", WikiPage(
        title="Finance Plan", tags=["finance"], content="# Finance Plan\n\nMedian of first 3 years.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    # Second page so BM25 corpus has 2+ docs (single-doc IDF is always ≤ 0)
    store.write_page("unrelated-topic", WikiPage(
        title="Unrelated Topic", tags=["other"], content="# Unrelated\n\nSomething else entirely.",
        status="draft", confidence="medium", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    source = tmp_wiki / "raw_sources" / "capex.md"
    source.write_text("Finance CAPEX: median of first 3 years of fixed assets.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    await agent.ingest(str(source))

    # The decision call is the second complete() call (after entity extraction).
    # Verify the prompt text passed to the LLM contains status= for the candidate page.
    decision_call_prompt = None
    for c in p.complete.call_args_list:
        messages = c.kwargs.get("messages") or (c.args[0] if c.args else [])
        if messages and "action" in messages[0].content and "RULE" in messages[0].content:
            decision_call_prompt = messages[0].content
            break

    assert decision_call_prompt is not None, "Decision LLM call not found"
    assert "status=active" in decision_call_prompt, (
        "Page status must appear in the decision prompt so the LLM can apply "
        "RULE 1b active-page-protection"
    )
    assert "RULE 1b" in decision_call_prompt, \
        "Decision prompt must contain RULE 1b (active page protection contract)"
    assert "action='flag'" in decision_call_prompt, \
        "Decision prompt must reference action='flag' in RULE 1b"


@pytest.mark.asyncio
async def test_fix10_decision_receives_full_source_not_summary(tmp_wiki, cache):
    """Fix 10: _DECISION_PROMPT must format with source_text, not summary.
    The decision LLM call must receive the full source text."""
    from synthadoc.agents.ingest_agent import _DECISION_PROMPT

    # _DECISION_PROMPT must accept {source_text} as a format variable
    # (not {summary} — if {summary} appears, the format call below raises KeyError)
    try:
        filled = _DECISION_PROMPT.format(
            pages="page context",
            source_text="some full source text here",
            entities="entity1, entity2",
        )
    except KeyError as exc:
        pytest.fail(
            f"_DECISION_PROMPT still uses {{summary}} — got KeyError: {exc}. "
            "Replace {{summary}} with {{source_text}} in _DECISION_PROMPT."
        )

    assert "some full source text here" in filled


# --- _extract_key_data unit tests ---

def test_extract_key_data_code_block():
    """Code blocks in source → extracted as formula items."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    src = "Some text.\n\n```\nFCF = CFO - Maintenance_CAPEX\n```\n"
    result = _extract_key_data(src)
    assert "FCF = CFO - Maintenance_CAPEX" in result


def test_extract_key_data_bold_bullet():
    """Bold-bullet numeric entries → extracted."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    src = "- **11%** — High-risk sectors\n- **10%** — Mid-risk\n"
    result = _extract_key_data(src)
    assert any("11%" in item for item in result)
    assert any("10%" in item for item in result)


def test_extract_key_data_no_numbers():
    """Pure prose with no numbers → empty list."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    src = "This document discusses methodology and approach in general terms."
    assert _extract_key_data(src) == []


def test_extract_key_data_empty():
    """Empty string → empty list, no crash."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    assert _extract_key_data("") == []


def test_extract_key_data_deduplicates():
    """Same formula in two code blocks → appears once."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    src = "```\nFCF = CFO - CAPEX\n```\n\nSome text.\n\n```\nFCF = CFO - CAPEX\n```\n"
    result = _extract_key_data(src)
    assert result.count("FCF = CFO - CAPEX") == 1


def test_extract_key_data_malformed_code_block():
    """Unclosed code block — function does not raise, returns whatever was found."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    src = "```\nFCF = CFO - CAPEX\n"  # unclosed
    result = _extract_key_data(src)   # must not raise
    assert isinstance(result, list)


def test_extract_key_data_formula_line():
    """Standalone formula lines (var = expr) are extracted."""
    from synthadoc.agents.ingest_agent import _extract_key_data
    src = "total_mv_cny = total_mv × 10,000\n"
    result = _extract_key_data(src)
    assert any("total_mv" in item for item in result)


# ── _normalize_citation_markers ───────────────────────────────────────────────

def test_normalize_single_line_citation():
    """^[file:N] → ^[file:N-N]."""
    from synthadoc.agents.ingest_agent import _normalize_citation_markers
    result = _normalize_citation_markers("Some claim. ^[report.md:42]")
    assert result == "Some claim. ^[report.md:42-42]"


def test_normalize_comma_range_citation():
    """^[file:N,M-P] → ^[file:N-P] (first-to-last number)."""
    from synthadoc.agents.ingest_agent import _normalize_citation_markers
    result = _normalize_citation_markers("Claim. ^[market.md:12,16-21]")
    assert result == "Claim. ^[market.md:12-21]"


def test_normalize_comma_pair_citation():
    """^[file:N,M] → ^[file:N-M]."""
    from synthadoc.agents.ingest_agent import _normalize_citation_markers
    result = _normalize_citation_markers("Claim. ^[data.md:27,54]")
    assert result == "Claim. ^[data.md:27-54]"


def test_normalize_trailing_comma_range():
    """^[file:N-M,P] → ^[file:N-P]."""
    from synthadoc.agents.ingest_agent import _normalize_citation_markers
    result = _normalize_citation_markers("Claim. ^[src.md:74-80,107]")
    assert result == "Claim. ^[src.md:74-107]"


def test_normalize_leaves_canonical_unchanged():
    """Already-canonical ^[file:N-N] markers are not modified."""
    from synthadoc.agents.ingest_agent import _normalize_citation_markers
    text = "Claim. ^[report.md:10-15]"
    assert _normalize_citation_markers(text) == text


def test_normalize_multiple_citations_in_text():
    """Multiple mixed citations in one string are all normalised."""
    from synthadoc.agents.ingest_agent import _normalize_citation_markers
    text = "A ^[a.md:5] B ^[b.md:10-12] C ^[c.md:7,9]"
    result = _normalize_citation_markers(text)
    assert "^[a.md:5-5]" in result
    assert "^[b.md:10-12]" in result
    assert "^[c.md:7-9]" in result


def test_citation_prompt_example_uses_actual_filename():
    """_CITATION_PROMPT formatted with a real filename must embed that name in the example.

    Regression: the prompt previously contained a literal ^[FILENAME:L-L] example,
    which caused LLMs to output 'FILENAME' as the source name in citations.  The fix
    embeds the actual {filename} variable in the example so the LLM sees the real name.
    """
    from synthadoc.agents.ingest_agent import _CITATION_PROMPT

    numbered = "\n".join(f"{i+1}: line {i+1}" for i in range(9))
    formatted = _CITATION_PROMPT.format(
        filename="my-source.txt",
        numbered_source=numbered,
        section="Some claim from the source.",
    )
    # The formatted prompt must include the concrete filename in the example
    assert "^[my-source.txt:7-9]" in formatted, \
        "Formatted _CITATION_PROMPT must embed the actual filename in the example citation"
    # The placeholder word must NOT appear as part of a citation marker
    assert "^[FILENAME:" not in formatted, \
        "Formatted _CITATION_PROMPT must not contain the literal placeholder ^[FILENAME:"
