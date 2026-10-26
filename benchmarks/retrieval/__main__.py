# Copyright (C) 2026 Peter W. / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Retrieval benchmark CLI — see benchmarks/retrieval/README.md.

    python -m benchmarks.retrieval fetch                 # download + build cached wikis
    python -m benchmarks.retrieval evaluate              # score configs, print tables
    python -m benchmarks.retrieval evaluate --write-baseline
    python -m benchmarks.retrieval generate --provider anthropic --model claude-sonnet-5-5
    python -m benchmarks.retrieval select                # maintainers: re-pin the article list
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime
import json
import subprocess
import sys
from pathlib import Path

from benchmarks.retrieval import corpus, evaluate, queries

BASELINE_FILE = corpus.DATA_DIR / "baseline.json"
HOTPOT_QUESTIONS = 300


def _hotpot(cache: Path) -> tuple[Path, list[queries.Query]]:
    """Build the HotpotQA wiki, checking the rows match the committed question IDs."""
    rows = corpus.fetch_hotpot(HOTPOT_QUESTIONS, cache)
    ids = [r["id"] for r in rows]
    if corpus.HOTPOT_FILE.exists():
        pinned = json.loads(corpus.HOTPOT_FILE.read_text(encoding="utf-8"))["ids"]
        if ids != pinned:
            sys.exit("HotpotQA rows differ from data/hotpot.json — the upstream dataset changed.")
    else:
        corpus.HOTPOT_FILE.write_text(json.dumps({"dataset": "hotpotqa/hotpot_qa", "config": "distractor",
                                                  "split": "validation", "ids": ids}, indent=0) + "\n")
    wiki_dir, questions = corpus.build_hotpot(rows, cache)
    return wiki_dir, [queries.Query(q.id, "human", q.question, q.gold) for q in questions]


def cmd_select(args) -> None:
    articles = corpus.select_articles(args.target)
    corpus.save_articles(articles)
    print(f"Pinned {len(articles)} articles in {corpus.ARTICLES_FILE}")


def cmd_fetch(args) -> None:
    print("Wikipedia:")
    wiki_dir = corpus.fetch_wikipedia(corpus.load_articles(), args.cache)
    print(f"  → {wiki_dir}")
    print("HotpotQA:")
    print(f"  → {_hotpot(args.cache)[0]}")


def cmd_generate(args) -> None:
    from synthadoc.config import AgentConfig, load_config
    from synthadoc.errors import ConfigError, MissingApiKeyError, ProviderConfigurationError
    from synthadoc.providers import make_provider

    cfg = load_config()
    cfg = dataclasses.replace(cfg, agents=dataclasses.replace(
        cfg.agents, default=AgentConfig(provider=args.provider, model=args.model)))
    try:
        provider = make_provider("query", cfg)
    except (ConfigError, MissingApiKeyError, ProviderConfigurationError) as exc:
        sys.exit(str(exc))
    wiki_dir = args.cache / "wikipedia" / "wiki"
    types = tuple(args.types.split(","))
    if unknown := set(types) - set(queries.QUERY_TYPES):
        sys.exit(f"Unknown query type(s): {', '.join(sorted(unknown))}")
    generated = asyncio.run(queries.generate(provider, wiki_dir, types=types,
                                             concurrency=args.concurrency))
    by_type = {t: sum(q.type == t for q in generated) for t in queries.QUERY_TYPES}
    print(f"{len(generated)} queries in {queries.QUERIES_FILE}: {by_type}")


def cmd_evaluate(args) -> None:
    configs = args.configs.split(",")
    if any(evaluate.CONFIGS[c].search_cfg.vector for c in configs) and not evaluate.has_fastembed():
        sys.exit('Embedding configs need fastembed: pip install "synthadoc[vectors]"')
    results: dict = {}
    if "wikipedia" in args.corpora:
        print("Wikipedia:")
        results["wikipedia"] = asyncio.run(evaluate.evaluate_corpus(
            args.cache / "wikipedia" / "wiki", queries.load_queries(), configs, evaluate.WIKI_SIZES))
    if "hotpot" in args.corpora:
        print("HotpotQA:")
        wiki_dir, hotpot_queries = _hotpot(args.cache)
        results["hotpot"] = asyncio.run(evaluate.evaluate_corpus(wiki_dir, hotpot_queries, configs, None))
    for name, res in results.items():
        print("\n" + evaluate.format_table(name, res))
    if args.write_baseline:
        write_baseline(results)
        print(f"\nUpdated {BASELINE_FILE}")


def write_baseline(results: dict, path: Path = BASELINE_FILE) -> None:
    """Merge *results* into the baseline, replacing only the corpus/config pairs just run."""
    baseline = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"results": {}}
    for corpus_name, by_config in results.items():
        baseline["results"].setdefault(corpus_name, {}).update(by_config)
    baseline["generated"] = datetime.date.today().isoformat()
    baseline["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                        capture_output=True, text=True).stdout.strip()
    path.write_text(json.dumps(baseline, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.retrieval")
    parser.add_argument("--cache", type=Path, default=corpus.CACHE_DIR,
                        help="download/cache directory (env SYNTHADOC_BENCH_CACHE)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("select", help="re-pin the Wikipedia article list (maintainers)")
    p.add_argument("--target", type=int, default=corpus.TARGET_ARTICLES)
    p.set_defaults(func=cmd_select)

    sub.add_parser("fetch", help="download pinned sources and build the cached wikis").set_defaults(func=cmd_fetch)

    p = sub.add_parser("generate", help="generate data/queries.jsonl with an LLM (maintainers)")
    p.add_argument("--provider", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--types", default=",".join(queries.QUERY_TYPES),
                   help="comma list of query types to fill in (default: all)")
    p.add_argument("--concurrency", type=int, default=4)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("evaluate", help="score search configurations")
    p.add_argument("--configs", default="bm25", help=f"comma list of {', '.join(evaluate.CONFIGS)}")
    p.add_argument("--corpora", default="wikipedia,hotpot")
    p.add_argument("--write-baseline", action="store_true", help=f"write {BASELINE_FILE.name}")
    p.set_defaults(func=cmd_evaluate)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
