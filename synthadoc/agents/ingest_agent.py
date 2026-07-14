# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from synthadoc.agents.citations import CITATION_RE as _CITATION_RE, MALFORMED_CITE_RE as _MALFORMED_CITE_RE
from synthadoc.agents.search_decompose_agent import SearchDecomposeAgent
from synthadoc.agents.skill_agent import SkillAgent
from synthadoc.core.cache import CACHE_VERSION, CacheManager, make_cache_key
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import SourceRef, WikiPage, WikiStorage, LifecycleState, is_url, TriggerSource
from synthadoc.skills.web_search.scripts.main import _INTENT_RE as _WEB_INTENT_RE
from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
from synthadoc.core.sanitizer import sanitize as _sanitize_source

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    source: str
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    pages_flagged: list[str] = field(default_factory=list)
    child_sources: list[str] = field(default_factory=list)
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cache_hits: int = 0
    skipped: bool = False
    skip_reason: str = ""


_ANALYSIS_PROMPT = (
    "Analyse the source text below. Return ONLY valid JSON with no markdown fences:\n"
    '{"entities": [...], "tags": [...], "summary": "One to three sentences describing '
    'the main topic, key claims, and relevance.", '
    '"type": "concept|person|technology|event|organization|location|product", "relevant": true}\n\n'
    "Keep entities and tags under 10 items each.\n"
    'For "type", pick exactly one label: "person" for individuals, "organization" for companies/institutions, '
    '"technology" for tools/systems/algorithms/standards, "event" for occurrences, '
    '"location" for places, "product" for commercial products, "concept" for abstract ideas (default).\n\n'
)

_ENTITY_PROMPT = (
    "Extract key entities, concepts, and tags from the text below.\n"
    "Return ONLY valid JSON: {\"entities\": [...], \"concepts\": [...], \"tags\": [...]}\n"
    "Keep each list under 10 items.\n\n"
)

_DECISION_PROMPT = (
    "You maintain a knowledge wiki. Decide how to handle a new source document.\n"
    "Return ONLY valid JSON - no markdown fences, no explanation.\n\n"
    "First write a 'reasoning' field explaining your decision, then set 'action'.\n\n"
    "WIKILINKS: Whenever you write page content (update_content or page_content), cross-reference\n"
    "related topics using [[slug]] notation where slug matches a page listed below.\n"
    "Example: 'Turing worked at [[bletchley-park]] on the [[enigma]] cipher.'\n"
    "Only link to pages that actually exist in the wiki (slugs shown below).\n\n"
    "Decision rules (apply in this order):\n\n"
    "RULE 1 — FLAG: If the new source DISPUTES or ARGUES AGAINST a factual claim in an existing page,\n"
    "use action='flag'. This includes academic debates, alternative historical interpretations,\n"
    "or sources that explicitly say an existing claim is wrong or a myth.\n"
    "Example: page says 'A-0 was the first compiler' + source says 'A-0 was a loader, not a compiler'\n"
    "-> action='flag', target=the slug of the page whose claim is disputed\n\n"
    "RULE 1b — ACTIVE PAGE PROTECTION: A page with status='active' has been human-reviewed and is\n"
    "authoritative. Treat its existing facts as correct. If the source gives a DIFFERENT value,\n"
    "date, formula, or conclusion for something the active page already states — even if the source\n"
    "seems more recent — use action='flag', not action='update'. Only use action='update' on an\n"
    "active page when the source adds a section on a topic the page does not yet mention at all.\n\n"
    "RULE 2 — UPDATE: If the source adds new information about a subject ALREADY covered by an existing page,\n"
    "and there is no factual dispute, use action='update'.\n"
    "-> action='update', target=slug of page to extend,\n"
    "   update_content=new ## section(s) to append (use [[slug]] links to related pages)\n\n"
    "RULE 2b — ENTITY PROFILE MUST CREATE: If the source is primarily a profile, case study, or\n"
    "comprehensive overview of ONE specific named entity — a company (with financials, team, products),\n"
    "a person (biography, career), a product, or an organization — always use action='create' with the\n"
    "entity's name as the slug, even if a thematically related page already exists.\n"
    "Do NOT merge entity-specific data (revenue, EBITDA, headcount, management team, org structure)\n"
    "into a broad thematic or market-level page.\n"
    "Example: a company profile covering revenue, EBITDA, employees, management, and products\n"
    "-> action='create', new_slug='company-name', NOT action='update' on a market analysis page.\n\n"
    "RULE 3 — CREATE: ONLY if the source covers a subject not in any existing page.\n"
    "-> action='create', new_slug=meaningful_topic_slug (e.g. 'history-of-computing', NOT 'watch' or URL path segments),\n"
    "   page_content=full synthesized Markdown body (# Title + paragraphs with [[slug]] links)\n\n"
    'Return: {{"reasoning":"...","action":"...","target":"","new_slug":"","update_content":"","page_content":""}}\n\n'
    "Existing wiki pages (top matches):\n{pages}\n\n"
    "New source:\n{source_text}\n\n"
    "Detected entities: {entities}"
)

_OVERVIEW_PROMPT = (
    "Write a 2-paragraph overview of a knowledge wiki based on the page titles and "
    "excerpts below.\n"
    "First paragraph: what topics this wiki covers.\n"
    "Second paragraph: key themes and concepts found.\n"
    "Keep it under 200 words. Plain text only — no markdown headings.\n\n"
    "Pages:\n{pages}"
)

CITATION_PASS4_CACHE_VERSION = "v4"  # bumped: total_lines ceiling in prompt + post-processing clamp
ANALYSIS_CACHE_VERSION = "v2"  # bumped to include OKF type field
DECISION_CACHE_VERSION = "v3"  # bumped to add entity-profile must-create rule (RULE 2b)
_CITATION_EXCERPT_LEN = 100
_MAX_CITATION_LINES = 400
_MAX_CITE_LEN_RATIO = 0.8
_CITATION_MAX_TOKENS = 8192   # output cap for citation pass — large enough for long transcript sections

_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_BOLD_BULLET_NUM_RE = re.compile(
    r"^\s*[-*+]\s+\*\*([^*]+)\*\*\s*[—–-]\s*(.+)$", re.MULTILINE
)
_FORMULA_LINE_RE = re.compile(
    r"^[A-Za-z_]\w*(?:\s+\w+)?\s*=\s*[^\n]{5,80}$", re.MULTILINE
)
_KEY_DATA_MIN_ITEMS = 1  # only append section when at least this many items found

# Matches any ^[filename:spec] where spec is not already a canonical N-N range.
_NONCANONICAL_CITE_RE = re.compile(r'\^\[([^:\]]+):([^\]]+)\]')


def _normalize_citation_markers(text: str) -> str:
    """Normalize LLM-emitted citation variants to canonical ^[file:N-N] format.

    LLMs frequently produce ^[file:42] for single-line references and
    ^[file:12,16-21] for multi-range references; neither matches CITATION_RE.
    Single-line → ^[file:42-42].  Multi-range/comma → ^[file:first-last].
    Already-canonical ^[file:N-N] markers pass through unchanged.
    """
    def _fix(m: re.Match) -> str:
        filename, spec = m.group(1), m.group(2)
        if re.fullmatch(r'\d+-\d+', spec):
            return m.group(0)
        if re.fullmatch(r'\d+', spec):
            return f"^[{filename}:{spec}-{spec}]"
        nums = [int(n) for n in re.findall(r'\d+', spec)]
        if len(nums) >= 2:
            return f"^[{filename}:{nums[0]}-{nums[-1]}]"
        if len(nums) == 1:
            return f"^[{filename}:{nums[0]}-{nums[0]}]"
        return m.group(0)

    return _NONCANONICAL_CITE_RE.sub(_fix, text)


def _scrub_source_citations(content: str, filename: str, source_text: str) -> str:
    """Remove or clamp ^[filename:start-end] markers in *content* that exceed the
    actual line count of *source_text*.

    Called on existing page content before appending a new update section so that
    stale out-of-range citations left by previous reingests are cleaned up.
    """
    total_lines = len(source_text.splitlines())
    fname_lower = filename.lower()

    def _fix(m: re.Match) -> str:
        if m.group(1).lower() != fname_lower:
            return m.group(0)
        start, end = int(m.group(2)), int(m.group(3))
        if start > total_lines:
            return ""
        if end > total_lines:
            return f"^[{m.group(1)}:{start}-{total_lines}]"
        return m.group(0)

    return _CITATION_RE.sub(_fix, content)


_CITATION_PROMPT = (
    "You are a citation annotator. Given a wiki page section and the source text it was "
    "compiled from, insert a citation marker at the END of each paragraph that makes a "
    "substantive claim traceable to the source.\n\n"
    "Citation format rules (follow exactly):\n"
    "  - Format: ^[SOURCE:START-END]\n"
    "  - SOURCE must be the exact source filename given below — copy it character-for-character. "
    "Do NOT write the word 'FILENAME', 'SOURCE', or any other placeholder; use only the actual filename.\n"
    "  - START-END is the 1-based line range in the numbered source text (use a hyphen, never a comma).\n"
    "  - Example: if the source filename is '{filename}' and the claim is on lines 7-9, write "
    "^[{filename}:7-9]\n\n"
    "Do not annotate headings, transition sentences, or [[wikilinks]].\n"
    "IMPORTANT: The source has exactly {total_lines} lines. "
    "Never write a line number greater than {total_lines}. "
    "If the relevant content is not visible in the excerpt, skip the citation for that paragraph.\n"
    "Return ONLY the annotated section — identical to the input except for added ^[...] markers.\n\n"
    "Source filename: {filename}\n\n"
    "Source text ({total_lines} lines, numbered):\n{numbered_source}\n\n"
    "Page section to annotate:\n{section}"
)

_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def _backfill_okf_fields(page: "WikiPage", analysis: dict, source: str) -> None:
    """Backfill type and resource on pages that predate v0.9.0. Never overwrites existing values.

    Uses getattr so this is safe against pages loaded from stale bytecode or any
    other path where WikiPage was instantiated before the type/resource fields existed.
    """
    if getattr(page, "type", None) is None:
        page.type = analysis.get("type") or None
    if getattr(page, "resource", None) is None and is_url(source):
        page.resource = source


def _confidence_passes_threshold(confidence: str, min_confidence: str) -> bool:
    return _CONFIDENCE_RANK.get(confidence, 0) >= _CONFIDENCE_RANK.get(min_confidence, 0)


_SLUG_BLACKLIST = frozenset({
    "wikilinks", "wikilink", "wiki", "obsidian", "dataview",
    # URL path segments that are never meaningful topic names
    "watch", "embed", "video", "index", "page", "post", "article", "content",
})

# Matches any YouTube URL form and captures the 11-char video ID.
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|live/|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def _canonical_source(source: str) -> str:
    """Normalise YouTube URL variants to a single canonical form.

    youtu.be/<id>, /shorts/, /live/, /embed/ all become
    https://www.youtube.com/watch?v=<id> so dedup hashes are consistent.
    """
    m = _YOUTUBE_ID_RE.search(source)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return source


def _coerce_str_list(lst: object) -> list[str]:
    """Ensure every item in an LLM-returned list is a plain string.

    Some models return entities as dicts ({"name": "Canada", "type": "location"})
    instead of strings.  Extract the most useful field or fall back to str().
    """
    if not isinstance(lst, list):
        return []
    result = []
    for item in lst:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            value = item.get("name") or item.get("value") or item.get("label") or item.get("text") or ""
            if value:
                result.append(str(value))
        else:
            result.append(str(item))
    return [s for s in result if s.strip()]


def _parse_json_response(text: str) -> dict:
    """Parse a JSON object from an LLM response, handling markdown code fences."""
    text = text.strip()
    # Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        # LLM sometimes wraps the dict in a top-level array; unwrap first element
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]
    except json.JSONDecodeError:
        pass
    # Strip markdown code block: ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find first {...} in the response
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _slugify(title: str) -> str:
    # Decompose accented characters (é → e + combining accent) so they map to ASCII
    normalized = unicodedata.normalize("NFKD", title)
    # Keep ASCII alphanumeric and CJK character blocks (valid Obsidian filename chars)
    slug = re.sub(
        r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+",
        "-",
        normalized.lower(),
    ).strip("-")
    # Fallback: if title was entirely symbols with no slug-able chars, use a content hash
    return slug or "page-" + hashlib.md5(title.encode()).hexdigest()[:8]


def _url_sidecar_name(url: str) -> str:
    """Derive a collision-resistant sidecar name from a URL.

    Uses the last two non-empty path segments joined with '-' so that URLs
    sharing the same terminal segment (e.g. /profile/dennis-ritchie vs
    /biography/dennis-ritchie) get distinct sidecar files and citation names.
    Single-segment paths fall back to that segment alone.
    """
    bare = url.split("?")[0].rstrip("/")
    parts = [seg for seg in bare.split("/") if seg]
    # parts[0] = "https:", parts[1] = domain — skip both
    segments = parts[2:] if len(parts) > 2 else parts[1:] if len(parts) > 1 else parts
    if len(segments) >= 2:
        name = f"{segments[-2]}-{segments[-1]}"
    elif segments:
        name = segments[-1]
    else:
        name = "url-source"
    return re.sub(r"[^A-Za-z0-9.\-]", "-", name).strip("-")[:80] or "url-source"


def _strip_leading_frontmatter(content: str) -> str:
    """Remove a leading YAML frontmatter block from LLM-generated page content.

    Some models return page_content as a full Obsidian markdown file including
    a ---...--- block.  write_page() adds its own block, producing double-frontmatter
    that corrupts BM25 indexing (YAML syntax becomes the searchable body text).
    """
    content = content.strip()
    if not content.startswith("---"):
        return content
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].lstrip("\n")
    return content


def _append_source_ref(page: "WikiPage", ref: "SourceRef") -> None:
    """Append ref to page.sources only when the source is not already recorded.

    Deduplicates on (file, hash) AND detects when an absolute path matches an
    existing relative-path entry (e.g. ``--force`` ingest with an absolute path
    given for a source that is already registered as a relative path).
    """
    seen: set[tuple[str, str]] = set()
    clean: list["SourceRef"] = []
    for s in page.sources:
        key = (s.file, s.hash)
        if key not in seen:
            seen.add(key)
            clean.append(s)
    page.sources = clean

    # If ref uses an absolute path, skip it when an existing relative-path entry
    # is a suffix of that absolute path (normalise separators for cross-platform safety).
    if Path(ref.file).is_absolute():
        norm_abs = ref.file.replace("\\", "/")
        for s in page.sources:
            if not Path(s.file).is_absolute():
                norm_rel = s.file.replace("\\", "/")
                if norm_abs.endswith("/" + norm_rel) or norm_abs == norm_rel:
                    return  # already recorded as a relative path

    if (ref.file, ref.hash) not in seen:
        page.sources.append(ref)
    else:
        # Update mutable fields on the existing entry so a re-ingest with a
        # higher max_source_chars clears a stale truncated=True flag.
        for s in page.sources:
            if (s.file, s.hash) == (ref.file, ref.hash):
                s.truncated = ref.truncated
                s.size = ref.size
                s.ingested = ref.ingested
                break


def _propagate_source_update(
    store: "WikiStorage", source_url: str, new_truncated: bool, new_size: int, skip_slug: str
) -> None:
    """After a force reingest, sync truncated/size on every OTHER page that still references source_url.

    When the LLM chooses action=create for a re-ingested URL, the source moves to a new page
    while the old page keeps a stale SourceRef(truncated=True).  This walks all other pages
    and updates the flag so lint stops reporting a warning that the user already resolved.
    """
    for slug in store.all_slugs():
        if slug == skip_slug:
            continue
        page = store.read_page(slug)
        if not page:
            continue
        changed = False
        for ref in (page.sources or []):
            if ref.file == source_url and (ref.truncated != new_truncated or ref.size != new_size):
                ref.truncated = new_truncated
                ref.size = new_size
                changed = True
        if changed:
            with store.page_lock(slug):
                store.write_page(slug, page)
            logger.debug("ingest: propagated truncation update to slug=%s source=%s", slug, source_url[:80])


def _extract_key_data(source_text: str) -> list[str]:
    """Extract numerical facts, formulas, and rates from source text deterministically.

    Returns a deduplicated list of strings. Returns [] when nothing is found.
    """
    items: list[str] = []
    seen: set[str] = set()

    def _add(item: str) -> None:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            items.append(item)

    for m in _CODE_BLOCK_RE.finditer(source_text):
        for line in m.group(1).splitlines():
            line = line.strip()
            if line:
                _add(line)

    for m in _BOLD_BULLET_NUM_RE.finditer(source_text):
        _add(f"{m.group(1).strip()} — {m.group(2).strip()}")

    for m in _FORMULA_LINE_RE.finditer(source_text):
        candidate = m.group(0).strip()
        # Skip lines already found in a code block (avoid duplicates from formula lines
        # that appear both inside a block and as a standalone copy in the text)
        if candidate not in seen:
            _add(candidate)

    return items


class IngestAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage, search: HybridSearch,
                 log_writer: LogWriter, audit_db: AuditDB, cache: CacheManager,
                 max_pages: int = 15, wiki_root: Optional[Path] = None,
                 cache_version: str = DECISION_CACHE_VERSION,
                 fetch_timeout: int = 30,
                 routing_path: Optional[Path] = None,
                 cfg=None) -> None:
        self._provider = provider
        self._store = store
        self._search = search
        self._log = log_writer
        self._audit = audit_db
        self._cache = cache
        self._max_pages = max_pages
        self._wiki_root = Path(wiki_root) if wiki_root is not None else None
        self._routing_path = Path(routing_path) if routing_path is not None else None
        self._cfg = cfg
        self._cache_version = cache_version
        self._skill_agent = SkillAgent(skill_kwargs={
            "url": {"fetch_timeout": fetch_timeout},
            "youtube": {"provider": self._provider},
            "image": {"provider": self._provider},
        })
        self._purpose = self._load_purpose()

    def _write_sidecar(self, source_path: str, text: str, pagemap: dict) -> None:
        """Write .synthadoc/extracted/<name>.txt and (for PDFs) <name>.pdf.pagemap."""
        if not self._wiki_root:
            return
        extracted_dir = self._wiki_root / ".synthadoc" / "extracted"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        name = Path(source_path).stem
        (extracted_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        if pagemap:
            (extracted_dir / f"{name}.pdf.pagemap").write_text(
                json.dumps(pagemap, indent=2), encoding="utf-8"
            )

    async def _annotate_citations(
        self, section: str, source_text: str, filename: str, bust_cache: bool = False
    ) -> tuple[str, list[dict]]:
        """Pass 4: annotate section with ^[filename:L-L] markers.

        Returns (annotated_section, citation_list). On any failure returns
        (original_section, []) so ingest always succeeds.
        """
        if not section.strip() or not source_text.strip():
            if not source_text.strip():
                logger.warning(
                    "Pass 4 skipped for %s — source text is empty; no citations added",
                    filename,
                )
                await self._audit.write_event(
                    "citation_pass4_skipped",
                    metadata={"source": filename, "error": "empty_source_text"},
                )
            return section, []

        # Bug C fix: truncate numbered source by line count, not character count.
        # Limit is configurable via [ingest] citation_source_lines in config.toml.
        _line_limit = int(getattr(getattr(self._cfg, "ingest", None), "citation_source_lines", _MAX_CITATION_LINES))
        source_lines = source_text.splitlines()
        total_lines = min(len(source_lines), _line_limit)
        numbered = "\n".join(
            f"{i+1}: {line}"
            for i, line in enumerate(source_lines[:_line_limit])
        )
        body_hash = hashlib.sha256(section.encode()).hexdigest()
        ck = make_cache_key(
            "citation-pass4",
            {"body_hash": body_hash, "filename": filename},
            version=CITATION_PASS4_CACHE_VERSION,
        )
        # Bug E fix: honour bust_cache flag
        cached = None if bust_cache else await self._cache.get(ck)
        if cached:
            annotated = cached
        else:
            try:
                _max_tok = int(getattr(getattr(self._cfg, "ingest", None), "citation_max_tokens", _CITATION_MAX_TOKENS))
                resp = await self._provider.complete(
                    messages=[Message(
                        role="user",
                        content=_CITATION_PROMPT.format(
                            filename=filename,
                            numbered_source=numbered,
                            section=section,
                            total_lines=total_lines,
                        ),
                    )],
                    temperature=0.0,
                    max_tokens=_max_tok,
                )
                raw = resp.text.strip() or section
                # Bug A fix: length-based sanity check replaces exact first-line match.
                # A response shorter than 80% of the section is likely structural garbage.
                if len(raw) < len(section) * _MAX_CITE_LEN_RATIO:
                    logger.warning(
                        "Pass 4 response for %s too short (%d vs %d chars) — using original section",
                        filename, len(raw), len(section),
                    )
                    await self._audit.write_event(
                        "citation_pass4_skipped",
                        metadata={"source": filename, "error": "response_too_short"},
                    )
                    return section, []
                # Structural check: if the response starts with JSON it is not a valid annotation.
                if raw.lstrip().startswith(('{', '[')):
                    logger.warning(
                        "Pass 4 response for %s looks like structured data — using original section",
                        filename,
                    )
                    await self._audit.write_event(
                        "citation_pass4_skipped",
                        metadata={"source": filename, "error": "response_not_markdown"},
                    )
                    return section, []
                # Secondary check: a key word from the section must appear in the response.
                _key_words = [w for w in section.replace("#", "").split() if len(w) >= 4]
                _key_word = _key_words[0].lower() if _key_words else ""
                if _key_word and _key_word not in raw.lower():
                    logger.warning(
                        "Pass 4 response for %s failed key-word check — using original section",
                        filename,
                    )
                    await self._audit.write_event(
                        "citation_pass4_skipped",
                        metadata={"source": filename, "error": "key_word_mismatch"},
                    )
                    return section, []
                annotated = raw
            except Exception as exc:
                logger.warning("Pass 4 citation annotation failed for %s: %s", filename, exc)
                await self._audit.write_event(
                    "citation_pass4_skipped",
                    metadata={"source": filename, "error": type(exc).__name__},
                )
                return section, []

        # Normalize single-line and multi-range citations to canonical N-N format
        # before extraction so they are not silently dropped or flagged as malformed.
        annotated = _normalize_citation_markers(annotated)

        # Safety clamp: remove citations whose start exceeds the source; clamp end
        # to total_lines so the LLM cannot produce out_of_range markers even when
        # it extrapolates chunk boundaries beyond the actual source length.
        def _clamp(m: re.Match) -> str:
            fname, start, end = m.group(1), int(m.group(2)), int(m.group(3))
            if start > total_lines:
                return ""
            if end > total_lines:
                end = total_lines
            return f"^[{fname}:{start}-{end}]"
        annotated = _CITATION_RE.sub(_clamp, annotated)

        # Bug B fix: case-insensitive filename comparison
        citations = [
            {
                "source_file": filename,
                "line_start": int(m.group(2)),
                "line_end": int(m.group(3)),
                "claim_excerpt": section.split("\n")[0][:_CITATION_EXCERPT_LEN],
            }
            for m in _CITATION_RE.finditer(annotated)
            if m.group(1).lower() == filename.lower()
        ]
        # Bug F fix: only cache when citations were actually produced
        if citations:
            await self._cache.set(ck, annotated)
        else:
            logger.warning(
                "Pass 4 produced no ^[filename:L-L] citations for %s — the configured model "
                "may not reliably follow the citation format. Consider switching to a more "
                "capable model (e.g. gemini-2.5-flash, minimax-m3, claude-haiku-4-5) for "
                "reliable citation annotation.",
                filename,
            )
            await self._audit.write_event(
                "citation_pass4_no_markers",
                metadata={"source": filename},
            )
        return annotated, citations

    async def _pick_routing_branch(self, slug: str, page: WikiPage, ri) -> str:
        """Ask LLM to select the best ROUTING.md branch for a newly created page."""
        from synthadoc.agents._routing import pick_routing_branches
        context = f"New page slug: {slug}\nTitle: {page.title}\nTags: {', '.join(page.tags)}"
        result = await pick_routing_branches(
            self._provider, ri.branches, context, multi=False
        )
        return result[0] if result else next(iter(ri.branches))

    async def _analyse(self, text: str, bust_cache: bool = False) -> dict:
        """Step 1 — analysis pass: entity extraction + summary + OKF type. Cached by content hash."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        ck = make_cache_key("analyse-v1", {"text_hash": text_hash}, version=ANALYSIS_CACHE_VERSION)
        if not bust_cache:
            cached = await self._cache.get(ck)
            if cached:
                return cached
        resp = await self._provider.complete(
            messages=[Message(role="user", content=f"{_ANALYSIS_PROMPT}{text[:3000]}")],
            temperature=0.0,
        )
        data = _parse_json_response(resp.text)
        if not isinstance(data, dict):
            data = {}
        data["entities"] = _coerce_str_list(data.get("entities", []))
        data["tags"] = _coerce_str_list(data.get("tags", []))
        data.setdefault("summary", text[:200])
        data.setdefault("relevant", True)
        data["_tokens"] = resp.total_tokens
        await self._cache.set(ck, data)
        return data

    async def _update_overview(self) -> None:
        """Regenerate wiki/overview.md from the 10 most-recently-modified pages."""
        if self._wiki_root is None:
            return
        wiki_dir = self._wiki_root / "wiki"
        pages = sorted(
            [p for p in wiki_dir.glob("*.md")
             if p.stem not in {"overview", "index", "dashboard", "log"}],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
        if not pages:
            return
        page_ctx = []
        for p in pages:
            snippet = p.read_text(encoding="utf-8")[:200].replace("\n", " ")
            page_ctx.append(f"- {p.stem}: {snippet}")
        pages_str = "\n".join(page_ctx)
        resp = await self._provider.complete(
            messages=[Message(role="user",
                              content=_OVERVIEW_PROMPT.format(pages=pages_str))],
            temperature=0.3,
            max_tokens=512,
        )
        _today = date.today().isoformat()
        content = (
            f"---\ntitle: Wiki Overview\nstatus: active\nconfidence: high\n"
            f"created: '{_today}'\nupdated: {_today}\n---\n\n"
            f"# Wiki Overview\n\n{resp.text.strip()}\n"
        )
        (wiki_dir / "overview.md").write_text(content, encoding="utf-8", newline="\n")

    def _staging_policy(self) -> str:
        return self._cfg.ingest.staging_policy if self._cfg else "off"

    def _write_or_stage(self, slug: str, page: "WikiPage", policy: str) -> bool:
        """Write page directly to wiki/ or to candidates/ when policy requires it.
        Returns True if staged, False if written directly."""
        if policy == "all" and self._wiki_root:
            from synthadoc.storage.wiki import WikiStorage as _WS
            cand_dir = self._wiki_root / "wiki" / "candidates"
            cand_dir.mkdir(exist_ok=True)
            _WS(cand_dir).write_page(slug, page)
            return True
        self._store.write_page(slug, page)
        self._search.invalidate_index()
        return False

    def _load_purpose(self) -> str:
        """Load wiki/purpose.md for scope filtering. Returns '' if absent."""
        if self._wiki_root is None:
            return ""
        p = self._wiki_root / "wiki" / "purpose.md"
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8")[:12000]

    def _hash(self, path: str) -> tuple[str, int]:
        data = Path(path).read_bytes()
        return hashlib.sha256(data).hexdigest(), len(data)

    def _needs_file_check(self, source: str) -> bool:
        """Return True when source must exist as a local file before ingestion."""
        return self._skill_agent.needs_path_resolution(source)

    async def _already_ingested(self, src_hash: str, src_size: int) -> bool:
        """Return True only if this source was ingested AND its wiki page still exists."""
        existing = await self._audit.find_by_hash(src_hash, src_size)
        if not existing:
            return False
        wiki_page = existing.get("wiki_page", "")
        return not wiki_page or self._store.page_exists(wiki_page)

    async def ingest(self, source: str, force: bool = False, bust_cache: bool = False) -> IngestResult:
        source = _canonical_source(source)
        result = IngestResult(source=source)

        if self._needs_file_check(source):
            p = Path(source).resolve()

            if not p.exists():
                raise FileNotFoundError(f"Source not found: {source}")
            if p.stat().st_size == 0:
                raise ValueError(f"Source file is empty: {source}")

            # Security: reject sources outside wiki_root.
            # Existence is checked first so that plain-text strings or typos
            # that get misclassified as paths produce FileNotFoundError (clear)
            # rather than PermissionError "outside wiki root" (misleading).
            if self._wiki_root is not None:
                root_resolved = self._wiki_root.resolve()
                try:
                    p.relative_to(root_resolved)
                except ValueError:
                    raise PermissionError(
                        f"Source {p} is outside wiki root {root_resolved}"
                    )

            # Dedup: hash + size (file sources only)
            src_hash, src_size = self._hash(str(p))

            # Check for hash collision (same hash, different size)
            if not force:
                existing = await self._audit.find_by_hash_only(src_hash)
                if existing and existing["size"] != src_size:
                    logger.warning(
                        "Hash collision detected: hash=%s matches existing record but size differs "
                        "(existing=%d, current=%d). Treating as new source.",
                        src_hash, existing["size"], src_size
                    )
                elif await self._already_ingested(src_hash, src_size):
                    result.skipped = True
                    result.skip_reason = "already ingested"
                    return result

            # Normalise to absolute path so the skill always receives an OS path,
            # not whatever vault-relative or CWD-relative string the caller passed in.
            source = str(p)

        # For URL / non-file sources p, src_hash, src_size are not set above.
        # Provide safe defaults so the audit call at the end always succeeds.
        if not self._needs_file_check(source):
            p = Path(_url_sidecar_name(source))
            _canonical = _canonical_source(source)
            src_hash = hashlib.sha256(_canonical.encode()).hexdigest()
            src_size = len(_canonical.encode())
            if not force and await self._already_ingested(src_hash, src_size):
                result.skipped = True
                result.skip_reason = "already ingested"
                return result

        # Web search decomposition: detect intent, decompose into keyword sub-queries,
        # fire N parallel Tavily searches, deduplicate URLs across results.
        try:
            _skill_meta = self._skill_agent.detect_skill(source)
            _is_web_search = _skill_meta.name == "web_search"
        except Exception:
            _is_web_search = False

        if _is_web_search:
            _bare_query = _WEB_INTENT_RE.sub("", source).strip() or source
            _sub_queries = await SearchDecomposeAgent(self._provider).decompose(_bare_query)
            _sub_results = await asyncio.gather(*[
                self._skill_agent.extract(f"search for: {q}") for q in _sub_queries
            ])
            _seen: set[str] = set()
            _merged_urls: list[str] = []
            for _r in _sub_results:
                for _url in _r.metadata.get("child_sources", []):
                    if _url not in _seen:
                        _seen.add(_url)
                        _merged_urls.append(_url)
            from synthadoc.skills.base import ExtractedContent as _EC
            extracted = _EC(
                text="", source_path=source,
                metadata={"child_sources": _merged_urls, "query": _bare_query,
                          "results_count": len(_merged_urls)},
            )
        else:
            _skill_timeout = (
                self._cfg.agents.llm_timeout_seconds
                if self._cfg and self._cfg.agents.llm_timeout_seconds > 0
                else None
            )
            if _skill_timeout:
                try:
                    extracted = await asyncio.wait_for(
                        self._skill_agent.extract(source), timeout=float(_skill_timeout)
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(
                        f"Skill extraction timed out after {_skill_timeout}s for source: {source}. "
                        f"Increase [agents] llm_timeout_seconds in .synthadoc/config.toml "
                        f"or skip image sources if your provider does not support vision."
                    )
            else:
                extracted = await self._skill_agent.extract(source)

        # Web search fan-out: return child sources; orchestrator enqueues them as jobs
        if extracted.metadata.get("child_sources"):
            result.child_sources = extracted.metadata["child_sources"]
            return result

        # If the skill returned a cleaner slug (e.g. YouTube's "youtube-{video_id}"),
        # use it as p so the sidecar and citation filename are meaningful and unique.
        # Without this, all YouTube URLs share the same sidecar name "watch" (from
        # the URL path segment "watch?v=…").
        if is_url(source) and not _is_web_search:
            _meta_slug = extracted.metadata.get("suggested_slug", "")
            if _meta_slug:
                p = Path(_slugify(_meta_slug))

        # Write text sidecar so the Obsidian Source Viewer can display extracted content.
        #   local file  → not is_url, not _is_web_search → sidecar from source path
        #   http/s URL  → is_url → sidecar keyed by URL slug (str(p))
        #   intent phrase ("search for: …") → _is_web_search=True → skip: the source string
        #     contains ":" which macOS treats as a path separator; content arrives via child_sources.
        #     (If Tavily returns no results the child_sources early-return was skipped, but we still
        #     must not attempt to write a sidecar with an intent phrase as the filename.)
        page_boundaries = extracted.metadata.get("page_boundaries", {})
        if not is_url(source) and not _is_web_search:
            self._write_sidecar(source, extracted.text, page_boundaries)
        elif is_url(source) and extracted.text:
            self._write_sidecar(str(p), extracted.text, page_boundaries)

        # Skill-level token costs (e.g. vision pre-pass in ImageSkill)
        if extracted.metadata.get("tokens_input"):
            result.tokens_used += extracted.metadata["tokens_input"] + extracted.metadata.get("tokens_output", 0)
            result.input_tokens += extracted.metadata["tokens_input"]
            result.output_tokens += extracted.metadata.get("tokens_output", 0)

        # Sanitize before any LLM call — strip injection vectors
        _clean_text, _san_warnings = _sanitize_source(extracted.text)
        if _san_warnings:
            logger.warning(
                "sanitizer stripped content from '%s': %s",
                source, ", ".join(_san_warnings),
            )
        extracted.text = _clean_text

        _max_chars = getattr(getattr(self._cfg, "ingest", None), "max_source_chars", 32000)
        _source_len = len(extracted.text)
        _truncated = _source_len > _max_chars
        text = extracted.text[:_max_chars]

        # Step 1: analysis pass (cached separately from decision)
        analysis = await self._analyse(text, bust_cache=bust_cache)
        result.tokens_used += analysis.pop("_tokens", 0)
        # input/output split not available for the analyse call (cached via _analyse)

        entities = _coerce_str_list(analysis.get("entities", []))
        tags = _coerce_str_list(analysis.get("tags", []))
        summary = analysis.get("summary", text[:1500])

        # Fallback: if LLM entity extraction returned nothing, extract key phrases
        # directly from the source text so BM25 always has meaningful search terms.
        if not entities:
            # English: capitalized noun phrases
            english = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', text[:2000])
            # CJK: 2–6 consecutive chars — shorter is too granular, longer risks full sentences
            cjk = re.findall(
                r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]{2,6}',
                text[:2000],
            )
            entities = list(dict.fromkeys(english + cjk))[:12]
            logger.debug("Entity extraction returned empty; using text-extracted phrases: %s", entities)

        # Pass 2: hybrid search
        candidates = self._search.bm25_search(entities + tags, top_n=self._max_pages)

        # Build page context: top 5 candidates with content snippets
        pages_ctx = []
        for r in candidates[:5]:
            page = self._store.read_page(r.slug)
            if page:
                snippet = page.content[:600].replace("\n", " ")
                status_label = page.status if isinstance(page.status, str) else page.status.value
                pages_ctx.append(f"[{r.slug}] status={status_label}: {snippet}")
        pages_str = "\n".join(pages_ctx) or "none"

        # Pass 3: decision (cached by text hash + candidate slugs + prompt hash)
        # prompt_hash is included so any change to purpose.md or the purpose_block
        # instructions automatically busts the cache.
        slugs = [r.slug for r in candidates]
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        decision_prompt = _DECISION_PROMPT
        if self._purpose:
            purpose_block = (
                f"Wiki scope (from purpose.md):\n{self._purpose}\n\n"
                "action=\"skip\" means the source is completely OUTSIDE the wiki's domain "
                "(e.g. spam, medical receipts, unrelated e-commerce). "
                "action=\"skip\" must NEVER be used because a topic is already covered by an "
                "existing page — that is what action=\"update\" is for. "
                "A source that covers the same topic as an existing page should ALWAYS be "
                "action=\"update\" (to add its unique perspective, examples, or depth) or "
                "action=\"create\" (if it introduces a distinct sub-topic). "
                "IMPORTANT: never skip based on source format — a YouTube video, podcast "
                "transcript, or lecture by a researcher in this domain must be ingested.\n\n"
            )
            decision_prompt = purpose_block + _DECISION_PROMPT
        prompt_hash = hashlib.sha256(decision_prompt.encode()).hexdigest()[:16]
        ck2 = make_cache_key(
            "make-decision",
            {"text_hash": text_hash, "slugs": slugs, "prompt_hash": prompt_hash},
            version=self._cache_version,
        )
        cached2 = None if bust_cache else await self._cache.get(ck2)
        if cached2:
            result.cache_hits += 1
            decisions = cached2
        else:
            resp2 = await self._provider.complete(
                messages=[Message(role="user", content=decision_prompt.format(
                    pages=pages_str,
                    source_text=text,
                    entities=entities,
                ))],
                temperature=0.0,
            )
            result.tokens_used += resp2.total_tokens
            result.input_tokens += resp2.input_tokens
            result.output_tokens += resp2.output_tokens
            decisions = _parse_json_response(resp2.text)
            await self._cache.set(ck2, decisions)

        # Pass 4: writes based on action
        action = decisions.get("action", "create")

        # Sources with a structured summary (e.g. YouTube) always get their own
        # page so the executive summary and transcript are not appended to an
        # existing page.  Override update → create and let the LLM-supplied
        # new_slug stand; fall back to a slug derived from the source path.
        if extracted.metadata.get("has_summary") and action == "update":
            action = "create"
            if not decisions.get("new_slug"):
                decisions["new_slug"] = p.stem.lower().replace(" ", "-")
            logger.info(
                "ingest: has_summary source forced to create (was update) — slug=%s",
                decisions["new_slug"],
            )

        logger.info(
            "ingest decision: source=%s action=%s target=%s new_slug=%s | %s",
            source[:80], action,
            decisions.get("target", "") or "-",
            decisions.get("new_slug", "") or "-",
            (decisions.get("reasoning", "") or "")[:200],
        )

        if action == "skip":
            logger.warning(
                "ingest skip: source=%s — LLM deemed out of scope. reasoning=%s",
                source[:80], (decisions.get("reasoning", "") or "")[:300],
            )
            result.skipped = True
            result.skip_reason = "out of scope (purpose.md)"
            # Record the current hash so lint doesn't mark the page stale on the
            # next run just because the audit DB never saw this file version.
            await self._audit.record_ingest(src_hash, src_size, source,
                                            p.stem, result.tokens_used, result.cost_usd)
            return result
        target = decisions.get("target", "")
        new_slug = decisions.get("new_slug") or ""
        update_content = decisions.get("update_content", "")
        page_content = decisions.get("page_content", "")
        title = (
            extracted.metadata.get("title")
            or p.stem.replace("-", " ").replace("_", " ").title()
        )

        citations: list[dict] = []
        final_slug: str = ""

        if action == "flag" and target and target not in LINT_SKIP_SLUGS and self._store.page_exists(target):
            with self._store.page_lock(target):
                page = self._store.read_page(target)
                if page:
                    page.status = "contradicted"
                    page.unresolved_note = None  # clear any previous auto-resolve failure
                    reasoning = decisions.get("reasoning", "")
                    page.contradiction_note = (
                        f"Flagged while ingesting '{p.name}': {reasoning}" if reasoning
                        else f"Flagged while ingesting '{p.name}'"
                    )
                    self._store.write_page(target, page)
                    self._search.invalidate_index()
            result.pages_flagged.append(target)

        elif action == "update" and target and self._store.page_exists(target):
            if not text and not update_content:
                logger.warning(
                    "ingest: update skipped for slug=%s — no extractable content from %s",
                    target, source[:80]
                )
                result.skipped = True
                result.skip_reason = "no extractable text"
            else:
                policy = self._staging_policy()
                staged = False
                with self._store.page_lock(target):
                    page = self._store.read_page(target)
                    if page:
                        # Reset stale pages to draft on re-ingest
                        if page.status == LifecycleState.STALE:
                            page.status = LifecycleState.DRAFT
                            self._stale_to_draft_slug = target
                        _backfill_okf_fields(page, analysis, source)
                        page.updated = date.today().isoformat()
                        if extracted.metadata.get("has_summary"):
                            section = extracted.text
                        elif update_content:
                            section = update_content
                        else:
                            section = f"## From {p.name}\n\n{text[:1000]}"
                        # Pass 0: append Key Data section for deterministic numerical preservation
                        _key_items = _extract_key_data(text)
                        if len(_key_items) >= _KEY_DATA_MIN_ITEMS:
                            key_section = "\n\n## Key Data\n\n" + "\n".join(f"- {item}" for item in _key_items)
                            section = section + key_section
                        # Scrub stale out-of-range citations from previous reingests
                        page.content = _scrub_source_citations(page.content, p.name, extracted.text)
                        # Pass 4: annotate only the new update section
                        section, citations = await self._annotate_citations(
                            section, extracted.text, p.name, bust_cache=bust_cache
                        )
                        page.content = page.content.rstrip() + f"\n\n{section}"
                        _append_source_ref(page, SourceRef(
                            file=source,
                            hash=src_hash or "",
                            size=_source_len,
                            ingested=date.today().isoformat(),
                            truncated=_truncated,
                        ))
                        staged = self._write_or_stage(target, page, policy)
                if staged:
                    logger.info("ingest: staged update to candidates slug=%s source=%s", target, source[:80])
                else:
                    logger.info("ingest: updated page slug=%s source=%s", target, source[:80])
                result.pages_updated.append(target)
                final_slug = target

        else:  # "create" or fallback
            # Don't create a page if there's no content to put in it
            if not text or not text.strip():
                logger.warning("Skipping page creation for %s — no text extracted", source)
                result.skip_reason = "no extractable text"
                result.skipped = True
            else:
                # Reject slugs that look like wiki syntax artifacts rather than real topics
                raw_slug = _slugify(new_slug or title)
                slug = raw_slug if raw_slug not in _SLUG_BLACKLIST else _slugify(title)
                # If title-based fallback is also blacklisted (e.g. URL path "watch"),
                # use the skill's suggested_slug or a hash-based ID rather than writing
                # a page with a generic, meaningless slug.
                if slug in _SLUG_BLACKLIST:
                    suggested = _slugify(extracted.metadata.get("suggested_slug", ""))
                    slug = suggested if suggested and suggested not in _SLUG_BLACKLIST \
                        else f"source-{src_hash[:12]}"

                if self._store.page_exists(slug):
                    # Slug already exists — never overwrite; append as update instead
                    policy = self._staging_policy()
                    staged = False
                    with self._store.page_lock(slug):
                        page = self._store.read_page(slug)
                        if page:
                            # Reset stale pages to draft on re-ingest
                            if page.status == LifecycleState.STALE:
                                page.status = LifecycleState.DRAFT
                                self._stale_to_draft_slug = slug
                            _backfill_okf_fields(page, analysis, source)
                            page.updated = date.today().isoformat()
                            if extracted.metadata.get("has_summary"):
                                section = extracted.text
                            else:
                                section = f"## From {p.name}\n\n{text[:1500]}"
                            # Pass 0: append Key Data section for deterministic numerical preservation
                            _key_items = _extract_key_data(text)
                            if len(_key_items) >= _KEY_DATA_MIN_ITEMS:
                                key_section = "\n\n## Key Data\n\n" + "\n".join(f"- {item}" for item in _key_items)
                                section = section + key_section
                            # Scrub stale out-of-range citations from previous reingests
                            page.content = _scrub_source_citations(page.content, p.name, extracted.text)
                            # Pass 4: annotate only the new section
                            section, citations = await self._annotate_citations(
                                section, extracted.text, p.name, bust_cache=bust_cache
                            )
                            page.content = page.content.rstrip() + f"\n\n{section}"
                            _append_source_ref(page, SourceRef(
                                file=source,
                                hash=src_hash or "",
                                size=_source_len,
                                ingested=date.today().isoformat(),
                                truncated=_truncated,
                            ))
                            staged = self._write_or_stage(slug, page, policy)
                    if staged:
                        logger.info("ingest: staged update to candidates slug=%s source=%s", slug, source[:80])
                    else:
                        logger.info("ingest: updated existing page slug=%s source=%s", slug, source[:80])
                    result.pages_updated.append(slug)
                    final_slug = slug
                else:
                    if extracted.metadata.get("has_summary"):
                        body = extracted.text
                    elif page_content.strip():
                        body = _strip_leading_frontmatter(page_content)
                    else:
                        body = f"# {title}\n\n{text[:4000]}"
                    # Pass 0: append Key Data section for deterministic numerical preservation
                    _key_items = _extract_key_data(text)
                    if len(_key_items) >= _KEY_DATA_MIN_ITEMS:
                        key_section = "\n\n## Key Data\n\n" + "\n".join(f"- {item}" for item in _key_items)
                        body = body + key_section
                    # Pass 4: annotate the full new page body
                    body, citations = await self._annotate_citations(
                        body, extracted.text, p.name, bust_cache=bust_cache
                    )
                    # Prefer H1 from generated body over source-derived title
                    _h1 = re.search(r"^# (.+)", body, re.MULTILINE)
                    page_title = _h1.group(1).strip() if _h1 else title
                    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                    new_page = WikiPage(
                        title=page_title, tags=tags,
                        content=body,
                        status="draft", confidence="medium",
                        sources=[SourceRef(
                            file=source,
                            hash=src_hash or "",
                            size=_source_len,
                            ingested=today,
                            truncated=_truncated,
                        )],
                        created=today,
                        type=analysis.get("type") or None,
                        resource=source if is_url(source) else None,
                    )

                    # Staging fork: route to candidates/ based on policy
                    policy = self._staging_policy()
                    go_to_candidates = (policy == "all") or (
                        policy == "threshold"
                        and self._cfg is not None
                        and not _confidence_passes_threshold(
                            new_page.confidence,
                            self._cfg.ingest.staging_confidence_min,
                        )
                    )

                    if go_to_candidates and self._wiki_root:
                        from synthadoc.storage.wiki import WikiStorage as _WS
                        cand_dir = self._wiki_root / "wiki" / "candidates"
                        cand_dir.mkdir(exist_ok=True)
                        _WS(cand_dir).write_page(slug, new_page)
                        logger.info("ingest: staged to candidates slug=%s source=%s", slug, source[:80])
                        result.pages_created.append(slug)
                        final_slug = slug
                    else:
                        with self._store.page_lock(slug):
                            self._store.write_page(slug, new_page)
                            self._search.invalidate_index()
                        logger.info("ingest: created page slug=%s source=%s", slug, source[:80])
                        result.pages_created.append(slug)
                        final_slug = slug
                        self._store.append_to_index(slug, new_page.title)
                        if self._routing_path:
                            from synthadoc.core.routing import RoutingIndex
                            ri = RoutingIndex.parse(self._routing_path)
                            if ri.branches:
                                branch = await self._pick_routing_branch(slug, new_page, ri)
                                ri.add_slug(slug, branch)
                                ri.save(self._routing_path)

        # On force reingest, propagate updated truncated/size to any other page that
        # still holds a SourceRef for the same URL (e.g. the old page when the LLM
        # chose action=create for a source it previously appended to a different page).
        if bust_cache and final_slug and "://" in source:
            _propagate_source_update(self._store, source, _truncated, _source_len, final_slug)

        if result.pages_created or result.pages_updated:
            await self._update_overview()

        self._log.log_ingest(source=p.name,
                             pages_created=result.pages_created,
                             pages_updated=result.pages_updated,
                             pages_flagged=result.pages_flagged,
                             tokens=result.tokens_used,
                             cost_usd=result.cost_usd,
                             cache_hits=result.cache_hits)
        _wiki_page = (result.pages_created + result.pages_updated
                      + result.pages_flagged or [title])[0]
        await asyncio.gather(
            self._audit.record_ingest(src_hash, src_size, source,
                                      _wiki_page, result.tokens_used, result.cost_usd),
            self._audit.record_claim_citations(final_slug or _wiki_page, citations)
            if citations else asyncio.sleep(0),
        )
        if self._audit:
            if result.pages_created:
                await self._audit.set_page_state(final_slug or _wiki_page, LifecycleState.DRAFT, TriggerSource.INGEST)
                await self._audit.record_lifecycle_event(
                    final_slug or _wiki_page, None, LifecycleState.DRAFT,
                    "new page created by ingest", TriggerSource.INGEST
                )
            elif result.pages_updated and getattr(self, "_stale_to_draft_slug", None):
                await self._audit.set_page_state(self._stale_to_draft_slug, LifecycleState.DRAFT, TriggerSource.INGEST)
                await self._audit.record_lifecycle_event(
                    self._stale_to_draft_slug, LifecycleState.STALE, LifecycleState.DRAFT,
                    "re-ingest of stale page", TriggerSource.INGEST
                )
        return result
