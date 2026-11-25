# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Link pass: pages promoted together are cross-linked, so a batch is not all orphans."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synthadoc.agents.link_pass import (
    RELATED_HEADING, RELATED_MARKER, add_related_links, link_promoted_pages,
)
from synthadoc.agents.lint_agent import read_current_lint_state
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiPage, WikiStorage


# ── add_related_links ────────────────────────────────────────────────────────

def test_adds_a_related_section_when_the_page_has_none():
    out = add_related_links("Body text.\n", [("spacing-effect", "Spacing Effect")])
    assert out.startswith("Body text.\n")
    assert f"{RELATED_HEADING}\n{RELATED_MARKER}\n- [[spacing-effect]] — Spacing Effect\n" in out


def test_appends_under_the_existing_marker_and_keeps_the_rest():
    content = (f"Body.\n\n{RELATED_HEADING}\n{RELATED_MARKER}\n- [[a]] — A\n\n"
               "## Notes\nKeep this.\n")
    out = add_related_links(content, [("b", "B")])
    assert out.index("- [[a]] — A") < out.index("- [[b]] — B") < out.index("## Notes")
    assert out.endswith("## Notes\nKeep this.\n")


def test_skips_a_page_that_is_already_linked_in_any_form():
    content = "See [[a]] and [[b|Bee]] and [[c#intro]]."
    assert add_related_links(content, [("a", "A"), ("b", "B"), ("c", "C")]) == content


def test_adding_the_same_links_twice_changes_nothing():
    once = add_related_links("Body.", [("a", "A"), ("b", "B")])
    assert add_related_links(once, [("a", "A"), ("b", "B")]) == once


# ── link_promoted_pages ──────────────────────────────────────────────────────

_PAGES = {
    "spaced-retrieval": ("Spaced Retrieval Practice",
                         "Spaced retrieval practice schedules memory recall tests over growing "
                         "intervals. Retrieval practice strengthens long term memory."),
    "spacing-effect": ("Spacing Effect",
                       "The spacing effect shows memory improves when study sessions are spaced. "
                       "Spacing and retrieval practice work together for long term memory."),
    "thesis-plan": ("Thesis Plan",
                    "Thesis plan for the statistics project: sections, deadlines and the "
                    "statistics methods chapter."),
    "statistics-methods": ("Statistics Methods",
                           "Statistics methods chapter for the thesis: regression, sampling and "
                           "statistics software used in the project."),
    "pasta-recipes": ("Pasta Recipes",
                      "Boil salted water, cook the pasta, add tomato sauce and basil."),
}


def _wiki(tmp_wiki, status="active", extra=None):
    store = WikiStorage(tmp_wiki / "wiki")
    for slug, (title, text) in {**_PAGES, **(extra or {})}.items():
        store.write_page(slug, WikiPage(title=title, tags=[], content=text,
                                        status=status, confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    return store, search


_BATCH = ["spaced-retrieval", "spacing-effect", "thesis-plan", "statistics-methods"]


def test_a_batch_of_unlinked_pages_stops_being_orphans(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    assert set(_BATCH) <= set(read_current_lint_state(store).orphans)   # the problem
    result = link_promoted_pages(store, search, _BATCH)
    orphans = set(read_current_lint_state(store).orphans)
    assert not (set(_BATCH) & orphans), orphans
    assert result.pages_changed >= 4


def test_related_pages_are_the_topically_close_ones(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    link_promoted_pages(store, search, _BATCH, max_per_page=1)
    assert "[[spacing-effect]]" in store.read_page("spaced-retrieval").content
    assert "[[statistics-methods]]" in store.read_page("thesis-plan").content
    assert "[[pasta-recipes]]" not in store.read_page("thesis-plan").content


def test_every_link_is_written_in_both_directions(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    link_promoted_pages(store, search, ["thesis-plan"], max_per_page=1)
    assert "[[statistics-methods]]" in store.read_page("thesis-plan").content
    assert "[[thesis-plan]]" in store.read_page("statistics-methods").content   # the inbound link


def test_a_second_run_changes_nothing(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    link_promoted_pages(store, search, _BATCH)
    snapshot = {s: store.read_page(s).content for s in _PAGES}
    again = link_promoted_pages(store, search, _BATCH)
    assert again.pages_changed == 0
    assert {s: store.read_page(s).content for s in _PAGES} == snapshot


def test_the_body_of_a_page_is_never_edited(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    link_promoted_pages(store, search, _BATCH)
    for slug, (_title, text) in _PAGES.items():
        assert store.read_page(slug).content.startswith(text)


def test_max_per_page_is_respected(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    result = link_promoted_pages(store, search, ["spaced-retrieval"], max_per_page=1)
    page = store.read_page("spaced-retrieval").content
    assert page.count("[[") == 1
    assert result.added["spaced-retrieval"] == ["spacing-effect"]


@pytest.mark.parametrize("state", ["archived", "contradicted"])
def test_pages_out_of_circulation_are_not_linked(tmp_wiki, state):
    store, search = _wiki(tmp_wiki)
    page = store.read_page("statistics-methods")
    page.status = state
    store.write_page("statistics-methods", page)
    link_promoted_pages(store, search, ["thesis-plan"])
    assert "[[statistics-methods]]" not in store.read_page("thesis-plan").content
    assert "[[thesis-plan]]" not in store.read_page("statistics-methods").content


def test_system_pages_are_never_linked(tmp_wiki):
    store, search = _wiki(tmp_wiki, extra={
        "index": ("Index", "Index of thesis statistics spacing retrieval pages."),
    })
    link_promoted_pages(store, search, _BATCH)
    assert "[[index]]" not in "".join(store.read_page(s).content for s in _PAGES)
    assert "[[" not in store.read_page("index").content


def test_nothing_to_do_for_an_empty_batch_or_a_zero_limit(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    assert link_promoted_pages(store, search, []).pages_changed == 0
    assert link_promoted_pages(store, search, _BATCH, max_per_page=0).pages_changed == 0


def test_a_missing_slug_is_skipped(tmp_wiki):
    store, search = _wiki(tmp_wiki)
    assert link_promoted_pages(store, search, ["no-such-page"]).pages_changed == 0


# ── wired into promote, and switchable ───────────────────────────────────────

def _candidate(tmp_wiki, slug, title, text):
    cdir = tmp_wiki / "wiki" / "candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / f"{slug}.md").write_text(
        f"---\ntitle: {title}\nstatus: active\nconfidence: high\ntags: []\nsources: []\n---\n\n{text}\n",
        encoding="utf-8")


def test_promote_all_cross_links_the_promoted_pages(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    for slug, (title, text) in _PAGES.items():
        _candidate(tmp_wiki, slug, title, text)
    with patch("synthadoc.core.orchestrator.Orchestrator.refresh_overview", new=AsyncMock()), \
         TestClient(create_app(wiki_root=tmp_wiki)) as client:
        assert client.post("/candidates/promote-all").json()["count"] == len(_PAGES)
    store = WikiStorage(tmp_wiki / "wiki")
    assert "[[spacing-effect]]" in store.read_page("spaced-retrieval").content
    assert not (set(_BATCH) & set(read_current_lint_state(store).orphans))


def test_promote_one_links_the_page_to_the_existing_wiki(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    _wiki(tmp_wiki)
    _candidate(tmp_wiki, "spaced-practice-notes", "Spaced Practice Notes",
               "Notes on spaced retrieval practice and the spacing effect for memory.")
    with patch("synthadoc.core.orchestrator.Orchestrator.refresh_overview", new=AsyncMock()), \
         TestClient(create_app(wiki_root=tmp_wiki)) as client:
        assert client.post("/candidates/spaced-practice-notes/promote").json()["promoted"] is True
    store = WikiStorage(tmp_wiki / "wiki")
    assert "[[" in store.read_page("spaced-practice-notes").content
    assert "[[spaced-practice-notes]]" in "".join(
        store.read_page(s).content for s in ("spaced-retrieval", "spacing-effect"))


def test_the_link_pass_can_be_switched_off(tmp_wiki):
    import asyncio
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.config import load_config
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    orch._cfg.ingest.link_on_promote = False
    store, _ = _wiki(tmp_wiki)
    orch._store, orch._search = store, MagicMock()
    asyncio.run(orch.link_promoted_pages(_BATCH))
    orch._search.bm25_search.assert_not_called()
    assert "[[" not in store.read_page("spaced-retrieval").content


def test_config_defaults_and_overrides(tmp_path):
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[agents]\ndefault = { provider = "anthropic", model = "m" }\n')
    ig = load_config(project_config=cfg_file).ingest
    assert ig.link_on_promote is True and ig.link_max_per_page == 3
    cfg_file.write_text('[agents]\ndefault = { provider = "anthropic", model = "m" }\n'
                        "[ingest]\nlink_on_promote = false\nlink_max_per_page = 5\n")
    ig = load_config(project_config=cfg_file).ingest
    assert ig.link_on_promote is False and ig.link_max_per_page == 5
