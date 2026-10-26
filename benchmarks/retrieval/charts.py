# Copyright (C) 2026 Peter W. / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Charts of the benchmark results, for the READMEs and the blog post.

    python -m benchmarks.retrieval charts          # writes docs/png/benchmarks/*.png

Static PNGs on a light surface: GitHub and dev.to render images, not scripts,
so every chart carries direct value labels, and the README next to it has the
same numbers as a table. Each search method keeps one colour in every chart.
Needs matplotlib (in the dev extra).
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.retrieval import corpus

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "png" / "benchmarks"

# Validated categorical slots (light mode), one per method.
SEMANTIC = "#2a78d6"     # fusion + keyword pin: what ships
KEYWORD = "#eb6834"      # BM25
RERANK = "#1baf7a"       # the former vector = true (BM25 top 20 re-sorted)
FUSION = "#6250d6"       # fusion without the keyword pin
SURFACE, TEXT, TEXT_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#c3c2b7"

# Measured while designing semantic search (benchmarks/retrieval/README.md,
# "How the design was chosen"); these setups no longer exist in the code.
DESIGN_SETUPS = [
    ("Keyword search (BM25)", KEYWORD, {"lexical": 0.998, "identifier": 0.994, "paraphrase": 0.479, "all": 0.840}),
    ("Vector re-rank (old)", RERANK, {"lexical": 0.986, "identifier": 0.625, "paraphrase": 0.595, "all": 0.742}),
    ("Fusion, no keyword pin", FUSION, {"lexical": 0.994, "identifier": 0.936, "paraphrase": 0.694, "all": 0.883}),
    ("Semantic search (fusion + pin)", SEMANTIC, {"lexical": 0.998, "identifier": 0.984, "paraphrase": 0.676, "all": 0.896}),
]
# P95 before the query embedding overlapped BM25 (the previous committed baseline).
LATENCY_BEFORE = {"200": 65.9, "500": 63.9, "1000": 70.1, "1985": 165.7}
# Knowledge graph, web UI Graph tab, headless Chromium (docs/design.md).
GRAPH_PAGES = [500, 1000, 2000, 5000]
GRAPH_BEFORE_S = [1.7, 5.2, 10.1, 34.2]
GRAPH_AFTER_S = [0.8, 1.3, 2.8, 5.8]

CORPUS_LABELS = {"wikipedia": "Wikipedia\n(tuned on)", "hotpot": "HotpotQA\n(human questions)",
                 "scifact": "SciFact\n(science claims)", "nfcorpus": "NFCorpus\n(medical)",
                 "duretrieval": "DuRetrieval\n(Chinese: keyword only)"}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "text.color": TEXT, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.alpha": 0.6,
        "axes.axisbelow": True, "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "legend.frameon": False,
    })
    return plt


def _save(fig, name: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return path


def _grouped_bars(ax, groups: list[str], series: list[tuple[str, str, list[float]]], fmt: str) -> None:
    n = len(series)
    width = 0.8 / n
    for i, (label, colour, values) in enumerate(series):
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        bars = ax.bar(xs, values, width * 0.92, color=colour, label=label, linewidth=0)
        ax.bar_label(bars, labels=[fmt.format(v) for v in values], padding=2, fontsize=8.5, color=TEXT_2)
    ax.set_xticks(range(len(groups)), groups)
    ax.grid(axis="x", visible=False)


def chart_design(out_dir: Path) -> Path:
    """Recall@5 by question type for each setup tried: why plain re-ranking failed."""
    plt = _plt()
    types = ["lexical", "identifier", "paraphrase", "all"]
    labels = ["Page's own words", "Exact name / ID", "Paraphrased", "All questions"]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    _grouped_bars(ax, labels, [(n, c, [v[t] for t in types]) for n, c, v in DESIGN_SETUPS], "{:.2f}")
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Right page in the top 5 (recall@5)")
    ax.set_title("Only fusion with the keyword pin keeps exact names and lifts paraphrases",)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=4, fontsize=9.5)
    return _save(fig, "design-choices.png", out_dir)


def chart_size(baseline: dict, out_dir: Path) -> Path:
    """Paraphrased-question recall@5 as the wiki grows, keyword vs semantic."""
    plt = _plt()
    wiki = baseline["results"]["wikipedia"]
    sizes = ["200", "500", "1000", "1985"]
    xs = [int(s) for s in sizes]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for name, label, colour in (("bm25", "Keyword search (BM25)", KEYWORD),
                                ("hybrid", "Semantic search", SEMANTIC)):
        ys = [wiki[name][s]["metrics"]["paraphrase"]["recall@5"] for s in sizes]
        ax.plot(xs, ys, color=colour, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label)
        ax.annotate(f"{ys[-1]:.2f}", (xs[-1], ys[-1]), textcoords="offset points", xytext=(10, -4),
                    color=TEXT_2, fontsize=10)
        ax.annotate(f"{ys[0]:.2f}", (xs[0], ys[0]), textcoords="offset points", xytext=(0, 10),
                    ha="center", color=TEXT_2, fontsize=10)
    ax.set_xticks(xs, ["200", "500", "1,000", "1,985"])
    ax.set_xlim(60, 2250)
    ax.set_ylim(0.4, 0.9)
    ax.set_xlabel("Pages in the wiki")
    ax.set_ylabel("Paraphrased questions:\nright page in the top 5")
    ax.set_title("Keyword search misses more paraphrases as the wiki grows")
    ax.legend(loc="upper right")
    return _save(fig, "paraphrase-by-wiki-size.png", out_dir)


def chart_corpora(baseline: dict, out_dir: Path) -> Path:
    """nDCG@10, keyword vs semantic, on every corpus with results.

    nDCG rather than recall@5: NFCorpus queries have ~38 relevant documents each,
    so a top 5 cannot hold most of them and recall@5 understates every method."""
    plt = _plt()
    results = baseline["results"]
    names = [n for n in CORPUS_LABELS if n in results and {"bm25", "hybrid"} <= set(results[n])]

    def ndcg(name: str, config: str) -> float:
        by_size = results[name][config]
        return by_size[max(by_size, key=int)]["metrics"]["all"]["ndcg@10"]

    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    _grouped_bars(ax, [CORPUS_LABELS[n] for n in names], [
        ("Keyword search (BM25)", KEYWORD, [ndcg(n, "bm25") for n in names]),
        ("Semantic search", SEMANTIC, [ndcg(n, "hybrid") for n in names]),
    ], "{:.2f}")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Ranking quality (nDCG@10)")
    ax.set_title("Better on every English corpus, unchanged on Chinese")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    return _save(fig, "independent-corpora.png", out_dir)


def chart_latency(baseline: dict, out_dir: Path) -> Path:
    """P95 search latency by wiki size: keyword, semantic before and after the overlap."""
    plt = _plt()
    wiki = baseline["results"]["wikipedia"]
    sizes = ["200", "500", "1000", "1985"]
    xs = [int(s) for s in sizes]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    series = [
        ("Semantic, embedding after BM25 (before)", SEMANTIC, "--", [LATENCY_BEFORE[s] for s in sizes]),
        ("Semantic, embedding alongside BM25 (now)", SEMANTIC, "-", [wiki["hybrid"][s]["latency"]["p95_ms"] for s in sizes]),
        ("Keyword search (BM25)", KEYWORD, "-", [wiki["bm25"][s]["latency"]["p95_ms"] for s in sizes]),
    ]
    for label, colour, style, ys in series:
        ax.plot(xs, ys, color=colour, linestyle=style, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label)
        ax.annotate(f"{ys[-1]:.0f} ms", (xs[-1], ys[-1]), textcoords="offset points", xytext=(10, -4),
                    color=TEXT_2, fontsize=10)
    ax.set_xticks(xs, ["200", "500", "1,000", "1,985"])
    ax.set_xlim(60, 2350)
    ax.set_ylim(0, 190)
    ax.set_xlabel("Pages in the wiki")
    ax.set_ylabel("Search time, P95 (ms)")
    ax.set_title("Overlapping the query embedding with BM25 halved semantic search time")
    ax.legend(loc="upper left", fontsize=9.5)
    return _save(fig, "search-latency.png", out_dir)


def chart_graph(out_dir: Path) -> Path:
    """Knowledge graph: seconds until the Graph tab shows something usable."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for label, colour, ys in (("Every page drawn (before)", KEYWORD, GRAPH_BEFORE_S),
                              ("Cluster overview (now)", SEMANTIC, GRAPH_AFTER_S)):
        ax.plot(GRAPH_PAGES, ys, color=colour, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label)
        ax.annotate(f"{ys[-1]:.0f} s" if ys[-1] >= 10 else f"{ys[-1]:.1f} s", (GRAPH_PAGES[-1], ys[-1]),
                    textcoords="offset points", xytext=(10, -4), color=TEXT_2, fontsize=10)
    ax.set_xticks(GRAPH_PAGES, ["500", "1,000", "2,000", "5,000"])
    ax.set_xlim(200, 5800)
    ax.set_ylim(0, 38)
    ax.set_xlabel("Pages in the wiki")
    ax.set_ylabel("Seconds until the graph appears")
    ax.set_title("Knowledge graph: 34 s and a frozen tab, down to 6 s at 5,000 pages")
    ax.legend(loc="upper left")
    return _save(fig, "graph-load-time.png", out_dir)


def write_all(out_dir: Path = OUT_DIR, baseline_path: Path = corpus.DATA_DIR / "baseline.json") -> list[Path]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    return [chart_design(out_dir), chart_size(baseline, out_dir), chart_corpora(baseline, out_dir),
            chart_latency(baseline, out_dir), chart_graph(out_dir)]
