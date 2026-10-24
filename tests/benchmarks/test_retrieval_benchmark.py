# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the retrieval benchmark harness (no network, no LLM)."""
from __future__ import annotations

import json

import pytest

from benchmarks.retrieval import corpus, evaluate, metrics, queries
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage


# ── metrics ──────────────────────────────────────────────────────────────────

def test_recall_counts_share_of_relevant_in_top_k():
    assert metrics.recall_at(["a", "b", "c"], ["c", "z"], 3) == 0.5
    assert metrics.recall_at(["a", "b", "c"], ["c"], 2) == 0.0
    assert metrics.recall_at(["a"], [], 5) == 0.0


def test_reciprocal_rank_uses_first_relevant_within_depth():
    assert metrics.reciprocal_rank(["a", "b", "c"], ["c", "b"]) == 0.5
    assert metrics.reciprocal_rank(["a", "b"], ["b"], depth=1) == 0.0


def test_ndcg_is_one_for_ideal_ranking_and_lower_otherwise():
    assert metrics.ndcg(["g1", "g2", "x"], ["g1", "g2"]) == pytest.approx(1.0)
    assert 0 < metrics.ndcg(["x", "g1"], ["g1"]) < 1
    assert metrics.ndcg(["x"], ["g1"]) == 0.0


def test_score_run_averages_and_counts_queries():
    scores = metrics.score_run([(["a"], ["a"]), (["b"], ["a"])])
    assert scores["recall@5"] == 0.5
    assert scores["mrr@10"] == 0.5
    assert scores["queries"] == 2
    assert metrics.score_run([]) == {}


def test_percentile_nearest_rank():
    assert metrics.percentile([5, 1, 3, 2, 4], 50) == 3
    assert metrics.percentile(list(range(1, 101)), 95) == 95
    assert metrics.percentile([], 95) == 0.0


# ── Wikipedia HTML → wiki Markdown ───────────────────────────────────────────

_HTML = """
<div class="mw-parser-output">
  <table class="infobox"><tr><td>Infobox junk</td></tr></table>
  <p>ENIAC was the first <b>general-purpose</b> computer.<sup class="reference">[1]</sup></p>
  <div class="mw-heading mw-heading2"><h2>History</h2><span class="mw-editsection">edit</span></div>
  <p>Built at the Moore School.[citation needed]</p>
  <ul><li>Designed by Mauchly</li><li>and Eckert</li></ul>
  <div class="mw-heading mw-heading2"><h2>Empty</h2></div>
  <div class="mw-heading mw-heading2"><h2>See also</h2></div>
  <p>Should not appear.</p>
</div>
"""


def test_html_to_markdown_keeps_prose_headings_and_lists():
    md = corpus.html_to_markdown(_HTML)
    assert md.startswith("ENIAC was the first general-purpose computer.\n")
    assert "## History" in md
    assert "Built at the Moore School." in md and "[citation needed]" not in md
    assert "- Designed by Mauchly\n- and Eckert" in md
    assert "Infobox" not in md and "edit" not in md and "[1]" not in md


def test_html_to_markdown_stops_at_reference_sections_and_drops_empty_headings():
    md = corpus.html_to_markdown(_HTML)
    assert "Should not appear" not in md
    assert "## Empty" not in md


def test_html_to_markdown_reads_rest_html_with_nested_sections():
    html = """<html><body>
      <section data-mw-section-id="0"><p>Lead text here.</p></section>
      <section data-mw-section-id="1"><h2>History</h2><p>Old times.</p>
        <section data-mw-section-id="2"><h3>Early</h3><p>Very old.</p></section></section>
      <section data-mw-section-id="3"><h2>References</h2><p>Refs.</p></section>
    </body></html>"""
    md = corpus.html_to_markdown(html)
    assert md == "Lead text here.\n\n## History\n\nOld times.\n\n### Early\n\nVery old.\n"


def test_html_to_markdown_renders_math_as_latex_source():
    html = """<div class="mw-parser-output"><p>Peano arithmetic
      <span class="mwe-math-element"><span style="display:none"><math><semantics><mi>PA</mi>
      <annotation encoding="application/x-tex">{\\displaystyle {\\mathsf {PA}}}</annotation>
      </semantics></math></span><img alt="{\\displaystyle {\\mathsf {PA}}}"/></span> is strong.</p></div>"""
    assert corpus.html_to_markdown(html) == "Peano arithmetic ${\\mathsf {PA}}$ is strong.\n"


def test_html_to_markdown_caps_words_at_a_block_boundary():
    html = "<div class='mw-parser-output'>" + "<p>one two three four five</p>" * 10 + "</div>"
    md = corpus.html_to_markdown(html, max_words=12)
    assert md.count("one two three four five") == 3


def test_articles_round_trip(tmp_path):
    path = tmp_path / "articles.json"
    rows = [corpus.Article("Alan Turing", 1, "Computer scientists"), corpus.Article("ENIAC", 2, "History")]
    corpus.save_articles(rows, path)
    assert corpus.load_articles(path) == rows
    assert rows[0].slug == "alan-turing"
    assert len(path.read_text().splitlines()) == 4   # brackets + one line per article


def test_build_hotpot_writes_each_paragraph_once_and_maps_gold(tmp_path):
    row = {
        "id": "q1", "question": "Who built ENIAC?",
        "supporting_facts": {"title": ["ENIAC", "ENIAC", "John Mauchly"]},
        "context": {"title": ["ENIAC", "John Mauchly"],
                    "sentences": [["ENIAC was a computer.", " It was big."], ["Mauchly was a physicist."]]},
    }
    wiki_dir, qs = corpus.build_hotpot([row, {**row, "id": "q2"}], tmp_path)
    store = WikiStorage(wiki_dir)
    assert sorted(store.list_pages()) == ["eniac", "john-mauchly"]
    assert "ENIAC was a computer. It was big." in store.read_page("eniac").content
    assert qs[0] == corpus.HotpotQuestion("q1", "Who built ENIAC?", ["eniac", "john-mauchly"])


# ── query generation ─────────────────────────────────────────────────────────

_BODY = ("The ENIAC computer used vacuum tubes. ENIAC vacuum tubes failed often. "
         "Programming ENIAC meant plugboards and switches. ") * 5


def _stats(tmp_path) -> queries.TermStats:
    """Ten pages: "the"/"computer"/"machine" are on all of them, the ENIAC terms on one."""
    store = WikiStorage(tmp_path / "stats-wiki")
    corpus.write_bench_page(store, "eniac", "ENIAC", [], _BODY)
    for i in range(9):
        corpus.write_bench_page(store, f"p{i}", f"Page {i}", [],
                                f"The computer is a machine with part{i} and the first unit{i}.")
    return queries.TermStats.from_store(store)


def test_term_stats_marks_widespread_terms_generic(tmp_path):
    stats = _stats(tmp_path)
    assert stats.pages == 10
    assert stats.is_generic("the") and stats.is_generic("computer")
    assert not stats.is_generic("eniac") and not stats.is_generic("plugboards")


def test_distinctive_terms_skip_generic_words(tmp_path):
    terms = queries.distinctive_terms("The ENIAC", _BODY, _stats(tmp_path))
    assert {"eniac", "vacuum", "plugboards"} <= terms
    assert not terms & {"the", "computer"}


def test_paraphrase_overlap_rejects_title_terms(tmp_path):
    assert "eniac" in queries.paraphrase_overlap("how big was eniac", "ENIAC", _BODY, _stats(tmp_path))


def test_paraphrase_overlap_ignores_generic_words_and_tolerates_a_few_page_terms(tmp_path):
    stats = _stats(tmp_path)
    assert queries.paraphrase_overlap("which early machine and computer used the glowing tubes",
                                      "ENIAC", _BODY, stats) == []
    assert queries.paraphrase_overlap("vacuum tubes plugboards switches programming",
                                      "ENIAC", _BODY, stats) != []


def test_drop_leaky_paraphrases_keeps_other_types(tmp_path):
    stats = _stats(tmp_path)
    store = WikiStorage(tmp_path / "stats-wiki")
    qs = [queries.Query("eniac:lexical", "lexical", "what was eniac", ["eniac"]),
          queries.Query("eniac:paraphrase", "paraphrase", "what was eniac", ["eniac"])]
    assert [q.type for q in queries.drop_leaky_paraphrases(qs, store, stats)] == ["lexical"]


class _FakeProvider:
    def __init__(self, replies: list[dict | str]):
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def complete(self, messages, system=None, temperature=0.0, max_tokens=4096):
        self.prompts.append(messages[0].content)
        reply = self.replies.pop(0)
        return CompletionResponse(reply if isinstance(reply, str) else json.dumps(reply), 0, 0)


_GOOD = {"lexical": "ENIAC vacuum tubes", "paraphrase": "first electronic machine for artillery tables",
         "identifier": "Moore School 1946"}


async def test_queries_for_page_returns_three_labelled_queries():
    qs = await queries.queries_for_page(_FakeProvider([_GOOD]), "eniac", "ENIAC", _BODY, queries.TermStats())
    assert [(q.id, q.type, q.relevant) for q in qs] == [
        ("eniac:lexical", "lexical", ["eniac"]),
        ("eniac:paraphrase", "paraphrase", ["eniac"]),
        ("eniac:identifier", "identifier", ["eniac"]),
    ]


async def test_queries_for_page_retries_a_leaky_paraphrase_with_feedback():
    provider = _FakeProvider([{**_GOOD, "paraphrase": "what was eniac"}, _GOOD])
    qs = await queries.queries_for_page(provider, "eniac", "ENIAC", _BODY, queries.TermStats())
    assert "previous paraphrase" in provider.prompts[1] and "eniac" in provider.prompts[1]
    assert next(q.text for q in qs if q.type == "paraphrase") == _GOOD["paraphrase"]


async def test_queries_for_page_drops_a_paraphrase_that_still_leaks():
    leaky = {**_GOOD, "paraphrase": "what was eniac"}
    logged: list[str] = []
    qs = await queries.queries_for_page(_FakeProvider([leaky, leaky]), "eniac", "ENIAC", _BODY,
                                        queries.TermStats(), logged.append)
    assert [q.type for q in qs] == ["lexical", "identifier"]
    assert "paraphrase dropped" in logged[0] and "what was eniac" in logged[0]


async def test_queries_for_page_tolerates_prose_around_json_and_bad_json():
    stats = queries.TermStats()
    qs = await queries.queries_for_page(_FakeProvider(["Sure! " + json.dumps(_GOOD)]), "e", "ENIAC", _BODY, stats)
    assert len(qs) == 3
    assert await queries.queries_for_page(_FakeProvider(["not json"]), "e", "ENIAC", _BODY, stats) == []


def test_sample_slugs_is_seeded_and_sorted():
    slugs = [f"p{i}" for i in range(50)]
    first = queries.sample_slugs(slugs, n=10)
    assert first == queries.sample_slugs(list(reversed(slugs)), n=10)
    assert first == sorted(first) and len(first) == 10


async def test_generate_fills_only_missing_types_and_keeps_existing(tmp_path):
    wiki_dir = tmp_path / "wiki"
    store = WikiStorage(wiki_dir)
    corpus.write_bench_page(store, "eniac", "ENIAC", [], _BODY)
    corpus.write_bench_page(store, "unix", "Unix", [], "Unix is an operating system from Bell Labs.")
    out = tmp_path / "q.jsonl"
    queries.save_queries([queries.Query("eniac:lexical", "lexical", "old lexical", ["eniac"]),
                          queries.Query("unix:paraphrase", "paraphrase", "kept as is", ["unix"])], out)
    provider = _FakeProvider([_GOOD])          # only eniac lacks a paraphrase
    result = await queries.generate(provider, wiki_dir, out, types=("paraphrase",), log=lambda _: None)
    assert len(provider.prompts) == 1 and "ENIAC" in provider.prompts[0]
    assert [(q.id, q.text) for q in result] == [
        ("eniac:lexical", "old lexical"),
        ("eniac:paraphrase", _GOOD["paraphrase"]),
        ("unix:paraphrase", "kept as is"),
    ]
    assert queries.load_queries(out) == result


def test_queries_round_trip(tmp_path):
    path = tmp_path / "q.jsonl"
    qs = [queries.Query("a:lexical", "lexical", "text", ["a"])]
    queries.save_queries(qs, path)
    assert queries.load_queries(path) == qs


# ── evaluation ───────────────────────────────────────────────────────────────

def test_nested_subsets_are_prefixes_of_one_shuffle_plus_the_full_corpus():
    subsets = evaluate.nested_subsets([f"p{i}" for i in range(30)], (5, 10, 40))
    assert set(subsets) == {5, 10, 30}
    assert subsets[10][:5] == subsets[5]
    assert subsets[30] is None


def test_nested_subsets_overlap_the_query_sample():
    """Regression: with a shared seed, sample() and shuffle() picked disjoint pages."""
    slugs = [f"p{i:04d}" for i in range(2000)]
    sampled = set(queries.sample_slugs(slugs))
    for size, subset in evaluate.nested_subsets(slugs, evaluate.WIKI_SIZES).items():
        share = len(sampled & set(subset or slugs)) / len(sampled)
        assert share == pytest.approx(size / len(slugs), abs=0.08)


def _tiny_wiki(tmp_path):
    wiki_dir = tmp_path / "wiki"
    store = WikiStorage(wiki_dir)
    for slug, title, body in [
        ("eniac", "ENIAC", "ENIAC was an early electronic computer built with vacuum tubes."),
        ("unix", "Unix", "Unix is a multitasking operating system developed at Bell Labs."),
        ("tcp-ip", "TCP/IP", "TCP/IP is the protocol suite that runs the internet."),
    ]:
        corpus.write_bench_page(store, slug, title, [], body)
    return wiki_dir


async def test_evaluate_corpus_scores_bm25_per_type_and_size(tmp_path):
    wiki_dir = _tiny_wiki(tmp_path)
    qs = [queries.Query("eniac:lexical", "lexical", "ENIAC vacuum tubes", ["eniac"]),
          queries.Query("unix:lexical", "lexical", "Bell Labs operating system", ["unix"]),
          queries.Query("unix:paraphrase", "paraphrase", "software managing a computer", ["unix"])]
    results = await evaluate.evaluate_corpus(wiki_dir, qs, ["bm25"], (2,), log=lambda _: None)
    full = results["bm25"]["3"]
    assert full["metrics"]["lexical"]["recall@5"] == 1.0
    assert full["metrics"]["all"]["queries"] == 3
    assert set(full["latency"]) == {"p50_ms", "p95_ms"}
    # The 2-page wiki only scores queries whose page is in it.
    assert results["bm25"]["2"]["metrics"]["all"]["queries"] < 3


def test_format_table_has_a_row_per_config_size_and_type():
    m = {"recall@5": 1, "recall@10": 1, "recall@20": 1, "mrr@10": 1, "ndcg@10": 1, "queries": 2}
    results = {"bm25": {"200": {"metrics": {"all": m, "lexical": m}, "latency": {"p95_ms": 3.0}}}}
    table = evaluate.format_table("wikipedia", results)
    assert table.count("| bm25 | 200 |") == 2



def test_write_baseline_replaces_only_the_configs_just_run(tmp_path):
    from benchmarks.retrieval.__main__ import write_baseline

    path = tmp_path / "baseline.json"
    write_baseline({"wikipedia": {"bm25": {"x": 1}, "rerank": {"x": 2}}}, path)
    write_baseline({"wikipedia": {"fusion": {"x": 3}}, "hotpot": {"bm25": {"x": 4}}}, path)
    results = json.loads(path.read_text())["results"]
    assert results == {"wikipedia": {"bm25": {"x": 1}, "rerank": {"x": 2}, "fusion": {"x": 3}},
                       "hotpot": {"bm25": {"x": 4}}}


async def test_make_search_syncs_embeddings_for_the_hybrid_config(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    from unittest.mock import MagicMock
    from synthadoc.storage.search import HybridSearch

    wiki_dir = _tiny_wiki(tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "fastembed", MagicMock())
    monkeypatch.setattr(HybridSearch, "_embed_texts",
                        lambda self, texts: np.ones((len(texts), 3), dtype=np.float32) / 3 ** 0.5)
    logged: list[str] = []
    search = await evaluate.make_search(wiki_dir, evaluate.CONFIGS["hybrid"], log=logged.append)
    assert sorted(search._page_slugs) == ["eniac", "tcp-ip", "unix"]
    assert "embedded 3 page(s)" in logged[0]
    bm25 = await evaluate.make_search(wiki_dir, evaluate.CONFIGS["bm25"], log=logged.append)
    assert bm25._vector_store is None
