# Synthadoc — Design Document

**Version:** 0.5.0 (released 2026-05-21)  
**Audience:** Product users who want to understand how the system works; developers adding features, skills, and plugins.

**Document owners:** Paul Chen, William Johnason

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Concepts](#2-core-concepts)
3. [System Architecture](#3-system-architecture)
4. [Agents](#4-agents)
5. [Skills System](#5-skills-system)
6. [Storage](#6-storage)
7. [HTTP API](#7-http-api)
8. [Obsidian Plugin](#8-obsidian-plugin)
9. [CLI](#9-cli)
10. [Configuration](#10-configuration)
11. [Hook System](#11-hook-system)
12. [Cache System](#12-cache-system)
13. [Cost Guard](#13-cost-guard)
14. [Job Queue](#14-job-queue)
15. [Observability and Logging](#15-observability-and-logging)
16. [Security](#16-security)
17. [Plugin Development Guide](#17-plugin-development-guide)
18. [Routing](#18-routing)
19. [Candidates Staging](#19-candidates-staging)
20. [Context Packs](#20-context-packs)
21. [Adversarial Review](#21-adversarial-review)
22. [Claim-Level Provenance](#22-claim-level-provenance)
23. [Lifecycle Machine](#23-lifecycle-machine)

**Appendices**
- [Appendix A — Release Feature Index](#appendix-a--release-feature-index)

---

## 1. Overview

Synthadoc is a **domain-agnostic LLM knowledge compilation engine**. It reads raw source documents and uses an LLM to synthesize them into a persistent structured wiki. Knowledge is compiled at **ingest time** — not at query time. The compiled wiki lives as plain Markdown files that are readable and editable without any tool running.

**Key design principles:**

- **Ingest-time compilation** — synthesis, cross-referencing, and contradiction detection happen once per source, not on every query.
- **Local-first** — all data stays on disk; the server binds only to `127.0.0.1`.
- **Obsidian-native** — wiki pages are valid Obsidian notes with `[[wikilinks]]`, YAML frontmatter, and Dataview compatibility.
- **Layered access** — CLI, HTTP REST API, and MCP server expose the same operations; the agent and storage logic is shared.
- **Extensible by design** — skills (file formats) and providers (LLM backends) are loaded as plugins; no core changes needed to add either.

---

## 2. Core Concepts

### Wiki

A self-contained knowledge base rooted at a filesystem directory. Contains:

```
my-wiki/
  wiki/               ← compiled Markdown pages
  raw_sources/        ← original source documents
  hooks/              ← wiki-specific hook scripts
  AGENTS.md           ← LLM instructions for this domain
  log.md              ← human-readable activity log
  .synthadoc/
    config.toml       ← per-project configuration
    audit.db          ← immutable audit trail
    jobs.db           ← job queue
    cache.db          ← LLM response cache
    embeddings.db     ← BM25 + vector search index
    extracted/        ← plain-text sidecars for ingested local sources (v0.5.0)
      report.txt      ← extracted text for report.pdf (or .docx, .xlsx, etc.)
      report.pdf.pagemap.json  ← PDF page-boundary map (PDF sources only)
    logs/
      synthadoc.log   ← rotating JSON-lines operational log
      traces.jsonl    ← OpenTelemetry traces
```

### Wiki Page

A Markdown file in `wiki/` with YAML frontmatter:

```yaml
---
title: Alan Turing
tags: [computer-science, cryptography, turing-test]
status: active          # active | contradicted | archived
confidence: high        # high | medium | low
created: '2026-04-10'
sources:
  - file: turing-biography.pdf
    hash: sha256:abc123…
    size: 204800
    ingested: '2026-04-10'
---

# Alan Turing

Content with [[wikilinks]] to related pages…
```

**`status` values:**

| Value | Meaning |
|-------|---------|
| `draft` | Newly compiled — not yet lint-reviewed |
| `active` | Lint-reviewed, current, trusted |
| `contradicted` | A new source conflicts with this page; needs resolution |
| `stale` | Source file changed since last ingest |
| `archived` | Source removed or manually retired |

New pages are created with `status: draft`. Lint promotes them to `active` automatically when all checks pass. See [§23 Lifecycle Machine](#23-lifecycle-machine) for full transition rules.

**`lint_warnings`** _(added in v0.5.0)_ — list of adversarial review findings written to frontmatter after each lint run:

```yaml
lint_warnings:
  - claim: "Saved over fourteen million lives."
    concern: "This specific figure lacks scholarly consensus…"
```

Cleared automatically when `--no-adversarial` is passed to `lint run`.

### Job

Every ingest, lint, and scheduled operation runs as a job:

```
pending → in_progress → completed
                      → failed
                      → dead
                      → skipped
pending → cancelled
```

Jobs persist across server restarts. See [§14 Job Queue](#14-job-queue) for full state transition rules, retry backoff, and status descriptions.

### Slug

The filename without extension, derived from the page title. ASCII-safe and CJK-aware:

- Lowercase, hyphens for separators
- Unicode accents decomposed (NFKD)
- CJK characters (Chinese, Japanese, Korean) preserved as-is
- Slug blacklist blocks reserved words (`wiki`, `obsidian`, `index`, `dashboard`, `wikilinks`)
- Collisions resolved by appending `-2`, `-3`, etc.

---

## 3. System Architecture

### Component Map

![Synthadoc Architecture](png/architecture.png)

### Request lifecycle (ingest via CLI)

1. `synthadoc ingest report.pdf -w my-wiki`
2. CLI posts `POST /jobs/ingest {source: "report.pdf"}` to `localhost:7070`
3. HTTP server validates path, writes job to `jobs.db` with status `pending`, returns `{job_id}`
4. Background worker picks up job within 2 seconds
5. Orchestrator instantiates IngestAgent, checks CostGuard
6. SkillAgent detects `.pdf`, lazy-loads `PdfSkill`, extracts text
7. IngestAgent Step 1 — Analysis: `_analyse()` extracts entities, tags, and a 3-sentence summary (cached under key `analyse-v1`)
8. IngestAgent Step 2 — Decision: LLM reads the summary (not raw text) + BM25-retrieved candidate pages + `purpose.md` scope, decides per-page action (`create` / `update` / `skip` / `flag_contradiction`)
9. IngestAgent Step 3 — Write: applies actions; updates frontmatter; writes `[[wikilinks]]`; fires hooks
10. IngestAgent Step 4 — Overview: if any pages were created or updated, regenerates `wiki/overview.md`
11. Job transitions to `completed`; `log.md` updated; `audit.db` record written

---

## 4. Agents

All agents are async Python classes. They receive a job context, write results to storage, and return a summary. Agents never call each other directly — they are dispatched by the Orchestrator.

### IngestAgent

Five-pass pipeline:

| Pass | Model | Purpose |
|------|-------|---------|
| 0 — Vision (optional) | Default | Extract text from image sources (`is_image=True`); requires a vision-capable provider |
| 1 — Analysis (`_analyse()`) | Default | Extract entities, tags, and a 3-sentence summary from raw text. Result cached under key `analyse-v1` keyed by SHA-256 of the text. |
| 2 — Candidate search | None (BM25) | Find existing wiki pages related to extracted entities |
| 3 — Decision | Default | LLM reads summary (not full text) + BM25 candidates + `purpose.md` scope. Outputs per-page action: `create`, `update`, `flag`, `skip` |
| 4 — Citation annotation (`_annotate_citations()`) | Default | For each page section being written, the LLM reads the section alongside the numbered source text and inserts `^[filename:L-L]` inline citation markers at the end of substantive paragraphs. Results cached by section SHA-256. Falls back gracefully (returns original section) on any LLM or parse failure — ingest always completes. Citations are recorded in `audit.db` `claim_citations` table. |
| 5 — Write | None | Apply actions; update frontmatter; write `[[wikilinks]]`; fire hooks. For local sources, writes a `.txt` sidecar to `.synthadoc/extracted/` (all file types) and a pagemap JSON sidecar when PDF page boundaries are available. |
| 6 — Overview | Default | Regenerate `wiki/overview.md` if any pages were created or updated |

**Analysis caching:** The analysis step is expensive (full text read + LLM call). Results are cached in `cache.db` by text SHA-256. Subsequent ingests of the same source (e.g. after a `--force` that hits the decision cache miss) re-use the analysis result without a new LLM call.

**purpose.md scope filtering:** IngestAgent reads `wiki/purpose.md` at init. Its content is prepended to the decision prompt. The LLM can respond with `action="skip"` when the source is clearly outside the wiki's stated scope. If `purpose.md` is absent, all sources are accepted.

**overview.md auto-maintenance:** After any ingest that creates or updates pages, IngestAgent calls `_update_overview()`, which reads the 10 most-recently-modified wiki pages and asks the LLM to write a 2-paragraph overview of the entire wiki. The result is saved to `wiki/overview.md` with `status: auto` frontmatter. This page is excluded from contradiction detection and orphan checks.

**Web search fan-out:** When a source is routed to the `web_search` skill, `ExtractedContent.metadata["child_sources"]` contains the top result URLs. IngestAgent detects this and returns early with the URL list; the Orchestrator enqueues each URL as a separate ingest job. This keeps the web search skill stateless and the queue the single source of work.

**Deduplication:** Every source tracked by SHA-256 in `audit.db`. Hash match → skip. Use `--force` to bypass.

**Slug derivation:**

```python
def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(
        r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+",
        "-", normalized.lower(),
    ).strip("-")
    return slug or "page-" + hashlib.md5(title.encode()).hexdigest()[:8]
```

**Contradiction flagging:** When Pass 3 returns `flag_contradiction`, the page's frontmatter is updated to `status: contradicted`, both the old claim and new conflicting claim are preserved with `⚠` markers and citations.

**CJK support:** Entity extraction falls back to CJK 2–6 char sequence regex when SpaCy is unavailable. `_slugify` preserves CJK characters. BM25 tokenizer handles CJK unigrams.

### QueryAgent

#### Query Decomposition

**Pipeline:**

```
Question
 → Call 1: decompose() — LLM splits question into 1–N sub-questions (cap=4)
   └─ on any LLM error: fall back to [question]          graceful degradation
 → parallel BM25 search per sub-question                 asyncio.gather()
 → merge candidates — best score wins per slug           deduplication
 → Call 2: LLM synthesises answer from merged context    unchanged from v0.1
 → record_query() in audit.db                            cost + history tracking
 → log_query() in activity log                           operator visibility
```

**Decomposition behaviour:**
- Simple questions decompose to a single sub-question — identical behaviour to v0.1
- Compound questions (e.g. "Who invented FORTRAN and what was the Bombe machine?") decompose into one sub-question per part — each part retrieved independently, pages merged before synthesis
- Comparative questions (e.g. "Compare Turing's contributions with Von Neumann's") retrieve both subjects in parallel
- The LLM returns a JSON array of strings. Markdown code fences (` ```json ``` `) are stripped before parsing — required for cross-model robustness (some providers wrap JSON in fences despite instructions)
- On any failure during decomposition (network error, invalid JSON, empty list, non-array response), the agent falls back silently to `[question]` — the query always completes

**BM25 corpus cache:** `HybridSearch` builds the BM25 corpus once per server session and caches it in memory (`_cached_corpus`). The cache is invalidated by `invalidate_index()` after every `write_page()` call in IngestAgent, so queries always see current wiki content without redundant disk reads.

#### Knowledge Gap Workflow

After the BM25 merge step, a knowledge gap is detected when ANY of three independent signals fire (gap is skipped when `gap_score_threshold = 0`):

1. `len(candidates) < 3` — wiki has almost nothing on the topic
2. `max_score < gap_score_threshold` (default: `2.0`, configurable via `[query] gap_score_threshold` in `config.toml`) — low keyword overlap
3. Fewer than 2 candidates contain any key noun from the question with sufficient frequency — corpus-relative BM25 scores can be inflated by shared vocabulary; this content-overlap check catches off-topic matches

When a gap fires:

1. `SearchDecomposeAgent.decompose(question)` is called to generate 1–4 focused keyword search strings
2. `QueryResult.knowledge_gap = True` and `QueryResult.suggested_searches = [...]` are set
3. The CLI appends a `[!tip] Knowledge Gap Detected` Obsidian callout with:
   - Obsidian Command Palette path (primary)
   - `synthadoc ingest "search for: ..."` terminal commands (with `-w`)
4. The API response includes `knowledge_gap` and `suggested_searches` fields
5. The Obsidian `QueryModal` renders the same callout using `MarkdownRenderer.render()`

When no gap is detected, `suggested_searches` is `[]` and no callout is shown.

---

### Web Search Decomposition (v0.2.0)

> **Note:** Implementation is in `docs/plans/web-search-decomposition-v0.2.md`. This section describes the delivered behavior.

**Motivation:** The v0.1 web search feature (`synthadoc ingest "search for: <topic>"`) fired a single Tavily API call for the entire input phrase. Decomposing the search intent into multiple focused keyword queries before fetching produces richer, more targeted pages — each sub-query targets a different aspect of the topic.

**Pipeline:**

```
User input: "search for: yard gardening in Canadian climate zones"
 → IngestAgent detects web_search skill
 → strip intent prefix → "yard gardening in Canadian climate zones"
 → SearchDecomposeAgent.decompose() — LLM returns terse keyword strings
   e.g. ["Canada hardiness zones map",
         "planting guide by province Canada",
         "frost dates Canadian cities"]
 → asyncio.gather() — N parallel Tavily API calls
 → deduplicate URLs across results (first-seen wins, order preserved)
 → merged child_sources → existing fan-out unchanged
```

**Key design decisions:**
- Uses a **separate prompt** from `QueryAgent.decompose()` — query decomposition asks "what distinct *questions* does this ask?" (natural-language sub-questions) while search decomposition asks "what distinct *search strings* would find the best authoritative sources?" (terse keyword phrases). The outputs are fundamentally different — they must not share a prompt.
- Implemented as `SearchDecomposeAgent` in `synthadoc/agents/search_decompose_agent.py` — kept separate to avoid coupling the two decomposition strategies.
- Cap: 4 search strings maximum — prevents runaway Tavily API spend.
- Fallback: if LLM call fails, JSON is invalid, or all entries are whitespace, use the original phrase as a single search query — the ingest always completes.

### Semantic Re-ranking

> **Opt-in.** BM25 is the default and works without any additional dependencies.

**Installation:**

```bash
pip install fastembed
```

**Enable in config:**

```toml
[search]
vector = true
vector_top_candidates = 20   # BM25 candidate pool; top_n returned after re-ranking
```

**Embedding model:** `BAAI/bge-small-en-v1.5` (~130 MB), managed by `fastembed`. Downloaded once on the first server start with `vector = true`; cached at `~/.cache/fastembed/` thereafter.

**On first enable**, the server prints and logs:

```
Vector search enabled — downloading embedding model BAAI/bge-small-en-v1.5 (~130 MB)
to ~/.cache/fastembed/. This is a one-time download.
```

**Search flow (when `vector = true`):**

1. BM25 retrieves top `vector_top_candidates` (default 20) candidates
2. The query is embedded; cosine similarity is computed against each candidate's stored vector
3. Results are re-ranked by vector score; top `top_n` (default 8) are returned to the caller

**Migration:** On first enable, a background task embeds all existing wiki pages into `embeddings.db`. BM25 continues to serve all queries during migration — no downtime. Progress is logged every 50 pages. New pages are embedded immediately on write.

**Fallback:** If `embeddings.db` is empty, the model is unavailable, or `fastembed` is not installed, BM25 ranking is used automatically with no error.

**Performance notes:**
- First enable on a large wiki may take several minutes to embed all pages. Subsequent server starts are instant (model and embeddings already cached).
- The re-ranking step is CPU-only and adds single-digit milliseconds per query after migration.
- Set `vector = false` to revert to BM25-only at any time. Existing embeddings are not deleted.

---

### LintAgent

Runs against the entire wiki or a scoped subset:

| Check | What it finds |
|-------|---------------|
| Contradiction | Pages with `status: contradicted` |
| Orphan | Pages with zero inbound `[[wikilinks]]` |
| Stale | Pages whose `sources[]` entries no longer exist on disk |
| Missing link | Entity mentioned in page body but no wikilink created |
| Adversarial review _(v0.5.0)_ | Independent LLM pass that flags overstated claims, unsupported assertions, and high-confidence statements the source material does not support |
| Lifecycle — archived detection _(v0.6.0)_ | Source file no longer on disk → transition page to `archived` |
| Lifecycle — stale detection _(v0.6.0)_ | SHA-256 hash of source on disk ≠ recorded ingest hash → transition page to `stale` |
| Lifecycle — draft promotion _(v0.6.0)_ | `draft` page with no active issues → transition to `active` |
| Lifecycle — manual-edit sync _(v0.6.0)_ | Frontmatter `status` differs from `page_states` DB record → reconcile DB to match |

**Auto-resolution:** For contradictions, LintAgent asks the LLM to propose a resolution with a confidence score. If score ≥ `auto_resolve_confidence_threshold` (default 0.85), applies automatically. Below threshold, queues for human review.

**Index suggestion:** For orphan pages, LintAgent reads the page frontmatter and generates a ready-to-paste `wiki/index.md` entry: `- [[slug]] — tag1, tag2, tag3`.

**Orphan frontmatter sync:** After computing orphans, both `LintAgent.lint()` (server-side, via `POST /jobs/lint`) and `synthadoc lint report` (CLI, offline) write `orphan: true` or `orphan: false` to each eligible page's YAML frontmatter. This keeps the Obsidian Dataview query (`WHERE orphan = true`) in sync with the computed orphan state without requiring the server to be running after `lint report`.

**Auto-generated page exclusions:** The pages `index`, `dashboard`, `overview`, `log`, and `purpose` are excluded from both orphan detection and contradiction checking. Links from these pages do not count as real inbound references — a page linked only from `overview.md` is still reported as an orphan. These pages are also never flagged as contradicted by the ingest pipeline.

**Adversarial review _(v0.5.0)_:** After structural checks complete, `LintAgent` runs an independent LLM review of every non-excluded page concurrently via `asyncio.gather()` — a 100-page wiki completes in wall-clock time equal to one call. The adversarial provider is configured via `[agents].adversarial` (falls back to `[agents].default` if absent); using a different model family from the ingest model reduces self-serving bias. Results are stored as `lint_warnings: [{claim, concern}]` in each page's YAML frontmatter. The cap is `adversarial_max_per_page` (default 2). Rate-limit failures are caught per-page and stored as non-fatal entries. Skipped entirely when `--no-adversarial` is passed to `lint run`; in that case, existing `lint_warnings` are cleared from all pages.

### SkillAgent

Dispatches to the correct skill based on file extension, URL prefix, or intent keyword match. Manages 3-tier lazy loading. Returns `ExtractedContent` to IngestAgent.

When a source is a URL or an intent phrase (e.g. `search for: Dennis Ritchie`), IngestAgent skips the local file checks — there is no file to verify or hash. File-existence validation and SHA-256 dedup only apply to local file paths.

### ExportAgent

Serialises the wiki to one of four formats with zero additional LLM calls. Invoked via `synthadoc export --format <fmt>` or the Obsidian **Export Wiki** command.

| Format | Output |
|--------|--------|
| `llms.txt` | Active pages as a compact index (title + first-line summary) in the [llmstxt.org](https://llmstxt.org) spec; pages with `contradicted` or `stale` status appear in a **Needs Review** section |
| `llms-full.txt` | Full page content for all pages, separated by `---` dividers with status and confidence headers; no size limit |
| `graphml` | Directed wikilink graph — one node per page, one edge per `[[wikilink]]`; includes `label` (Gephi), `y:NodeLabel` (yEd), status, confidence, orphan flag, inbound link count, and routing branch per node |
| `json` | Full structured dump: content, tags, sources, claims (from audit DB), lifecycle history, routing branch memberships, per-page `ingest_cost_usd` and `ingest_tokens`, and total compilation cost |

**Status filter:** All formats accept `--status-filter active|contradicted|stale|archived|draft|all` (default `all`) to scope the export to a lifecycle subset.

**GraphML tool compatibility:** The file includes both a standard `label` data key (read by Gephi and Cytoscape) and a `y:ShapeNode/y:NodeLabel` element (read by yEd). No position data is embedded — run the tool's own layout algorithm after import.

---

## 5. Skills System

Skills extract text from source documents. They are Python classes that subclass `BaseSkill` (`synthadoc/skills/base.py`, Apache-2.0).

### Folder-based skill structure

Each skill is a self-contained directory:

```
pdf/
  SKILL.md          ← YAML frontmatter (parsed by engine) + Markdown body (for humans/LLMs)
  scripts/
    main.py         ← BaseSkill subclass; entry point declared in SKILL.md
  assets/           ← data files bundled with the skill (optional)
  references/       ← reference documents loaded via get_resource() (optional)
```

**`SKILL.md` frontmatter schema:**

```yaml
name: pdf
version: "1.0"
description: Extract text from PDF documents
entry:
  script: scripts/main.py
  class: PdfSkill
triggers:
  extensions: [".pdf"]
  intents: ["pdf", "research paper", "document"]
requires: [pypdf, pdfminer.six]
```

The Markdown body is for human readers and LLMs — never engine-parsed. Use it to document usage, edge cases, and references.

### 3-Tier Lazy Loading

| Tier | What loads | When |
|------|-----------|------|
| 1 — Metadata | `SkillMeta` parsed from `SKILL.md` frontmatter | Always; startup |
| 2 — Body | Full skill class via `importlib.util` | When a matching source is encountered |
| 3 — Resources | Files from `assets/` or `references/` via `get_resource()` | On first access within the skill |

This means importing 20 skills costs essentially zero memory until they are needed.

### Registry cache

`SkillAgent` writes `skill_registry.json` to `<wiki-root>/.synthadoc/` on init. Each entry stores the `SKILL.md` mtime; on subsequent startups, unchanged entries are deserialised without re-parsing YAML (warm start). New, changed, or deleted skill folders are detected automatically.

### Intent-based dispatch

`detect_skill(source)` matches against `triggers.extensions` (file suffix or URL prefix) **and** `triggers.intents` (substring match on lowercased source string). This enables purely intent-driven skills with no file extension — e.g., `web_search` triggers on `"search for"`, `"look up"`, `"find on the web"`, etc.

For URL sources, **longest prefix wins**: the matched extension string length determines priority. A skill with prefix `https://www.youtube.com/` (28 chars) takes priority over the generic URL skill prefix `https://` (8 chars). This makes Tavily web search results that happen to be YouTube links automatically routed to the YouTube skill without any special-case logic.

### Built-in Skills

| Skill | Extensions | Intent phrases | Notes |
|-------|-----------|---------------|-------|
| `pdf` | `.pdf` | `pdf`, `research paper`, `document` | pypdf primary; pdfminer.six fallback if yield < 50 chars/page |
| `url` | `http://`, `https://` | `fetch url`, `web page`, `website` | httpx fetch + BeautifulSoup clean |
| `markdown` | `.md`, `.txt` | `markdown`, `text file`, `notes` | Direct read |
| `docx` | `.docx` | `word document`, `docx` | python-docx |
| `pptx` | `.pptx` | `powerpoint`, `presentation`, `pptx` | python-pptx; each slide rendered as a titled section; speaker notes appended when present |
| `xlsx` | `.xlsx`, `.csv` | `spreadsheet`, `excel`, `csv` | openpyxl |
| `image` | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff` | `image`, `screenshot`, `diagram`, `photo` | Base64 + vision LLM |
| `web_search` | _(none)_ | `search for`, `find on the web`, `look up`, `web search`, `browse` | Calls Tavily API; returns top result URLs as child sources enqueued individually. Requires `TAVILY_API_KEY`. |
| `youtube` | `https://www.youtube.com/`, `https://youtu.be/` | `youtube video`, `youtube lecture`, `youtube talk` | Extracts captions via YouTube caption system; no API key or audio download needed. Generates an executive summary (what the video covers, main topics, key takeaway) followed by the full timestamped transcript. Skips gracefully when no captions are available. |

### Custom Skill Locations

Skills are discovered from five locations in priority order:

| Source | Path | Override priority |
|--------|------|------------------|
| `extra_dirs` (programmatic) | Passed at `SkillAgent()` init | Highest |
| Local wiki | `<wiki-root>/skills/` | High |
| Global user | `~/.synthadoc/skills/` | Medium |
| pip entry points | `entry_points('synthadoc.skills')` | Low |
| Built-in | Ships with package (`synthadoc/skills/`) | Lowest |

No server restart needed — registry cache detects changes automatically on next startup.

### BaseSkill Interface

```python
# synthadoc/skills/base.py  (Apache-2.0)
@dataclass
class Triggers:
    extensions: list[str]   # e.g. [".pdf"] or ["http://", "https://"]
    intents:    list[str]   # e.g. ["search for", "look up"]

@dataclass
class SkillMeta:
    name: str
    description: str
    version: str
    entry_script: str       # relative path within skill_dir
    entry_class: str        # class name in that script
    triggers: Triggers
    requires: list[str]     # pip distribution names
    skill_dir: Path = None  # set by SkillAgent after loading

@dataclass
class ExtractedContent:
    text: str
    source_path: str
    metadata: dict = field(default_factory=dict)

class BaseSkill(ABC):

    @abstractmethod
    async def extract(self, source: str) -> ExtractedContent: ...

    def get_resource(self, filename: str) -> str:
        """Load a file from assets/ or references/ within the skill folder."""
        ...
```

---

## 6. Storage

### wiki/ — Page files

Plain Markdown. One file per page. Filename = slug + `.md`. Frontmatter is YAML between `---` delimiters. Body uses standard Markdown with `[[wikilinks]]` for internal references.

### audit.db — Immutable audit trail

SQLite. Two key tables:

**`ingest_log`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `source` | TEXT | Original path or URL |
| `hash` | TEXT | `sha256:<hex>` |
| `size` | INTEGER | Bytes |
| `cost_usd` | REAL | |
| `tokens` | INTEGER | |
| `pages_created` | TEXT | JSON array of slugs |
| `pages_updated` | TEXT | JSON array of slugs |
| `ingested_at` | TEXT | UTC ISO-8601 |

**`audit_events`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `event` | TEXT | e.g. `contradiction_found`, `auto_resolved`, `cost_gate_triggered` |
| `details` | TEXT | JSON |
| `recorded_at` | TEXT | UTC ISO-8601 |

**`queries`** _(added in v0.2.0)_

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `question` | TEXT | Original question text |
| `sub_questions_count` | INTEGER | Number of sub-questions decomposed (1 for simple questions) |
| `tokens` | INTEGER | Answer call token usage |
| `cost_usd` | REAL | Approximate cost (answer tokens × rate) |
| `queried_at` | TEXT | UTC ISO-8601 |

**`claim_citations`** _(added in v0.5.0)_

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `page_slug` | TEXT | Wiki page the citation belongs to |
| `source_file` | TEXT | Filename of the raw source (basename only) |
| `line_start` | INTEGER | First line of the supporting passage |
| `line_end` | INTEGER | Last line of the supporting passage |
| `claim_excerpt` | TEXT | First ~100 chars of the annotated paragraph (for display) |
| `ingested_at` | TEXT | UTC ISO-8601 |

**`page_states`** _(added in v0.6.0)_

Fast slug-keyed current state index. One row per wiki page.

| Column | Type | Notes |
|--------|------|-------|
| `slug` | TEXT PK | Wiki page slug |
| `state` | TEXT | One of: `draft`, `active`, `contradicted`, `stale`, `archived` |
| `updated_at` | TEXT | UTC ISO-8601 — when this row was last modified |
| `triggered_by` | TEXT | Who caused the last transition: `ingest`, `lint`, `cli`, `api` |

**`lifecycle_events`** _(added in v0.6.0)_

Immutable append-only audit log of every lifecycle transition.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `slug` | TEXT | Wiki page slug |
| `from_state` | TEXT | Previous state (`null` on first creation) |
| `to_state` | TEXT | New state |
| `reason` | TEXT | Human-readable reason (empty string if none provided) |
| `triggered_by` | TEXT | `ingest`, `lint`, `cli`, `api` |
| `timestamp` | TEXT | UTC ISO-8601 |

### jobs.db — Job queue

See [Section 14 — Job Queue](#14-job-queue).

### cache.db — LLM response cache

See [Section 12 — Cache System](#12-cache-system).

### embeddings.db — Search index

BM25 + optional vector index over all wiki pages. When vector search is disabled (default), only the BM25 index is used. When `[search] vector = true`, the same SQLite file also stores a `embeddings` table holding `float32` embedding vectors alongside the BM25 entries.

**BM25 tokenizer** handles ASCII and CJK:

```python
@staticmethod
def _tokenize(text: str) -> list[str]:
    ascii_tokens = re.findall(r"[a-z0-9]+", text.lower())
    cjk_tokens   = re.findall(
        r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]", text
    )
    return ascii_tokens + cjk_tokens
```

Note: BM25 IDF requires a minimum of 3 documents in the corpus for non-zero scores when a term appears in exactly one document (formula: `log((N-df+0.5)/(df+0.5))`; N=2, df=1 → log(1) = 0).

---

## 7. HTTP API

**Base URL:** `http://127.0.0.1:<port>` (default port: 7070)

### Middleware

- **CORS:** Allows `app://obsidian.md`, `http://localhost:*`, `http://127.0.0.1:*`
- **ContentSizeLimitMiddleware:** Rejects bodies > 10 MB with HTTP 413
- **Asyncio semaphore:** Max 20 concurrent requests
- **Timeout:** 60 seconds per request

### Endpoints

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/jobs/ingest` | `{source: str}` | `{job_id: str}` |
| `POST` | `/jobs/lint` | `{scope?: str}` | `{job_id: str}` |
| `GET` | `/jobs` | `?status=<filter>&sort=<col>&order=<dir>` | `[Job]` |
| `GET` | `/jobs/{id}` | — | `Job` |
| `DELETE` | `/jobs/{id}` | — | `{deleted: job_id}` |
| `GET` | `/query` | `?q=<question>` | `{answer: str, citations: [str]}` |
| `POST` | `/query` | `{question: str, save?: bool}` | `{answer: str, citations: [str], slug?: str}` |
| `GET` | `/status` | — | `WikiStatus` |
| `GET` | `/lint/report` | — | `LintReport` |
| `GET` | `/health` | — | `{status: "ok"}` |
| `GET` | `/provenance/citations` _(v0.5.0)_ | `?page=<slug>&source=<file>&broken=<bool>&limit=N&offset=N&sort=<col>&order=<dir>` | `{total: int, citations: [CitationRow]}` |
| `GET` | `/lifecycle/status` _(v0.6.0)_ | — | `{draft: int, active: int, contradicted: int, stale: int, archived: int}` |
| `GET` | `/lifecycle/events` _(v0.6.0)_ | `?slug=<slug>&to_state=<state>&limit=N&offset=N` | `{total: int, events: [LifecycleEvent]}` |
| `POST` | `/lifecycle/transition` _(v0.6.0)_ | `{slug: str, to_state: str, reason?: str}` | `{slug, from_state, to_state, timestamp}` |

**`GET /jobs` query parameters:**

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `status` | `pending` \| `in_progress` \| `completed` \| `failed` \| `skipped` \| `dead` \| `cancelled` | _(all)_ | Filter to one status |
| `sort` | `created_at` \| `status` \| `operation` | `created_at` | Column to sort by |
| `order` | `asc` \| `desc` | `asc` | Sort direction |

**Operation types:** `ingest` (file/URL/web-search ingest jobs) and `lint` (lint pass jobs).

**Job object:**

```json
{
  "id": "abc123",
  "status": "completed",
  "operation": "ingest",
  "created_at": "2026-04-10T14:32:01Z",
  "payload": {"source": "report.pdf"},
  "result": {"pages_created": ["alan-turing"], "cost_usd": 0.0, "child_job_ids": []},
  "progress": {"phase": "found_urls", "total": 5},
  "error": null
}
```

The `progress` field is updated in real time during execution (e.g. `{"phase": "searching"}` before Tavily call, `{"phase": "found_urls", "total": N}` after URLs are returned). It is `null` for jobs that do not emit progress. Web search jobs additionally store `child_job_ids` in `result` so callers can track the fan-out URL ingest jobs.

**LintReport object:**

```json
{
  "contradictions": ["grace-hopper"],
  "orphans": ["quantum-computing"],
  "orphan_details": [
    {
      "slug": "quantum-computing",
      "index_suggestion": "- [[quantum-computing]] — physics, computing, qubits"
    }
  ],
  "adversarial_warnings": [
    {
      "slug": "alan-turing",
      "claim": "Saved over fourteen million lives.",
      "concern": "This figure lacks scholarly consensus…"
    }
  ]
}
```

`adversarial_warnings` is present in v0.5.0+; it is an empty list when no warnings were found or when the adversarial pass was skipped.

**CitationRow object** _(v0.5.0)_:

```json
{
  "page_slug": "alan-turing",
  "source_file": "turing-enigma-decryption.pdf",
  "line_start": 8,
  "line_end": 10,
  "claim_excerpt": "## Bletchley Park and the Bombé",
  "ingested_at": "2026-05-21T14:32:01"
}
```

**Note on timestamps:** All `created_at` values are stored and returned as UTC. The Obsidian plugin appends `+00:00` before passing to `new Date()` to ensure correct local-time display.

### Path resolution

`POST /jobs/ingest` accepts:
- Absolute path: `/home/user/docs/report.pdf`
- Vault-relative path: `raw_sources/report.pdf` (resolved against `wiki_root`)
- URL: `https://example.com/article`

### Background worker

The HTTP server runs a background task that polls `jobs.db` every 2 seconds and dispatches pending jobs. Max 4 concurrent ingest jobs (configurable via `max_parallel_ingest`).

---

## 8. Obsidian Plugin

**Package:** `synthadoc-obsidian` (TypeScript)  
**Location:** `obsidian-plugin/` in the repo  
**Version:** 0.5.0

Each vault configures its server URL in plugin settings (default `http://127.0.0.1:7070`).

**Installation:** Build with `npm run build` in `obsidian-plugin/`, then copy `main.js` and
`manifest.json` to `<vault>/.obsidian/plugins/synthadoc/`. Enable in Settings → Community Plugins.
Reload the plugin (toggle off/on) after copying — a full Obsidian restart is not required.

### Command palette

| Command | Behaviour |
|---------|-----------|
| `Synthadoc: Ingest...` | Tabbed modal with four ingest modes. **Web search** — type a topic, set max results (1–50, default 20) and poll interval (500–10 000 ms, default 2000 ms); polls live showing phase text, pages list, and per-URL errors until all fan-out jobs settle. `Ctrl/Cmd+Enter` to submit. **From URL** — paste any URL and queue it for ingest; polls job status live. **All sources in folder** — queues every supported file in the configured raw sources folder. **Pick files** — click **Browse…** to select a folder from the OS picker, then **Scan** to list supported files; wiki sub-folder contents and common system files are excluded automatically; select files and click **Ingest selected**. |
| `Synthadoc: Query: ask the wiki...` | Responsive modal (min 520px, 60vw, max 860px); markdown-rendered answer with citation footer; stays open when clicking elsewhere — must be closed explicitly via ✕ or Escape |
| `Synthadoc: Lint: report` | 3-tab modal — **Contradictions**, **Orphans**, **Adversarial** _(v0.5.0)_. The Adversarial tab shows each flagged claim (orange) with its concern and suggested re-ingest commands. |
| `Synthadoc: Lint: run...` | Modal with **Auto-resolve** and **Skip adversarial review** _(v0.5.0)_ checkboxes. Queues a lint job; polls progress live; reports contradiction, orphan, and adversarial warning counts when complete. Tick **Skip adversarial review** to run structural-only lint (also clears existing `lint_warnings`). |
| `Synthadoc: View Page Provenance` _(v0.5.0)_ | Sortable, paginated table of every claim citation recorded across the wiki — page, claim excerpt, source file, line range, and ingest timestamp. Draggable; all cell content is selectable and copyable. Click any row to open the Source Viewer showing the exact source lines with ±5 lines of context. For PDF sources a page-jump button opens the native PDF viewer at the correct page. |
| `Synthadoc: Manage Page Lifecycle` _(v0.6.0)_ | Sortable, filterable, paginated table of all wiki pages with their current lifecycle state (`draft`, `active`, `contradicted`, `stale`, `archived`) and last transition timestamp. State filter checkboxes narrow the table; click column headers to sort. Each row shows valid transition buttons — click a button to trigger a transition; a reason dialog appears before committing. Clicking a draft or stale badge on the lint modal or jobs panel opens this table pre-filtered to that state. |
| `Synthadoc: Jobs...` | Modal with status-filter checkboxes (pending, in_progress, completed, failed, skipped, dead, cancelled), sortable results table (click **Status**, **Operation**, or **Created** headers to sort ascending; click again to reverse; ▲/▼ indicates active sort, ⇅ indicates unsorted; default: newest first), error detail rows for failed/dead/cancelled jobs, pagination (25 per page), auto-refresh countdown, a **Retry selected** button (enabled when ≥ 1 selected job is failed/dead/cancelled) and a **Delete selected** button (enabled when ≥ 1 job is selected). A **Purge old jobs** footer row lets you set a day threshold and remove old completed/dead jobs in one click. |
| `Synthadoc: Routing: manage ROUTING.md...` | Modal panel with three buttons. **Init** creates ROUTING.md from the current index.md branch structure (enabled only when ROUTING.md does not exist). **Validate** reports dangling slugs — pages listed in ROUTING.md that no longer exist in the wiki (enabled only when ROUTING.md exists). **Clean** removes dangling slugs from ROUTING.md (enabled only when ROUTING.md exists). After each action the result appears inline with per-entry `[Branch] [[slug]]` detail rows. |
| `Synthadoc: Staging: manage staging policy...` | Modal panel showing the current policy state. A segmented control switches between **Off**, **All**, and **Threshold**. When **Threshold** is selected, a second segmented control sets the minimum confidence (**High** / **Medium** / **Low**). A **Save** button persists the change via the HTTP API and updates the inline status. A footer link opens the Candidates modal directly. |
| `Synthadoc: Candidates: review candidate pages...` | Paginated table (50 per page) of all staged candidate pages. Each row shows the slug, a colour-coded confidence badge, and a checkbox. **Promote All** and **Discard All** act on every candidate; **Promote Selected** and **Discard Selected** act on checked rows. The table reloads automatically after each action. A footer link opens the Staging policy modal. |
| `Synthadoc: Context: build context pack...` | Modal with a goal/question text area, a token budget field (default 4000), and a **Build Context Pack** button (`Ctrl/Cmd+Enter` also triggers). The server decomposes the goal, retrieves and ranks wiki pages via BM25, and packs them within the budget. The result is rendered as cited Markdown in a read-only text area. **Copy to Clipboard** copies the content to the OS clipboard. **Save as .md** downloads the Markdown file with a slug-derived filename. |
| `Synthadoc: Audit...` | Tabbed modal with four audit views, each loading automatically on open. **Query history** — last N query records (default 50) with question, sub-question count, token use, cost, and timestamp. **Ingest history** — last N ingest records (default 50) with source filename, wiki page slug, tokens, cost, and ingested-at timestamp. **Events** — last N raw audit events (default 100, max 1000) with timestamp, job ID, event type, and metadata; scrollable when tall. **Cost summary** — total tokens and cost over the last N days (default 30) plus per-day breakdown. |

### Ribbon icon

The Synthadoc ribbon icon (a book icon — `synthadoc-ribbon-icon`) appears in the **left sidebar ribbon** of Obsidian, alongside other plugin icons. Click it to open the engine status at a glance.

Shows engine health and live page count: `✅ online · 12 pages` or `❌ offline — run 'synthadoc serve'`.
Calls `GET /health` and `GET /status` in parallel (`Promise.allSettled`).

If the icon is not visible, make sure the plugin is enabled under **Settings → Community plugins** and that you are looking at the left ribbon (not the right sidebar). You can also pin it via right-clicking the ribbon area.

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Server URL | `http://127.0.0.1:7070` | HTTP server for this vault |
| Raw sources folder | `raw_sources` | Folder scanned by "Ingest all sources" |

### Supported ingest formats

`.md`, `.txt`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`

---

## 9. CLI


The CLI is a thin HTTP client — it posts jobs to the running server and polls for results. No LLM agents run in the CLI process.

**File:** `synthadoc/cli/main.py` + subcommands in `synthadoc/cli/`

### Command tree

```
synthadoc
├── install <name> --target <dir> [--demo] [--domain <str>] [--port <N>]
├── uninstall <name>
├── scaffold [-w wiki]
├── demo list
├── plugin
│   ├── install <wiki>                            — copy plugin files into <wiki>/.obsidian/plugins/synthadoc/
│   └── upgrade                                   — upgrade plugin in all registered wikis at once
├── serve [-w wiki] [--port N] [--background] [--mcp-only] [--http-only] [--verbose]
├── ingest <source> [-w wiki] [--batch] [--file manifest] [--force] [--analyse-only] [--max-results N]
├── query "<question>" [-w wiki] [--save] [--timeout N]
├── lint
│   ├── run [-w wiki] [--scope contradictions|orphans|all] [--auto-resolve] [--no-adversarial]
│   └── report [-w wiki]
├── jobs
│   ├── list [-w wiki] [--status pending|in_progress|completed|failed|skipped|dead|cancelled] [--sort created_at|status|operation] [--order asc|desc]
│   ├── status <id> [-w wiki]
│   ├── retry <id> [-w wiki]
│   ├── delete <id> [-w wiki]
│   ├── cancel [-w wiki] [--yes]
│   └── purge --older-than <days> [-w wiki]
├── audit
│   ├── history [-w wiki] [--limit N] [--json]         — ingest records: timestamp, source, page, tokens, cost
│   ├── cost [-w wiki] [--days N] [--json]              — token totals + daily breakdown
│   ├── queries [-w wiki] [--limit N] [--json]         — query history: question, sub-Qs, tokens, cost
│   ├── events [-w wiki] [--limit N] [--json]          — audit events: timestamp, job_id, event type, metadata
│   └── citations [-w wiki] [--page <slug>] [--broken] — claim citations: all or filtered by page; --broken shows validation failures (v0.5.0)
├── routing
│   ├── init [--wiki-root <path>]                 — generate ROUTING.md from index.md branch structure
│   ├── validate [--wiki-root <path>]             — report dangling slugs and cross-branch duplicates
│   └── clean [--wiki-root <path>]               — remove dangling slugs from ROUTING.md
├── staging
│   └── policy [off|all|threshold] [--min-confidence high|medium|low] [--wiki-root <path>]
├── candidates
│   ├── list [--wiki-root <path>]
│   ├── promote <slug>|--all [--wiki-root <path>]
│   └── discard <slug>|--all [--wiki-root <path>]
├── context
│   └── build "<goal>" [-w wiki] [--tokens N] [--output <file>]
├── status [-w wiki]
├── lifecycle
│   ├── activate <slug> [-w wiki] [--reason "<str>"]
│   ├── archive  <slug> [-w wiki] [--reason "<str>"]
│   ├── restore  <slug> [-w wiki] [--reason "<str>"]
│   └── log      [slug] [-w wiki] [--state <state>]
├── audit
│   └── lifecycle purge -w wiki (--before <date> | --keep-latest <n>)
├── cache clear [-w wiki]
└── schedule
    ├── add --op "<cmd>" --cron "<expr>" [-w wiki]
    ├── list [-w wiki]
    ├── remove <id> [-w wiki]
    └── apply [-w wiki]
```

`synthadoc status -w <wiki>` now shows a per-state page count breakdown alongside the existing page total and job counts.

### `query` options

| Flag | Default | Description |
|------|---------|-------------|
| `--save` | off | Save the answer as a new wiki page |
| `--timeout N` | `60` | Seconds to wait for the LLM response. Increase for slower providers (e.g. `--timeout 120` for MiniMax reasoning models) |

### `ingest --analyse-only`

Runs the analysis step only (entity extraction + tagging + summary) and prints the JSON result without writing any wiki pages. Useful for previewing how a source will be interpreted before committing it to the wiki.

`--analyse-only` works with all three ingest modes — single source, `--batch`, and `--file` manifest. Each source is analysed in turn and its result printed as JSON:

```bash
# Single file
synthadoc ingest report.pdf --analyse-only -w my-wiki
# → {"entities": ["Alan Turing", "Enigma"], "tags": ["cryptography"], "summary": "…"}

# Whole folder — analyses every supported file, no pages written
synthadoc ingest --batch raw_sources/ --analyse-only -w my-wiki

# Manifest — analyses each line in the file
synthadoc ingest --file sources.txt --analyse-only -w my-wiki
```

### `audit` sub-commands

Query the append-only `audit.db` directly from the CLI:

```bash
# Last 20 ingest records
synthadoc audit history -w my-wiki

# Token spend + cost for the last 30 days (default) or custom window
synthadoc audit cost -w my-wiki
synthadoc audit cost --days 7 -w my-wiki

# Last 100 audit events (contradictions found, auto-resolutions, cost gate triggers)
synthadoc audit events -w my-wiki
```

### Wiki targeting

The `-w` / `--wiki` option accepts either a **registry name** (registered via `install`) or a **filesystem path**. Without `-w`, defaults to the current working directory.

Registry stored at `~/.synthadoc/wikis.json`:

```json
{
  "my-wiki": "/home/user/wikis/my-wiki",
  "research": "/home/user/wikis/research"
}
```

### Wiki context resolution

Every CLI command resolves the target wiki through a priority chain rather than
requiring `-w` on each invocation:

1. **Explicit `-w <name>`** — highest priority, always wins
2. **`SYNTHADOC_WIKI` environment variable** — shell-session scope
3. **`~/.synthadoc/default_wiki`** — persistent default, set by `synthadoc use <name>`
4. **Current directory fallback** — if `.synthadoc/config.toml` is present in CWD
   (backward compat for users who `cd` into a wiki directory)
5. **Error** — actionable message directing user to `synthadoc use`

All hint and notification messages are written to **stderr**. Stdout carries only
command results, keeping `synthadoc ... | jq` and other pipelines clean.

The `synthadoc use` command manages the saved default. `synthadoc use` (no args)
shows which wiki is active and from which source, equivalent to `kubectl config current-context`.

### Error codes

Every user-facing error carries a stable code in the format `[ERR-<CATEGORY>-<NNN>]`. Codes are printed to stderr and embedded in job `error` fields, making them greppable in logs.

**File:** `synthadoc/errors.py`

| Code | Meaning |
|------|---------|
| `ERR-SRV-001` | No server listening for the requested wiki |
| `ERR-SRV-002` | Port already bound by another process |
| `ERR-SRV-003` | Server returned a 4xx/5xx HTTP response |
| `ERR-SRV-004` | Background server process exited immediately |
| `ERR-WIKI-001` | Wiki root directory does not exist |
| `ERR-WIKI-002` | Directory exists but missing `wiki/` subfolder |
| `ERR-WIKI-003` | `wiki/` directory is not writable |
| `ERR-WIKI-004` | Install target already exists on disk |
| `ERR-WIKI-005` | Unknown demo template name |
| `ERR-WIKI-006` | Name not in `~/.synthadoc/wikis.json` |
| `ERR-CFG-001` | Required API key environment variable not set |
| `ERR-CFG-002` | Provider name not recognised |
| `ERR-SKILL-001` | No skill matched the source string |
| `ERR-SKILL-002` | Required pip package for skill not installed |
| `ERR-SKILL-003` | URL returned 403 (bot/paywall protection) |
| `ERR-SKILL-004` | `TAVILY_API_KEY` not set for web search |
| `ERR-INGEST-001` | Source file or directory not found |
| `ERR-INGEST-002` | Source file exists but is empty |
| `ERR-INGEST-003` | `--batch` target is not a directory |
| `ERR-JOB-001` | Job ID does not exist in `jobs.db` |

**CLI errors** go through the `cli_error(code, message, hint)` helper, which prints `[ERR-XXX-NNN] message` to stderr with an optional hint line and exits with code 1. **Agent and skill errors** embed the code directly in the exception message string so it surfaces in the job `error` field.

---

## 10. Configuration

### Resolution order

```
Per-agent override  →  [agents].default (project)  →  [agents].default (global)  →  error
```

Project config wins over global config. Unspecified keys inherit from global defaults.

### Global config — `~/.synthadoc/config.toml`

```toml
[agents]
default = { provider = "anthropic", model = "claude-opus-4-6" }
lint    = { model = "claude-haiku-4-5-20251001" }

[wikis]
research = "~/wikis/research"

[observability]
exporter      = "file"                    # or "otlp"
otlp_endpoint = "http://localhost:4317"   # used when exporter = "otlp"
```

### Provider switching

All seven supported providers (`anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `ollama`) share the same config key. Gemini, Groq, MiniMax, and DeepSeek use OpenAI-compatible endpoints internally, so no custom provider class is needed — just set the provider name and supply the corresponding API key:

```toml
# Switch from Claude to Gemini Flash (free tier available)
[agents]
default = { provider = "gemini", model = "gemini-2.5-flash" }
```

Required environment variables per provider:

| Provider | Env var | Free tier | Vision |
|----------|---------|-----------|--------|
| `anthropic` | `ANTHROPIC_API_KEY` | No (pay-per-token) | Yes |
| `openai` | `OPENAI_API_KEY` | No (pay-per-token) | Yes |
| `gemini` | `GEMINI_API_KEY` | **Yes** — 15 RPM / 1M tokens/day on Flash | Yes |
| `groq` | `GROQ_API_KEY` | **Yes** — generous free tier on Llama/Mixtral models | No |
| `minimax` | `MINIMAX_API_KEY` | No (pay-per-token) | Yes (M2.5 / M2.7 natively multimodal) |
| `deepseek` | `DEEPSEEK_API_KEY` | No (pay-per-token, very cheap) | No (text-only) |
| `ollama` | _(none)_ | **Yes** — fully local | Model-dependent |

### Coding tool CLI providers — no API key needed

If you have an active **Claude Code** or **Opencode** subscription, you can use it as the LLM provider with no separate API key.

**Requirements:** the CLI tool must be installed and reachable on `PATH`:
- Claude Code: `claude` binary — install via `npm install -g @anthropic-ai/claude-code`
- Opencode: `opencode` binary — install via `npm install -g opencode`

**Configuration — set in `<wiki-root>/.synthadoc/config.toml`:**

```toml
[agents]
default = { provider = "claude-code", model = "claude-opus-4-7" }
lint    = { provider = "claude-code", model = "claude-haiku-4-5-20251001" }
```

For Opencode:

```toml
[agents]
default = { provider = "opencode", model = "anthropic/claude-opus-4-7" }
```

**Runtime override** — bypasses config.toml for the current server session:

```bash
synthadoc serve -w <wiki-name> --provider claude-code
```

**Limitations:**
- Vector search (`search.vector = true`) is not supported — search falls back to BM25-only. Sufficient for wikis up to a few hundred pages.
- Quota is shared with your coding tool usage. Heavy batch ingest consumes from the same daily budget. Quota exhaustion permanently fails the job (no retry) with a clear message.

### Per-project config — `<wiki-root>/.synthadoc/config.toml`

```toml
[server]
port = 7070

[agents]
default = { provider = "anthropic", model = "claude-opus-4-6" }
lint    = { model = "claude-haiku-4-5-20251001" }
skill   = { model = "claude-haiku-4-5-20251001" }
# llm_timeout_seconds = 90  # set for reasoning models to fail fast instead of silent empty response

[queue]
max_parallel_ingest  = 4
max_retries          = 3
backoff_base_seconds = 5

[cost]
soft_warn_usd                     = 0.50
hard_gate_usd                     = 2.00
auto_resolve_confidence_threshold = 0.85

[ingest]
max_pages_per_ingest  = 15
chunk_size            = 1500
chunk_overlap         = 150
fetch_timeout_seconds = 30   # seconds to wait for a URL response before retrying

[logs]
level        = "INFO"
max_file_mb  = 5
backup_count = 5

[hooks]
on_ingest_complete = "python hooks/auto_commit.py"                        # non-blocking
on_lint_complete   = { cmd = "python hooks/notify.py", blocking = true }  # blocking

[web_search]
provider    = "tavily"   # only supported provider
max_results = 20         # URLs returned per query; each enqueued as an ingest job

[audit]
lifecycle_retention_days = 0   # 0 = keep forever (default); set to e.g. 365 to prune old events

# Cron format: minute hour day-of-month month day-of-week
#              0-59   0-23 1-31         1-12  0-6 (0=Sun)

[[schedule.jobs]]
op   = "ingest --batch raw_sources/"
cron = "0 2 * * *"   # every day at 02:00

[[schedule.jobs]]
op   = "lint run"
cron = "0 3 * * 0"   # every Sunday at 03:00
```

### Config keys reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `agents.default.provider` | str | `"gemini"` | LLM provider: `anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `ollama` |
| `agents.default.model` | str | `"gemini-2.5-flash"` | Model ID |
| `agents.adversarial.provider` | str | (inherits default) | Dedicated LLM provider for adversarial lint review. Falls back to `agents.default` when not set. Cross-model adversarial reduces self-serving bias — a different model family evaluates claims independently. |
| `agents.adversarial.model` | str | (inherits default) | Model ID for the adversarial reviewer. For maximum independence, choose a model from a different family than the ingest model. |
| `lint.adversarial_max_per_page` | int | `2` | Maximum adversarial warnings flagged per page. Raise to 3–5 for a thorough audit; lower to 1 to reduce noise on large wikis. |
| `agents.llm_timeout_seconds` | int | `0` | Per-call LLM timeout in seconds; `0` = no limit. Set to e.g. `90` when using reasoning models (MiniMax-M2.5, DeepSeek-R1) that can exceed their internal generation budget silently. Restart required. |
| `server.port` | int | `7070` | HTTP listen port |
| `queue.max_parallel_ingest` | int | `4` | Max concurrent ingest agents |
| `queue.max_retries` | int | `3` | Retries before job → dead |
| `queue.backoff_base_seconds` | int | `5` | Exponential backoff base (±20% jitter) |
| `cache.version` | str | `"4"` | Bump to invalidate all cached LLM responses without touching source code |
| `cost.soft_warn_usd` | float | `0.50` | Log warning, continue _(configured but not yet enforced — cost_guard is wired to the config but check() is not called in the ingest path)_ |
| `cost.hard_gate_usd` | float | `2.00` | Require explicit confirmation _(configured but not yet enforced — see above)_ |
| `cost.auto_resolve_confidence_threshold` | float | `0.85` | Auto-apply lint resolutions above this score |
| `ingest.max_pages_per_ingest` | int | `15` | Max pages one ingest may update |
| `ingest.chunk_size` | int | `1500` | Text chunk size (characters) |
| `ingest.chunk_overlap` | int | `150` | Overlap between chunks |
| `ingest.fetch_timeout_seconds` | int | `30` | Seconds to wait for a URL response before retrying |
| `logs.level` | str | `"INFO"` | Console log level |
| `logs.max_file_mb` | int | `5` | Rotate `synthadoc.log` at this size |
| `logs.backup_count` | int | `5` | Rotated files to keep |
| `web_search.provider` | str | `"tavily"` | Web search provider (currently only `tavily` supported) |
| `web_search.max_results` | int | `20` | Maximum results fetched per web search query |
| `search.vector` | bool | `false` | Enable semantic re-ranking; downloads `BAAI/bge-small-en-v1.5` (~130 MB) once on first enable |
| `search.vector_top_candidates` | int | `20` | BM25 candidate pool size when vector re-ranking is active |
| `audit.lifecycle_retention_days` | int | `0` | Days to retain lifecycle events in `audit.db`. `0` = keep forever (default). When set, events older than this threshold are pruned at the end of each lint run. |

---

## 11. Hook System

Hooks are shell commands executed when lifecycle events fire. They are configured in `.synthadoc/config.toml` under `[hooks]` and receive a JSON context object on stdin.

### Configuration

```toml
# .synthadoc/config.toml

[hooks]
on_ingest_complete = "python scripts/auto_commit.py"                        # non-blocking
on_lint_complete   = { cmd = "python scripts/notify.py", blocking = true }  # blocking
```

### Blocking vs. non-blocking

- **Non-blocking** (default): runs in a background thread; failures are logged but do not affect the operation.
- **Blocking**: must exit `0` for the operation to succeed; a non-zero exit code raises an error and surfaces it to the caller.

### Events

Two events are fired in v0.1:

| Event | Fires when | Context fields |
|-------|-----------|----------------|
| `on_ingest_complete` | A source is successfully ingested | `event`, `wiki`, `source`, `pages_created`, `pages_updated`, `pages_flagged`, `tokens_used`, `cost_usd` |
| `on_lint_complete` | A lint run finishes | `event`, `wiki`, `contradictions_found`, `orphans` |

### Context JSON examples

**on_ingest_complete**
```json
{
  "event": "on_ingest_complete",
  "wiki": "/home/user/wikis/my-wiki",
  "source": "report.pdf",
  "pages_created": ["alan-turing"],
  "pages_updated": ["computing-history"],
  "pages_flagged": [],
  "tokens_used": 4820,
  "cost_usd": 0.031
}
```

**on_lint_complete**
```json
{
  "event": "on_lint_complete",
  "wiki": "/home/user/wikis/my-wiki",
  "contradictions_found": 2,
  "orphans": ["stub-page", "draft-notes"]
}
```

### Hook library

The [`hooks/`](../hooks/) folder in the repository is a community-maintained
library of ready-to-use scripts. Copy a script to your wiki root and configure
it in `config.toml`.

**Writing a hook script:**

- Read context from `sys.stdin` (JSON) — never from files or env vars
- Write human-readable status to `sys.stderr` (not stdout)
- Exit `0` on success, non-zero on failure
- Include the standard header block (event, description, setup instructions)

See [`hooks/README.md`](../hooks/README.md) for contribution guidelines and
the full list of available scripts.

---

## 12. Cache System

Three independent cache layers:

### Layer 1 — Embedding cache (`embeddings.db`)

Stores the BM25 index entry for each wiki page, keyed by page content SHA-256. When a page is updated, only that page's entry is refreshed.

### Layer 2 — LLM response cache (`cache.db`)

Stores deterministic LLM responses keyed by a hash of the operation type and full input text. Enables zero-token lint runs on unchanged pages.

**Cache key:**

```python
def make_cache_key(operation: str, inputs: dict, version: str = CACHE_VERSION) -> str:
    payload = {"v": version, "op": operation, "inputs": inputs}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:32]
```

The version is part of every cache key, so bumping it causes all existing entries to be bypassed (they remain in `cache.db` but no longer match any key).

To invalidate the cache without touching source code, set `version` in `.synthadoc/config.toml`:

```toml
[cache]
version = "5"   # bump to bypass all entries cached under previous versions
```

The default (`"4"`) is defined in `synthadoc/core/cache.py`. Custom skill authors and wiki operators can bump this freely without modifying core code.

**Invalidation triggers:**

| Trigger | Behavior |
|---------|----------|
| Source content changes | New SHA-256 → cache miss → fresh LLM call |
| `[cache] version` bumped in config | All old entries bypassed |
| `ingest --force` | `bust_cache=True` → skips `cache.get()`, repopulates |
| `cache clear` | Deletes all rows from `cache.db` |

### Layer 3 — Provider prompt cache

Anthropic, OpenAI, and compatible providers cache stable prompt segments server-side. Long system prompts and `AGENTS.md` content hit this cache on repeated calls, giving 50–90% token savings.

**Target cache hit rate:** > 80% on repeated lint runs across unchanged pages.

---

## 13. Cost Guard

**File:** `synthadoc/core/cost_guard.py`

Enforces per-operation budget limits. Evaluated before every LLM call.

### Thresholds

| Threshold | Default | Behaviour |
|-----------|---------|-----------|
| `soft_warn_usd` | $0.50 | Log warning; auto-continue |
| `hard_gate_usd` | $2.00 | Prompt user `Proceed? [y/N]`; block if N; skip prompt if `auto_confirm=True` or `--yes` flag |

### Cost Tracking and Pricing

**How cost is computed (v0.2.0+):**

```
LLM call → CompletionResponse(input_tokens, output_tokens)
             ↓
         estimate_cost(model, input_tokens, output_tokens, is_local)
             ↓
         pricing table lookup in synthadoc/providers/pricing.py
             ↓
         IngestResult.cost_usd  or  audit.db queries.cost_usd
```

**Pricing table (`synthadoc/providers/pricing.py`):**

A static Python dict maps model name → `(input_usd_per_token, output_usd_per_token)`.
Separate input and output rates reflect real-world API pricing (output tokens cost 3–5× more than input tokens for most models).

| Provider | Example model | Input (per token) | Output (per token) |
|---|---|---|---|
| Anthropic | claude-haiku-4-5-20251001 | $0.000001 | $0.000005 |
| Anthropic | claude-sonnet-4-6 | $0.000003 | $0.000015 |
| OpenAI | gpt-4o-mini | $0.00000015 | $0.0000006 |
| Gemini | gemini-2.5-flash | $0.0000003 | $0.0000025 |
| Groq | llama-3.3-70b-versatile | $0.00000059 | $0.00000079 |
| MiniMax | MiniMax-M2.5 | $0.00000015 | $0.0000012 |
| MiniMax | MiniMax-M2.7 | $0.0000003 | $0.0000012 |

**Special cases:**
- **Ollama (local inference):** Always `$0.00` regardless of token count — `is_local=True` short-circuits the calculation.
- **Unknown models:** Use a conservative fallback rate (`$0.000003` per token for both input and output) rather than crashing or silently reporting `$0.00`.

**Token propagation:**

- `CompletionResponse` (already in v0.1) carries `input_tokens` and `output_tokens` from every provider.
- `QueryResult` gains `input_tokens` and `output_tokens` fields (v0.2.0); `Orchestrator.query()` calls `estimate_cost()` to compute `cost_usd` before writing to `audit.db`.
- `IngestResult` gains `input_tokens` and `output_tokens` fields (v0.2.0); `Orchestrator._run_ingest()` calls `estimate_cost()` after ingest completes.
- The vision call and analysis call in `IngestAgent` also accumulate tokens; the analysis call only has a total (split not available due to internal caching).

**Refresh cadence:** The pricing table is refreshed at each major release. `_LAST_UPDATED` in `pricing.py` records the date of last review. See `CONTRIBUTING.md` for the release checklist.

### API

```python
class CostEstimate:
    tokens: int
    cost_usd: float
    operation: str

class CostGuard:
    def check(
        self,
        estimate: CostEstimate,
        auto_confirm: bool = False,   # HTTP server / batch: always proceed
        interactive: bool = True,     # CLI: prompt; HTTP server: False
    ) -> None: ...
```

The HTTP server always passes `auto_confirm=True` (no interactive terminal available). The CLI passes `interactive=True`.

---

## 14. Job Queue

**File:** `synthadoc/core/queue.py`  
**Storage:** `<wiki-root>/.synthadoc/jobs.db` (SQLite)

### State transitions

```
pending     → in_progress  (worker picks up job)
pending     → cancelled    (user-initiated; `synthadoc jobs cancel`)

in_progress → completed
in_progress → failed       (non-retryable error; permanent, no retry)
in_progress → pending      (retryable error; retries < max_retries, after backoff)
in_progress → dead         (retryable error; retries == max_retries)
in_progress → skipped      (system-initiated skip; e.g. auto-blocked domain)
```

| Status | Meaning | Action |
|--------|---------|--------|
| `failed` | Non-retryable error (e.g. stub skill, bad source) | Inspect error; fix source; enqueue again |
| `dead` | Retryable error exhausted max retries | `synthadoc jobs retry <id>` to reset to pending |
| `skipped` | System-initiated permanent skip (e.g. domain auto-blocked after repeated 403s) | No action needed; remove domain from blocked list to re-enable |
| `cancelled` | Pending job cancelled by user via `synthadoc jobs cancel` | Re-enqueue manually if cancelled in error |

**Backoff formula:** `backoff_base_seconds × 2^(retry_count) × jitter`  
where `jitter ∈ [0.8, 1.2]` (±20% random). Applied only to retryable errors (LLM API timeouts, 5xx responses).

**Persistence:** Jobs survive server restarts. `in_progress` jobs at shutdown are reset to `pending` on startup.

---

## 15. Observability and Logging

**Files:** `synthadoc/core/logging_config.py`, `synthadoc/observability/telemetry.py`

### Handler stack

```
Root logger (level: DEBUG)
├── Console handler
│   Level  : cfg.logs.level (default INFO); overridden to DEBUG if --verbose
│   Format : "HH:MM:SS LEVEL  logger — message"
│   Target : stderr
│   Note   : suppressed when --background spawns the detached child process
│
└── File handler (RotatingFileHandler)
    Level  : DEBUG always
    Format : JSON lines
    Target : <wiki-root>/.synthadoc/logs/synthadoc.log
    Rotate : cfg.logs.max_file_mb MB; cfg.logs.backup_count old files kept
```

Suppressed to WARNING: `httpx`, `httpcore`, `uvicorn.access`, `anthropic`, `openai`.

**Background mode (`--background` / `-b`):** the parent process prints the startup banner, spawns a detached child process (`pythonw.exe` on Windows, `start_new_session=True` on Unix), and exits — returning the shell to the user. The child runs without a console handler; all output goes to the file handler only. PID is written to `<wiki-root>/.synthadoc/server.pid`.

### Log record fields

| Field | Always present | Source |
|-------|---------------|--------|
| `ts` | Yes | `record.created` |
| `level` | Yes | `record.levelname` |
| `logger` | Yes | `record.name` |
| `msg` | Yes | `record.getMessage()` |
| `job_id` | Job context only | `LoggerAdapter.extra` |
| `operation` | Job context only | `LoggerAdapter.extra` |
| `wiki` | Job context only | `LoggerAdapter.extra` |
| `trace_id` | When OTel active | OTel span context |

### Job-scoped logging

```python
from synthadoc.core.logging_config import get_job_logger

log = get_job_logger(__name__, job_id="abc123", operation="ingest", wiki="my-wiki")
log.info("Page created: %s", slug)
# → {"ts": "…", "level": "INFO", "logger": "…", "msg": "Page created: alan-turing",
#    "job_id": "abc123", "operation": "ingest", "wiki": "my-wiki"}
```

### Setup (called once at server start)

```python
from synthadoc.core.logging_config import setup_logging
setup_logging(wiki_root=Path("/path/to/wiki"), cfg=config.logs, verbose=False)
```

Idempotent — safe to call multiple times (subsequent calls are no-ops).

### OpenTelemetry

Default: file exporter writing to `traces.jsonl`. Switch to any OTLP backend:

```toml
[observability]
exporter      = "otlp"
otlp_endpoint = "http://localhost:4317"
```

Spans cover: full operation tree (orchestrator → agent → LLM calls → storage writes), with token counts, cost, and cache hit/miss as span attributes.

### Log level guidance

| Level | When to use |
|-------|------------|
| `DEBUG` | LLM prompt bodies, cache key details, BM25 scores, entity extraction details |
| `INFO` | Job lifecycle, page created/updated, server started, lint summary |
| `WARNING` | Soft failures (network unreachable), suspicious patterns |
| `ERROR` | Job failed, API error, file write failed |
| `CRITICAL` | Server cannot start |

---

## 16. Security

### Path traversal

`WikiStorage` normalizes all paths with `Path.resolve()` and asserts each is a child of `wiki_root`. Raises `PermissionError` on violation.

### Prompt injection

- LLM output validated against a strict schema; unrecognized keys dropped silently
- Slug blacklist: `wikilinks`, `wiki`, `obsidian`, `dataview`, `index`, `dashboard`, `log`, `audit`, `hooks`, `skills`
- System prompt instructs the model to never follow instructions embedded in source documents

### Network exposure

HTTP and MCP servers bind to `127.0.0.1` at OS socket level. Not configurable. No remote access without a separate reverse proxy (which the user must explicitly set up).

### HTTP DoS

- Body limit: 10 MB (returns 413)
- Concurrent request cap: 20 (asyncio semaphore)
- Request timeout: 60 seconds

### Audit trail

`audit.db` is append-only in normal operation. The only deletion command is `jobs purge --older-than <days>`, which only removes records older than the given threshold.

### Custom skills trust model

Skills in `<wiki-root>/skills/` or `~/.synthadoc/skills/` run in the same Python process. This is intentional — the wiki root is a trusted location, analogous to `~/bin`. Do not point a wiki root at an untrusted directory.

---

## 17. Plugin Development Guide

This section is for developers building custom skills or LLM providers.

### Writing a skill

1. Create a skill folder in `<wiki-root>/skills/` or `~/.synthadoc/skills/`.
2. Add a `SKILL.md` with YAML frontmatter (name, version, entry, triggers, requires).
3. Create `scripts/main.py` and subclass `BaseSkill` from `synthadoc.skills.base` (Apache-2.0 — no AGPL obligation).
4. Implement `extract(source: str) -> ExtractedContent`.

**Folder layout:**
```
slack_export/
  SKILL.md
  scripts/
    main.py
  references/
    format-notes.md   ← optional; load with self.get_resource("format-notes.md")
```

**`SKILL.md`:**
```yaml
---
name: slack_export
version: "1.0"
description: Extract messages from a Slack export ZIP
entry:
  script: scripts/main.py
  class: SlackExportSkill
triggers:
  extensions: [".slack.zip"]
  intents: ["slack export", "slack archive"]
requires: []
---

Loads all JSON channel files from a Slack export ZIP and returns the message text.
```

**`scripts/main.py`:**
```python
# SPDX-License-Identifier: MIT
from synthadoc.skills.base import BaseSkill, ExtractedContent

class SlackExportSkill(BaseSkill):

    async def extract(self, source: str) -> ExtractedContent:
        import zipfile, json
        messages = []
        with zipfile.ZipFile(source) as zf:
            for name in zf.namelist():
                if name.endswith(".json"):
                    data = json.loads(zf.read(name))
                    for msg in data:
                        if "text" in msg:
                            messages.append(msg["text"])
        return ExtractedContent(
            text="\n".join(messages),
            source_path=source,
            metadata={},
        )
```

**Error handling:** Raise `ValueError` with a clear message if the source cannot be processed. Raise `ImportError` if an optional dependency is missing (the agent will surface a helpful message to the user).

### Writing a provider

Built-in providers: `anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `ollama`. For any provider that exposes an OpenAI-compatible API, no custom class is needed — the built-in `openai` provider with a custom `base_url` is sufficient.

For a fully proprietary API, subclass `LLMProvider`:

```python
# SPDX-License-Identifier: MIT
from synthadoc.providers.base import LLMProvider, Message, CompletionResponse

class MyProvider(LLMProvider):

    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.0,
        **kwargs,
    ) -> CompletionResponse:
        # Call your API …
        return CompletionResponse(
            text="…",
            input_tokens=N,
            output_tokens=M,
        )
```

Place in `~/.synthadoc/providers/` or the wiki `providers/` directory. Reference by name in config:

```toml
[agents]
default = { provider = "my_provider", model = "my-model-id" }
```

### Writing a hook

Hooks can be in any language. They receive JSON on stdin and must exit 0 on success.

```bash
#!/usr/bin/env bash
# hooks/notify.sh
context=$(cat)
event=$(echo "$context" | jq -r '.event')
wiki=$(echo "$context" | jq -r '.wiki')
echo "Event $event fired on wiki $wiki" | mail -s "Synthadoc notification" you@example.com
```

---

## 18. Routing

### ROUTING.md format

`ROUTING.md` lives at `<wiki-root>/ROUTING.md`. It groups page slugs under topic branch headings:

```markdown
## People
- [[alan-turing]]
- [[grace-hopper]]

## Hardware
- [[eniac]]
- [[von-neumann-architecture]]
```

### RoutingIndex

`RoutingIndex` parses the file, exposes a `branches: dict[str, list[str]]` mapping, and provides:

- `parse(path)` — class method; returns an empty index if the file is absent
- `validate(existing_slugs)` — returns `(branch, slug)` pairs present in ROUTING.md but not in the wiki
- `clean(existing_slugs)` — removes dangling entries in-place; returns removed pairs
- `add_slug(slug, branch)` — idempotent append
- `slugs_for_branches(branch_names)` — flat list of slugs across the named branches
- `save(path)` — serialises back to disk

### Query routing

When `routing_path` is passed to `QueryAgent`, each query first picks the 1–2 most relevant branches via a lightweight LLM call (returns `[]` on any failure) and restricts the BM25 corpus to those slugs. Falls back to full-corpus search when no branch is selected.

### Ingest placement

When `routing_path` is passed to `IngestAgent`, newly created pages are automatically placed into the most appropriate branch via a lightweight LLM call after the page is written.

### Alias expansion

Pages may carry an `aliases:` list in YAML frontmatter. `QueryAgent._expand_aliases` replaces alias matches in the question with the canonical slug before BM25 search (longest alias first to avoid partial-match conflicts).

### Protected scaffold zone

`SCAFFOLD_MARKER = "<!-- synthadoc:scaffold -->"` separates user-authored content (above) from scaffold-managed content (below) in `wiki/index.md`. The `preserve_user_zone(existing, new_scaffold)` helper in `synthadoc.agents.scaffold_agent` preserves the user zone when re-running the scaffold command. If the marker is absent, scaffold rewrites the whole file (original behaviour).

### CLI commands

| Command | Description |
|---|---|
| `synthadoc routing init` | Generate ROUTING.md from current index.md branch structure |
| `synthadoc routing validate` | Report dangling slugs (dry run) |
| `synthadoc routing clean` | Remove dangling slugs from ROUTING.md |

All commands accept `--wiki-root <path>`.

### Obsidian plugin

The `Routing: manage ROUTING.md...` command opens a `RoutingModal`. On open it calls `GET /routing/status` and enables or disables the three buttons accordingly:

| State | Init | Validate | Clean |
|---|---|---|---|
| ROUTING.md absent | enabled | disabled | disabled |
| ROUTING.md present | disabled | enabled | enabled |
| Server unreachable | disabled | disabled | disabled |

After each action the result appears in an inline result area with per-entry `[Branch] [[slug]]` detail rows. The ROUTING.md preview box (max-height 120 px, scrollable) is shown/refreshed by Init and Clean operations.

---

## 19. Candidates Staging

### Staging policy

New pages can be routed to `wiki/candidates/` instead of `wiki/` based on the `[ingest] staging_policy` setting:

| Value | Behaviour |
|---|---|
| `off` | All new pages go directly to `wiki/` (default) |
| `all` | All new pages go to `wiki/candidates/` |
| `threshold` | Pages below `staging_confidence_min` go to `wiki/candidates/` |

`staging_confidence_min` values: `high` (default), `medium`, `low`. Confidence ordering: `high > medium > low`.

### Exclusion from search

`wiki/candidates/` is excluded from `WikiStorage.list_pages()` and therefore from BM25, lint, and contradiction detection. Candidates are invisible to all agents until promoted.

### CLI commands

| Command | Description |
|---|---|
| `synthadoc staging policy [off\|all\|threshold]` | Show or set the staging policy |
| `synthadoc staging policy --min-confidence <level>` | Set minimum confidence threshold |
| `synthadoc candidates list` | List all candidate pages with confidence and date |
| `synthadoc candidates promote <slug>` | Move a candidate to `wiki/` |
| `synthadoc candidates promote --all` | Promote all candidates |
| `synthadoc candidates discard <slug>` | Delete a candidate |
| `synthadoc candidates discard --all` | Delete all candidates |

Policy changes take effect on the next ingest job — no server restart needed.

### HTTP API

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `GET` | `/staging/policy` | — | `{policy: str, confidence_min: str\|null}` |
| `POST` | `/staging/policy` | `{policy: str, confidence_min?: str}` | `{policy: str, confidence_min: str\|null}` |
| `GET` | `/candidates` | — | `[{slug: str, title: str, confidence: str, ingested_at: str}]` |
| `POST` | `/candidates/promote-all` | — | `{promoted: int, updated: int}` |
| `POST` | `/candidates/discard-all` | — | `{discarded: int}` |
| `POST` | `/candidates/{slug}/promote` | — | `{promoted: slug, new: bool, updated: bool}` |
| `POST` | `/candidates/{slug}/discard` | — | `{discarded: slug}` |

Promote moves the file from `wiki/candidates/<slug>.md` to `wiki/<slug>.md`. If a page with the same slug already exists in `wiki/` (a staged update to an existing page), the existing file is overwritten. Only newly created pages (not overwrites) are indexed into BM25.

### Obsidian plugin

The **Staging: manage staging policy...** command opens `StagingModal`:

- A status block shows the current policy in plain language (e.g. "Staging is **enabled (threshold)**. Pages below *high* confidence are staged.")
- A segmented control switches between **Off** / **All** / **Threshold**.
- When **Threshold** is selected, a second segmented control sets **Min confidence**: **High** / **Medium** / **Low**.
- **Save** calls `POST /staging/policy` and refreshes the status block inline.
- A footer link **Candidate pages →** closes the modal and opens `CandidatesModal`.

The **Candidates: review candidate pages...** command opens `CandidatesModal`:

- Loads all candidates via `GET /candidates` and displays them in a paginated table (50 rows per page).
- Each row has a checkbox, the page slug, a colour-coded confidence badge (green = high, amber = medium, red = low), and the ingest timestamp.
- A select-all checkbox in the header checks or clears every row on the current page.
- **Promote All** / **Discard All** operate on every candidate regardless of page; **Promote Selected** / **Discard Selected** operate on checked rows only. The table reloads automatically after each action.
- A footer link **← Staging policy** closes the modal and opens `StagingModal`.

---

## 20. Context Packs

### ContextAgent

`ContextAgent` builds a token-bounded evidence pack from the wiki:

1. Decomposes the goal into sub-questions (reuses `QueryAgent.decompose`)
2. Runs BM25 hybrid search per sub-question in parallel
3. Merges results, keeping the best score per slug
4. Packs pages greedily within the token budget (word count / 0.75 approximation)
5. Records omissions when the budget is exhausted

Constructor: `ContextAgent(provider, store, search, token_budget=4000, top_n=8)`

Method: `await agent.build(goal, token_budget=None) → ContextPack`

### ContextPack

| Field | Type | Description |
|---|---|---|
| `goal` | `str` | The input goal string |
| `token_budget` | `int` | Effective budget used |
| `tokens_used` | `int` | Tokens consumed by included pages |
| `pages` | `list[ContextPage]` | Included pages, ranked by relevance |
| `omitted` | `list[ContextPage]` | Pages excluded due to budget |

`ContextPack.to_markdown()` renders a human-readable evidence pack. `ContextPack.to_dict()` returns a JSON-serialisable dict for the REST API.

### Default token budget

The default token budget is configured via `[query] context_token_budget` in `config.toml` (default: 4000). The HTTP request body and CLI `--tokens` flag can override it per call.

### REST API

```
POST /context/build
Content-Type: application/json

{"goal": "early computing pioneers", "token_budget": 2000}
```

Response: `ContextPack.to_dict()` — keys `goal`, `token_budget`, `tokens_used`, `pages`, `omitted`.

### CLI command

```bash
# Print to terminal — inspect, copy, or pipe into another tool
synthadoc context build "early computing pioneers"

# Custom token budget (default 4000)
synthadoc context build "early computing pioneers" --tokens 2000

# Save to a file — feed to an external LLM prompt or store next to a document you're writing
synthadoc context build "early computing pioneers" --output briefing.md
```

---

## 21. Adversarial Review

### Concept

Standard lint validates wiki structure — contradictions, orphans, broken links. It does not evaluate whether the *content* of a page is accurate. The adversarial review closes this gap: after structural checks complete, a second independent LLM pass interrogates every page for epistemic overreach — overstated claims, unsupported assertions, and high-confidence statements the source material does not support.

The key architectural decision is cross-model independence. When the adversarial reviewer is a different model family from the ingest model, neither shares the training-induced inductive biases that cause same-model self-review to systematically miss the same class of errors.

### LintAgent integration

The adversarial review runs as the final phase of every `synthadoc lint run`. After orphan detection and contradiction checks complete, `LintAgent` calls `_adversarial_single(slug, content)` for every non-excluded page concurrently via `asyncio.gather()`. A 100-page wiki completes in the same wall-clock time as a single LLM call.

Each `_adversarial_single` call prompts the adversarial model to act as a skeptical editor and return a JSON array of `{claim, concern}` objects. Results are capped at `adversarial_max_per_page` (default 2) per page. Failures are caught per-page — rate-limit errors and parse failures are stored as non-fatal warning entries and never abort the lint job.

When `--no-adversarial` is passed to `lint run`, the adversarial phase is skipped entirely and any existing `lint_warnings` are cleared from all page frontmatter.

When `--no-lifecycle` is passed to `lint run`, all four lifecycle checks are skipped. Existing `page_states` and `lifecycle_events` records are not modified.

### `lint_warnings` frontmatter

Warnings are written directly to each page's YAML frontmatter after each lint run:

```yaml
lint_warnings:
  - claim: "Saved over fourteen million lives."
    concern: "This figure lacks scholarly consensus — historians dispute both the
              precision and the causal attribution to Turing's cryptanalysis alone."
  - claim: "Most consequential business decision of the era."
    concern: "An unsupported superlative — the MS-DOS licence retention and Intel's
              exclusive CPU supply deal were equally pivotal."
```

The field is absent when no warnings exist. Cleared automatically when `--no-adversarial` is used, ensuring stale warnings do not persist after the pass is disabled.

### Configuration

```toml
# config.toml
[agents]
lint        = { provider = "minimax",   model = "MiniMax-M2.5" }
adversarial = { provider = "anthropic", model = "claude-sonnet-4-6" }   # independent judge — different model family

[lint]
adversarial_max_per_page = 2   # raise to 3–5 for a deeper audit; lower to 1 for less noise
```

`[agents].adversarial` falls back to `[agents].default` if absent — the adversarial pass always runs, it just uses the same model as ingest (less effective, still useful).

### CLI commands

| Command | Description |
|---|---|
| `synthadoc lint run` | Full lint pass including adversarial review |
| `synthadoc lint run --no-adversarial` | Structural-only lint; clears existing `lint_warnings` |
| `synthadoc lint report` | Show warnings — CLI output has a dedicated Adversarial section |

### HTTP API

`GET /lint/report` returns a `LintReport` object. The `adversarial_warnings` field carries all warnings across all pages:

```json
{
  "adversarial_warnings": [
    {
      "slug": "alan-turing",
      "claim": "Saved over fourteen million lives.",
      "concern": "This figure lacks scholarly consensus…"
    }
  ]
}
```

Empty list when no warnings exist or the pass was skipped.

### Obsidian plugin

`Synthadoc: Lint: run...` modal adds a **Skip adversarial review** checkbox alongside the existing **Auto-resolve** checkbox. When ticked, the lint job runs structural checks only and clears stale warnings.

`Synthadoc: Lint: report` is a 3-tab modal — **Contradictions**, **Orphans**, **Adversarial**. The Adversarial tab renders each warning with the flagged claim in orange, the concern below it in muted text, and suggested re-ingest commands derived from the page's source files.

---

## 22. Claim-Level Provenance

### Concept

Every compiled wiki page is a synthesis — the LLM reads source documents and rewrites them as prose. Claim-level provenance closes the audit gap: during ingest, a dedicated annotation pass inserts a `^[filename:L-L]` citation marker at the end of each substantive paragraph, mapping the compiled claim to the exact line range in the raw source that supports it. Markers are stored in the page body, validated by lint, and recorded in `audit.db`. In Obsidian they render as interactive chips — one click opens the Source Viewer.

### IngestAgent Pass 4 — `_annotate_citations()`

Called within the Write pass for each page section immediately before it is appended to the page. The LLM receives:

1. The numbered raw source text (lines 1, 2, 3 … N)
2. The compiled section to annotate

It returns the section with `^[filename:L-L]` markers appended to substantive paragraphs. The result is validated against a sanity check (markers must reference real line numbers in the source). On any failure — LLM error, parse failure, or sanity check — the original un-annotated section is used and the failure is recorded as a `citation_pass4_skipped` audit event. Ingest always completes.

Results are cached by section SHA-256 so re-ingest of unchanged sections does not incur an extra LLM call.

### Sidecar files

To support the Source Viewer in Obsidian, `_write_sidecar()` writes two files to `.synthadoc/extracted/` for every locally ingested source:

| File | Contents | Source types |
|------|----------|-------------|
| `<basename>.txt` | Plain UTF-8 extracted text with line numbers preserved | All local file types |
| `<basename>.pagemap.json` | JSON array mapping line numbers to PDF page numbers | PDF only |

The pagemap enables the "Open PDF at page N →" button in the Source Viewer to resolve a line range to the correct PDF page without re-parsing the document. Web and YouTube sources do not produce sidecars (no stable local path to key on).

### `claim_citations` table

Stored in `audit.db`. Written by `AuditDB.record_claim_citations()` after each annotated page section is saved.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `page_slug` | TEXT | Wiki page the citation belongs to |
| `source_file` | TEXT | Basename of the raw source file |
| `line_start` | INTEGER | First line of the supporting passage |
| `line_end` | INTEGER | Last line of the supporting passage |
| `claim_excerpt` | TEXT | First ~100 chars of the annotated paragraph |
| `ingested_at` | TEXT | UTC ISO-8601 |

### HTTP API

```
GET /provenance/citations
  ?page=<slug>        filter by wiki page
  &source=<filename>  filter by source file
  &broken=<bool>      return only citations that failed validation
  &limit=N            page size (default 50)
  &offset=N           pagination offset
  &sort=<col>         ingested_at | page_slug | source_file (default: ingested_at)
  &order=asc|desc     (default: desc)
```

Response: `{total: int, citations: [CitationRow]}`

### CLI commands

| Command | Description |
|---|---|
| `synthadoc audit citations -w <wiki>` | Last 50 citations across the whole wiki |
| `synthadoc audit citations -w <wiki> --page <slug>` | All citations for one page |
| `synthadoc audit citations -w <wiki> --broken` | Citations that failed line-range validation |

### Obsidian plugin

**Citation chips (Reading View only):** The Obsidian post-processor transforms `^[filename:L-L]` inline footnote markers into styled chips rendered after the claim. Chips only appear in Reading View (`Ctrl/Cmd+E`) — not in Edit or Live Preview mode.

**Source Viewer modal:** Clicking a chip opens a draggable modal showing the referenced source lines highlighted with ±5 lines of surrounding context. File resolution order:

1. `.synthadoc/extracted/<basename>.txt` — pre-extracted sidecar (all local types)
2. `raw_sources/<filename>` — direct fallback for plain-text types (`.md`, `.txt`, `.csv`)
3. Friendly error for binary types (`.xlsx`, etc.) with instructions to open the original

For PDF sources, if the pagemap sidecar exists and the target page is > 1, a **"Open PDF at page N →"** button closes the Source Viewer and opens the PDF at the correct page in Obsidian's native viewer.

**Page Provenance modal (`Synthadoc: View Page Provenance`):** A sortable, paginated table of every citation across the wiki. Columns: Page, Claim, Source, Lines, Ingested. Sort by any column header; filter by slug or source filename. Pagination is pinned below the table and always visible. Click any row to open the Source Viewer for that citation. All cell content can be selected and copied independently of the row-click action.

---


## 23. Lifecycle Machine

### Concept

Every wiki page moves through a defined set of states that reflect its review status and the health of its source material. Pages start as `draft` — compiled but not yet validated — and advance to `active` when lint passes all checks. Subsequent changes to the source file on disk push the page to `stale`; a missing source file triggers `archived`. Manual transitions allow operators to override any state.

### States

| State | Meaning | How to reach it |
|---|---|---|
| `draft` | Newly compiled, not yet lint-reviewed | Automatic on ingest |
| `active` | Lint-reviewed, current, trusted | Lint auto-promotes from `draft` |
| `contradicted` | Conflict detected | Lint detects contradiction between sources |
| `stale` | Source file changed since last ingest | Lint detects SHA-256 hash mismatch |
| `archived` | Source removed or explicitly retired | Lint auto-archives on missing source; or manual |

### Transition rules

| From | To | Trigger | Condition |
|---|---|---|---|
| _(none)_ | `draft` | `ingest` | New page created by ingest |
| `draft` | `active` | `lint` | Page passes all lint checks |
| `active` | `stale` | `lint` | Local source: SHA-256 hash mismatch; or URL source older than `url_staleness_days` |
| `active` / `stale` | `archived` | `lint` | Local source no longer exists on disk; or URL source returns 404/410 (opt-in) |
| any | `archived` | `cli` / `api` | Manual archive (`synthadoc lifecycle archive`) |
| `archived` | `draft` | `cli` / `api` | Manual restore (`synthadoc lifecycle restore`) |
| `contradicted` | `archived` | `cli` / `api` | Manual archive after reviewing the conflict |

### Storage

Two new tables in `audit.db`:

**`page_states`** — fast slug-keyed current state index (one row per page):

```sql
page_states (slug TEXT PK, state TEXT, updated_at TEXT, triggered_by TEXT)
```

**`lifecycle_events`** — immutable append-only audit log:

```sql
lifecycle_events (id INTEGER PK, slug TEXT, from_state TEXT, to_state TEXT,
                  reason TEXT, triggered_by TEXT, timestamp TEXT)
```

`triggered_by` values: `ingest`, `lint`, `cli`, `api`.

### LintAgent integration

Four lifecycle checks run at the end of every lint pass, after all existing checks, unless `--no-lifecycle` is passed:

1. **Archived detection** — source no longer available → transition page to `archived`
2. **Stale detection** — source has changed since last ingest → transition page to `stale`
3. **Draft promotion** — `draft` page with no active issues → transition to `active`
4. **Manual-edit sync** — frontmatter `status` ≠ `page_states` DB → reconcile DB record to match

Pass `--no-lifecycle` to `synthadoc lint run` to skip all four checks. Existing `page_states` and `lifecycle_events` records are not modified.

#### Check 1 — Archived detection (local and URL sources)

For **local file sources**: if the source path recorded in frontmatter no longer exists on disk, the page is transitioned to `archived`.

For **URL sources** (`http://`, `https://`, `youtube.com/watch?v=…`): availability is checked only when `[lint] check_url_availability = true` (default: `false` — opt-in because it adds a network call per URL source during every lint run).

- **Generic URLs** — an HTTP HEAD request is issued. Responses of 404 or 410 are treated as archived. Timeouts, connection errors, and any other status code leave the page unchanged (conservative: no false positives on transient failures).
- **YouTube URLs** — the transcript API is probed with the video ID. A `VideoUnavailable` response means the video is deleted or private → `archived`. Any other error (network error, parsing failure) leaves the page unchanged.

Enable with the `--check-urls` flag or the config key:

```bash
synthadoc lint run --check-urls
```

```toml
[lint]
check_url_availability = true   # default: false
```

#### Check 2 — Stale detection (local and URL sources)

For **local file sources**: a SHA-256 hash of the current file on disk is compared to the hash recorded at ingest time. A mismatch transitions the page to `stale`.

For **URL sources**: staleness is age-based. If `url_staleness_days` is non-zero, the `ingested_at` timestamp from `audit.db` is compared to the current time. Pages whose last ingest is older than the threshold are transitioned to `stale`, prompting a re-ingest.

```toml
[audit]
url_staleness_days = 90   # 0 = never mark URL sources stale (default)
```

URL staleness detection runs on every lint pass when the config value is non-zero — no extra flag required.

#### Debug logging

When URL availability or staleness checks run, the lint agent emits `DEBUG`-level log lines for each check outcome:

```
lifecycle url-check [youtube] id=dQw4w9WgXcQ url=https://www.youtube.com/watch?v=dQw4w9WgXcQ → unavailable
lifecycle url-check [head]    url=https://example.com/page → status=404 → unavailable
lifecycle url-stale           url=https://example.com/page → age=102d threshold=90d → stale
```

Enable debug logging in `config.toml`:

```toml
[logs]
level = "DEBUG"
```

### Auto-retention

```toml
[audit]
lifecycle_retention_days = 365   # 0 = keep forever (default)
```

When non-zero, events older than `lifecycle_retention_days` are pruned from `lifecycle_events` at the end of each lint run. `page_states` records are never pruned — they represent current state, not history.

### CLI commands

```
synthadoc status -w <wiki>
    Show page counts by lifecycle state alongside existing page and job totals.

synthadoc lint run [--no-lifecycle] [--check-urls]
    Run lint. --no-lifecycle skips all four lifecycle checks.
    --check-urls enables HTTP availability checks for URL sources (overrides config).

synthadoc lifecycle activate <slug> -w <wiki> [--reason "..."]
    Transition a page to active.

synthadoc lifecycle archive  <slug> -w <wiki> [--reason "..."]
    Transition a page to archived.

synthadoc lifecycle restore  <slug> -w <wiki> [--reason "..."]
    Transition an archived page back to draft.

synthadoc lifecycle log      [slug] -w <wiki> [--state <state>]
    Print the event log for one page (or all pages). Filter by to_state with --state.

synthadoc audit lifecycle purge -w <wiki> --before <date>
    Delete lifecycle events older than <date> (ISO-8601, e.g. 2026-01-01).

synthadoc audit lifecycle purge -w <wiki> --keep-latest <n>
    Keep only the most recent <n> events per slug, delete the rest.
```

### HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/lifecycle/status` | Current state counts from `page_states` |
| `GET` | `/lifecycle/events` | Paginated event log (`slug`, `to_state`, `limit`, `offset` query params) |
| `POST` | `/lifecycle/transition` | Body: `{slug, to_state, reason?}` — validates allowed transition, writes both tables |

### Obsidian plugin

**`Synthadoc: Manage Page Lifecycle`** — opens `LifecycleModal`:

- Loads all pages via `GET /lifecycle/status` and lists them in a sortable, paginated table (25 per page by default).
- State filter checkboxes (one per state) narrow the table to the selected states.
- Column headers (Slug, State, Last transition) are sortable — click to cycle ascending/descending/unsorted.
- Each row shows valid action buttons for the current state. Click a button to trigger a transition — `ReasonModal` appears first, prompting for an optional reason string, before committing via `POST /lifecycle/transition`.
- Draft and stale badge links on the lint modal and jobs panel open `LifecycleModal` pre-filtered to that state.

### Configuration

```toml
[audit]
lifecycle_retention_days = 365   # 0 = keep forever (default)
url_staleness_days = 90          # 0 = never mark URL sources stale (default)

[lint]
check_url_availability = true    # default: false — adds a network call per URL source during lint
```

---

## 24. Export Formats

The `synthadoc export` command serializes the wiki in four machine-readable formats, assembled server-side from cached data with zero additional LLM calls. Requires `synthadoc serve` to be running.

### Formats

**`llms.txt`** — Navigation index per the [llmstxt.org](https://llmstxt.org/) spec. Active pages appear under `## Pages` with a one-line description; contradicted and stale pages appear under `## Needs Review` with a reason note; archived pages are omitted entirely. With `--status active` only `## Pages` is emitted.

**`llms-full.txt`** — Flat content dump. Pages are separated by `---`. Each page opens with `Status: <state> | Confidence: <level> | Tags: ...`. Provenance footnotes (`^[source.txt:42-58]`) are preserved verbatim in the body. No size limit — the full wiki is always exported. For very large wikis a streaming export path is planned as a future enhancement.

**`graphml`** — Standard GraphML 1.1. Nodes = pages; edges = wikilinks extracted from page bodies. Node attributes: `title`, `status`, `confidence`, `orphan` (boolean), `citation_count` (int), `inbound_link_count` (int), `routing_branch` (from ROUTING.md branch membership). All edges carry `edge_type="wikilink"`. Self-links are suppressed.

**`json`** — Agent-ready structured dump. Six unique differentiators beyond what any competing tool exports:
- `claims[]` per page — source file, line range, claim excerpt (from the claim provenance audit database)
- `lifecycle_history[]` per page — every state transition with from/to/timestamp/reason
- `compilation_cost_usd` per page and `total_compilation_cost_usd` for the whole wiki
- `routing.branch_memberships` — ROUTING.md branch name for each page
- Lifecycle state filter (`status_filter`) applied at export time
- Context pack scope (`context_pack`) — exports only pages within the named pack

### CLI

```bash
synthadoc export --format <fmt> [--output <path>] [--status <state>] [--context-pack <name>] [--wiki <name>]
```

Outputs to stdout by default; `--output` writes to a file. `--status` filters pages by lifecycle state (`all` / `active` / `draft` / `stale` / `contradicted` / `archived`).

### POST /export endpoint

Accepts `{ format, status_filter, context_pack }`. Returns raw content with appropriate `Content-Type` (`text/plain; charset=utf-8` for text formats, `application/xml` for graphml, `application/json` for json). Returns 422 for unknown format. No LLM calls.

### Obsidian

**Export Wiki** command opens a modal with: format dropdown (json / llms.txt / llms-full.txt / graphml), output path input pre-filled with today's date and the correct extension, status filter selector, Export button (writes to vault), and a View Graph button (graphml format only — opens the Graph View Modal).

**View Knowledge Graph** command opens an embedded Cytoscape.js graph viewer. Nodes are colored by lifecycle state (active=green, draft=yellow, stale=orange, contradicted=red, archived=grey) and sized by inbound link count. An "Export to file" button in the toolbar saves the GraphML to the vault's `exports/` folder.

---

## Appendix A — Release Feature Index

### v0.1.0 (Community Edition)

- **3 agents** — IngestAgent (two-step cached synthesis), QueryAgent (BM25 + LLM), LintAgent (contradiction + orphan detection + auto-resolution)
- **9 built-in skills** — PDF, URL, Markdown/TXT, DOCX, PPTX, XLSX/CSV, Image (vision), Web search (Tavily), YouTube transcript
- **Folder-based skill system** — each skill is a self-contained folder with a `SKILL.md` manifest; intent-based dispatch alongside extension matching; drop a folder in `skills/` to add a new format without touching core code
- **2 access surfaces** — CLI (thin HTTP client), HTTP REST API
- **Obsidian plugin** — ingest (file picker, URL, all sources, web search), query modal, lint report, jobs list — all from the command palette; ribbon shows engine health + page count
- **7 LLM providers** — Anthropic, OpenAI, Gemini (free tier), Groq (free tier), MiniMax (paid, multimodal), DeepSeek (paid, very cheap text-only), Ollama (local); switch with one config line
- **Two-step ingest** — `_analyse()` caches entity extraction + summary; decision prompt uses summary instead of full text; reduces cost on large documents
- **purpose.md scope filtering** — define what belongs in your wiki; the LLM skips out-of-scope sources cleanly
- **overview.md auto-summary** — 2-paragraph wiki overview regenerated automatically after every ingest
- **Audit CLI** — `synthadoc audit history / cost / events` query `audit.db`; `--analyse-only` flag previews ingest analysis before writing pages
- **3-layer cache** — embedding cache, LLM response cache, provider prompt cache
- **Cost guards** — configurable soft-warn and hard-gate USD thresholds
- **Hook system** — shell commands on `on_ingest_complete` and `on_lint_complete` lifecycle events; blocking or background; context passed as JSON on stdin
- **Job queue** — SQLite-backed, persistent, retry with exponential backoff; `failed` vs `dead` status distinction
- **Multi-wiki** — unlimited isolated wikis, each on its own port
- **OpenTelemetry** — traces, metrics, structured logs; OTLP export optional
- **Cross-platform** — Windows, Linux, macOS

### v0.2.0 (Community Edition)

- **Query decomposition** — `QueryAgent.decompose()` breaks complex questions into 1–N focused sub-questions (cap=4); parallel BM25 search per sub-question; merged and deduplicated by highest score; graceful fallback on LLM error; markdown fence stripping for cross-model robustness
- **Query audit trail** — `queries` table in `audit.db`; every query recorded with question text, sub-question count, tokens, cost, timestamp; `cost_summary()` now aggregates ingest + query spend; exposed via `GET /audit/queries`, `synthadoc audit queries`, and the Obsidian `Audit...` modal (Query history tab)
- **Per-model cost tracking** — per-token rate table covers all 5 providers; cost calculated for both ingest and query operations and stored in `audit.db`; Ollama records no API cost (local model); unknown models use a conservative fallback rate; exposed via `audit cost` CLI and `GET /audit/costs`
- **Knowledge gap detection** — three independent signals (too few pages, low BM25 max score, low content-overlap page count); query result carries a gap flag and targeted ingest suggestions when the wiki lacks relevant coverage; displayed as an Obsidian callout block in the plugin and CLI output
- **BM25 in-memory corpus cache** — `HybridSearch._cached_corpus` built once per session, invalidated via `invalidate_index()` after each page write; eliminates N×disk reads on decomposed queries
- **OpenAIProvider contract tests** — 4 tests covering happy path, system message, null content, and custom `base_url` forwarding; applies to OpenAI, Gemini, Groq, and Ollama (all use `OpenAIProvider`)
- **HTTP 502 on LLM failure** — `/query` GET and POST return 502 Bad Gateway (not raw 500) when the LLM provider is unreachable
- **Web search decomposition** — `SearchDecomposeAgent` breaks a web search intent into 1–4 focused keyword search strings (separate prompt from query decomposition); parallel Tavily searches; URL deduplication; graceful fallback on LLM error; integrated into `IngestAgent` at the web search fan-out point
- **New Obsidian commands** — `Lint: run`, `Lint: run with auto-resolve`, `Jobs: retry dead job...`, `Jobs: purge old completed/dead...`, `Wiki: regenerate scaffold...`; audit surfaces added as separate commands (later consolidated into `Audit...` in v0.5.0)
- **Vector search + semantic re-ranking** — opt-in hybrid BM25 + local vector search using `BAAI/bge-small-en-v1.5` via `fastembed`; one-time background migration embeds existing pages; BM25 serves during migration; enable with `[search] vector = true`
- **Obsidian web search live view** — `WebSearchModal` replaced with live-polling panel that shows phase text, pages list, and URL errors in real time; configurable poll interval; modal stays open until all fan-out URL jobs settle; job progress tracked via new `progress` column in `jobs.db`
- **Web search URL cap** — `synthadoc ingest "search for: …" --max-results N` limits total URLs enqueued across all sub-queries; Obsidian modal exposes the same as a numeric input (1–50, default 20); cap applied after dedup
- **Image ingest for OpenAI-compatible providers** — `OpenAIProvider` auto-converts Anthropic image blocks to OpenAI `image_url` format; Groq flagged as non-vision (`supports_vision = False`); image jobs routed to Groq get `fail_permanent` with a clear message
- **Job crash recovery** — `in_progress` jobs are reset to `pending` on server `init()`, so all pending work resumes automatically after a restart
- **Rate-limit requeue** — HTTP 429 responses from any LLM provider are detected and requeued via `requeue()` (retry counter unchanged), preserving the retry budget for real errors
- **Bulk cancel (`jobs cancel`)** — `synthadoc jobs cancel [-w wiki] [--yes]` marks all pending jobs as `skipped` in one operation; also `POST /jobs/cancel-pending`

### v0.3.0 (Community Edition)

- **Session wiki resolution (`synthadoc use`)** — `synthadoc use <name>` writes the default wiki to `~/.synthadoc/default_wiki`; all commands resolve it automatically via priority chain: `-w` flag > `SYNTHADOC_WIKI` env var > saved default > CWD fallback; hint messages simplified to `[wiki: <name>]`; `-w .` omitted from job hints when CWD is the active wiki
- **MiniMax reasoning-model fixes** — `OpenAIProvider` now handles three failure modes of reasoning models (e.g. MiniMax-M2.5): (1) `choices=null` response converted from silent `TypeError` to a descriptive `RuntimeError` with error code logged; (2) `content=null` with prose answer in `reasoning_content` — think-tag stripping then full-text fallback so query synthesis returns a real answer; (3) `APITimeoutError` caught, logged with the config key to set, then re-raised
- **Configurable LLM call timeout (`agents.llm_timeout_seconds`)** — new `[agents]` key (default `0` = no limit); passed as `timeout` to every OpenAI-compatible `create()` call; `APITimeoutError` logs an actionable message naming the exact config key; config.toml template ships the key commented out with a 5-line explanation of when to enable it
- **`parse_json_string_array` utility** — extracted shared fence-strip + JSON-parse + filter logic from `QueryAgent.decompose()` and `SearchDecomposeAgent.decompose()` into `synthadoc/agents/_utils.py`; 16 unit tests; LLM call failures and JSON-parse failures now log separate, distinct messages
- **DeepSeek provider** — `deepseek` added as an eighth provider; routes through `OpenAIProvider` with `base_url="https://api.deepseek.com/v1"` and `DEEPSEEK_API_KEY`; vision disabled (`_NO_VISION_HOSTS`); DeepSeek-R1 `<think>` tags in the `content` field are stripped by the existing regex; config.toml template ships a commented-out example for `deepseek-chat`
- **YouTube transcript skill** — `synthadoc ingest "https://www.youtube.com/watch?v=..."` extracts captions via the YouTube caption system (no API key, no audio download) and feeds the transcript through the existing IngestAgent pipeline. Short videos produce one wiki page; long videos chunk automatically. Graceful skip when no captions are available or the video is private. Tavily web search results that are YouTube URLs are routed automatically via the longest-prefix routing fix in `detect_skill`.
- **Longest-prefix URL routing** — `detect_skill` now selects the skill whose trigger prefix is the longest match, rather than the first match. This makes YouTube URLs reliably route to the YouTube skill ahead of the generic URL skill, and will correctly handle any future URL-specific skills without priority fields.
- **v0.2.0 gap fixes** — Ollama `eval_count` mapped to `output_tokens` (was always 0); `_SLUG_BLACKLIST` moved to module-level `frozenset`; synthetic URL fields in ingest_agent commented; four test-coverage gaps closed (no-text guard, orphan flag inversion, `/analyse` endpoint, hybrid-search partial-miss fallback)
- **Coding tool CLI providers (`claude-code`, `opencode`)** — users with a Claude Code or Opencode subscription can set `provider = "claude-code"` (or `"opencode"`) in `config.toml` and run all three agents (ingest, query, lint) without a separate API key. `CodingToolCLIProvider` abstract base handles subprocess mechanics (stdin prompt passing, timeout, exit code, stderr capture); `ClaudeCodeCLIProvider` and `OpencodeProvider` each implement `_build_command()`, `_parse_output()`, and `_is_quota_exhausted()`. Quota exhaustion raises `CodingToolQuotaExhaustedException` and permanently fails the job with a clear retry message. `synthadoc serve --provider <name>` overrides `config.toml` for the lifetime of the server process. Vector search falls back to BM25-only (CLI providers do not support `embed()`). Codex support planned for v0.4.0.
- **Knowledge gap detection hardening** — signal 5 redesigned from single-discriminating-term check to `min(qualifying_pages per specific term) == 0`, making multi-aspect queries deterministic; Windows asyncio `ConnectionResetError` (WinError 10054) downgraded from ERROR to DEBUG via a scoped exception handler; `aiosqlite` and `asyncio` noisy DEBUG output silenced.
- **CJK multilingual query support** — Chinese, Japanese, and Korean queries no longer trigger false knowledge-gap reports. `QueryAgent._key_terms` now detects CJK character ranges and skips whitespace-based tokenization (which produces whole-sentence tokens with doc_freq=0), leaving signals 1 and 2 (page count and BM25 score) active for language-agnostic coverage assessment.
- **ImageSkill standalone refactor** — `ImageSkill` now accepts `provider=` and performs the vision LLM call itself, returning populated text and token counts in `ExtractedContent`. `IngestAgent` injects its provider via `skill_kwargs` (same pattern as `YoutubeSkill`) and no longer contains a special `is_image` branch. The skill is now usable independently of the Synthadoc pipeline.
- **YouTube executive summary** — each ingested YouTube video page opens with an LLM-generated executive summary (what the video is about, main topics, key takeaway) followed by the full timestamped transcript. Summary is generated once and cached; CJK transcripts receive a higher word-limit for the summary. YouTube Shorts are fully supported alongside standard-length videos.
- **Obsidian UX improvements** — all modals are draggable and support full text selection and copy-paste; `Lint: run...` consolidates lint and auto-resolve into a single modal with an auto-resolve checkbox; `Jobs: retry failed or dead jobs...` shows a multi-select table with all checkboxes pre-ticked and polls progress live; `Synthadoc: Audit: events...` command added (table of system events with configurable limit); `Ingest: from URL...`, `Ingest: current file`, and `Wiki: regenerate scaffold...` modals all poll job status live.

### v0.4.0 (Community Edition)

- **Routing layer** — `ROUTING.md` groups wiki pages into named topic branches; `QueryAgent` picks 1–2 branches via a lightweight LLM call and restricts BM25 to those slugs, reducing noise on large wikis; falls back to full-corpus search when no branch is selected; `IngestAgent` auto-places new pages into the best branch on create
- **Alias expansion** — pages may carry `aliases:` in YAML frontmatter; `QueryAgent._expand_aliases` substitutes alias matches in the question with the canonical slug before search (longest-first to avoid partial-match conflicts)
- **Protected scaffold zone** — `<!-- synthadoc:scaffold -->` marker in `index.md` separates user-authored content (preserved) from scaffold-managed content (rewritten); absent marker → full rewrite (original behaviour)
- **Routing CLI** — `synthadoc routing init / validate / clean` commands manage `ROUTING.md` offline; `init` builds it from the current `index.md` branch structure; `validate` reports dangling slugs; `clean` removes them
- **Candidates staging** — new pages can be routed to `wiki/candidates/` based on `[ingest] staging_policy` (`off` / `all` / `threshold`); `threshold` mode compares page confidence against `staging_confidence_min`; candidates are excluded from BM25, lint, and contradiction detection until promoted
- **Candidates CLI** — `synthadoc staging policy` shows/sets the staging policy; `synthadoc candidates list / promote / discard` manage the candidate queue; policy changes take effect on next ingest without a server restart
- **ContextAgent** — `ContextAgent.build(goal)` decomposes the goal, runs parallel BM25 searches, merges by best score per slug, and greedily packs pages within a configurable token budget; omissions are recorded; output is a `ContextPack` with `to_markdown()` and `to_dict()` renderers
- **Context CLI + REST endpoint** — `synthadoc context build "..."` with `--tokens` and `--output` flags; prints to terminal by default, saves to any file with `--output`; typical uses: paste into an external LLM prompt, save next to a document you are writing, or pipe into another CLI tool; `POST /context/build` JSON endpoint; default token budget configurable via `[query] context_token_budget` (default 4000)
- **Plugin install CLI** — `synthadoc plugin install <wiki>` copies the pre-built Obsidian plugin (`main.js`, `manifest.json`, `styles.css`) from the repo's `obsidian-plugin/` directory into `<wiki-root>/.obsidian/plugins/synthadoc/`; replaces the previous manual file-copy step; wiki must be registered via `synthadoc install` first so the path can be resolved from the registry
- **Plugin upgrade CLI** — `synthadoc plugin upgrade` (no arguments) reads the wiki registry and reinstalls the latest plugin files into every registered vault; run once after each `pip install` upgrade to keep all wikis in sync without having to remember individual `plugin install` calls; wikis with stale registry paths are reported and skipped gracefully
- **Web search moved into Ingest modal** — the standalone `Synthadoc: Ingest: web search...` command palette entry is removed; web search is now the first tab of `Synthadoc: Ingest...`, consolidating all ingest surfaces in one place
- **Audit commands consolidated** — the four separate audit command palette entries (`Audit: ingest history...`, `Audit: cost summary...`, `Audit: query history...`, `Audit: events...`) are merged into a single `Synthadoc: Audit...` tabbed modal with tabs for Query history, Ingest history, Events, and Cost summary
- **Jobs commands consolidated** — the three separate jobs command palette entries (`Jobs: list...`, `Jobs: retry failed or dead jobs...`, `Jobs: purge old completed/dead...`) are merged into a single `Synthadoc: Jobs...` modal; a **Retry selected** button (enabled when ≥ 1 checked job is failed/dead/cancelled) replaces the standalone retry command; a **Purge old jobs** footer row (day threshold input + button) replaces the standalone purge command
- **ai-research demo template** — `synthadoc install ai-research --target <dir> --demo` installs a second demo wiki (alongside history-of-computing) with 12 pre-built AI/ML pages, five raw source files covering multiple ingest scenarios, a contradiction scenario (Gemini Ultra MMLU benchmark methodology dispute), and a pre-configured ROUTING.md
- **Decision cache prompt-awareness** — the decision-pass cache key (`ck2`) now includes a hash of the full decision prompt (purpose block + instruction template); any change to `purpose.md` content or the purpose-block instructions automatically invalidates cached decisions, preventing stale skip results from being served after prompt edits
- **YouTube always creates own page** — sources with a structured executive summary (YouTube transcripts) are forced to `action=create` even when the LLM suggests `action=update`, ensuring the executive summary and transcript are never appended to an existing page

### v0.5.0 (Community Edition)

- **Adversarial review** — concurrent independent LLM review of every wiki page after lint runs; flags overstated claims, unsupported assertions, and high-confidence statements the source material does not support; results stored as `lint_warnings: [{claim, concern}]` in page frontmatter; surfaced in redesigned 3-tab `Lint: report` modal (Contradictions / Orphans / Adversarial) and redesigned `synthadoc lint report` CLI output; configured via `[agents].adversarial` and `[lint].adversarial_max_per_page` (default 2) in `config.toml`; skipped with `synthadoc lint run --no-adversarial` (also clears stale warnings); cross-model review — a different model family from the ingest model reduces self-serving bias; concurrent via `asyncio.gather()` — a 100-page wiki completes in the same wall-clock time as one call; per-page rate-limit failures are non-fatal
- **Claim-level provenance** — during ingest, Pass 4 (`_annotate_citations()`) reads each page section alongside numbered source text and inserts `^[filename:L-L]` inline citation markers at the end of substantive paragraphs; markers map compiled claims to exact source line ranges; stored in the page body, recorded in `audit.db` `claim_citations` table, and validated by lint; local source sidecars written to `.synthadoc/extracted/` (plain-text `.txt` for all file types; pagemap JSON for PDFs to resolve line numbers to PDF page numbers); in Obsidian (Reading View only) markers render as interactive citation chips — one click opens the Source Viewer showing the referenced lines with ±5 lines of context; PDF sources show a page-jump button; `GET /provenance/citations` endpoint powers the **View Page Provenance** modal (sortable, paginated citation table); `synthadoc audit citations` CLI queries the same table with `--page` and `--broken` filters
- **Routing Obsidian plugin** — `Synthadoc: Routing: manage ROUTING.md...` command palette entry opens a modal panel with three buttons: **Init** creates ROUTING.md from the current index.md branch structure (enabled only when ROUTING.md does not exist), **Validate** reports dangling slugs, **Clean** removes dangling slugs from ROUTING.md; after each action results appear inline
- **Candidates Staging Obsidian plugin** — `Synthadoc: Staging: manage staging policy...` and `Synthadoc: Candidates: review candidate pages...` command palette entries; Staging modal shows policy state with segmented controls; Candidates modal shows a paginated table with promote/discard bulk and per-row actions
### v0.6.0 (Community Edition)

- **5-state lifecycle machine** — every wiki page tracks a `draft | active | contradicted | stale | archived` state in two new `audit.db` tables: `page_states` (fast current-state index, slug PK) and `lifecycle_events` (immutable audit log of every transition with slug, from/to state, reason, triggered_by, and timestamp)
- **Ingest creates draft pages** — all new pages are created with `status: draft` instead of `active`; pages must pass a lint run to be promoted
- **LintAgent lifecycle checks** — four automated checks run at the end of every lint pass: archived detection (source file missing → `archived`), stale detection (source hash mismatch → `stale`), draft promotion (draft + no active issues → `active`), manual-edit sync (frontmatter `status` ≠ DB → reconcile); skipped when `--no-lifecycle` is passed
- **Auto-retention** — `[audit] lifecycle_retention_days = N` in `config.toml` prunes old `lifecycle_events` at the end of each lint run; `0` = keep forever (default)
- **Lifecycle CLI** — `synthadoc lifecycle activate/archive/restore/log`, `synthadoc status` extended with per-state counts, `synthadoc audit lifecycle purge --before / --keep-latest`
- **Lifecycle HTTP API** — `GET /lifecycle/status`, `GET /lifecycle/events`, `POST /lifecycle/transition`
- **Lifecycle Obsidian plugin** — `Synthadoc: Manage Page Lifecycle` command opens `LifecycleModal`: sortable, filterable, paginated table of all pages with current state and last transition; valid transition action buttons per row; `ReasonModal` prompts for reason before committing; draft/stale badge links on lint modal and jobs panel open the table pre-filtered
- **Export formats** — `synthadoc export --format <fmt>` serializes the wiki in four formats assembled server-side with zero LLM calls: `llms.txt` (navigation index per llmstxt.org spec — active pages in `## Pages`, contradicted/stale in `## Needs Review`, archived omitted); `llms-full.txt` (flat content dump with `---` separators, provenance footnotes preserved verbatim, ≤5 MB with truncation notice); `graphml` (standard GraphML 1.1 — nodes=pages with `title`, `status`, `confidence`, `orphan`, `citation_count`, `inbound_link_count`, `routing_branch` attributes; edges=wikilinks with `edge_type="wikilink"`); `json` (agent-ready dump with `claims[]` per page, `lifecycle_history[]`, `compilation_cost_usd`, `total_compilation_cost_usd`, `routing.branch_memberships`); `POST /export` endpoint accepts `{format, status_filter, context_pack}`, returns raw content with appropriate `Content-Type`; Obsidian adds two commands: **Export Wiki** (format picker modal, writes to vault `exports/` folder) and **View Knowledge Graph** (embedded Cytoscape.js graph with lifecycle-colored nodes and "Export to file" button)
