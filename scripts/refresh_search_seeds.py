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
  python scripts/refresh_search_seeds.py --fix-first-ingests # also repair blocked first-ingest URLs
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
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from _url_quality import BOT_BLOCK_RE as _BOT_BLOCK_RE
from _url_quality import MIN_CONTENT_CHARS as _MIN_CONTENT_CHARS

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

_LABEL_RE = re.compile(r'^\*\*(.+?)\*\*\s*\n', re.MULTILINE)


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


def extract_curated_urls(seeds_text: str) -> list[str]:
    """Return existing ingest URLs from the 'Curated reference websites' section."""
    body = _section_text(seeds_text, _CURATED_HEADER)
    return [m.group(1) for m in _INGEST_URL_RE.finditer(body)]


def extract_first_ingests(seeds_text: str) -> list[tuple[str, str]]:
    """Return (label, url) pairs for every URL entry in 'Recommended first ingests'.

    Skips entries backed by local file paths (no http scheme).
    Each bold **label** is matched to the first ingest URL that follows it
    within the section body.
    """
    body = _section_text(seeds_text, _FIRST_INGESTS_HEADER)
    pairs: list[tuple[str, str]] = []
    for label_m in _LABEL_RE.finditer(body):
        label = label_m.group(1).strip()
        rest = body[label_m.end():]
        url_m = _INGEST_URL_RE.search(rest)
        if url_m:
            pairs.append((label, url_m.group(1)))
    return pairs


def _label_to_query(label: str) -> str:
    """Return a Tavily search query from a bold label.

    Strips trailing annotation tokens like (public), (free), (open access).
    E.g. "Nareit — REITs and listed real estate companies (public)"
      -> "Nareit — REITs and listed real estate companies"
    """
    return re.sub(r'\s*\([^)]*\)\s*$', '', label).strip()


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

async def _url_accessible(url: str, skill: object, sem: asyncio.Semaphore) -> tuple[bool, str]:
    """Return (accessible, content) where accessible is True only when UrlSkill
    fetches at least _MIN_CONTENT_CHARS of substantive text from *url*.

    Challenge pages (e.g. Cloudflare JS challenges), paywall stubs, and other
    thin responses are treated as inaccessible even when HTTP returns 200.
    """
    _ensure_path()
    from synthadoc.skills.base import DomainBlockedException  # type: ignore

    async with sem:
        try:
            result = await skill.extract(url)  # type: ignore[attr-defined]
            text = result.text.strip()
            if _BOT_BLOCK_RE.search(text[:1_000]):
                return False, ""
            return len(text) >= _MIN_CONTENT_CHARS, text
        except DomainBlockedException:
            return False, ""
        except Exception:
            return False, ""


# ── Scope check (mirrors validate_seeds.py) ───────────────────────────────────

_SCOPE_PROMPT = """\
You maintain a knowledge wiki. Decide whether a new source document is in scope.

Wiki scope (from purpose.md):
{purpose}

action="skip" means the source is completely OUTSIDE the wiki's domain \
(e.g. spam, unrelated e-commerce, generic listicles with no domain-specific value).
A broad general resource that adds no domain-specific value should be action="skip".
A source clearly authored for practitioners in this specific domain should be \
action="ingest".

Source text (first 4 000 characters):
{content}

Return ONLY valid JSON (no markdown fences):
{{"action": "ingest or skip", "reasoning": "one concise sentence"}}"""

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _extract_scope_json(raw: str) -> dict:
    clean = _ANSI_RE.sub("", raw)
    clean = re.sub(r"^```[a-z]*\s*|\s*```$", "", clean, flags=re.MULTILINE)
    matches = list(re.finditer(r"\{[^{}]+\}", clean, re.DOTALL))
    if not matches:
        raise ValueError(f"no JSON object in output: {clean[:200]!r}")
    return json.loads(matches[-1].group())


class _Backend:
    def __init__(self, label: str, client=None, cli_cmd: list = None, model: str = "") -> None:
        self.label = label
        self._client = client
        self._cli_cmd: list = cli_cmd or []
        self._model = model

    async def complete(self, prompt: str) -> str:
        if self._client is not None:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.content[0].text if resp.content else "").strip()
        cmd = [*self._cli_cmd, prompt]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"{self._cli_cmd[0]} timed out")
        return stdout.decode(errors="replace").strip()


def _detect_backend(
    model: str = "claude-haiku-4-5-20251001",
    prefer: str = "auto",
) -> "_Backend | None":
    if prefer == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                import anthropic
                return _Backend(label="anthropic-sdk",
                                client=anthropic.AsyncAnthropic(api_key=api_key),
                                model=model)
            except ImportError:
                pass
        return None
    if prefer == "opencode":
        if shutil.which("opencode"):
            return _Backend(label="opencode", cli_cmd=["opencode", "run"])
        return None
    if prefer == "claude":
        if shutil.which("claude"):
            return _Backend(label="claude", cli_cmd=["claude", "-p"])
        return None
    # auto: anthropic-sdk → opencode → claude
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            import anthropic
            return _Backend(label="anthropic-sdk",
                            client=anthropic.AsyncAnthropic(api_key=api_key),
                            model=model)
        except ImportError:
            pass
    for binary, cli_cmd in [("opencode", ["opencode", "run"]), ("claude", ["claude", "-p"])]:
        if shutil.which(binary):
            return _Backend(label=binary, cli_cmd=cli_cmd)
    return None


async def _in_scope(content: str, purpose: str, backend: "_Backend", sem: asyncio.Semaphore) -> bool:
    """Return True when the LLM judges *content* as in scope for *purpose*."""
    prompt = _SCOPE_PROMPT.format(purpose=purpose.strip()[:4_000], content=content[:4_000])
    async with sem:
        try:
            raw = await backend.complete(prompt)
            data = _extract_scope_json(raw)
            return str(data.get("action", "ingest")).strip().lower() != "skip"
        except Exception:
            return True  # treat errors as pass to avoid false negatives


# ── First-ingest replacement search ──────────────────────────────────────────

async def _find_replacement_url(
    query: str,
    blocked: set[str],
    skip_domains: set[str],
    skill: object,
    url_sem: asyncio.Semaphore,
    tav_sem: asyncio.Semaphore,
    tavily_key: str,
    max_per_query: int,
    *,
    purpose: str = "",
    backend: "_Backend | None" = None,
    llm_sem: "asyncio.Semaphore | None" = None,
    template_name: str = "",
) -> str | None:
    """Search Tavily for *query* and return the first accessible, in-scope URL.

    *skip_domains* prevents re-using the same domain that just failed.
    When *purpose* and *backend* are provided, candidates are also checked
    against the wiki scope before being accepted.

    Retries with 3× max_per_query when the initial result set is exhausted
    without finding an acceptable replacement, then with 6× as a final
    attempt, logging each scope rejection to stderr.
    Returns None when no working replacement is found.
    """
    _ensure_path()
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily  # type: ignore

    seen: set[str] = set()

    for attempt, n in enumerate([max_per_query, max_per_query * 3, max_per_query * 6]):
        async with tav_sem:
            try:
                resp = await search_tavily(query, n, tavily_key)
            except Exception:
                return None

        for result in resp.get("results", []):
            url = result.get("url", "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            if _is_blocked(url, blocked):
                continue
            if _netloc(url) in skip_domains:
                continue
            ok, content = await _url_accessible(url, skill, url_sem)
            if not ok:
                continue
            if purpose and backend and llm_sem:
                if not await _in_scope(content, purpose, backend, llm_sem):
                    label = f"[{template_name}] " if template_name else ""
                    print(
                        f"  {label}first-ingest candidate scope-rejected: {url}",
                        file=sys.stderr,
                    )
                    continue
            return url

        if attempt == 0:
            label = f"[{template_name}] " if template_name else ""
            print(
                f"  {label}first-ingest: initial {n} results exhausted, retrying with more …",
                file=sys.stderr,
            )

    return None


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
    llm_sem: asyncio.Semaphore,
    skill: object,
    backend: "_Backend | None",
) -> dict:
    """Refresh one template's curated section.  Returns a status dict."""
    seeds_path = template_dir / "seeds.md"
    if not seeds_path.exists():
        return {"template": str(template_dir.name), "status": "no-seeds"}

    seeds_text = seeds_path.read_text(encoding="utf-8")
    template_name = template_dir.relative_to(TEMPLATES_DIR).as_posix()

    # Read purpose.md so scope checks mirror what the ingest agent enforces.
    purpose_path = template_dir / "wiki" / "purpose.md"
    purpose = purpose_path.read_text(encoding="utf-8") if purpose_path.exists() else ""

    # ── Step 0: repair blocked/broken/out-of-scope first-ingest URLs ─────────
    repairs: dict[str, str] = {}   # {old_url: new_url}
    no_replacement: list[str] = []
    for label, url in extract_first_ingests(seeds_text):
        ok, content = await _url_accessible(url, skill, url_sem)
        if ok:
            # Accessible — also verify it is in scope when we have a backend.
            if purpose and backend:
                if await _in_scope(content, purpose, backend, llm_sem):
                    continue  # accessible and in scope — nothing to do
                # Accessible but out of scope — treat as needing replacement.
                print(
                    f"  [{template_name}] first-ingest out-of-scope, replacing: {url}",
                    file=sys.stderr,
                )
            else:
                continue  # no backend available — skip scope check
        query = _label_to_query(label)
        replacement = await _find_replacement_url(
            query, blocked,
            skip_domains={_netloc(url)},
            skill=skill, url_sem=url_sem, tav_sem=tav_sem,
            tavily_key=tavily_key, max_per_query=max_per_query,
            purpose=purpose, backend=backend, llm_sem=llm_sem,
            template_name=template_name,
        )
        if replacement:
            repairs[url] = replacement
        else:
            no_replacement.append(url)
            print(
                f"  [{template_name}] WARNING: no replacement found for {url}",
                file=sys.stderr,
            )
    for old, new in repairs.items():
        seeds_text = seeds_text.replace(f'"{old}"', f'"{new}"')

    queries = extract_search_queries(seeds_text)
    existing_domains = first_ingest_domains(seeds_text)

    _ensure_path()
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily  # type: ignore

    # ── Step 1: validate existing curated URLs (concurrent) ───────────────────
    # Only query Tavily for the slots that are missing or broken/out-of-scope.
    existing_curated = extract_curated_urls(seeds_text)

    async def _check_existing(url: str) -> "str | None":
        ok, content = await _url_accessible(url, skill, url_sem)
        if not ok:
            print(f"  [{template_name}] curated dropped (inaccessible): {url}", file=sys.stderr)
            return None
        if purpose and backend:
            if not await _in_scope(content, purpose, backend, llm_sem):
                print(f"  [{template_name}] curated dropped (out-of-scope): {url}", file=sys.stderr)
                return None
        return url

    checked = await asyncio.gather(*[_check_existing(u) for u in existing_curated])
    valid_existing = [u for u in checked if u is not None]
    valid_existing_domains = {_netloc(u) for u in valid_existing}

    needed = max_refs - len(valid_existing)

    if needed <= 0:
        # Existing curated URLs fill all slots.
        accessible = valid_existing[:max_refs]
        if accessible == existing_curated:
            # Nothing changed — skip the write entirely.
            return {
                "template": template_name,
                "status": "ok-no-change",
                "repairs": repairs,
                "no_replacement": no_replacement,
            }
        # Some URLs were dropped — rewrite without Tavily.
        today = date.today().isoformat()
        if not dry_run:
            seeds_path.write_text(
                update_curated_section(seeds_text, accessible, today), encoding="utf-8"
            )
        return {
            "template": template_name,
            "status": "updated",
            "queries_run": 0,
            "candidates": len(existing_curated),
            "urls_added": len(accessible),
            "urls": accessible,
            "repairs": repairs,
            "no_replacement": no_replacement,
            "dry_run": dry_run,
        }

    # Some slots are empty or broken — fill via Tavily.
    if not queries:
        return {
            "template": template_name,
            "status": "no-queries",
            "repairs": repairs,
            "no_replacement": no_replacement,
        }

    skip_domains = existing_domains | valid_existing_domains
    if valid_existing:
        print(
            f"  [{template_name}] {len(valid_existing)}/{len(existing_curated)} curated valid,"
            f" querying Tavily for {needed} more …",
            file=sys.stderr,
        )

    # ── Step 2: collect Tavily results ────────────────────────────────────────
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

    # ── Step 3: filter and deduplicate ────────────────────────────────────────
    seen_domains: set[str] = set()
    candidates: list[str] = []
    for url in raw_urls:
        if _is_blocked(url, blocked):
            continue
        d = _netloc(url)
        if d in skip_domains or d in seen_domains:
            continue
        seen_domains.add(d)
        candidates.append(url)

    # ── Step 4: accessibility + scope check (sequential, with retry) ──────────
    found: list[str] = []
    seen_all: set[str] = set(candidates)

    async def _try_candidate(url: str) -> bool:
        ok, content = await _url_accessible(url, skill, url_sem)
        if not ok:
            return False
        if purpose and backend:
            if not await _in_scope(content, purpose, backend, llm_sem):
                print(f"  [{template_name}] scope-rejected: {url}", file=sys.stderr)
                return False
        return True

    for url in candidates:
        if len(found) >= needed:
            break
        if await _try_candidate(url):
            found.append(url)

    # Retry with larger result set if still short.
    if len(found) < needed:
        retry_per_query = max_per_query * 3
        for query in queries:
            if len(found) >= needed:
                break
            async with tav_sem:
                try:
                    resp = await search_tavily(query, retry_per_query, tavily_key)
                except Exception as exc:
                    print(
                        f"  [{template_name}] Tavily retry error for {query!r}: {exc}",
                        file=sys.stderr,
                    )
                    continue
            for result in resp.get("results", []):
                if len(found) >= needed:
                    break
                url = result.get("url", "").strip()
                if not url or url in seen_all:
                    continue
                if _is_blocked(url, blocked):
                    continue
                d = _netloc(url)
                if d in skip_domains or d in {_netloc(u) for u in found}:
                    continue
                seen_all.add(url)
                if await _try_candidate(url):
                    found.append(url)

    accessible = valid_existing + found

    # ── Step 5: write section ─────────────────────────────────────────────────
    today = date.today().isoformat()
    if not dry_run:
        seeds_path.write_text(
            update_curated_section(seeds_text, accessible, today), encoding="utf-8"
        )

    return {
        "template": template_name,
        "status": "updated",
        "queries_run": len(queries),
        "candidates": len(candidates),
        "urls_added": len(found),
        "urls": accessible,
        "repairs": repairs,
        "no_replacement": no_replacement,
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
            p.parent         # …/<cat>/<name>/seeds.md → …/<cat>/<name>
            for p in TEMPLATES_DIR.glob("*/*/seeds.md")
        })

    skill = UrlSkill(fetch_timeout=15)
    url_sem = asyncio.Semaphore(4)  # concurrent URL accessibility checks
    tav_sem = asyncio.Semaphore(2)  # concurrent Tavily API calls
    llm_sem = asyncio.Semaphore(2)  # concurrent LLM scope checks

    backend = _detect_backend(model=args.model, prefer=args.backend)
    scope_note = f", scope via {backend.label}" if backend else ", scope check skipped (no LLM backend)"

    mode = "[DRY RUN] " if args.dry_run else ""
    lm_label = backend.label if backend else "none"
    print(
        f"{mode}Refreshing {len(dirs)} template(s) "
        f"(Tavily: configured, "
        f"LLM backend: {lm_label}, "
        f"max_per_query={args.max_per_query}, "
        f"max_refs={args.max_refs}) …"
    )
    if not backend:
        print(
            "ERROR: no LLM backend available — scope checks will be SKIPPED.\n"
            "  Without scope checks, Tavily can return off-domain URLs that look\n"
            "  accessible but are completely wrong (e.g. a city zoning board for a\n"
            "  banking wiki because both abbreviate to 'BSA').\n"
            "  Fix one of:\n"
            "    • set ANTHROPIC_API_KEY in your environment\n"
            "    • install opencode  (opencode run is used)\n"
            "    • install claude    (Claude Code, claude -p is used)\n"
            "  Then re-run this script so curated URLs are scope-validated before\n"
            "  being written to seeds.md.",
            file=sys.stderr,
        )
        return 1

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
            llm_sem=llm_sem,
            skill=skill,
            backend=backend,
        )
        for d in dirs
    ])

    total_added = 0
    total_repaired = 0
    total_unresolved = 0
    for r in sorted(results, key=lambda x: x["template"]):
        repairs = r.get("repairs", {})
        no_rep = r.get("no_replacement", [])
        total_repaired += len(repairs)
        total_unresolved += len(no_rep)

        if r["status"] == "updated":
            dr = " (dry-run)" if r.get("dry_run") else ""
            total_added += r["urls_added"]
            n = r["urls_added"]
            q = r["queries_run"]
            c = r["candidates"]
            tav_note = f", {q} queries, {c} candidates" if q else ", no Tavily (trimmed stale)"
            print(f"  [{r['template']}] {n} URL(s) written{dr}  ({tav_note})")
            for url in r["urls"]:
                print(f"    + {url}")
        elif r["status"] == "ok-no-change":
            pass  # all URLs still valid — nothing to report
        elif r["status"] == "no-queries":
            print(f"  [{r['template']}] skipped — all queries have <placeholders>")
        # "no-seeds" templates skipped silently

        for old, new in repairs.items():
            dr = " (dry-run)" if r.get("dry_run") else ""
            print(f"  [{r['template']}] first-ingest repaired{dr}:")
            print(f"    - {old}")
            print(f"    + {new}")
        for url in no_rep:
            print(f"  [{r['template']}] first-ingest UNRESOLVED (update manually): {url}")

    total_skipped = sum(1 for r in results if r["status"] == "ok-no-change")
    print(f"\n{'='*60}")
    print(f"Done: {total_added} curated URL(s) written, {total_repaired} first-ingest(s) repaired"
          + (f", {total_unresolved} unresolved" if total_unresolved else "")
          + (f", {total_skipped} template(s) skipped (all URLs still valid)" if total_skipped else "")
          + f" across {len(dirs)} template(s).")
    if not args.dry_run:
        print("Next step: run  python scripts/validate_seeds.py  to verify scope + accessibility.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Populate each template's 'Curated reference websites' section "
            "by running its web-search queries through Tavily. "
            "Also checks 'Recommended first ingests' URLs and replaces any "
            "that are blocked, unavailable, or out of scope."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment:\n"
            "  TAVILY_API_KEY   required (https://tavily.com)\n\n"
            "Examples:\n"
            "  python scripts/refresh_search_seeds.py\n"
            "  python scripts/refresh_search_seeds.py --template real-estate/investment\n"
            "  python scripts/refresh_search_seeds.py --backend claude\n"
            "  python scripts/refresh_search_seeds.py --dry-run\n"
        ),
    )
    parser.add_argument(
        "--template", metavar="CATEGORY/NAME",
        help="Refresh only this template (e.g. real-estate/investment).",
    )
    parser.add_argument(
        "--backend", metavar="NAME", default="auto",
        choices=["auto", "anthropic", "opencode", "claude"],
        help="LLM backend for scope checks: auto (default), anthropic, opencode, claude.",
    )
    parser.add_argument(
        "--model", metavar="MODEL_ID", default="claude-haiku-4-5-20251001",
        help="Model ID passed to the anthropic backend (default: claude-haiku-4-5-20251001).",
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
