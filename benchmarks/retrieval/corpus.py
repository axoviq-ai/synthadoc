# Copyright (C) 2026 Peter W. / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Benchmark corpora: pinned Wikipedia articles and a HotpotQA subset.

Only the article list (titles + revision IDs) and the HotpotQA question IDs are
committed. Text is downloaded on demand into a local cache and converted into
Synthadoc wiki pages there, so the repo never carries the corpus itself.
Both sources are CC BY-SA (see NOTICE.md).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup, Tag

from synthadoc.agents.ingest_agent import _slugify
from synthadoc.storage.wiki import WikiStorage

DATA_DIR = Path(__file__).parent / "data"
ARTICLES_FILE = DATA_DIR / "articles.json"
HOTPOT_FILE = DATA_DIR / "hotpot.json"

CACHE_DIR = Path(os.environ.get("SYNTHADOC_BENCH_CACHE", Path.home() / ".cache" / "synthadoc-bench"))

USER_AGENT = "synthadoc-retrieval-benchmark/1.0 (https://github.com/axoviq-ai/synthadoc)"
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_REST_HTML = "https://en.wikipedia.org/api/rest_v1/page/html/{title}/{revid}"
_MAX_ATTEMPTS = 6
_HOTPOT_ROWS = "https://datasets-server.huggingface.co/rows"
_HOTPOT_DATASET = "hotpotqa/hotpot_qa"

# Overlapping domains, so that similar pages compete for the same queries —
# the situation where paraphrase queries miss under keyword search.
CATEGORIES = [
    "History of computing", "Computer science", "Programming languages",
    "Operating systems", "Computer architecture", "Cryptography",
    "Artificial intelligence", "Machine learning", "Natural language processing",
    "Computer vision", "Robotics", "Databases", "Computer networking",
    "Internet", "World Wide Web", "Software engineering", "Free software",
    "Video game development", "Semiconductors", "Personal computers",
    "Computer companies", "Computer scientists", "Mathematical logic",
    "Information theory", "Computer security",
]
TARGET_ARTICLES = 2000

# Keep pages close to the size of a compiled wiki page rather than a full
# Wikipedia article; the lead and the first sections carry the substance.
MAX_PAGE_WORDS = 1500

_SKIP_TITLE_RE = re.compile(r"^(List|Index|Outline|Timeline|Glossary|Comparison) of ", re.I)
_STOP_SECTIONS = {"see also", "references", "notes", "external links", "further reading",
                  "bibliography", "sources", "citations", "footnotes"}
_DISPLAYSTYLE_RE = re.compile(r"^\{\\displaystyle\s*(.*?)\s*\}$", re.S)
_CITATION_RE = re.compile(r"\[(?:\d+|[a-z]|citation needed|note \d+)\]")


@dataclass
class Article:
    title: str
    revid: int
    domain: str

    @property
    def slug(self) -> str:
        return _slugify(self.title)


# ---------------------------------------------------------------------------
# Wikipedia: selection (run once, result committed) and fetch (cached)
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)


def _get(client: httpx.Client, url: str, **params) -> httpx.Response:
    """GET with backoff on rate limiting and server errors, honouring Retry-After."""
    for attempt in range(_MAX_ATTEMPTS):
        resp = client.get(url, params=params or None)
        if resp.status_code != 429 and resp.status_code < 500:
            break
        retry_after = resp.headers.get("retry-after", "")
        time.sleep(int(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1))
    resp.raise_for_status()
    return resp


def _api(client: httpx.Client, **params) -> dict:
    return _get(client, _WIKI_API, format="json", formatversion=2, **params).json()


def select_articles(target: int = TARGET_ARTICLES) -> list[Article]:
    """Pick articles round-robin from CATEGORIES and pin their current revisions."""
    with _client() as client:
        members: dict[str, list[str]] = {}
        for cat in CATEGORIES:
            titles: list[str] = []
            params = {"action": "query", "list": "categorymembers", "cmtitle": f"Category:{cat}",
                      "cmnamespace": 0, "cmlimit": 500}
            while len(titles) < target:
                data = _api(client, **params)
                titles += [m["title"] for m in data["query"]["categorymembers"]
                           if not _SKIP_TITLE_RE.match(m["title"])]
                if "continue" not in data:
                    break
                params.update(data["continue"])
            members[cat] = titles

        chosen: dict[str, tuple[str, str]] = {}   # slug -> (title, domain)
        depth = 0
        while len(chosen) < target and any(depth < len(t) for t in members.values()):
            for cat, titles in members.items():
                if depth < len(titles) and len(chosen) < target:
                    title = titles[depth]
                    chosen.setdefault(_slugify(title), (title, cat))
            depth += 1

        pinned: dict[str, Article] = {}
        items = list(chosen.values())
        for i in range(0, len(items), 50):
            domains = dict(items[i:i + 50])
            data = _api(client, action="query", prop="revisions|pageprops", rvprop="ids",
                        titles="|".join(domains), redirects=1)
            query = data["query"]
            for hop in query.get("normalized", []) + query.get("redirects", []):
                domains.setdefault(hop["to"], domains.get(hop["from"], ""))
            for page in query["pages"]:
                if page.get("missing") or "disambiguation" in page.get("pageprops", {}):
                    continue
                article = Article(page["title"], page["revisions"][0]["revid"], domains[page["title"]])
                pinned.setdefault(article.slug, article)   # two titles may redirect to one page
    return sorted(pinned.values(), key=lambda a: a.title)


def save_articles(articles: list[Article], path: Path = ARTICLES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"title": a.title, "revid": a.revid, "domain": a.domain} for a in articles]
    lines = ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    path.write_text(f"[\n{lines}\n]\n", encoding="utf-8")   # one article per line


def load_articles(path: Path = ARTICLES_FILE) -> list[Article]:
    return [Article(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def _block_text(el: Tag) -> str:
    for junk in el.select("sup.reference, span.mw-editsection, style"):
        junk.decompose()
    for math in el.select(".mwe-math-element"):   # MathML + image fallback -> $LaTeX$
        annotation = math.find("annotation")
        tex = _DISPLAYSTYLE_RE.sub(r"\1", annotation.get_text().strip()) if annotation else ""
        math.replace_with(f"${tex}$" if tex else "")
    return " ".join(_CITATION_RE.sub("", el.get_text()).split())


def _blocks(node: Tag):
    """Top-level block elements in document order, descending into <section>
    (REST/Parsoid HTML nests each section; action=parse HTML is flat)."""
    for child in node.find_all(recursive=False):
        if child.name == "section":
            yield from _blocks(child)
        else:
            yield child


def html_to_markdown(html: str, max_words: int = MAX_PAGE_WORDS) -> str:
    """Convert a Wikipedia parse HTML body to plain wiki Markdown.

    Keeps headings, paragraphs and lists in order; drops tables, infoboxes,
    figures and navigation; stops at the first reference-type section or once
    *max_words* is reached (at a block boundary).
    """
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("div.mw-parser-output") or soup.body or soup
    lines: list[str] = []
    words = 0
    for el in _blocks(root):
        heading = el.find(re.compile("^h[2-4]$")) if "mw-heading" in (el.get("class") or []) else el
        if heading is not None and heading.name in ("h2", "h3", "h4"):
            text = _block_text(heading)
            if text.lower() in _STOP_SECTIONS:
                break
            lines += ["", "#" * int(heading.name[1]) + " " + text, ""]
            continue
        if el.name == "p":
            text = _block_text(el)
            block = [text] if text else []
        elif el.name in ("ul", "ol") and not (el.get("class") or []):
            block = [f"- {t}" for li in el.find_all("li", recursive=False) if (t := _block_text(li))]
        else:
            continue
        if not block:
            continue
        lines += block + [""]
        words += sum(len(b.split()) for b in block)
        if words >= max_words:
            break
    # Drop headings left without a body (e.g. the section after the cut-off).
    out: list[str] = []
    for line in lines:
        if line.startswith("#") and out and out[-1].startswith("#"):
            out.pop()
        if line or (out and out[-1]):
            out.append(line)
    while out and (not out[-1] or out[-1].startswith("#")):
        out.pop()
    return "\n".join(out).strip() + "\n"


def fetch_wikipedia(articles: list[Article], cache_dir: Path = CACHE_DIR, log=print) -> Path:
    """Download each pinned revision (cached per revid) and write a wiki page for it.

    Returns the wiki directory. Re-running only downloads missing revisions.
    """
    raw_dir = cache_dir / "wikipedia" / "html"
    wiki_dir = cache_dir / "wikipedia" / "wiki"
    raw_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    wiki_dir.mkdir(parents=True, exist_ok=True)
    with _client() as client:
        for i, article in enumerate(articles, 1):
            raw = raw_dir / f"{article.revid}.html"
            if not raw.exists():
                # The REST endpoint serves stored HTML for a revision and is far
                # less rate-limited than action=parse, which renders on demand.
                url = _WIKI_REST_HTML.format(title=quote(article.title.replace(" ", "_"), safe=""),
                                             revid=article.revid)
                raw.write_text(_get(client, url).text, encoding="utf-8")
            if i % 100 == 0:
                log(f"  {i}/{len(articles)} articles")
            write_bench_page(store, article.slug, article.title, [_slugify(article.domain)],
                             html_to_markdown(raw.read_text(encoding="utf-8")))
    return wiki_dir


def write_bench_page(store: WikiStorage, slug: str, title: str, tags: list[str], body: str) -> None:
    store.write_page(slug, f"# {title}\n\n{body}", frontmatter={
        "title": title, "tags": tags, "status": "active", "confidence": "high", "sources": [],
    })


# ---------------------------------------------------------------------------
# HotpotQA (distractor setting): human-written questions, two gold paragraphs
# ---------------------------------------------------------------------------

@dataclass
class HotpotQuestion:
    id: str
    question: str
    gold: list[str]          # slugs of the supporting paragraphs


def fetch_hotpot(count: int, cache_dir: Path = CACHE_DIR) -> list[dict]:
    """Download the first *count* validation rows (cached as JSON)."""
    cached = cache_dir / "hotpot" / "rows.json"
    if cached.exists():
        rows = json.loads(cached.read_text(encoding="utf-8"))
        if len(rows) >= count:
            return rows[:count]
    rows: list[dict] = []
    with _client() as client:
        for offset in range(0, count, 100):
            resp = client.get(_HOTPOT_ROWS, params={
                "dataset": _HOTPOT_DATASET, "config": "distractor", "split": "validation",
                "offset": offset, "length": min(100, count - offset)})
            resp.raise_for_status()
            rows += [r["row"] for r in resp.json()["rows"]]
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def build_hotpot(rows: list[dict], cache_dir: Path = CACHE_DIR) -> tuple[Path, list[HotpotQuestion]]:
    """Write every context paragraph as a page; questions point at their gold slugs."""
    wiki_dir = cache_dir / "hotpot" / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    written: set[str] = set()
    questions: list[HotpotQuestion] = []
    for row in rows:
        for title, sentences in zip(row["context"]["title"], row["context"]["sentences"]):
            slug = _slugify(title)
            if slug not in written:
                write_bench_page(store, slug, title, [], "".join(sentences).strip() + "\n")
                written.add(slug)
        gold = list(dict.fromkeys(_slugify(t) for t in row["supporting_facts"]["title"]))
        questions.append(HotpotQuestion(row["id"], row["question"], gold))
    return wiki_dir, questions
