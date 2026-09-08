# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
refresh_search_seeds.py — Populate each template's "Curated reference websites"
section by running its "Recommended web searches" queries through Tavily and
keeping the top accessible, non-blocked URLs as a stable snapshot.

Why a snapshot?
  Tavily results change over time.  This script pins the top results at
  release time so validate_seeds.py can verify them deterministically.
  Re-run to refresh the snapshot (e.g. before a new release).

Workflow
--------
1. Parse each seeds.md → extract non-placeholder "Recommended web searches" queries.
2. Run each query through Tavily (--max-per-query results each, default 3).
3. Filter out domains in _BLOCKED_DOMAINS (same list as the web_search skill).
4. Skip domains already covered by the "Recommended first ingests" section.
5. Deduplicate by domain (keep the first URL seen per domain).
6. Test remaining URLs with UrlSkill — same HTTP path as `synthadoc ingest`.
7. Write accessible URLs (up to --max-refs, default 6) to a
   "## Curated reference websites" section in each seeds.md (replaced on each run).

After running this script, run validate_seeds.py to confirm scope and accessibility.

Usage
-----
  python scripts/refresh_search_seeds.py                     # all templates
  python scripts/refresh_search_seeds.py --template real-estate/investment
  python scripts/refresh_search_seeds.py --dry-run           # print, don't write
  python scripts/refresh_search_seeds.py --max-per-query 2   # fewer Tavily results
  python scripts/refresh_search_seeds.py --max-refs 4        # fewer refs per template

Environment
-----------
  TAVILY_API_KEY   required (get a free key at https://tavily.com)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = REPO_ROOT / "synthadoc" / "templates"

_SYS_PATH_SET = False


def _ensure_path() -> None:
    global _SYS_PATH_SET
    if not _SYS_PATH_SET:
        sys.path.insert(0, str(REPO_ROOT))
        _SYS_PATH_SET = True


# ── Domain blocking ───────────────────────────────────────────────────────────

def _load_blocked_domains() -> set[str]:
    """Import the canonical blocked-domain set from the web_search skill."""
    _ensure_path()
    try:
        from synthadoc.skills.web_search.scripts.main import _BLOCKED_DOMAINS  # type: ignore
        return set(_BLOCKED_DOMAINS)
    except Exception:
        # Minimal fallback if the import fails
        return {
            "quora.com", "medium.com", "reddit.com", "facebook.com",
            "instagram.com", "twitter.com", "x.com", "linkedin.com",
            "tiktok.com", "wikipedia.org", "ieeexplore.ieee.org",
            "dl.acm.org", "sciencedirect.com", "springer.com", "jstor.org",
        }


def _netloc(url: str) -> str:
    """Return bare domain without leading www. prefix."""
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_blocked(url: str, blocked: set[str]) -> bool:
    d = _netloc(url)
    return any(d == b or d.endswith("." + b) for b in blocked)


# ── Seeds.md parsing ──────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"<[^>]+>")
_INGEST_URL_RE = re.compile(r'synthadoc\s+ingest\s+"(https?://[^"]+)"')
_QUERY_RE = re.compile(r"^- `([^`]+)`", re.MULTILINE)

_CURATED_HEADER = "## Curated reference websites"
_FIRST_INGESTS_HEADER = "## Recommended first ingests"
_WEB_SEARCHES_HEADER = "## Recommended web searches"
_CHECKLIST_HEADER = "## First steps checklist"


def _section_text(seeds_text: str, header: str) -> str:
    """Return the body of a ## section (empty string if the section is absent)."""
    m = re.search(
        re.escape(header) + r"\n(.*?)(?=\n## |\Z)",
        seeds_text,
        re.DOTALL,
    )
    return m.group(1) if m else ""


def extract_search_queries(seeds_text: str) -> list[str]:
    """Return non-placeholder queries from 'Recommended web searches'."""
    body = _section_text(seeds_text, _WEB_SEARCHES_HEADER)
    queries: list[str] = []
    for m in _QUERY_RE.finditer(body):
        q = m.group(1).strip()
        if not _PLACEHOLDER_RE.search(q):
            queries.append(q)
    return queries


def first_ingest_domains(seeds_text: str) -> set[str]:
    """Domains already present in the 'Recommended first ingests' section."""
    body = _section_text(seeds_text, _FIRST_INGESTS_HEADER)
    return {_netloc(m.group(1)) for m in _INGEST_URL_RE.finditer(body)}


def update_curated_section(seeds_text: str, urls: list[str], today: str) -> str:
    """Insert or replace the '## Curated reference websites' section.

    Placement: between 'Recommended web searches' and 'First steps checklist'.
    When ``urls`` is empty the section is removed entirely.
    """
    if urls:
        ingest_lines = "".join(
            f'synthadoc ingest "{u}" -w <wiki>\n' for u in urls
        )
        # Wrap in a fenced code block so markdown renderers preserve `<wiki>`
        # (without the fence, `<wiki>` is parsed as an invisible HTML tag).
        new_section = (
            f"{_CURATED_HEADER}\n\n"
            f"<!-- auto-generated by refresh_search_seeds.py on {today}"
            f" — re-run to update -->\n\n"
            f"```\n"
            f"{ingest_lines}"
            f"```\n\n"
        )
    else:
        new_section = ""  # remove section when no URLs are available

    if _CURATED_HEADER in seeds_text:
        # Replace: from header to (but not including) the next ## marker or EOF.
        start = seeds_text.index(_CURATED_HEADER)
        rest = seeds_text[start + len(_CURATED_HEADER):]
        next_sec = re.search(r"\n## ", rest)
        if next_sec:
            after = rest[next_sec.start() + 1:]   # drop leading \n; keep ## …
            return seeds_text[:start] + new_section + after
        else:
            return seeds_text[:start] + new_section
    elif new_section:
        # Insert before 'First steps checklist' or at end of file.
        if _CHECKLIST_HEADER in seeds_text:
            return seeds_text.replace(_CHECKLIST_HEADER, new_section + _CHECKLIST_HEADER, 1)
        return seeds_text.rstrip("\n") + "\n\n" + new_section
    return seeds_text  # nothing to add and section already absent


# ── URL accessibility test ────────────────────────────────────────────────────

async def _url_accessible(url: str, skill: object, sem: asyncio.Semaphore) -> bool:
    """Return True when UrlSkill can fetch non-empty text from *url*."""
    _ensure_path()
    from synthadoc.skills.base import DomainBlockedException  # type: ignore

    async with sem:
        try:
            result = await skill.extract(url)  # type: ignore[attr-defined]
            return bool(result.text.strip())
        except DomainBlockedException:
            return False
        except Exception:
            return False


# ── Per-template refresh ──────────────────────────────────────────────────────

async def refresh_template(
    template_dir: Path,
    *,
    tavily_key: str,
    max_per_query: int,
    max_refs: int,
    dry_run: bool,
    blocked: set[str],
    url_sem: asyncio.Semaphore,
    tav_sem: asyncio.Semaphore,
    skill: object,
) -> dict:
    """Refresh one template's curated section.  Returns a status dict."""
    seeds_path = template_dir / "wiki" / "seeds.md"
    if not seeds_path.exists():
        return {"template": str(template_dir.name), "status": "no-seeds"}

    seeds_text = seeds_path.read_text(encoding="utf-8")
    queries = extract_search_queries(seeds_text)
    if not queries:
        return {
            "template": template_dir.relative_to(TEMPLATES_DIR).as_posix(),
            "status": "no-queries",
        }

    existing_domains = first_ingest_domains(seeds_text)
    template_name = template_dir.relative_to(TEMPLATES_DIR).as_posix()

    _ensure_path()
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily  # type: ignore

    # ── Step 1: collect Tavily results ────────────────────────────────────────
    raw_urls: list[str] = []
    for query in queries:
        async with tav_sem:
            try:
                resp = await search_tavily(query, max_per_query, tavily_key)
                for result in resp.get("results", []):
                    url = result.get("url", "").strip()
                    if url:
                        raw_urls.append(url)
            except Exception as exc:
                print(f"  [{template_name}] Tavily error for {query!r}: {exc}", file=sys.stderr)

    # ── Step 2: filter and deduplicate ────────────────────────────────────────
    seen_domains: set[str] = set()
    candidates: list[str] = []
    for url in raw_urls:
        if _is_blocked(url, blocked):
            continue
        d = _netloc(url)
        if d in existing_domains or d in seen_domains:
            continue
        seen_domains.add(d)
        candidates.append(url)

    # ── Step 3: accessibility check ───────────────────────────────────────────
    checks = await asyncio.gather(*[
        _url_accessible(u, skill, url_sem) for u in candidates
    ])
    accessible = [u for u, ok in zip(candidates, checks) if ok][:max_refs]

    # ── Step 4: write section ─────────────────────────────────────────────────
    today = date.today().isoformat()
    updated = update_curated_section(seeds_text, accessible, today)

    if not dry_run:
        seeds_path.write_text(updated, encoding="utf-8")

    return {
        "template": template_name,
        "status": "updated",
        "queries_run": len(queries),
        "candidates": len(candidates),
        "urls_added": len(accessible),
        "urls": accessible,
        "dry_run": dry_run,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

async def async_main(args: argparse.Namespace) -> int:
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not tavily_key:
        print(
            "ERROR: TAVILY_API_KEY is not set.\n"
            "  Get a free key at https://tavily.com and add it to your environment:\n"
            "    export TAVILY_API_KEY=tvly-...",
            file=sys.stderr,
        )
        return 1

    _ensure_path()
    from synthadoc.skills.url.scripts.main import UrlSkill  # type: ignore

    blocked = _load_blocked_domains()

    if args.template:
        dirs = [TEMPLATES_DIR / args.template]
        if not dirs[0].exists():
            print(f"ERROR: template not found: {dirs[0]}", file=sys.stderr)
            return 1
    else:
        dirs = sorted({
            p.parent.parent  # …/<cat>/<name>/wiki/seeds.md → …/<cat>/<name>
            for p in TEMPLATES_DIR.glob("**/wiki/seeds.md")
        })

    skill = UrlSkill(fetch_timeout=15)
    url_sem = asyncio.Semaphore(4)  # concurrent URL accessibility checks
    tav_sem = asyncio.Semaphore(2)  # concurrent Tavily API calls

    mode = "[DRY RUN] " if args.dry_run else ""
    print(
        f"{mode}Refreshing {len(dirs)} template(s) "
        f"(Tavily max_per_query={args.max_per_query}, "
        f"max_refs={args.max_refs}) …"
    )

    results = await asyncio.gather(*[
        refresh_template(
            d,
            tavily_key=tavily_key,
            max_per_query=args.max_per_query,
            max_refs=args.max_refs,
            dry_run=args.dry_run,
            blocked=blocked,
            url_sem=url_sem,
            tav_sem=tav_sem,
            skill=skill,
        )
        for d in dirs
    ])

    total_added = 0
    for r in sorted(results, key=lambda x: x["template"]):
        if r["status"] == "updated":
            dr = " (dry-run)" if r.get("dry_run") else ""
            total_added += r["urls_added"]
            n = r["urls_added"]
            q = r["queries_run"]
            c = r["candidates"]
            print(f"  [{r['template']}] {n} URL(s) added{dr}  ({q} queries, {c} candidates)")
            for url in r["urls"]:
                print(f"    + {url}")
        elif r["status"] == "no-queries":
            print(f"  [{r['template']}] skipped — all queries have <placeholders>")
        # "no-seeds" templates skipped silently

    print(f"\n{'='*60}")
    print(f"Done: {total_added} URL(s) written across {len(dirs)} template(s).")
    if not args.dry_run:
        print("Next step: run  python scripts/validate_seeds.py  to verify scope + accessibility.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Populate each template's 'Curated reference websites' section "
            "by running its web-search queries through Tavily."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment:\n"
            "  TAVILY_API_KEY   required (https://tavily.com)\n\n"
            "Examples:\n"
            "  python scripts/refresh_search_seeds.py\n"
            "  python scripts/refresh_search_seeds.py --template real-estate/investment\n"
            "  python scripts/refresh_search_seeds.py --dry-run\n"
        ),
    )
    parser.add_argument(
        "--template", metavar="CATEGORY/NAME",
        help="Refresh only this template (e.g. real-estate/investment).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without modifying any file.",
    )
    parser.add_argument(
        "--max-per-query", type=int, default=3, metavar="N",
        help="Tavily results per search query (default: 3).",
    )
    parser.add_argument(
        "--max-refs", type=int, default=6, metavar="N",
        help="Max total reference URLs written per template (default: 6).",
    )
    sys.exit(asyncio.run(async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
