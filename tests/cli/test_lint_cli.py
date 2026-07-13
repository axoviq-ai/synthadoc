# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import patch
from typer.testing import CliRunner
from synthadoc.cli.main import app
from synthadoc.cli.lint import _parse_frontmatter, _index_suggestion

runner = CliRunner()


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------

def test_parse_frontmatter_valid():
    text = "---\ntitle: My Page\ntags: [foo, bar]\nstatus: active\n---\n\nbody"
    fm = _parse_frontmatter(text)
    assert fm["title"] == "My Page"
    assert fm["tags"] == ["foo", "bar"]


def test_parse_frontmatter_missing():
    assert _parse_frontmatter("no frontmatter here") == {}


def test_parse_frontmatter_invalid_yaml():
    text = "---\n: bad: yaml: [\n---\nbody"
    assert _parse_frontmatter(text) == {}


# ---------------------------------------------------------------------------
# _index_suggestion
# ---------------------------------------------------------------------------

def test_index_suggestion_with_tags():
    result = _index_suggestion("alan-turing", {"title": "Alan Turing", "tags": ["pioneer", "ai"]})
    assert "[[alan-turing]]" in result
    assert "pioneer" in result


def test_index_suggestion_without_tags():
    result = _index_suggestion("alan-turing", {})
    assert "[[alan-turing]]" in result
    assert "Alan Turing" in result


def test_index_suggestion_title_fallback():
    result = _index_suggestion("von-neumann", {"title": "Von Neumann"})
    assert "Von Neumann" in result


# ---------------------------------------------------------------------------
# lint report command (reads files directly, no server required)
# ---------------------------------------------------------------------------

def _make_wiki(tmp_path, pages: dict[str, str]):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    for name, content in pages.items():
        (wiki_dir / f"{name}.md").write_text(content, encoding="utf-8")
    import synthadoc.cli.install as install_mod
    return wiki_dir, tmp_path


def test_lint_report_all_clear(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":   "# Index\n",
        "topic-a": "---\nstatus: active\n---\n\n# Topic A\n\nSee also [[topic-b]].",
        "topic-b": "---\nstatus: active\n---\n\n# Topic B\n\nRelated to [[topic-a]].",
    })
    monkeypatch.setattr(install_mod, "_REGISTRY",
                        tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "All clear" in result.output


def test_lint_report_contradicted(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "bad-page": "---\nstatus: contradicted\n---\n# Bad",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "bad-page" in result.output
    assert "contradiction" in result.output.lower()


def test_lint_report_orphan(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "orphan-page": "---\nstatus: active\n---\n# Orphan",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "orphan-page" in result.output
    assert "orphan" in result.output.lower()


def test_lint_report_overview_links_do_not_mask_orphans(tmp_path, monkeypatch):
    """overview.md is auto-generated and links to every page — its links must not
    count as real inbound references. A page linked only from overview.md is still an orphan."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":    "# Index\n",
        "overview": "# Overview\n\n[[orphan-page]] [[linked-page]]",
        "orphan-page": "---\nstatus: active\n---\n# Orphan",
        "linked-page": "---\nstatus: active\n---\n# Linked\n\n[[orphan-page]]",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    # linked-page references orphan-page → not an orphan
    assert "orphan-page" not in result.output
    # linked-page is only referenced by overview.md (excluded) → IS an orphan
    assert "linked-page" in result.output


def test_lint_report_missing_wiki_dir(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code != 0


def test_lint_report_syncs_orphan_frontmatter(tmp_path, monkeypatch):
    """lint report must write orphan: true on orphan pages and orphan: false on linked ones."""
    import synthadoc.cli.install as install_mod

    orphan_fm = "---\ntitle: Orphan Page\nstatus: active\norphan: false\n---\n\n# Orphan Page\n"
    linked_fm = "---\ntitle: Linked Page\nstatus: active\norphan: true\n---\n\n# Linked Page\n"
    hub_content = "# Hub\n\nSee [[linked-page]]."

    wiki_dir, root = _make_wiki(tmp_path, {
        "index":       "# Index\n",
        "hub":         hub_content,
        "orphan-page": orphan_fm,
        "linked-page": linked_fm,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})

    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output

    from synthadoc.cli.lint import _parse_frontmatter
    orphan_text = (wiki_dir / "orphan-page.md").read_text(encoding="utf-8")
    linked_text = (wiki_dir / "linked-page.md").read_text(encoding="utf-8")

    assert _parse_frontmatter(orphan_text).get("orphan") is True, \
        "orphan-page must be flagged orphan: true"
    assert _parse_frontmatter(linked_text).get("orphan") is False, \
        "linked-page must be cleared to orphan: false"


def test_lint_report_frontmatter_wikilink_does_not_prevent_orphan(tmp_path, monkeypatch):
    """A [[wikilink]] appearing only in frontmatter YAML must not rescue a page from orphan status.
    Only links in the page body count as real inbound references."""
    import synthadoc.cli.install as install_mod
    # page-b is linked only from the frontmatter of hub-page (not from any body)
    hub_with_fm_link = (
        "---\ntitle: Hub\nstatus: active\nrelated: '[[page-b]]'\n---\n\n"
        "# Hub\n\nThis page has no body links.\n"
    )
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":  "# Index\n",
        "hub":    hub_with_fm_link,
        "page-b": "---\nstatus: active\n---\n# Page B\n",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    # page-b has no inbound body links → IS an orphan
    assert "page-b" in result.output


def test_lint_report_all_clear_clears_stale_orphan_flags(tmp_path, monkeypatch):
    """When lint report finds no issues, stale orphan: true flags must be cleared."""
    import synthadoc.cli.install as install_mod
    # All pages are mutually linked; one has a stale orphan: true from a previous run
    stale_orphan_fm = (
        "---\ntitle: Linked Page\nstatus: active\norphan: true\n---\n\n"
        "# Linked Page\n\nSee [[hub]].\n"
    )
    hub_content = "---\nstatus: active\n---\n\n# Hub\n\nSee [[linked-page]]."
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":       "# Index\n",
        "hub":         hub_content,
        "linked-page": stale_orphan_fm,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "All clear" in result.output

    from synthadoc.cli.lint import _parse_frontmatter
    linked_text = (wiki_dir / "linked-page.md").read_text(encoding="utf-8")
    assert _parse_frontmatter(linked_text).get("orphan") is False, \
        "stale orphan: true must be cleared on All clear"


def test_lint_report_index_links_do_not_rescue_from_orphan(tmp_path, monkeypatch):
    """Adding [[slug]] to index.md must NOT rescue from orphan — only content-page
    links count. index.md is a directory; a page must be linked from a real content
    page to be considered integrated into the knowledge graph."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":        "# Index\n\n[[page-a]]\n",
        "page-a":       "---\nstatus: active\n---\n# Page A\n",
        "page-b":       "---\nstatus: active\n---\n# Page B\n",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "page-a" in result.output   # index link doesn't count → still orphan
    assert "page-b" in result.output   # nothing links to page-b → also orphan


def test_lint_report_self_link_does_not_rescue_from_orphan(tmp_path, monkeypatch):
    """A page that links only to itself must still be reported as an orphan."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":   "# Index\n",
        "lonely":  "---\nstatus: active\n---\n# Lonely\n\nSee also [[lonely]].\n",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "lonely" in result.output


def test_lint_report_shows_adversarial_warnings_section(tmp_path, monkeypatch):
    """lint report shows adversarial warnings when lint_warnings exist in frontmatter."""
    import synthadoc.cli.install as install_mod
    # Real ingest stores absolute paths; relative paths are placeholder entries
    # that should be filtered out.  Use an absolute path to test the positive case.
    abs_source = str(tmp_path / "raw_sources" / "study.pdf")
    flagged_page = (
        "---\n"
        "status: active\n"
        "sources:\n"
        f"  - {{file: '{abs_source}', hash: 'abc', size: 1000, ingested: '2026-05-01'}}\n"
        "lint_warnings:\n"
        "  - claim: 'Claim A was the first.'\n"
        "    concern: 'Overstated — prior work existed'\n"
        "---\n\n# Flagged Page\n"
    )
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "flagged-page": flagged_page,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "Adversarial" in result.output
    assert "Claim A was the first." in result.output
    assert "Overstated" in result.output
    assert "study.pdf" in result.output  # re-ingest suggestion references the source file


def test_lint_report_relative_source_no_reingest_suggestion(tmp_path, monkeypatch):
    """Relative source paths (placeholder/demo entries) must not generate re-ingest suggestions."""
    import synthadoc.cli.install as install_mod
    flagged_page = (
        "---\n"
        "status: active\n"
        "sources:\n"
        "  - {file: 'papers/study.pdf', hash: 'placeholder', size: 0, ingested: '2026-05-01'}\n"
        "lint_warnings:\n"
        "  - claim: 'Some claim.'\n"
        "    concern: 'Some concern'\n"
        "---\n\n# Flagged Page\n"
    )
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "flagged-page": flagged_page,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "Adversarial" in result.output   # warning still shown
    assert "Re-ingest" not in result.output  # but no re-ingest command for a relative path


def test_lint_report_no_adversarial_section_when_clean(tmp_path, monkeypatch):
    """lint report omits adversarial section when no lint_warnings in any page."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":   "# Index\n",
        "topic-a": "---\nstatus: active\n---\n\n# Topic A\n\nSee also [[topic-b]].",
        "topic-b": "---\nstatus: active\n---\n\n# Topic B\n\nRelated to [[topic-a]].",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "Adversarial" not in result.output


def test_lint_report_shows_citation_issues(tmp_path, monkeypatch):
    """lint report shows Citation Issues section when broken citations found."""
    import synthadoc.cli.install as install_mod
    page_with_broken = (
        "---\nstatus: active\nsources:\n"
        "  - {file: '/path/bio.txt', hash: 'x', size: 1, ingested: '2026-01-01'}\n"
        "---\n\n# Page\n\nA claim.^[other.txt:1-5]\n"
    )
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "page-a": page_with_broken,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0
    assert "Citation" in result.output
    assert "broken_ref" in result.output


# ---------------------------------------------------------------------------
# lint run command (enqueues a job via the HTTP API)
# ---------------------------------------------------------------------------

def test_lint_run_enqueues_job(tmp_path, monkeypatch):
    """lint run must POST to /jobs/lint and echo the returned job_id."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    with patch("synthadoc.cli.lint.post", return_value={"job_id": "lint-001"}):
        result = runner.invoke(app, ["lint", "run", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "lint-001" in result.output


def test_lint_run_no_adversarial_flag(tmp_path, monkeypatch):
    """lint run --no-adversarial must pass adversarial=False in the payload."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    captured = {}
    def fake_post(wiki, path, payload):
        captured["payload"] = payload
        return {"job_id": "lint-002"}
    with patch("synthadoc.cli.lint.post", side_effect=fake_post):
        result = runner.invoke(app, ["lint", "run", "--no-adversarial", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert captured["payload"]["adversarial"] is False
    assert "lint_warnings cleared" in result.output.lower() or "adversarial pass skipped" in result.output.lower()


def test_lint_run_scope_forwarded(tmp_path, monkeypatch):
    """lint run --scope contradictions must forward scope in the payload."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    captured = {}
    def fake_post(wiki, path, payload):
        captured["payload"] = payload
        return {"job_id": "lint-003"}
    with patch("synthadoc.cli.lint.post", side_effect=fake_post):
        result = runner.invoke(app, ["lint", "run", "--scope", "contradictions", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert captured["payload"]["scope"] == "contradictions"


def test_lint_report_no_citation_section_when_clean(tmp_path, monkeypatch):
    """lint report omits Citation Issues when no broken citations."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "topic-a": "---\nstatus: active\nsources:\n  - {file: '/p/a.txt', hash: 'x', size: 1, ingested: '2026-01-01'}\n---\n\n# A\n\nSee [[topic-b]].",
        "topic-b": "---\nstatus: active\nsources:\n  - {file: '/p/b.txt', hash: 'x', size: 1, ingested: '2026-01-01'}\n---\n\n# B\n\nSee [[topic-a]].",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert "Citation" not in result.output


# ---------------------------------------------------------------------------
# Truncated sources — CLI lint report (regression: section was missing)
# ---------------------------------------------------------------------------

_TRUNCATED_PAGE = (
    "---\n"
    "title: Long Article\n"
    "status: active\n"
    "sources:\n"
    "  - file: 'https://example.com/long-article'\n"
    "    hash: abc123\n"
    "    size: 45000\n"
    "    ingested: '2026-07-12'\n"
    "    truncated: true\n"
    "---\n\n"
    "# Long Article\n\n"
    "See [[hub-page]] for more.\n"
)


def test_lint_report_shows_truncated_sources(tmp_path, monkeypatch):
    """CLI lint report must render a Truncated Sources section when a page has truncated: true.

    Regression: _state.truncated_pages was computed but never rendered — the
    section was silently absent from the CLI output while the plugin showed it.
    """
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":        "# Index\n",
        "hub-page":     "---\nstatus: active\n---\n# Hub\n\nSee [[long-article]].",
        "long-article": _TRUNCATED_PAGE,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "Truncated" in result.output
    assert "long-article" in result.output
    assert "--max-source-chars" in result.output


def test_lint_report_truncated_prevents_all_clear(tmp_path, monkeypatch):
    """A page with a truncated source must prevent 'All clear' even if no other issues."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":        "# Index\n",
        "hub-page":     "---\nstatus: active\n---\n# Hub\n\nSee [[long-article]].",
        "long-article": _TRUNCATED_PAGE,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert "All clear" not in result.output


def test_lint_report_footer_includes_truncated_count(tmp_path, monkeypatch):
    """Footer summary line must include the truncated source count."""
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index":        "# Index\n",
        "hub-page":     "---\nstatus: active\n---\n# Hub\n\nSee [[long-article]].",
        "long-article": _TRUNCATED_PAGE,
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert "1 truncated source(s)" in result.output
