# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import hashlib
import json as _json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import networkx as nx
try:
    import community as community_louvain  # python-louvain
    _LOUVAIN_AVAILABLE = True
except ImportError:
    _LOUVAIN_AVAILABLE = False

from synthadoc.agents.citations import CITATION_RE as _CITATION_BODY_RE
from synthadoc.agents.citations import MALFORMED_CITE_RE as _MALFORMED_CITE_RE
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.wiki import WikiStorage, LifecycleState, is_url, TriggerSource

import logging as _logging

if TYPE_CHECKING:
    from synthadoc.config import Config
    from synthadoc.storage.wiki import WikiPage

_log = _logging.getLogger(__name__)


@dataclass
class LintReport:
    contradictions_found: int = 0
    contradictions_resolved: int = 0
    contradictions_unresolved: list[dict] = field(default_factory=list)  # [{slug, reason}]
    orphan_slugs: list[str] = field(default_factory=list)
    dangling_links_removed: int = 0
    tokens_used: int = 0
    adversarial_warnings: list[dict] = field(default_factory=list)
    citation_issues: list[dict] = field(default_factory=list)
    lifecycle_promoted: int = 0
    lifecycle_stale: int = 0
    lifecycle_archived: int = 0
    lifecycle_synced: int = 0
    warnings: list[str] = field(default_factory=list)


_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

_CITATION_MIN_WORDS = 50  # skip presence check on stub pages shorter than this

# Auto-generated / directory pages whose outbound links must NOT count as real
# references.  A page linked only from index/overview/dashboard is still an
# orphan in the content graph — it is not integrated into the knowledge network.
LINT_SKIP_SOURCE_SLUGS: frozenset[str] = frozenset(
    {"index", "overview", "log", "dashboard"}
)

# Pages never reported as orphans (root / auto-generated pages).
LINT_SKIP_SLUGS: frozenset[str] = frozenset(
    {"index", "log", "dashboard", "purpose", "overview"}
)


# Matches a list item whose first significant content is a single wikilink,
# e.g. "- [[some-slug]] — description" or "* [[slug]]"
_LIST_LINK_RE = re.compile(r"^\s*[-*+]\s+\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Extracts the 11-char video ID from any canonical YouTube URL form.
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|live/|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

# Same character set allowed in sidecar filenames as _url_sidecar_name in ingest_agent.py.
_URL_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9.\-]+")


def _url_name_normalize(raw: str) -> str:
    """Apply the same character filter as _url_sidecar_name in ingest_agent.py."""
    return _URL_NAME_SAFE_RE.sub("-", raw).strip("-") or "url-source"


def _citation_source_names(file: str) -> set[str]:
    """Return all citation names a source may use, for backward-compatible lint checking.

    Ingest agent now uses the last two URL path segments for collision resistance
    (e.g. biography-dennis-ritchie instead of dennis-ritchie), but older pages
    were ingested with just the last segment.  Including both forms in the set
    ensures existing pages don't suddenly show broken_ref after the naming fix.
    For local files, return {Path(file).name}.
    YouTube URLs are a special case: the ingest agent renames the sidecar to
    "youtube-{video_id}" via suggested_slug, so SourceRef.file (the raw URL)
    must map to that same slug here.
    For all URL-based sources, names are normalized through _url_name_normalize
    to match the transformation applied by _url_sidecar_name (e.g. underscores
    in Wikipedia-style paths become hyphens).
    """
    if "://" not in file:
        return {Path(file).name}
    yt = _YOUTUBE_ID_RE.search(file)
    if yt:
        slug = re.sub(r"[^a-z0-9]+", "-", f"youtube-{yt.group(1)}".lower()).strip("-")
        return {slug}
    bare = file.split("?")[0].rstrip("/")
    parts = [seg for seg in bare.split("/") if seg]
    segments = parts[2:] if len(parts) > 2 else parts[1:] if len(parts) > 1 else parts
    names: set[str] = set()
    if segments:
        names.add(_url_name_normalize(segments[-1]))                              # old 1-segment form
        if len(segments) >= 2:
            names.add(_url_name_normalize(f"{segments[-2]}-{segments[-1]}"))     # new 2-segment form
    return names or {"url-source"}


def _check_page_citations(
    slug: str, page: WikiPage, extracted_dir: Path
) -> list[dict]:
    """Return list of {slug, citation, reason} for each invalid citation in page body.

    Three failure reasons:
    - malformed: ^[...] marker missing L-L range, or line_start > line_end, or line_start < 1
    - broken_ref: filename not listed in page.sources[]
    - out_of_range: line_end exceeds actual line count of the extracted .txt file
    """
    source_basenames: set[str] = set()
    for s in (page.sources or []):
        source_basenames.update(_citation_source_names(s.file))
    issues: list[dict] = []
    seen_citations: set[str] = set()

    for m in _CITATION_BODY_RE.finditer(page.content or ""):
        filename, raw_start, raw_end = m.group(1), m.group(2), m.group(3)
        line_start, line_end = int(raw_start), int(raw_end)
        citation = m.group(0)
        seen_citations.add(citation)

        if line_start > line_end or line_start < 1:
            issues.append({"slug": slug, "citation": citation, "reason": "malformed"})
            continue

        if filename not in source_basenames:
            issues.append({"slug": slug, "citation": citation, "reason": "broken_ref"})
            continue

        # Check line range against extracted .txt. Sidecars are always written as
        # <stem>.txt (ingest strips the original extension and appends .txt), so
        # try the citation filename directly first, then fall back to stem + ".txt".
        txt_path = Path(extracted_dir) / filename
        if not txt_path.exists():
            txt_path = Path(extracted_dir) / (Path(filename).stem + ".txt")
        if txt_path.exists():
            try:
                line_count = txt_path.read_text(encoding="utf-8").count("\n") + 1
                if line_end > line_count:
                    issues.append({"slug": slug, "citation": citation, "reason": "out_of_range"})
            except OSError:
                pass

    # Catch malformed ^[...] without a valid L-L pattern (not matched by _CITATION_BODY_RE)
    for m in _MALFORMED_CITE_RE.finditer(page.content or ""):
        citation = m.group(0)
        if citation not in seen_citations:
            issues.append({"slug": slug, "citation": citation, "reason": "malformed"})

    return issues


def _has_citations(page: "WikiPage") -> bool:
    """Return True if the page body contains at least one ^[filename:L-L] marker."""
    return bool(_CITATION_BODY_RE.search(page.content or ""))


def _fix_dangling_wikilinks(content: str, existing_slugs: set[str]) -> str:
    """Remove or unlink [[slug]] references whose target page no longer exists.

    List items whose entire content is a dangling link are dropped.
    Inline dangling links are replaced with just their display text.
    """
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n\r")
        m = _LIST_LINK_RE.match(stripped)
        if m:
            slug_part = m.group(1).strip().lower().replace(" ", "-")
            if slug_part not in existing_slugs:
                continue  # drop the whole list-item line

        def _unlink(match: re.Match) -> str:
            inner = match.group(1)
            parts = inner.split("|", 1)
            slug_key = parts[0].strip().lower().replace(" ", "-")
            display = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            return display if slug_key not in existing_slugs else match.group(0)

        line = _WIKILINK_RE.sub(_unlink, line)
        result.append(line)
    return "".join(result)


async def cascade_archive(
    archived_slug: str,
    store: "WikiStorage",
    audit_db: Optional["AuditDB"] = None,
    trigger_source: str = TriggerSource.USER,
) -> list[str]:
    """Remove [[archived_slug]] wikilinks from all other active pages immediately.

    Called after any archive transition so dead links don't accumulate between
    lint runs.  Writes a lifecycle_events audit record for each rewritten page.
    Returns list of slugs whose content changed.
    """
    slugs = store.all_slugs()
    # Exclude the just-archived slug so _fix_dangling_wikilinks treats it as gone
    active_slugs: set[str] = set(slugs) - {archived_slug}
    affected: list[str] = []
    for slug in slugs:
        if slug == archived_slug or slug in LINT_SKIP_SLUGS:
            continue
        page = store.read_page(slug)
        if not page or page.status == LifecycleState.ARCHIVED:
            continue
        new_content = _fix_dangling_wikilinks(page.content, active_slugs)
        if new_content != page.content:
            page.content = new_content
            with store.page_lock(slug):
                store.write_page(slug, page)
            affected.append(slug)
            if audit_db:
                await audit_db.record_lifecycle_event(
                    slug, page.status, page.status,
                    f"cascade: [[{archived_slug}]] link removed",
                    trigger_source,
                )
    # Prune the knowledge graph immediately so GET /graph is consistent.
    # The /graph endpoint reads audit.db directly on every request (no in-memory cache),
    # so this takes effect on the next request without any additional invalidation.
    if audit_db:
        await audit_db.delete_graph_node(archived_slug)

    if affected:
        _log.info(
            "cascade_archive: [[%s]] removed from %d page(s): %s",
            archived_slug, len(affected), affected,
        )
    return affected


def suggested_reingest_cmd(file: str, wiki_name: str, size: int) -> str:
    """Return the CLI command a user should run to re-ingest a truncated source."""
    return f'synthadoc ingest "{file}" -w {wiki_name} --max-source-chars {size * 2} --force'


def find_orphan_slugs(
    page_texts: dict[str, str],
    skip: frozenset[str] = LINT_SKIP_SLUGS,
    skip_source: frozenset[str] = LINT_SKIP_SOURCE_SLUGS,
) -> list[str]:
    """Return slugs with no inbound [[wikilinks]] from other content pages.

    page_texts maps slug → page body text (frontmatter must be stripped by caller).
    Links from skip_source pages (index, overview, dashboard, log) and self-links
    are not counted — only connections between content pages rescue from orphan.
    """
    referenced: set[str] = set()
    for slug, text in page_texts.items():
        if slug in skip_source:
            continue
        for link in _WIKILINK_RE.findall(text):
            slug_part = link.split("|")[0].strip()
            target = slug_part.lower().replace(" ", "-")
            if target != slug:  # self-links don't count as inbound references
                referenced.add(target)
    return [s for s in page_texts if s not in referenced and s not in skip]


def _parse_adversarial_response(text: str) -> list[dict]:
    """Parse LLM adversarial response into list of {claim, concern} dicts."""
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw).strip()
    try:
        parsed = _json.loads(raw)
        if isinstance(parsed, list):
            return [
                {"claim": item.get("claim"), "concern": item.get("concern")}
                for item in parsed
                if isinstance(item, dict) and item.get("concern")
            ]
    except Exception:
        pass
    return []


class LintFocus:
    """Named constants for lint report focus categories."""
    CONTRADICTED = "contradicted"
    ORPHANS      = "orphans"
    ADVERSARIAL  = "adversarial"
    TRUNCATED    = "truncated"
    ALL: frozenset[str] = frozenset({"contradicted", "orphans", "adversarial", "truncated"})


@dataclass
class LintStateSummary:
    contradicted: list[str]
    orphans: list[str]
    adv_pages: list[dict]                                   # [{slug, warnings: list[dict]}]
    truncated_pages: list[dict] = field(default_factory=list)  # [{slug, file, size}]


def read_current_lint_state(store: WikiStorage) -> LintStateSummary:
    """Scan wiki pages and return contradictions, orphans, adversarial warnings, and truncated sources.

    Reads from WikiStorage directly — no LLM, no server required.
    """
    slugs = store.list_pages()
    contradicted: list[str] = []
    page_bodies: dict[str, str] = {}
    adv_pages: list[dict] = []
    truncated_pages: list[dict] = []

    for slug in slugs:
        page = store.read_page(slug)
        if page is None:
            continue
        page_bodies[slug] = page.content or ""
        if slug in LINT_SKIP_SLUGS:
            continue
        if page.status == LifecycleState.CONTRADICTED:
            contradicted.append(slug)
        if page.lint_warnings:
            adv_pages.append({"slug": slug, "warnings": list(page.lint_warnings)})
        for src in (page.sources or []):
            if getattr(src, "truncated", False):
                truncated_pages.append({"slug": slug, "file": src.file, "size": src.size})

    orphans = find_orphan_slugs(page_bodies)
    return LintStateSummary(
        contradicted=contradicted,
        orphans=orphans,
        adv_pages=adv_pages,
        truncated_pages=truncated_pages,
    )


class LintAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 log_writer: LogWriter, confidence_threshold: float = 0.85,
                 audit_db: AuditDB | None = None,
                 adversarial_provider: LLMProvider | None = None,
                 adversarial_max_per_page: int = 2,
                 adversarial_concurrency: int = 8,
                 wiki_root: "Path | str | None" = None,
                 cfg: "Config | None" = None) -> None:
        self._provider = provider
        self._store = store
        self._log = log_writer
        self._threshold = confidence_threshold
        self._audit = audit_db
        self._adversarial_provider = adversarial_provider or provider
        self._adversarial_max_per_page = adversarial_max_per_page
        self._adversarial_concurrency = adversarial_concurrency
        self._wiki_root = Path(wiki_root) if wiki_root else self._store._root.parent
        self._cfg = cfg

    def _find_orphans(self, slugs: list[str]) -> list[str]:
        page_texts = {}
        for slug in slugs:
            page = self._store.read_page(slug)
            page_texts[slug] = page.content if page else ""
        return find_orphan_slugs(page_texts)

    def _clean_dangling_links(self, slugs: list[str]) -> int:
        slug_set = set(slugs)
        fixed = 0
        for slug in slugs:
            page = self._store.read_page(slug)
            if not page:
                continue
            new_content = _fix_dangling_wikilinks(page.content, slug_set)
            if new_content != page.content:
                page.content = new_content
                self._store.write_page(slug, page)
                fixed += 1
        return fixed

    def _check_truncated_sources(self, slug: str, page) -> list[str]:
        """Return warning strings for any sources flagged as truncated."""
        warnings = []
        for src in (page.sources or []):
            if getattr(src, "truncated", False):
                max_chars = getattr(
                    getattr(self._cfg, "ingest", None), "max_source_chars", 32000
                )
                warnings.append(
                    f"[WARN] {slug}.md: source '{src.file}' was truncated at ingest "
                    f"(source exceeded max_source_chars={max_chars} — {src.size:,} chars in source).\n"
                    f"       To re-ingest with a higher limit (this source only):\n"
                    f"         synthadoc ingest {src.file} --max-source-chars {src.size * 2} --force\n"
                    f"       To raise the limit for all future ingests:\n"
                    f"         set [ingest] max_source_chars = {src.size * 2} in your config"
                )
        return warnings

    def _build_graph(self) -> tuple[list[dict], list[dict]]:
        """Extract weighted graph from all pages and run Louvain clustering.

        Returns (nodes, edges) where each node has {slug, cluster_id} and each
        edge has {from_slug, to_slug, weight, edge_type}.  Self-links are
        ignored.  Edge weight combines wikilink occurrences (+1 each) and
        co-source connections (+2 per shared source hash).  edge_type is one
        of 'wikilink', 'co_source', or 'mixed'.
        """
        slugs = self._store.list_pages()
        if not slugs:
            return [], []

        all_slugs = set(slugs)
        edge_counts: dict[tuple[str, str], int] = defaultdict(int)
        wikilink_pairs: set[tuple[str, str]] = set()
        source_map: dict[str, set[str]] = {}

        # Pass 1: wikilink edges + source hash extraction in one read per page
        for slug in slugs:
            page = self._store.read_page(slug)
            if page is None:
                continue
            for match in _WIKILINK_RE.finditer(page.content or ""):
                target = match.group(1).split("|")[0].strip()
                if target and target != slug and target in all_slugs:
                    edge_counts[(slug, target)] += 1
                    wikilink_pairs.add((slug, target))
            if page.sources:
                hashes = {s.hash for s in page.sources if s.hash}
                if hashes:
                    source_map[slug] = hashes

        # Pass 2: co-source edges — pages sharing a source hash get +2 per shared source
        cosource_pairs: set[tuple[str, str]] = set()
        slug_list = list(source_map)
        for i, s1 in enumerate(slug_list):
            for s2 in slug_list[i + 1:]:
                shared = source_map[s1] & source_map[s2]
                if shared:
                    increment = len(shared) * 2
                    edge_counts[(s1, s2)] += increment
                    edge_counts[(s2, s1)] += increment
                    cosource_pairs.add((s1, s2))
                    cosource_pairs.add((s2, s1))

        # Use DiGraph to preserve link direction (a→b and b→a are distinct edges)
        G = nx.DiGraph()
        G.add_nodes_from(slugs)
        for (src, dst), weight in edge_counts.items():
            G.add_edge(src, dst, weight=weight)

        # Louvain requires undirected graph
        if _LOUVAIN_AVAILABLE and G.number_of_nodes() > 0:
            partition = community_louvain.best_partition(G.to_undirected())
        else:
            partition = {slug: 0 for slug in slugs}

        nodes = [
            {"slug": slug, "cluster_id": int(partition.get(slug, 0))}
            for slug in slugs
        ]
        edges = []
        for src, dst, data in G.edges(data=True):
            has_wikilink = (src, dst) in wikilink_pairs
            has_cosource = (src, dst) in cosource_pairs
            if has_wikilink and has_cosource:
                edge_type = "mixed"
            elif has_cosource:
                edge_type = "co_source"
            else:
                edge_type = "wikilink"
            edges.append({"from_slug": src, "to_slug": dst, "weight": data["weight"], "edge_type": edge_type})
        return nodes, edges

    async def _adversarial_single(self, slug: str, content: str) -> tuple[list[dict], int]:
        """Adversarially review one page. Always returns; never raises (rate-limits are caught)."""
        n = self._adversarial_max_per_page
        prompt = (
            "You are a skeptical editor reviewing a wiki page compiled from source documents.\n\n"
            f"List up to {n} claim{'s' if n != 1 else ''} in this page that are clearly overstated or directly\n"
            "contradict well-established facts. Only flag issues you are highly confident\n"
            "about — if a claim is defensible or nuanced, skip it.\n\n"
            "For each claim:\n"
            "1. Quote the exact claim (one sentence or phrase)\n"
            "2. Explain the specific concern concisely\n\n"
            "If you find no such issues, return an empty JSON array: []\n\n"
            "Return ONLY a JSON array, no markdown fences:\n"
            '[{"claim": "...", "concern": "..."}, ...]\n\n'
            f"--- PAGE CONTENT ---\n{content[:3000]}"
        )
        try:
            resp = await self._adversarial_provider.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.0,
            )
            return _parse_adversarial_response(resp.text), resp.total_tokens
        except Exception as exc:
            err = str(exc).lower()
            if "429" in str(exc) or "rate limit" in err or "rate_limit" in err or "too many" in err:
                return [{"claim": None,
                         "concern": "adversarial-pass-skipped: rate limit — consider a paid model or a higher rate-limit tier"}], 0
            return [], 0

    async def _run_adversarial_pass(self, slugs: list[str]) -> tuple[list[dict], int]:
        """Concurrent adversarial review of all non-skip pages.

        Returns (adversarial_warnings_list, total_tokens).
        adversarial_warnings_list: [{slug, warnings}] for pages with at least one warning.
        """
        scan = [
            (s, self._store.read_page(s))
            for s in slugs
            if s not in LINT_SKIP_SLUGS
        ]
        scan = [(s, p) for s, p in scan if p is not None]
        if not scan:
            return [], 0

        sem = asyncio.Semaphore(self._adversarial_concurrency)

        async def _bounded(slug: str, content: str) -> tuple[list[dict], int]:
            async with sem:
                return await self._adversarial_single(slug, content)

        results = await asyncio.gather(
            *(_bounded(s, p.content) for s, p in scan)
        )

        all_warnings: list[dict] = []
        total_tokens = 0
        for (slug, page), (warnings, tokens) in zip(scan, results):
            total_tokens += tokens
            page.lint_warnings = warnings
            self._store.write_page(slug, page)
            if warnings:
                all_warnings.append({"slug": slug, "warnings": warnings})

        return all_warnings, total_tokens

    async def _transition(self, slug: str, page: "WikiPage", from_state: str,
                          to_state: str, reason: str) -> None:
        if self._audit:
            await self._audit.set_page_state(slug, to_state, TriggerSource.LINT)
            await self._audit.record_lifecycle_event(
                slug, from_state, to_state, reason, TriggerSource.LINT
            )
        page.status = to_state
        self._store.write_page(slug, page)

    async def _is_url_unavailable(self, url: str) -> bool:
        """Return True only if URL is definitively gone (404/410 or YouTube VideoUnavailable).
        Returns False on timeout, connection error, or any ambiguous failure — avoid false positives.
        """
        import re as _re
        _YT = _re.compile(
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})'
        )
        m = _YT.search(url)
        if m:
            _log.debug("lifecycle url-check [youtube] id=%s url=%s", m.group(1), url)
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                from youtube_transcript_api._errors import VideoUnavailable
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: YouTubeTranscriptApi.get_transcript(m.group(1))  # type: ignore[attr-defined]
                )
                _log.debug("lifecycle url-check [youtube] unavailable=%s url=%s", False, url)
                return False
            except Exception as exc:
                # Only VideoUnavailable is a definitive signal
                try:
                    result = isinstance(exc, VideoUnavailable)
                except NameError:
                    result = False
                _log.debug("lifecycle url-check [youtube] unavailable=%s url=%s", result, url)
                return result

        # Generic URL: HTTP HEAD
        _log.debug("lifecycle url-check [http-head] url=%s", url)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(url, follow_redirects=True)
                _log.debug("lifecycle url-check [http-head] status=%d url=%s", resp.status_code, url)
                return resp.status_code in (404, 410)
        except Exception as exc:
            _log.debug("lifecycle url-check [http-head] error=%s url=%s", type(exc).__name__, url)
            return False  # timeout / connection error = assume available

    async def _run_lifecycle_checks(self, slugs: list[str], report: LintReport,
                                     check_url_availability: bool = False,
                                     url_staleness_days: int = 0,
                                     promote_drafts: bool = True) -> None:
        raw_sources_dir = self._wiki_root / "raw_sources"
        _auto_archived_slugs: list[str] = []
        for slug in slugs:
            if slug in LINT_SKIP_SLUGS:
                continue
            try:
                page = self._store.read_page(slug)
                if not page:
                    continue
                current = page.status

                # Check 1: archived detection -- source file no longer on disk / URL unavailable
                if current in (LifecycleState.ACTIVE, LifecycleState.STALE, LifecycleState.DRAFT):
                    for src_ref in page.sources:
                        if src_ref.file and not is_url(src_ref.file):
                            if raw_sources_dir.exists():
                                src_path = raw_sources_dir / src_ref.file
                                if not src_path.exists():
                                    local_sources = [
                                        s for s in page.sources
                                        if s.file and not is_url(s.file)
                                    ]
                                    all_missing = all(
                                        not (raw_sources_dir / s.file).exists()
                                        for s in local_sources
                                    )
                                    if all_missing:
                                        await self._transition(
                                            slug, page, current,
                                            LifecycleState.ARCHIVED,
                                            "all source files no longer on disk",
                                        )
                                        report.lifecycle_archived += 1
                                        _auto_archived_slugs.append(slug)
                                        current = LifecycleState.ARCHIVED
                                    else:
                                        await self._transition(
                                            slug, page, current,
                                            LifecycleState.STALE,
                                            "source file no longer on disk; other sources remain",
                                        )
                                        report.lifecycle_stale += 1
                                        current = LifecycleState.STALE
                                    break
                        # URL archived: HTTP HEAD or YouTube availability (opt-in)
                        elif src_ref.file and is_url(src_ref.file) and check_url_availability:
                            _log.debug("lifecycle archived-check [url] slug=%s url=%s", slug, src_ref.file)
                            if await self._is_url_unavailable(src_ref.file):
                                _log.debug("lifecycle archived [url] slug=%s url=%s → archived", slug, src_ref.file)
                                await self._transition(slug, page, current,
                                                       LifecycleState.ARCHIVED,
                                                       "URL source no longer available")
                                report.lifecycle_archived += 1
                                _auto_archived_slugs.append(slug)
                                current = LifecycleState.ARCHIVED
                                break

                if current == LifecycleState.ARCHIVED:
                    # Bootstrap DB entry for pages archived via frontmatter that have
                    # never been through the lifecycle system (no page_states row yet).
                    # Pages archived via _transition() already have a row, so this is a no-op for them.
                    if self._audit:
                        db_state = await self._audit.get_page_state(slug)
                        if not db_state:
                            await self._audit.set_page_state(
                                slug, LifecycleState.ARCHIVED, TriggerSource.LINT
                            )
                    continue

                # Check 2: stale detection -- source file hash changed
                if current == LifecycleState.ACTIVE and self._audit:
                    for src_ref in page.sources:
                        if src_ref.file and not is_url(src_ref.file):
                            src_path = raw_sources_dir / src_ref.file
                            if src_path.exists():
                                current_hash = hashlib.sha256(src_path.read_bytes()).hexdigest()
                                record = await self._audit.find_by_source_path(str(src_path))
                                if record and record.get("source_hash") is not None and record.get("source_hash") != current_hash:
                                    await self._transition(slug, page, LifecycleState.ACTIVE,
                                                           LifecycleState.STALE,
                                                           "source file modified since last ingest")
                                    report.lifecycle_stale += 1
                                    current = LifecycleState.STALE
                                    break
                        # URL stale: age-based (no network call)
                        elif src_ref.file and is_url(src_ref.file) and url_staleness_days > 0 and self._audit:
                            record = await self._audit.find_by_source_path(src_ref.file)
                            if record and record.get("ingested_at"):
                                try:
                                    ingested_dt = datetime.fromisoformat(record["ingested_at"])
                                    if ingested_dt.tzinfo is None:
                                        ingested_dt = ingested_dt.replace(tzinfo=timezone.utc)
                                    age_days = (datetime.now(timezone.utc) - ingested_dt).days
                                    _log.debug(
                                        "lifecycle stale-check [url] slug=%s url=%s age_days=%d threshold=%d",
                                        slug, src_ref.file, age_days, url_staleness_days,
                                    )
                                    if age_days > url_staleness_days:
                                        _log.debug("lifecycle stale [url] slug=%s url=%s → stale", slug, src_ref.file)
                                        await self._transition(slug, page, LifecycleState.ACTIVE,
                                                               LifecycleState.STALE,
                                                               f"URL source not re-ingested in {age_days} days")
                                        report.lifecycle_stale += 1
                                        current = LifecycleState.STALE
                                        break
                                except (ValueError, TypeError):
                                    pass  # malformed timestamp — skip

                # Check 3: draft promotion (skipped for stale-only runs)
                if promote_drafts and current == LifecycleState.DRAFT:
                    await self._transition(slug, page, LifecycleState.DRAFT,
                                           LifecycleState.ACTIVE, "lint passed")
                    report.lifecycle_promoted += 1
                    current = LifecycleState.ACTIVE

                # Check 4: manual-edit sync -- frontmatter state differs from DB
                if self._audit:
                    db_state = await self._audit.get_page_state(slug)
                    if current in LifecycleState.ALL:
                        if db_state and db_state["state"] != current:
                            await self._audit.set_page_state(slug, current, TriggerSource.MANUAL_EDIT)
                            await self._audit.record_lifecycle_event(
                                slug, db_state["state"], current,
                                "manual frontmatter edit detected", TriggerSource.MANUAL_EDIT
                            )
                            report.lifecycle_synced += 1
                        elif not db_state:
                            await self._audit.set_page_state(slug, current, TriggerSource.LINT)
                    elif not db_state:
                        # frontmatter has no valid status — bootstrap as draft so the page
                        # is registered in page_states and visible to the lifecycle system
                        await self._audit.set_page_state(slug, LifecycleState.DRAFT, TriggerSource.LINT)

            except Exception as exc:
                _log.warning(
                    "lifecycle check failed for %s: %s", slug, exc
                )

        # Ghost-draft sweep: DB entries in 'draft' with no corresponding wiki file.
        # This happens when the server is restarted mid-ingest before the file is written.
        # Candidate pages (wiki/candidates/<slug>.md) are legitimately draft — skip them.
        if self._audit and promote_drafts:
            fs_slugs = set(slugs)
            candidates_dir = self._wiki_root / "wiki" / "candidates"
            all_states = await self._audit.get_all_page_states()
            for entry in all_states:
                slug = entry["slug"]
                if entry["state"] == LifecycleState.DRAFT and slug not in fs_slugs:
                    if (candidates_dir / f"{slug}.md").exists():
                        continue  # staged candidate — not a ghost
                    _log.warning(
                        "lifecycle ghost-draft: slug=%s has no wiki file — archiving "
                        "(ingest was interrupted before file was written)",
                        slug,
                    )
                    await self._audit.set_page_state(
                        slug, LifecycleState.ARCHIVED, TriggerSource.LINT
                    )
                    await self._audit.record_lifecycle_event(
                        slug, LifecycleState.DRAFT, LifecycleState.ARCHIVED,
                        "wiki file missing — ingest interrupted before file was written",
                        TriggerSource.LINT,
                    )
                    report.lifecycle_archived += 1
                    _auto_archived_slugs.append(slug)

        if self._audit and self._cfg:
            retention = getattr(getattr(self._cfg, "audit", None), "lifecycle_retention_days", 0)
            if retention > 0:
                from datetime import timedelta
                cutoff = (datetime.now(timezone.utc) - timedelta(days=retention)).isoformat()
                await self._audit.purge_lifecycle_events(before_date=cutoff)

        # Cascade: immediately clean [[slug]] refs for every page auto-archived above.
        # Called once per archived slug after the full loop so we avoid O(n²) store
        # scans (each cascade_archive call is O(n) — sequential is fine since they
        # are independent).
        for _slug in _auto_archived_slugs:
            _affected = await cascade_archive(
                _slug, self._store,
                audit_db=self._audit, trigger_source=TriggerSource.LINT,
            )
            report.dangling_links_removed += len(_affected)

    async def lint(self, scope: str = "all", auto_resolve: bool = False,
                   adversarial: bool = True, lifecycle: bool = True,
                   check_url_availability: Optional[bool] = None,
                   job_id: str = "system") -> LintReport:
        report = LintReport()
        slugs = self._store.list_pages()

        if scope in ("all", "contradictions"):
            for slug in slugs:
                if slug in LINT_SKIP_SLUGS:
                    continue
                page = self._store.read_page(slug)
                if page and page.status == LifecycleState.CONTRADICTED:
                    report.contradictions_found += 1
                    if self._audit:
                        await self._audit.record_audit_event(
                            job_id, "contradiction_found", {"slug": slug})
                    if auto_resolve:
                        note = page.contradiction_note or ""
                        prompt = (
                            "A wiki page has been flagged as contradicted by a new source.\n"
                            "Your job is to produce an updated page that is accurate given both sources.\n"
                            "Resolution strategy: rewrite the disputed claim to represent BOTH perspectives "
                            "accurately — do NOT pick a winner. If one source says X and another says Y, "
                            "present both with appropriate hedging (e.g. 'widely regarded as…, though some "
                            "historians argue…').\n"
                            "Only mark resolvable=false if the page itself should not exist, or the conflict "
                            "cannot be addressed through editorial nuance (e.g. the entire page is a fabrication).\n"
                            "Return ONLY valid JSON, no markdown fences:\n"
                            '{"resolvable": true|false, "reason": "one sentence explaining why or why not", '
                            '"resolution": "complete rewritten page content if resolvable, else empty string"}\n\n'
                            f"Contradiction note: {note}\n\n"
                            f"Current page content:\n{page.content[:2000]}"
                        )
                        resp = await self._provider.complete(
                            messages=[Message(role="user", content=prompt)],
                            temperature=0.0,
                        )
                        report.tokens_used += resp.total_tokens
                        try:
                            from synthadoc.agents.ingest_agent import _parse_json_response
                            decision = _parse_json_response(resp.text)
                        except Exception:
                            decision = {"resolvable": False, "reason": "auto-resolve returned unparseable output", "resolution": ""}
                        if decision.get("resolvable"):
                            page.status = LifecycleState.ACTIVE
                            page.contradiction_note = None
                            page.unresolved_note = None
                            resolution = decision.get("resolution", "").strip()
                            if resolution:
                                page.content = resolution
                            else:
                                page.content += f"\n\n**Auto-resolved:** {decision.get('reason', '')}"
                            self._store.write_page(slug, page)
                            report.contradictions_resolved += 1
                            if self._audit:
                                await self._audit.record_audit_event(
                                    job_id, "auto_resolved", {"slug": slug})
                        else:
                            reason = decision.get("reason", "Could not determine a confident resolution.")
                            page.unresolved_note = reason
                            self._store.write_page(slug, page)
                            report.contradictions_unresolved.append({"slug": slug, "reason": reason})
                            if self._audit:
                                await self._audit.record_audit_event(
                                    job_id, "auto_resolve_failed", {"slug": slug, "reason": reason})

        if scope in ("all", "orphans"):
            report.dangling_links_removed = self._clean_dangling_links(slugs)
            slugs = self._store.list_pages()  # re-read after deletions
            report.orphan_slugs = self._find_orphans(slugs)
            orphan_set = set(report.orphan_slugs)
            for slug in slugs:
                page = self._store.read_page(slug)
                if page and page.orphan != (slug in orphan_set):
                    page.orphan = slug in orphan_set
                    self._store.write_page(slug, page)

        # Check 5: citation validation (pure regex + file-stat, no LLM)
        if scope == "all":
            wiki_root = self._store._root.parent
            extracted_dir = wiki_root / ".synthadoc" / "extracted"
            for slug in [s for s in slugs if s not in LINT_SKIP_SLUGS]:
                page = self._store.read_page(slug)
                if not page:
                    continue
                issues = _check_page_citations(slug, page, extracted_dir)
                for issue in issues:
                    report.citation_issues.append(issue)
                    if self._audit:
                        await self._audit.record_audit_event(
                            job_id, "citation_validation_failed", issue,
                        )
                # Check 6: truncated source warnings
                truncation_warnings = self._check_truncated_sources(slug, page)
                for warning in truncation_warnings:
                    report.warnings.append(warning)

                # Check 5b: citation presence warning
                if not _has_citations(page):
                    word_count = len((page.content or "").split())
                    if word_count >= _CITATION_MIN_WORDS:
                        warn = (
                            f"Page '{slug}' has {word_count} words but no citations — "
                            "the configured model may not support the ^[filename:L-L] format"
                        )
                        report.warnings.append(warn)
                        if self._audit:
                            await self._audit.record_audit_event(
                                job_id,
                                "citation_presence_warning",
                                {"slug": slug, "word_count": word_count},
                            )

        # adversarial pass — runs only on full scope; default on
        if scope == "all":
            if adversarial:
                # slugs was re-read after dangling-link cleanup — use the up-to-date list
                adv_warnings, adv_tokens = await self._run_adversarial_pass(slugs)
                report.adversarial_warnings = adv_warnings
                report.tokens_used += adv_tokens
            else:
                # --no-adversarial: clear stale lint_warnings from all pages
                for slug in [s for s in slugs if s not in LINT_SKIP_SLUGS]:
                    page = self._store.read_page(slug)
                    if page and page.lint_warnings:
                        page.lint_warnings = []
                        self._store.write_page(slug, page)

        if scope in ("all", "stale") and lifecycle:
            _check_urls = (
                check_url_availability
                if check_url_availability is not None
                else getattr(getattr(self._cfg, "lint", None), "check_url_availability", False)
            )
            _url_staleness = getattr(getattr(self._cfg, "audit", None), "url_staleness_days", 0)
            await self._run_lifecycle_checks(
                slugs, report, _check_urls, _url_staleness,
                promote_drafts=(scope == "all"),
            )

        if scope == "all" and self._audit:
            try:
                nodes, edges = self._build_graph()
                await self._audit.write_graph(nodes, edges)
            except Exception as exc:
                _log.warning("[graph] build failed during lint, skipping: %s", exc)

        self._log.log_lint(resolved=report.contradictions_resolved,
                           flagged=report.contradictions_found - report.contradictions_resolved,
                           orphans=len(report.orphan_slugs),
                           dangling_removed=report.dangling_links_removed)
        return report
