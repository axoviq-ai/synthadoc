# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from synthadoc.agents.lint_agent import LintAgent, LintReport, find_orphan_slugs, find_broken_wikilink_refs, _fix_dangling_wikilinks, LINT_SKIP_SLUGS, LINT_SKIP_SOURCE_SLUGS, _parse_adversarial_response, _check_page_citations, _citation_source_names, read_current_lint_state, _load_adv_hash_cache, _save_adv_hash_cache
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
    report = await agent.run(scope="contradictions")
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
    report = await agent.run(scope="orphans")
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
    report = await agent.run(scope="orphans")
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


def test_find_broken_wikilink_refs_detects_dead_links():
    """find_broken_wikilink_refs returns dead refs that are not in all_slugs."""
    page_texts = {
        "alan-turing": "See [[bletchley-park]] and [[von-neumann-architecture]].",
        "von-neumann-architecture": "See [[alan-turing]].",
    }
    all_slugs = {"alan-turing", "von-neumann-architecture"}
    result = find_broken_wikilink_refs(page_texts, all_slugs)
    assert "alan-turing" in result
    assert "bletchley-park" in result["alan-turing"]
    assert "von-neumann-architecture" not in result  # all its links resolve


def test_find_broken_wikilink_refs_anchor_and_display_stripped():
    """Anchors ([[slug#section]]) and display text ([[slug|Label]]) are handled."""
    page_texts = {"page": "[[real-page#intro]] and [[ghost-page|Ghost]]."}
    all_slugs = {"page", "real-page"}
    result = find_broken_wikilink_refs(page_texts, all_slugs)
    assert result == {"page": ["ghost-page"]}


def test_find_broken_wikilink_refs_deduplicates_per_page():
    """Duplicate dead refs within a page are only counted once."""
    page_texts = {"page": "[[dead]] again [[dead]]."}
    all_slugs = {"page"}
    result = find_broken_wikilink_refs(page_texts, all_slugs)
    assert result == {"page": ["dead"]}


def test_find_broken_wikilink_refs_empty_when_all_links_valid():
    """Returns empty dict when every [[link]] resolves to an existing slug."""
    page_texts = {"a": "See [[b]].", "b": "See [[a]]."}
    all_slugs = {"a", "b"}
    assert find_broken_wikilink_refs(page_texts, all_slugs) == {}


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
    report = await agent.run(scope="contradictions")
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
    await agent.run(scope="orphans")

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


# ── link_texts (contradicted-page link-graph) coverage ───────────────────────

def test_find_orphan_slugs_link_texts_rescues_page():
    """A contradicted page's outgoing link should rescue another page from orphan status.

    When page-b is contradicted it is excluded from page_texts (orphan candidates)
    but its link to page-a must still be counted via link_texts so page-a is NOT
    reported as an orphan.
    """
    page_texts = {
        "page-a": "No outbound links.",     # active — orphan candidate
        "page-c": "See [[page-b]].",        # active — orphan candidate; links to contradicted
    }
    all_page_texts = {
        "page-a": "No outbound links.",
        "page-b": "See [[page-a]].",        # contradicted — in link_texts only
        "page-c": "See [[page-b]].",
    }
    orphans = find_orphan_slugs(page_texts, link_texts=all_page_texts)
    assert "page-a" not in orphans   # page-b (contradicted) links to page-a → rescued
    assert "page-c" in orphans       # nothing links to page-c → orphan


def test_find_orphan_slugs_contradicted_page_not_a_candidate():
    """Contradicted pages must not appear as orphans even when link_texts is provided."""
    page_texts = {
        "page-a": "No outbound links.",     # active
    }
    all_page_texts = {
        "page-a": "No outbound links.",
        "contradicted-page": "Standalone.", # contradicted — in link_texts but NOT page_texts
    }
    orphans = find_orphan_slugs(page_texts, link_texts=all_page_texts)
    assert "contradicted-page" not in orphans   # not in page_texts → never a candidate
    assert "page-a" in orphans                  # nothing links to it → orphan


def test_find_orphan_slugs_link_texts_defaults_to_page_texts():
    """When link_texts is omitted the behaviour is identical to the legacy call."""
    page_texts = {
        "hub":     "Links to [[spoke]].",
        "spoke":   "No outbound links.",
        "loner":   "Standalone.",
    }
    assert find_orphan_slugs(page_texts) == find_orphan_slugs(page_texts, link_texts=page_texts)


def test_read_current_lint_state_contradicted_links_count(tmp_wiki):
    """read_current_lint_state must not report false orphans when a contradicted page links to them."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(
        title="Hub", tags=[], content="See [[spoke]].",
        status="contradicted", confidence="high", sources=[],
    ))
    store.write_page("spoke", WikiPage(
        title="Spoke", tags=[], content="No outbound links.",
        status="active", confidence="high", sources=[],
    ))

    result = read_current_lint_state(store)
    # hub is contradicted and should be reported as such
    assert "hub" in result.contradicted
    # spoke is referenced by hub (even though hub is contradicted) — must NOT be an orphan
    assert "spoke" not in result.orphans


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
    report = await agent.run(scope="orphans")

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
    report = await agent.run(scope="contradictions")

    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_lint_records_contradiction_found_audit_event(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AsyncMock(spec=AuditDB)
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    await agent.run(scope="contradictions", job_id="job-123")
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
    await agent.run(scope="contradictions", auto_resolve=True, job_id="job-456")
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
    report = await agent.run(scope="orphans")

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


def test_parse_adversarial_response_filters_no_issue_concerns():
    """'No issue', 'Defensible', 'N/A' etc. are not real warnings and must be dropped."""
    payload = (
        '[{"claim": "A", "concern": "No issue"},'
        ' {"claim": "B", "concern": "Defensible and nuanced"},'
        ' {"claim": "C", "concern": "N/A"},'
        ' {"claim": "D", "concern": "Accurate"},'
        ' {"claim": "E", "concern": "Clearly overstated claim here"}]'
    )
    result = _parse_adversarial_response(payload)
    # Only the one genuine concern survives
    assert len(result) == 1
    assert result[0]["claim"] == "E"


def test_parse_adversarial_response_no_issue_case_insensitive():
    """'no issue' filter is case-insensitive."""
    result = _parse_adversarial_response('[{"claim": "X", "concern": "NO ISSUE"}]')
    assert result == []


def test_parse_adversarial_response_with_preamble_text():
    """Fallback regex extraction handles LLM preamble before the JSON array."""
    text = (
        'Based on my review, I found these issues:\n'
        '[{"claim": "The Earth is flat.", "concern": "Contradicts established science."}]'
    )
    result = _parse_adversarial_response(text)
    assert len(result) == 1
    assert result[0]["claim"] == "The Earth is flat."


def test_parse_adversarial_response_with_trailing_commentary():
    """Fallback regex extraction handles JSON array followed by text."""
    text = (
        '[{"claim": "Vaccines cause autism.", "concern": "Retracted Wakefield study."}]\n'
        "Please review these findings carefully."
    )
    result = _parse_adversarial_response(text)
    assert len(result) == 1
    assert result[0]["concern"] == "Retracted Wakefield study."


@pytest.mark.asyncio
async def test_adversarial_single_logs_warning_on_unparseable_response(tmp_wiki):
    """_adversarial_single emits a WARNING when the LLM returns non-empty non-parseable text."""
    store = WikiStorage(tmp_wiki / "wiki")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="I cannot identify any factual concerns with this page.",
        input_tokens=10, output_tokens=10,
    )

    agent = LintAgent(provider=provider, store=store, log_writer=log)

    with patch("synthadoc.agents.lint_agent._log") as mock_log:
        warnings, tokens = await agent._adversarial_single("some-slug", "Some page content.")
    assert warnings == []
    assert tokens == 20  # total_tokens = input_tokens(10) + output_tokens(10)
    # Must log a WARNING so the operator can see the parse failure
    mock_log.warning.assert_called_once()
    assert "unparseable" in mock_log.warning.call_args[0][0]


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
    report = await agent.run(adversarial=True)
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
    report = await agent.run(adversarial=True)
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
    report = await agent.run(adversarial=True)
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
    await agent.run(adversarial=False)
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
    await agent.run(adversarial=True)
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
    await agent.run(adversarial=True)
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
    await agent.run(scope="contradictions", adversarial=True)
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


def test_citation_source_names_plain_url():
    """Regular URL: underscores normalized to hyphens, matching _url_sidecar_name output."""
    names = _citation_source_names("https://en.wikipedia.org/wiki/Alan_Turing")
    # ingest produces "wiki-Alan-Turing" (underscore → hyphen); both 1- and 2-segment forms present
    assert "wiki-Alan-Turing" in names
    assert "Alan-Turing" in names
    # raw underscore form must NOT be present — that would never match the sidecar filename
    assert "Alan_Turing" not in names
    assert "wiki-Alan_Turing" not in names


def test_citation_source_names_youtube_watch():
    """YouTube watch URL maps to 'youtube-{slugified_id}', matching ingest suggested_slug."""
    names = _citation_source_names("https://www.youtube.com/watch?v=O5nskjZ_GoI")
    assert names == {"youtube-o5nskjz-goi"}


def test_citation_source_names_youtube_shorts():
    names = _citation_source_names("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    assert names == {"youtube-dqw4w9wgxcq"}


def test_citation_source_names_youtube_does_not_produce_watch():
    """Ensure old broken derivation ('watch') is no longer returned for YouTube URLs."""
    names = _citation_source_names("https://www.youtube.com/watch?v=O5nskjZ_GoI")
    assert "watch" not in names


def test_check_citations_youtube_no_broken_ref(tmp_path):
    """Citations annotated as youtube-... should not be flagged broken_ref."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    txt = extracted / "youtube-o5nskjz-goi.txt"
    txt.write_text("line1\nline2\nline3\n")
    page = WikiPage(
        title="T", tags=[], content="Fact.^[youtube-o5nskjz-goi:1-2]",
        status="active", confidence="high",
        sources=[SourceRef(
            file="https://www.youtube.com/watch?v=O5nskjZ_GoI",
            hash="x", size=1, ingested="2026-01-01",
        )],
    )
    issues = _check_page_citations("t", page, extracted_dir=extracted)
    assert issues == []


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
    report = await agent.run(adversarial=False)

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
    report = await agent.run(adversarial=False)

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
    report = await agent.run(adversarial=False)

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
    report = await agent.run(adversarial=False)

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
    report = await agent.run(adversarial=False)

    ghost_state = await audit.get_page_state("ghost-draft")
    assert ghost_state["state"] == "archived", "ghost draft must be archived by lint"
    assert report.lifecycle_archived >= 1
    # The real page should be promoted, not affected
    assert report.lifecycle_promoted >= 1


@pytest.mark.asyncio
async def test_lint_does_not_archive_staged_candidates(tmp_wiki):
    """A draft DB entry whose file exists in wiki/candidates/ is a staged candidate,
    not a ghost draft — lint must leave it alone."""
    from synthadoc.storage.log import AuditDB
    from synthadoc.storage.wiki import WikiStorage

    store = WikiStorage(tmp_wiki / "wiki")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()

    # Create the candidate file on disk
    candidates_dir = tmp_wiki / "wiki" / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    (candidates_dir / "my-candidate.md").write_text(
        "---\ntitle: My Candidate\nstatus: draft\n---\n\nContent.\n"
    )
    # Seed the DB as draft (as ingest would)
    await audit.set_page_state("my-candidate", "draft", "ingest")

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    await agent.run(adversarial=False)

    state = await audit.get_page_state("my-candidate")
    assert state["state"] == "draft", "staged candidate must not be archived by ghost-draft sweep"


# ── cascade_archive ───────────────────────────────────────────────────────────


def _make_store(tmp_path, pages: dict) -> "WikiStorage":
    """Helper: create a WikiStorage with pre-populated pages."""
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    store = WikiStorage(tmp_path / "wiki")
    for slug, content in pages.items():
        store.write_page(slug, WikiPage(
            title=slug, tags=[], content=content,
            status="active", confidence="high", sources=[],
        ))
    return store


@pytest.mark.asyncio
async def test_cascade_archive_writes_audit_events(tmp_path):
    from unittest.mock import AsyncMock
    from synthadoc.agents.lint_agent import cascade_archive
    from synthadoc.storage.wiki import TriggerSource

    store = _make_store(tmp_path, {
        "old-page": "Archived content.",
        "referencing": "See [[old-page]] for details.",
    })
    page = store.read_page("old-page")
    page.status = "archived"
    store.write_page("old-page", page)

    mock_audit = AsyncMock()
    affected = await cascade_archive("old-page", store, audit_db=mock_audit,
                                    trigger_source=TriggerSource.USER)

    assert "referencing" in affected
    mock_audit.record_lifecycle_event.assert_awaited_once()
    call_args = mock_audit.record_lifecycle_event.call_args
    assert call_args.args[0] == "referencing"       # slug
    assert "cascade" in call_args.args[3]            # reason contains "cascade"
    assert "[[old-page]]" in call_args.args[3]       # reason names the archived slug
    mock_audit.delete_graph_node.assert_awaited_once_with("old-page")


@pytest.mark.asyncio
async def test_cascade_archive_no_audit_when_no_refs(tmp_path):
    from unittest.mock import AsyncMock
    from synthadoc.agents.lint_agent import cascade_archive

    store = _make_store(tmp_path, {
        "isolated": "No links pointing here.",
        "other": "Talks about something else.",
    })
    page = store.read_page("isolated")
    page.status = "archived"
    store.write_page("isolated", page)

    mock_audit = AsyncMock()
    affected = await cascade_archive("isolated", store, audit_db=mock_audit)

    assert affected == []
    mock_audit.record_lifecycle_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_cascade_archive_removes_inline_link(tmp_path):
    from synthadoc.agents.lint_agent import cascade_archive

    store = _make_store(tmp_path, {
        "silicon-transistors": "## Silicon transistors\n\nSome content.",
        "cpu-design": "CPUs use [[silicon-transistors]] extensively.",
    })
    # Archive silicon-transistors
    page = store.read_page("silicon-transistors")
    page.status = "archived"
    store.write_page("silicon-transistors", page)

    affected = await cascade_archive("silicon-transistors", store)

    assert "cpu-design" in affected
    updated = store.read_page("cpu-design")
    assert "[[silicon-transistors]]" not in updated.content
    assert "silicon-transistors" in updated.content  # display text preserved


@pytest.mark.asyncio
async def test_cascade_archive_removes_list_item(tmp_path):
    from synthadoc.agents.lint_agent import cascade_archive

    store = _make_store(tmp_path, {
        "alpha": "# Alpha\nContent.",
        "beta": "See also:\n- [[alpha]]\n- other item",
    })
    page = store.read_page("alpha")
    page.status = "archived"
    store.write_page("alpha", page)

    affected = await cascade_archive("alpha", store)

    assert "beta" in affected
    updated = store.read_page("beta")
    assert "[[alpha]]" not in updated.content
    # list item dropped entirely
    assert "- [[alpha]]" not in updated.content


@pytest.mark.asyncio
async def test_cascade_archive_no_op_when_no_refs(tmp_path):
    from synthadoc.agents.lint_agent import cascade_archive

    store = _make_store(tmp_path, {
        "lonely": "No inbound links.",
        "other": "Talks about something else entirely.",
    })
    page = store.read_page("lonely")
    page.status = "archived"
    store.write_page("lonely", page)

    affected = await cascade_archive("lonely", store)

    assert affected == []


@pytest.mark.asyncio
async def test_cascade_archive_skips_already_archived_pages(tmp_path):
    from synthadoc.agents.lint_agent import cascade_archive

    store = _make_store(tmp_path, {
        "target": "Content.",
        "already-archived": "References [[target]] extensively.",
    })
    page = store.read_page("target")
    page.status = "archived"
    store.write_page("target", page)
    # Mark already-archived as archived too
    other = store.read_page("already-archived")
    other.status = "archived"
    store.write_page("already-archived", other)

    affected = await cascade_archive("target", store)

    assert "already-archived" not in affected


@pytest.mark.asyncio
async def test_cascade_archive_skips_lint_skip_slugs(tmp_path):
    from synthadoc.agents.lint_agent import cascade_archive, LINT_SKIP_SLUGS
    from synthadoc.storage.wiki import WikiPage

    store = _make_store(tmp_path, {
        "some-page": "Content.",
    })
    # Populate a skip-slug page with a reference
    for skip_slug in list(LINT_SKIP_SLUGS)[:1]:
        store.write_page(skip_slug, WikiPage(
            title=skip_slug, tags=[], content=f"[[some-page]] ref",
            status="active", confidence="high", sources=[],
        ))
    page = store.read_page("some-page")
    page.status = "archived"
    store.write_page("some-page", page)

    affected = await cascade_archive("some-page", store)

    # Skip slug pages must not be rewritten
    assert all(s not in LINT_SKIP_SLUGS for s in affected)


@pytest.mark.asyncio
async def test_cascade_archive_aliased_link(tmp_path):
    """[[slug|Display Text]] should become just Display Text."""
    from synthadoc.agents.lint_agent import cascade_archive

    store = _make_store(tmp_path, {
        "vacuum-tubes": "## Vacuum tubes\nOld tech.",
        "history": "Early computers used [[vacuum-tubes|vacuum tube technology]].",
    })
    page = store.read_page("vacuum-tubes")
    page.status = "archived"
    store.write_page("vacuum-tubes", page)

    affected = await cascade_archive("vacuum-tubes", store)

    assert "history" in affected
    updated = store.read_page("history")
    assert "[[vacuum-tubes" not in updated.content
    assert "vacuum tube technology" in updated.content


# ── lint auto-archive cascade integration ─────────────────────────────────────


@pytest.mark.asyncio
async def test_lint_auto_archive_cascades_links(tmp_wiki):
    """When lint auto-archives a page (source file missing), cascade_archive removes
    [[page-b]] from all active pages immediately — not waiting for the next lint run."""
    store = WikiStorage(tmp_wiki / "wiki")
    raw = tmp_wiki / "raw_sources"
    raw.mkdir(exist_ok=True)

    # Source file exists for page-a but NOT for page-b
    (raw / "source-a.txt").write_text("Content A", encoding="utf-8")

    store.write_page("page-a", WikiPage(
        title="Page A", tags=[], content="Intro. See also [[page-b]].",
        status="active", confidence="high",
        sources=[SourceRef(file="source-a.txt", hash="x", size=1, ingested="2026-01-01")],
    ))
    store.write_page("page-b", WikiPage(
        title="Page B", tags=[], content="Page B content.",
        status="active", confidence="high",
        sources=[SourceRef(file="source-b.txt", hash="y", size=1, ingested="2026-01-01")],
    ))
    # source-b.txt does NOT exist on disk

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log,
                      wiki_root=tmp_wiki)
    report = await agent.run(scope="all", adversarial=False)

    # page-b archived because source-b.txt missing
    page_b = store.read_page("page-b")
    assert page_b.status == "archived"

    # cascade: [[page-b]] removed from page-a immediately (not waiting for next lint)
    page_a = store.read_page("page-a")
    assert "[[page-b]]" not in page_a.content
    assert report.dangling_links_removed >= 1


@pytest.mark.asyncio
async def test_lint_multi_source_page_goes_stale_not_archived(tmp_wiki):
    """When a page has multiple local sources and only ONE is missing from disk, lint must
    mark it stale (not archived) because valid content from the remaining source still exists."""
    store = WikiStorage(tmp_wiki / "wiki")
    raw = tmp_wiki / "raw_sources"
    raw.mkdir(exist_ok=True)

    # source-a exists on disk; source-b does NOT
    (raw / "source-a.txt").write_text("Content A", encoding="utf-8")

    store.write_page("multi-source-page", WikiPage(
        title="Multi", tags=[], content="Content.",
        status="active", confidence="high",
        sources=[
            SourceRef(file="source-a.txt", hash="x", size=1, ingested="2026-01-01"),
            SourceRef(file="source-b.txt", hash="y", size=1, ingested="2026-01-01"),
        ],
    ))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, wiki_root=tmp_wiki)
    report = await agent.run(scope="all", adversarial=False)

    page = store.read_page("multi-source-page")
    assert page.status == "stale"        # NOT archived
    assert report.lifecycle_stale >= 1
    assert report.lifecycle_archived == 0


@pytest.mark.asyncio
async def test_lint_bootstrap_archived_frontmatter_records_lifecycle_event(tmp_wiki):
    """A page with status: archived already set in frontmatter but no DB row yet
    (e.g. a pre-generated demo page on first lint run) must produce a lifecycle_events
    audit entry so the Audit log in the UI is not empty for that page."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("pre-archived", WikiPage(
        title="Pre-Archived Page", tags=[], content="Retired content.",
        status="archived", confidence="high", sources=[],
    ))

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    # No DB row for "pre-archived" — simulates first lint run on a demo wiki

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    await agent.run(adversarial=False)

    events, total = await audit.get_lifecycle_events("pre-archived")
    assert total > 0, "bootstrap must write a lifecycle_events row for the pre-archived page"
    assert events[0]["to_state"] == "archived"
    assert "bootstrapped" in events[0]["reason"]


@pytest.mark.asyncio
async def test_lint_auto_resolve_records_lifecycle_event(tmp_wiki):
    """Successful auto-resolve (contradicted → active) must write a lifecycle_events row
    with from_state=contradicted, to_state=active, and reason containing 'auto-resolved'."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("auto-resolve-page", WikiPage(
        title="Auto Resolve", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[],
    ))

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    await audit.set_page_state("auto-resolve-page", "contradicted", "ingest")

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"resolvable": true, "reason": "Claims reconciled.", "resolution": "Reconciled content."}',
        input_tokens=10, output_tokens=5,
    )
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=provider, store=store, log_writer=log, audit_db=audit)
    await agent.run(scope="contradictions", auto_resolve=True)

    events, total = await audit.get_lifecycle_events("auto-resolve-page")
    assert total > 0, "auto-resolve must write a lifecycle_events row"
    assert events[0]["from_state"] == "contradicted"
    assert events[0]["to_state"] == "active"
    assert "auto-resolved" in events[0]["reason"]


@pytest.mark.asyncio
async def test_lint_auto_resolve_failed_no_lifecycle_event(tmp_wiki):
    """When auto-resolve decides resolvable=False, no lifecycle_events row must be written
    (the page stays contradicted; only audit_events gets an auto_resolve_failed entry)."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("unresolvable-page", WikiPage(
        title="Unresolvable", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[],
    ))

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    await audit.set_page_state("unresolvable-page", "contradicted", "ingest")

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"resolvable": false, "reason": "Entire page is fabricated.", "resolution": ""}',
        input_tokens=10, output_tokens=5,
    )
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=provider, store=store, log_writer=log, audit_db=audit)
    await agent.run(scope="contradictions", auto_resolve=True)

    events, total = await audit.get_lifecycle_events("unresolvable-page")
    assert total == 0, "failed auto-resolve must not write a lifecycle_events row"
    page = store.read_page("unresolvable-page")
    assert page.status == "contradicted"


@pytest.mark.asyncio
async def test_lint_transition_archive_records_reason(tmp_wiki):
    """When lint archives a page because its source file is gone, the lifecycle_events row
    must carry reason='all source files no longer on disk'."""
    store = WikiStorage(tmp_wiki / "wiki")
    raw = tmp_wiki / "raw_sources"
    raw.mkdir(exist_ok=True)
    # Source file intentionally absent from disk
    store.write_page("gone-page", WikiPage(
        title="Gone Page", tags=[], content="Content.",
        status="active", confidence="high",
        sources=[SourceRef(file="missing.txt", hash="abc", size=10, ingested="2026-01-01")],
    ))

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    await audit.set_page_state("gone-page", "active", "ingest")

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log,
                      audit_db=audit, wiki_root=tmp_wiki)
    await agent.run(adversarial=False)

    events, total = await audit.get_lifecycle_events("gone-page")
    assert total > 0, "archive transition must write a lifecycle_events row"
    assert events[0]["to_state"] == "archived"
    assert events[0]["reason"] == "all source files no longer on disk"


@pytest.mark.asyncio
async def test_lint_transition_draft_to_active_records_reason(tmp_wiki):
    """When lint promotes a draft page to active, the lifecycle_events row
    must carry reason='lint passed'."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("new-draft", WikiPage(
        title="New Draft", tags=[], content="Some content.",
        status="draft", confidence="high", sources=[],
    ))

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    await audit.set_page_state("new-draft", "draft", "ingest")

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    await agent.run(adversarial=False)

    events, total = await audit.get_lifecycle_events("new-draft")
    assert total > 0, "draft→active promotion must write a lifecycle_events row"
    assert events[0]["from_state"] == "draft"
    assert events[0]["to_state"] == "active"
    assert events[0]["reason"] == "lint passed"


# ── Adversarial gate ───────────────────────────────────────────────────────────


def _gate_cfg(threshold):
    """Minimal Config-like object with just the lint and audit fields."""
    return SimpleNamespace(
        lint=SimpleNamespace(
            adversarial_gate_threshold=threshold,
            adversarial_max_per_page=2,
            adversarial_concurrency=1,
            check_url_availability=False,
        ),
        audit=SimpleNamespace(lifecycle_retention_days=0, url_staleness_days=0),
    )


@pytest.mark.asyncio
async def test_adversarial_gate_demotes_page_at_threshold(tmp_wiki):
    """A page with warning count == threshold transitions to contradicted."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("suspect", WikiPage(
        title="Suspect", tags=[], content="A disputed factual claim lives here.",
        status="active", confidence="high", sources=[]))
    # Need 3+ pages so BM25 IDF doesn't collapse (not relevant here, but good practice)
    store.write_page("pad-a", WikiPage(title="Pad A", tags=[], content="Unrelated alpha.",
        status="active", confidence="high", sources=[]))
    store.write_page("pad-b", WikiPage(title="Pad B", tags=[], content="Unrelated beta.",
        status="active", confidence="high", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="", input_tokens=10, output_tokens=0)

    agent = LintAgent(
        provider=provider, store=store, log_writer=log,
        cfg=_gate_cfg(threshold=3))

    three_warnings = [
        {"claim": "Claim A", "concern": "unverified"},
        {"claim": "Claim B", "concern": "disputed"},
        {"claim": "Claim C", "concern": "contradicted by source X"},
    ]

    async def _mock_single(slug, content):
        if slug == "suspect":
            return three_warnings, 50
        return [], 10

    with patch.object(agent, "_adversarial_single", side_effect=_mock_single):
        report = await agent.run(scope="all", adversarial=True, lifecycle=False)

    page = store.read_page("suspect")
    assert page is not None
    assert page.status == "contradicted", f"Expected contradicted, got {page.status!r}"
    assert report.adversarial_demotions == 1


@pytest.mark.asyncio
async def test_adversarial_gate_disabled_when_threshold_is_none(tmp_wiki):
    """When adversarial_gate_threshold is None, pages are never auto-demoted."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("clean-enough", WikiPage(
        title="Clean", tags=[], content="Many warnings but gate is off.",
        status="active", confidence="high", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="", input_tokens=10, output_tokens=0)

    agent = LintAgent(
        provider=provider, store=store, log_writer=log,
        cfg=_gate_cfg(threshold=None))

    ten_warnings = [{"claim": f"Claim {i}", "concern": "disputed"} for i in range(10)]

    async def _mock_single(slug, content):
        return ten_warnings, 50

    with patch.object(agent, "_adversarial_single", side_effect=_mock_single):
        report = await agent.run(scope="all", adversarial=True, lifecycle=False)

    page = store.read_page("clean-enough")
    assert page is not None
    assert page.status == "active", f"Expected active (gate off), got {page.status!r}"
    assert report.adversarial_demotions == 0


@pytest.mark.asyncio
async def test_adversarial_gate_skips_already_contradicted_page(tmp_wiki):
    """A page already contradicted is never transitioned again (idempotent)."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("already-bad", WikiPage(
        title="Already Bad", tags=[], content="Already contradicted content.",
        status="contradicted", confidence="low", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="", input_tokens=10, output_tokens=0)

    agent = LintAgent(
        provider=provider, store=store, log_writer=log,
        cfg=_gate_cfg(threshold=1))

    async def _mock_single(slug, content):
        return [{"claim": "Claim", "concern": "disputed"}], 20

    with patch.object(agent, "_adversarial_single", side_effect=_mock_single):
        report = await agent.run(scope="all", adversarial=True, lifecycle=False)

    page = store.read_page("already-bad")
    # Status unchanged; no extra transition fired
    assert page.status == "contradicted"
    assert report.adversarial_demotions == 0


@pytest.mark.asyncio
async def test_adversarial_gate_skips_archived_page(tmp_wiki):
    """Archived pages are not in (ACTIVE, STALE) — gate guard prevents demotion."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("retired", WikiPage(
        title="Retired", tags=[], content="Archived page with many issues.",
        status="archived", confidence="low", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="", input_tokens=10, output_tokens=0)

    agent = LintAgent(
        provider=provider, store=store, log_writer=log,
        cfg=_gate_cfg(threshold=1))

    async def _mock_single(slug, content):
        return [{"claim": "Claim", "concern": "disputed"}], 20

    with patch.object(agent, "_adversarial_single", side_effect=_mock_single):
        report = await agent.run(scope="all", adversarial=True, lifecycle=False)

    # archived page's status is not in (ACTIVE, STALE) → gate guard prevents demotion
    page = store.read_page("retired")
    assert page.status == "archived"
    assert report.adversarial_demotions == 0


@pytest.mark.asyncio
async def test_adversarial_gate_threshold_zero_disables_gate(tmp_wiki):
    """When adversarial_gate_threshold is 0, pages are never auto-demoted (disabled)."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("problematic", WikiPage(
        title="Problematic", tags=[], content="Page with many warnings.",
        status="active", confidence="high", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="", input_tokens=10, output_tokens=0)

    agent = LintAgent(
        provider=provider, store=store, log_writer=log,
        cfg=_gate_cfg(threshold=0))

    many_warnings = [{"claim": f"Claim {i}", "concern": "disputed"} for i in range(5)]

    async def _mock_single(slug, content):
        return many_warnings, 50

    with patch.object(agent, "_adversarial_single", side_effect=_mock_single):
        report = await agent.run(scope="all", adversarial=True, lifecycle=False)

    page = store.read_page("problematic")
    assert page is not None
    assert page.status == "active", f"Expected active (threshold=0 disables gate), got {page.status!r}"
    assert report.adversarial_demotions == 0


# ── Coverage: exception paths ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adversarial_single_generic_exception_returns_empty(tmp_wiki):
    """_adversarial_single returns ([], 0) when the LLM raises a non-rate-limit exception."""
    store = WikiStorage(tmp_wiki / "wiki")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")

    provider = AsyncMock()
    provider.complete.side_effect = Exception("connection timeout from network")

    agent = LintAgent(provider=provider, store=store, log_writer=log)

    warnings, tokens = await agent._adversarial_single("some-slug", "Some page content here.")
    assert warnings == []
    assert tokens == 0


@pytest.mark.asyncio
async def test_lint_auto_resolve_unparseable_response(tmp_wiki):
    """When _parse_json_response raises an exception, decision defaults to unresolvable."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("conflict-page", WikiPage(
        title="Conflict", tags=[],
        content="⚠ This page has a contradiction.",
        status="contradicted", confidence="low",
        sources=[], contradiction_note="Two sources disagree."))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"resolvable": true, "reason": "resolved", "resolution": "content"}',
        input_tokens=20, output_tokens=10)

    agent = LintAgent(provider=provider, store=store, log_writer=log)

    # Patch _parse_json_response to raise an exception → hits except block at lint_agent.py:874
    with patch("synthadoc.agents.ingest_agent._parse_json_response", side_effect=Exception("parse error")):
        report = await agent.run(scope="contradictions", auto_resolve=True)

    assert report.contradictions_found == 1
    # Page remains contradicted because exception made it unresolvable
    page = store.read_page("conflict-page")
    assert page is not None
    assert page.status == "contradicted"
    assert page.unresolved_note == "auto-resolve returned unparseable output"


@pytest.mark.asyncio
async def test_lint_auto_resolve_empty_resolution_appends_note(tmp_wiki):
    """When auto_resolve=True and JSON has resolvable=true but empty resolution, page content gets an auto-resolved note."""
    import json

    store = WikiStorage(tmp_wiki / "wiki")
    original_content = "⚠ This page has a contradiction."
    store.write_page("resolvable-page", WikiPage(
        title="Resolvable", tags=[],
        content=original_content,
        status="contradicted", confidence="low",
        sources=[], contradiction_note="Sources conflict on date."))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text=json.dumps({
            "resolvable": True,
            "reason": "Dates reconciled",
            "resolution": ""   # empty resolution → line 884 path
        }),
        input_tokens=20, output_tokens=10)

    agent = LintAgent(provider=provider, store=store, log_writer=log)
    report = await agent.run(scope="contradictions", auto_resolve=True)

    page = store.read_page("resolvable-page")
    assert page is not None
    assert page.status == "active"
    # Content must include the auto-resolved marker
    assert "Auto-resolved" in page.content


# ── Coverage: OSError and graph exception paths ───────────────────────────────


@pytest.mark.asyncio
async def test_check_page_citations_ioerror_ignored(tmp_wiki):
    """OSError reading a citation file is swallowed (lines 162-163)."""
    from pathlib import Path

    # Create the extracted txt file so txt_path.exists() is True
    extracted = tmp_wiki / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    txt_file = extracted / "report.txt"
    txt_file.write_text("line1\nline2\nline3", encoding="utf-8")

    page = WikiPage(
        title="Citation Test", tags=[],
        content="Some claim ^[report.txt:1-2]",
        status="active", confidence="high",
        sources=[SourceRef(file="raw_sources/report.txt", hash="abc", size=0, ingested="2026-01-01")],
        contradiction_note=None,
    )

    # Patch Path.read_text to raise OSError
    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        issues = _check_page_citations("citation-test", page, extracted_dir=extracted)

    # OSError should be swallowed — no issues reported for ioerror
    assert all(i.get("reason") != "ioerror" for i in issues)


@pytest.mark.asyncio
async def test_lint_graph_build_exception_swallowed(tmp_wiki):
    """Exception during graph build in lint(scope='all') is swallowed (lines 985-986)."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("graph-page", WikiPage(
        title="Graph Test", tags=[],
        content="Simple page content.",
        status="active", confidence="high",
        sources=[], contradiction_note=None,
    ))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(text="ok", input_tokens=5, output_tokens=5)

    agent = LintAgent(provider=provider, store=store, log_writer=log)

    # Inject a fake audit with all required async methods
    mock_audit = AsyncMock()
    mock_audit.write_graph = AsyncMock(side_effect=RuntimeError("graph boom"))
    mock_audit.get_all_page_states = AsyncMock(return_value={})
    mock_audit.record_audit_event = AsyncMock()
    mock_audit.record_lifecycle_event = AsyncMock()
    mock_audit.delete_graph_node = AsyncMock()
    agent._audit = mock_audit

    # Should complete without raising — graph exception is swallowed
    report = await agent.run(scope="all", adversarial=False)
    assert report is not None


# ── Adversarial gate: auto-resolve cycle prevention ───────────────────────────


@pytest.mark.asyncio
async def test_auto_resolve_skipped_when_gate_threshold_exceeded(tmp_wiki):
    """Auto-resolve is skipped for contradicted pages whose lint_warnings meet the gate threshold."""
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.storage.log import LogWriter

    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(
        title="Flagged Page", tags=[],
        content="This page has contested claims.",
        status="contradicted", confidence="medium",
        sources=[], contradiction_note="Two sources conflict on this claim.",
    )
    # Simulate 3 adversarial warnings already on this page
    page.lint_warnings = [
        {"claim": "Claim A", "concern": "Overstated"},
        {"claim": "Claim B", "concern": "Unsupported"},
        {"claim": "Claim C", "concern": "Disputed"},
    ]
    store.write_page("flagged-page", page)

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    # Provider should NOT be called — the guard fires before the LLM call
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"resolvable": true, "reason": "resolved", "resolution": "Updated content."}',
        input_tokens=10, output_tokens=10,
    ))

    agent = LintAgent(provider=provider, store=store, log_writer=log)
    agent._cfg = _gate_cfg(3)  # threshold = 3

    report = await agent.run(scope="contradictions", auto_resolve=True)

    # Page must stay contradicted — guard blocked the promotion
    refreshed = store.read_page("flagged-page")
    assert refreshed is not None
    assert refreshed.status == "contradicted"

    # Report must record the skip
    assert "flagged-page" in report.adversarial_gate_skipped_resolve

    # LLM must NOT have been called
    provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_auto_resolve_proceeds_when_gate_disabled(tmp_wiki):
    """Auto-resolve runs normally when adversarial_gate_threshold is None (gate off)."""
    import json
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.storage.log import LogWriter

    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(
        title="Gate Off Page", tags=[],
        content="Contested content.",
        status="contradicted", confidence="medium",
        sources=[], contradiction_note="Sources conflict.",
    )
    page.lint_warnings = [
        {"claim": "Claim A", "concern": "Overstated"},
        {"claim": "Claim B", "concern": "Unsupported"},
        {"claim": "Claim C", "concern": "Disputed"},
    ]
    store.write_page("gate-off-page", page)

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps({
            "resolvable": True,
            "reason": "Claims reconciled",
            "resolution": "Updated page content with both perspectives.",
        }),
        input_tokens=20, output_tokens=20,
    ))

    agent = LintAgent(provider=provider, store=store, log_writer=log)
    agent._cfg = _gate_cfg(None)  # gate disabled

    report = await agent.run(scope="contradictions", auto_resolve=True)

    # Page should be promoted — gate is off, auto-resolve ran
    refreshed = store.read_page("gate-off-page")
    assert refreshed is not None
    assert refreshed.status == "active"
    assert report.adversarial_gate_skipped_resolve == []
    provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_auto_resolve_proceeds_when_warnings_below_threshold(tmp_wiki):
    """Auto-resolve runs when page warnings are below the gate threshold."""
    import json
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    from synthadoc.storage.log import LogWriter

    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(
        title="Below Threshold Page", tags=[],
        content="Mostly accurate content with one issue.",
        status="contradicted", confidence="medium",
        sources=[], contradiction_note="Minor conflict.",
    )
    page.lint_warnings = [
        {"claim": "Claim A", "concern": "Slightly overstated"},
    ]  # 1 warning, threshold is 3
    store.write_page("below-threshold-page", page)

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps({
            "resolvable": True,
            "reason": "Minor issue resolved",
            "resolution": "Corrected content.",
        }),
        input_tokens=15, output_tokens=15,
    ))

    agent = LintAgent(provider=provider, store=store, log_writer=log)
    agent._cfg = _gate_cfg(3)  # threshold = 3, but only 1 warning

    report = await agent.run(scope="contradictions", auto_resolve=True)

    # Auto-resolve should have run — 1 warning < threshold 3
    refreshed = store.read_page("below-threshold-page")
    assert refreshed is not None
    assert refreshed.status == "active"
    assert report.adversarial_gate_skipped_resolve == []
    provider.complete.assert_called_once()


# ──────────────────────────────────────────────────────────────
# Targeted coverage tests for previously-uncovered branches
# ──────────────────────────────────────────────────────────────

def test_parse_adversarial_response_fallback_bracket_invalid_json():
    """Fallback regex finds [...] block but it contains invalid JSON (lines 393-394)."""
    # The direct json.loads fails; the regex finds "[broken json{]"; that also fails.
    result = _parse_adversarial_response('Based on review [broken json{]')
    assert result == []


def test_read_current_lint_state_skips_none_page(tmp_path):
    """read_current_lint_state skips slugs where read_page returns None (line 431)."""
    from unittest.mock import MagicMock
    store = MagicMock()
    # list_pages returns a slug but read_page can't find it
    store.list_pages.return_value = ["ghost-slug"]
    store.read_page.return_value = None
    result = read_current_lint_state(store)
    # No crash; all collections should be empty
    assert result.contradicted == []
    assert result.orphans == []


def test_load_adv_hash_cache_reads_valid_file(tmp_path):
    """_load_adv_hash_cache returns dict when the cache file is valid JSON (lines 488-490)."""
    cache_dir = tmp_path / ".synthadoc"
    cache_dir.mkdir(parents=True)
    (cache_dir / "adv_hashes.json").write_text('{"slug-a": "abc123"}', encoding="utf-8")
    result = _load_adv_hash_cache(tmp_path)
    assert result == {"slug-a": "abc123"}


def test_load_adv_hash_cache_returns_empty_on_corrupt_file(tmp_path):
    """_load_adv_hash_cache returns {} when the cache file is not valid JSON (lines 491-492)."""
    cache_dir = tmp_path / ".synthadoc"
    cache_dir.mkdir(parents=True)
    (cache_dir / "adv_hashes.json").write_text("not json", encoding="utf-8")
    result = _load_adv_hash_cache(tmp_path)
    assert result == {}


def test_save_adv_hash_cache_ignores_write_error(tmp_path):
    """_save_adv_hash_cache silently swallows write errors (lines 501-502)."""
    # Point the cache path at a directory so write_text fails
    cache_dir = tmp_path / ".synthadoc"
    cache_dir.mkdir(parents=True)
    # Create adv_hashes.json as a *directory* so write fails
    (cache_dir / "adv_hashes.json").mkdir()
    # Should not raise
    _save_adv_hash_cache(tmp_path, {"slug": "hash"})
