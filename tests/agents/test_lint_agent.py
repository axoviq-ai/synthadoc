# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.lint_agent import LintAgent, LintReport, find_orphan_slugs, _fix_dangling_wikilinks, LINT_SKIP_SLUGS, LINT_SKIP_SOURCE_SLUGS, _parse_adversarial_response, _check_page_citations, read_current_lint_state
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef
from synthadoc.storage.log import LogWriter, AuditDB


@pytest.mark.asyncio
async def test_lint_finds_contradictions(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    store.write_page("p2", WikiPage(title="P2", tags=[], content="Normal.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Resolution.", input_tokens=50, output_tokens=10)
    agent = LintAgent(provider=provider, store=store, log_writer=log)
    report = await agent.lint(scope="contradictions")
    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_lint_finds_orphans(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(title="Hub", tags=[], content="See [[linked]].",
        status="active", confidence="medium", sources=[]))
    store.write_page("linked", WikiPage(title="Linked", tags=[], content="content",
        status="active", confidence="medium", sources=[]))
    store.write_page("orphan", WikiPage(title="Orphan", tags=[], content="alone",
        status="active", confidence="medium", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")
    assert "orphan" in report.orphan_slugs
    assert "index" not in report.orphan_slugs
    assert "dashboard" not in report.orphan_slugs
    assert "log" not in report.orphan_slugs


@pytest.mark.asyncio
async def test_lint_aliased_wikilink_not_orphan(tmp_wiki):
    """[[slug|Display Text]] aliases should not cause the target to be flagged as orphan."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(title="Hub", tags=[],
        content="See [[quantum-computing|Quantum Computing]] for details.",
        status="active", confidence="medium", sources=[]))
    store.write_page("quantum-computing", WikiPage(title="Quantum Computing", tags=[],
        content="content", status="active", confidence="medium", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")
    assert "quantum-computing" not in report.orphan_slugs


def test_find_orphan_slugs_basic():
    """Pages with no inbound links from content pages are orphans."""
    page_texts = {
        "page-a": "See [[page-b]].",
        "page-b": "No links here.",
        "page-c": "Standalone page.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "page-a" in orphans      # nothing links to page-a
    assert "page-b" not in orphans  # page-a links to page-b
    assert "page-c" in orphans      # nothing links to page-c


def test_find_orphan_slugs_overview_excluded():
    """Links from overview (and other skip slugs) must not count as real references."""
    page_texts = {
        "overview": "[[page-a]] [[page-b]]",
        "page-a":   "See [[page-b]].",
        "page-b":   "No links here.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "overview" not in orphans   # skip slugs never reported
    assert "page-a" in orphans         # overview link doesn't count; nothing else links to page-a
    assert "page-b" not in orphans     # page-a links to page-b → not an orphan


def test_find_orphan_slugs_skip_slugs_never_reported():
    """Skip slugs (index, dashboard, …) are never returned as orphans."""
    page_texts = {slug: "" for slug in LINT_SKIP_SLUGS}
    page_texts["real-page"] = "content"
    orphans = find_orphan_slugs(page_texts)
    for slug in LINT_SKIP_SLUGS:
        assert slug not in orphans


def test_find_orphan_slugs_index_links_do_not_rescue():
    """Links from index.md must NOT rescue pages from orphan status.
    index is a directory page; only content-page links count.
    index itself must never appear in the orphan report."""
    page_texts = {
        "index":   "## Recently Added\n- [[page-a]]\n",
        "page-a":  "No outbound links.",
        "page-b":  "No outbound links.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "page-a" in orphans       # index link doesn't count → still orphan
    assert "page-b" in orphans       # nothing links to page-b → orphan
    assert "index" not in orphans    # index itself never reported as orphan


def test_find_orphan_slugs_self_link_does_not_prevent_orphan():
    """A page that links only to itself must still be reported as an orphan."""
    page_texts = {
        "lonely": "See also [[lonely]] for more.",  # self-link
        "hub":    "Links to [[real-page]].",
        "real-page": "No outbound links.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "lonely" in orphans       # self-link must not count as an inbound reference
    assert "real-page" not in orphans  # hub links to real-page → not an orphan
    assert "hub" in orphans            # nothing links to hub


@pytest.mark.asyncio
async def test_lint_skip_slugs_not_counted_as_contradictions(tmp_wiki):
    """index, dashboard, and other auto-generated pages must never appear in contradiction reports."""
    store = WikiStorage(tmp_wiki / "wiki")
    for slug in LINT_SKIP_SLUGS:
        store.write_page(slug, WikiPage(title=slug.title(), tags=[],
            content="auto-generated", status="contradicted",
            confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="contradictions")
    assert report.contradictions_found == 0


@pytest.mark.asyncio
async def test_orphan_flag_cleared_when_inbound_link_added(tmp_wiki):
    """Page with orphan=True transitions to orphan=False once another page links to it."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("page-a", WikiPage(title="Page A", tags=[],
        content="Content of page A.", status="active", confidence="high",
        sources=[], orphan=True))
    store.write_page("page-b", WikiPage(title="Page B", tags=[],
        content="Links to [[page-a]] here.", status="active", confidence="high",
        sources=[]))

    page_before = store.read_page("page-a")
    assert page_before is not None
    assert page_before.orphan is True

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    await agent.lint(scope="orphans")

    page_after = store.read_page("page-a")
    assert page_after is not None
    assert page_after.orphan is False


# ── CJK (Chinese / Japanese / Korean) coverage ───────────────────────────────

def test_find_orphan_slugs_cjk_wikilinks():
    """[[量子计算]] wikilinks with CJK targets are parsed correctly by the orphan detector."""
    page_texts = {
        "人工智能":  "人工智能是一个广泛的领域，包括[[机器学习]]和[[量子计算]]。",
        "机器学习":  "机器学习是人工智能的子领域。",
        "量子计算":  "量子计算利用量子力学原理。",
        "深度学习":  "深度学习是机器学习的一种方法。没有人链接到这里。",
    }
    orphans = find_orphan_slugs(page_texts)

    assert "机器学习" not in orphans      # linked from 人工智能
    assert "量子计算" not in orphans      # linked from 人工智能
    assert "深度学习" in orphans          # no inbound links
    assert "人工智能" in orphans          # nothing links to 人工智能


@pytest.mark.asyncio
async def test_lint_cjk_orphan_detection(tmp_wiki):
    """Full async lint correctly identifies orphans among CJK-slugged pages."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("人工智能", WikiPage(title="人工智能", tags=[],
        content="参见[[机器学习]]了解更多。",
        status="active", confidence="medium", sources=[]))
    store.write_page("机器学习", WikiPage(title="机器学习", tags=[],
        content="机器学习是一种技术。",
        status="active", confidence="medium", sources=[]))
    store.write_page("量子计算", WikiPage(title="量子计算", tags=[],
        content="量子计算尚未在本维基中建立链接。",
        status="active", confidence="medium", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")

    assert "量子计算" in report.orphan_slugs    # no inbound link
    assert "机器学习" not in report.orphan_slugs  # linked from 人工智能


@pytest.mark.asyncio
async def test_lint_cjk_contradiction_detected(tmp_wiki):
    """CJK page with contradicted status is found and included in the contradiction report."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("量子纠错", WikiPage(title="量子纠错", tags=[],
        content="⚠ 此页面存在矛盾内容。量子纠错需要大量量子比特。",
        status="contradicted", confidence="low", sources=[]))
    store.write_page("人工智能", WikiPage(title="人工智能", tags=[],
        content="正常内容，没有矛盾。",
        status="active", confidence="high", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="矛盾已解决。", input_tokens=50, output_tokens=10)
    agent = LintAgent(provider=provider, store=store, log_writer=log)
    report = await agent.lint(scope="contradictions")

    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_lint_records_contradiction_found_audit_event(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AsyncMock(spec=AuditDB)
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    await agent.lint(scope="contradictions", job_id="job-123")
    audit.record_audit_event.assert_awaited_once_with("job-123", "contradiction_found", {"slug": "p1"})


@pytest.mark.asyncio
async def test_lint_records_auto_resolved_audit_event(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AsyncMock(spec=AuditDB)
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"resolvable": true, "reason": "Claims reconciled.", "resolution": "Reconciled content."}',
        input_tokens=10, output_tokens=5,
    )
    agent = LintAgent(provider=provider, store=store, log_writer=log, audit_db=audit)
    await agent.lint(scope="contradictions", auto_resolve=True, job_id="job-456")
    calls = [c.args for c in audit.record_audit_event.await_args_list]
    assert ("job-456", "contradiction_found", {"slug": "p1"}) in calls
    assert ("job-456", "auto_resolved", {"slug": "p1"}) in calls


# ── Dangling link cleanup ─────────────────────────────────────────────────────

def test_fix_dangling_wikilinks_drops_list_item():
    """List item whose primary content is a dangling link is removed."""
    existing = {"alan-turing", "index"}
    content = (
        "# Index\n\n"
        "- [[alan-turing]] — pioneer\n"
        "- [[deleted-page]] — Watch\n"
        "- [[also-gone]] — old reference\n"
    )
    result = _fix_dangling_wikilinks(content, existing)
    assert "[[deleted-page]]" not in result
    assert "[[also-gone]]" not in result
    assert "[[alan-turing]]" in result


def test_fix_dangling_wikilinks_unlinks_inline():
    """Inline dangling [[link]] is replaced with plain display text."""
    existing = {"real-page"}
    content = "As described in [[gone-page]], and also in [[real-page]]."
    result = _fix_dangling_wikilinks(content, existing)
    assert "[[gone-page]]" not in result
    assert "gone-page" in result          # display text kept
    assert "[[real-page]]" in result      # existing link untouched


def test_fix_dangling_wikilinks_aliased_inline():
    """[[slug|Display Text]] strips the link notation, keeps display text."""
    existing = {"real-page"}
    content = "See [[deleted|Old Name]] for details."
    result = _fix_dangling_wikilinks(content, existing)
    assert "[[deleted|Old Name]]" not in result
    assert "Old Name" in result


@pytest.mark.asyncio
async def test_lint_removes_dangling_links(tmp_wiki):
    """Running lint cleans up [[links]] pointing to pages that no longer exist."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("index", WikiPage(title="Index", tags=[],
        content="# Index\n\n- [[alan-turing]] — pioneer\n- [[crashcourse-computer-science]] — Watch\n",
        status="active", confidence="high", sources=[]))
    store.write_page("alan-turing", WikiPage(title="Alan Turing", tags=[],
        content="Mathematician.", status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")

    assert report.dangling_links_removed == 1
    updated = store.read_page("index")
    assert updated is not None
    assert "[[crashcourse-computer-science]]" not in updated.content
    assert "[[alan-turing]]" in updated.content


# ── Adversarial pass ──────────────────────────────────────────────────────────


def test_parse_adversarial_response_valid_json():
    result = _parse_adversarial_response('[{"claim": "X was the first.", "concern": "Overstated"}]')
    assert result == [{"claim": "X was the first.", "concern": "Overstated"}]


def test_parse_adversarial_response_markdown_fenced():
    result = _parse_adversarial_response(
        '```json\n[{"claim": "X", "concern": "Y"}]\n```'
    )
    assert result == [{"claim": "X", "concern": "Y"}]


def test_parse_adversarial_response_empty_list():
    assert _parse_adversarial_response("[]") == []


def test_parse_adversarial_response_invalid_returns_empty():
    assert _parse_adversarial_response("not valid json") == []


def test_parse_adversarial_response_skips_entries_without_concern():
    result = _parse_adversarial_response('[{"claim": "X", "concern": ""}, {"claim": "Y", "concern": "Valid"}]')
    assert len(result) == 1
    assert result[0]["claim"] == "Y"


@pytest.mark.asyncio
async def test_adversarial_pass_stores_warnings(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("ai-page", WikiPage(
        title="AI", tags=[], content="Transformers replaced RNNs entirely by 2020.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text='[{"claim": "Transformers replaced RNNs entirely by 2020.", "concern": "Overstated"}]',
        input_tokens=100, output_tokens=50,
    )
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    report = await agent.lint(adversarial=True)
    page = store.read_page("ai-page")
    assert page is not None
    assert len(page.lint_warnings) == 1
    assert page.lint_warnings[0]["claim"] == "Transformers replaced RNNs entirely by 2020."
    assert len(report.adversarial_warnings) == 1
    assert report.adversarial_warnings[0]["slug"] == "ai-page"


@pytest.mark.asyncio
async def test_adversarial_pass_no_warnings_on_clean_page(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("clean", WikiPage(
        title="Clean", tags=[], content="Well-cited facts.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text="[]", input_tokens=10, output_tokens=2,
    )
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    report = await agent.lint(adversarial=True)
    clean_page = store.read_page("clean")
    assert clean_page is not None
    assert clean_page.lint_warnings == []
    assert report.adversarial_warnings == []


@pytest.mark.asyncio
async def test_adversarial_pass_rate_limit_is_non_fatal(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(
        title="P1", tags=[], content="Claim one.",
        status="active", confidence="high", sources=[]))
    store.write_page("p2", WikiPage(
        title="P2", tags=[], content="Claim two.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.side_effect = [
        Exception("429 Too Many Requests"),
        CompletionResponse(
            text='[{"claim": "Claim two.", "concern": "Unsupported"}]',
            input_tokens=50, output_tokens=20,
        ),
    ]
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    report = await agent.lint(adversarial=True)
    all_warnings = [
        w
        for slug in ["p1", "p2"]
        for p in [store.read_page(slug)] if p is not None
        for w in (p.lint_warnings or [])
    ]
    claims = {w["claim"] for w in all_warnings}
    # list_pages() order is filesystem-dependent (inode order on macOS), so assert
    # on the set of outcomes rather than which slug got which call.
    assert None in claims
    assert any("rate limit" in (w["concern"] or "") for w in all_warnings)
    assert "Claim two." in claims


@pytest.mark.asyncio
async def test_no_adversarial_clears_existing_warnings(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(
        title="P", tags=[], content="Content.", status="active", confidence="high",
        sources=[], lint_warnings=[{"claim": "Old claim", "concern": "Old concern"}],
    )
    store.write_page("p", page)
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    await agent.lint(adversarial=False)
    p_page = store.read_page("p")
    assert p_page is not None
    assert p_page.lint_warnings == []


@pytest.mark.asyncio
async def test_adversarial_pass_uses_adversarial_provider(tmp_wiki):
    """When adversarial_provider is set, it is used for adversarial calls, not self._provider."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p", WikiPage(
        title="P", tags=[], content="Some content.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    lint_provider = AsyncMock()
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text="[]", input_tokens=5, output_tokens=1,
    )
    agent = LintAgent(
        provider=lint_provider, store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    await agent.lint(adversarial=True)
    # adv_provider called; lint_provider not called (no contradictions, no auto-resolve)
    adv_provider.complete.assert_called_once()
    lint_provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_adversarial_pass_skip_slugs_not_evaluated(tmp_wiki):
    """LINT_SKIP_SLUGS pages (index, log, dashboard) are never adversarially reviewed."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("index", WikiPage(
        title="Index", tags=[], content="# Index", status="active", confidence="high", sources=[]))
    store.write_page("real-page", WikiPage(
        title="Real", tags=[], content="Real content.", status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(text="[]", input_tokens=5, output_tokens=1)
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    await agent.lint(adversarial=True)
    # Only real-page evaluated (1 call), not index
    assert adv_provider.complete.call_count == 1


@pytest.mark.asyncio
async def test_adversarial_pass_skipped_on_non_all_scope(tmp_wiki):
    """Adversarial pass does not run when scope != 'all' even if adversarial=True."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p", WikiPage(
        title="P", tags=[], content="Some content.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text="[]", input_tokens=5, output_tokens=1,
    )
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    await agent.lint(scope="contradictions", adversarial=True)
    adv_provider.complete.assert_not_called()


# ── Check 5: citation validation ──────────────────────────────────────────────


def test_check_citations_broken_ref(tmp_path):
    """Citation pointing to file not in sources[] is a broken_ref."""
    page = WikiPage(
        title="Test", tags=[], content="A claim.^[other.txt:1-5]",
        status="active", confidence="medium",
        sources=[SourceRef(file="/path/to/bio.txt", hash="x", size=1, ingested="2026-01-01")],
    )
    issues = _check_page_citations("test", page, extracted_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0]["reason"] == "broken_ref"


def test_check_citations_out_of_range(tmp_path):
    """Citation with line_end beyond file length is out_of_range."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "bio.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt:1-9999]",
        status="active", confidence="medium",
        sources=[SourceRef(file=str(tmp_path / "bio.txt"), hash="x", size=1, ingested="2026-01-01")],
    )
    issues = _check_page_citations("t", page, extracted_dir=extracted)
    assert any(i["reason"] == "out_of_range" for i in issues)


def test_check_citations_malformed(tmp_path):
    """Citation without line range is malformed."""
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt]",
        status="active", confidence="medium",
        sources=[SourceRef(file="/p/bio.txt", hash="x", size=1, ingested="2026-01-01")],
    )
    issues = _check_page_citations("t", page, extracted_dir=tmp_path)
    assert any(i["reason"] == "malformed" for i in issues)


def test_check_citations_clean_page_no_issues(tmp_path):
    """Page with correct citations produces no issues."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "bio.txt").write_text("\n".join(f"line{i}" for i in range(1, 101)), encoding="utf-8")
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt:1-5]",
        status="active", confidence="medium",
        sources=[SourceRef(file=str(tmp_path / "bio.txt"), hash="x", size=1, ingested="2026-01-01")],
    )
    issues = _check_page_citations("t", page, extracted_dir=extracted)
    assert issues == []


def test_check_citations_reversed_range(tmp_path):
    """line_start > line_end is malformed."""
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt:50-10]",
        status="active", confidence="medium",
        sources=[SourceRef(file="/p/bio.txt", hash="x", size=1, ingested="2026-01-01")],
    )
    issues = _check_page_citations("t", page, extracted_dir=tmp_path)
    assert any(i["reason"] == "malformed" for i in issues)


# ── read_current_lint_state ───────────────────────────────────────────────────

def test_read_current_lint_state_all_clear(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(title="Hub", tags=[], content="See [[spoke]].",
        status="active", confidence="high", sources=[]))
    store.write_page("spoke", WikiPage(title="Spoke", tags=[], content="content",
        status="active", confidence="high", sources=[]))
    state = read_current_lint_state(store)
    assert state.contradicted == []
    assert state.adv_pages == []


def test_read_current_lint_state_contradicted(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("conflict-page", WikiPage(title="Conflict", tags=[], content="disputed",
        status="contradicted", confidence="low", sources=[]))
    state = read_current_lint_state(store)
    assert "conflict-page" in state.contradicted


def test_read_current_lint_state_orphan(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(title="Hub", tags=[], content="See [[linked]].",
        status="active", confidence="medium", sources=[]))
    store.write_page("linked", WikiPage(title="Linked", tags=[], content="content",
        status="active", confidence="medium", sources=[]))
    store.write_page("orphan", WikiPage(title="Orphan", tags=[], content="alone",
        status="active", confidence="medium", sources=[]))
    state = read_current_lint_state(store)
    assert "orphan" in state.orphans
    assert "linked" not in state.orphans


def test_read_current_lint_state_adv_warnings(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("flagged", WikiPage(title="Flagged", tags=[], content="content",
        status="active", confidence="high", sources=[],
        lint_warnings=[{"claim": "Overstated fact", "concern": "not accurate"}]))
    state = read_current_lint_state(store)
    assert len(state.adv_pages) == 1
    assert state.adv_pages[0]["slug"] == "flagged"


def test_read_current_lint_state_skips_lint_skip_slugs(tmp_wiki):
    """LINT_SKIP_SLUGS pages never appear in contradicted or adv_pages."""
    store = WikiStorage(tmp_wiki / "wiki")
    for slug in LINT_SKIP_SLUGS:
        store.write_page(slug, WikiPage(title=slug, tags=[], content="auto",
            status="contradicted", confidence="low", sources=[],
            lint_warnings=[{"claim": "c", "concern": "c"}]))
    state = read_current_lint_state(store)
    assert state.contradicted == []
    assert state.adv_pages == []


# ── Check 5b: citation presence ───────────────────────────────────────────────

def test_has_citations_returns_true_when_present():
    """_has_citations returns True when body contains ^[file.md:1-3]."""
    from synthadoc.agents.lint_agent import _has_citations
    from synthadoc.storage.wiki import WikiPage

    page = WikiPage(
        title="Test",
        tags=[],
        content="Some content.^[source.md:1-3] More content.",
        status="active",
        confidence="high",
        sources=[],
    )
    assert _has_citations(page) is True


def test_has_citations_returns_false_when_absent():
    """_has_citations returns False when body has no ^[...] markers."""
    from synthadoc.agents.lint_agent import _has_citations
    from synthadoc.storage.wiki import WikiPage

    page = WikiPage(
        title="Test",
        tags=[],
        content="No citation here at all.",
        status="active",
        confidence="high",
        sources=[],
    )
    assert _has_citations(page) is False


def test_has_citations_empty_content():
    """_has_citations handles None/empty content without crashing."""
    from synthadoc.agents.lint_agent import _has_citations
    from synthadoc.storage.wiki import WikiPage

    page = WikiPage(
        title="Test",
        tags=[],
        content=None,
        status="active",
        confidence="high",
        sources=[],
    )
    assert _has_citations(page) is False


@pytest.mark.asyncio
async def test_lint_warns_when_no_citations_on_substantive_page(tmp_wiki):
    """A page with >= 50 words and 0 citations must trigger a citation_presence_warning."""
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.config import LintConfig

    wiki = WikiStorage(tmp_wiki / "wiki")
    # 60 words, no citations
    content = " ".join(["word"] * 60)
    wiki.write_page("plan", WikiPage(title="Plan", tags=[], content=content, status="draft", confidence="high", sources=[]))

    agent = LintAgent(provider=AsyncMock(), store=wiki, log_writer=LogWriter(tmp_wiki / "wiki" / "log.md"), cfg=LintConfig())
    report = await agent.lint(adversarial=False)

    assert any("plan" in w and "citation" in w.lower() for w in report.warnings), \
        f"Expected citation presence warning, got: {report.warnings}"


@pytest.mark.asyncio
async def test_lint_no_warning_when_page_has_citations(tmp_wiki):
    """A page with citations must NOT trigger citation_presence_warning."""
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.config import LintConfig

    wiki = WikiStorage(tmp_wiki / "wiki")
    content = " ".join(["word"] * 60) + "^[source.md:1-3]"
    wiki.write_page("plan", WikiPage(title="Plan", tags=[], content=content, status="draft", confidence="high", sources=[]))

    agent = LintAgent(provider=AsyncMock(), store=wiki, log_writer=LogWriter(tmp_wiki / "wiki" / "log.md"), cfg=LintConfig())
    report = await agent.lint(adversarial=False)

    citation_warnings = [w for w in report.warnings if "citation" in w.lower() and "plan" in w]
    assert not citation_warnings, f"Unexpected warning: {citation_warnings}"


@pytest.mark.asyncio
async def test_lint_no_warning_for_stub_page_below_min_words(tmp_wiki):
    """A page with fewer than _CITATION_MIN_WORDS words must not get citation_presence_warning."""
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.config import LintConfig

    wiki = WikiStorage(tmp_wiki / "wiki")
    content = " ".join(["word"] * 30)  # 30 words, below threshold
    wiki.write_page("stub", WikiPage(title="Stub", tags=[], content=content, status="draft", confidence="high", sources=[]))

    agent = LintAgent(provider=AsyncMock(), store=wiki, log_writer=LogWriter(tmp_wiki / "wiki" / "log.md"), cfg=LintConfig())
    report = await agent.lint(adversarial=False)

    citation_warnings = [w for w in report.warnings if "citation" in w.lower() and "stub" in w]
    assert not citation_warnings, f"Stub page below min_words triggered unexpected warning"


@pytest.mark.asyncio
async def test_lint_warns_at_exactly_min_words_boundary(tmp_wiki):
    """Boundary: a page with exactly _CITATION_MIN_WORDS words and 0 citations → warning."""
    from synthadoc.agents.lint_agent import LintAgent, _CITATION_MIN_WORDS
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.config import LintConfig

    wiki = WikiStorage(tmp_wiki / "wiki")
    content = " ".join(["word"] * _CITATION_MIN_WORDS)
    wiki.write_page("boundary", WikiPage(title="Boundary", tags=[], content=content, status="draft", confidence="high", sources=[]))

    agent = LintAgent(provider=AsyncMock(), store=wiki, log_writer=LogWriter(tmp_wiki / "wiki" / "log.md"), cfg=LintConfig())
    report = await agent.lint(adversarial=False)

    assert any("boundary" in w and "citation" in w.lower() for w in report.warnings)


@pytest.mark.asyncio
async def test_lint_archives_ghost_draft(tmp_wiki):
    """A DB entry in 'draft' state with no corresponding wiki file (ghost draft from an
    interrupted ingest) must be archived by lint, not silently ignored."""
    from synthadoc.storage.log import AuditDB
    from synthadoc.storage.wiki import WikiStorage, WikiPage

    # Real page on disk in draft state (will be promoted normally)
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("real-page", WikiPage(
        title="Real Page", tags=[], content="Real content.", status="draft",
        confidence="high", sources=[]))

    # Seed the DB with a ghost draft — no file exists for this slug
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    await audit.set_page_state("ghost-draft", "draft", "ingest")

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    report = await agent.lint(adversarial=False)

    ghost_state = await audit.get_page_state("ghost-draft")
    assert ghost_state["state"] == "archived", "ghost draft must be archived by lint"
    assert report.lifecycle_archived >= 1
    # The real page should be promoted, not affected
    assert report.lifecycle_promoted >= 1
