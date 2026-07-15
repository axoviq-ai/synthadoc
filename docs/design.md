# Synthadoc — Design Document

**Version:** 1.0.2  
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
24. [Export Formats](#24-export-formats)
25. [Streaming Query and Query Cache](#25-streaming-query-and-query-cache)
26. [Web Chat UI and Session Management](#26-web-chat-ui-and-session-management)
27. [MCP Server](#27-mcp-server)
28. [Backup & Restore](#28-backup--restore)
29. [Pre-LLM Source Sanitizer](#29-pre-llm-source-sanitizer)
30. [Per-Source Truncation Flag](#30-per-source-truncation-flag)
31. [Proportional Context Budget](#31-proportional-context-budget)
32. [Knowledge Graph](#32-knowledge-graph)

**Appendices**
- [Appendix A — Release Feature Index](#appendix-a--release-feature-index)

---

## 1. Overview

Synthadoc is a **domain-agnostic LLM knowledge compilation engine**. It reads raw source documents and uses an LLM to synthesize them into a persistent structured wiki. Knowledge is compiled at **ingest time** — not at query time. The compiled wiki lives as plain Markdown files that are readable and editable without any tool running.

**Key design principles:**

- **Ingest-time compilation** — synthesis, cross-referencing, and contradiction detection happen once per source, not on every query.
- **Local-first** — all data stays on disk; the server binds only to `127.0.0.1`.
- **Obsidian-native** — wiki pages are valid Obsidian notes with `[[wikilinks]]`, YAML frontmatter, and Dataview compatibility.
- **Layered access** — CLI, HTTP REST API, and MCP server expose the same operations; the agent and storage logic is shared. The MCP layer positions Synthadoc as persistent domain memory: an AI client (Claude Desktop, Claude Code) acts as the reasoning brain while Synthadoc handles BM25 search, lifecycle, and the immutable audit trail.
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
type: person            # OKF knowledge type — set by IngestAgent during compilation
status: active          # active | contradicted | archived
confidence: high        # high | medium | low
created: '2026-04-10'
resource: https://example.com/turing-bio  # OKF primary source URL (URL sources only)
sources:
  - file: turing-biography.pdf
    hash: sha256:abc123…
    size: 204800
    ingested: '2026-04-10'
---

# Alan Turing

Content with [[wikilinks]] to related pages…
```

**`type` values** _(added in v0.9.0, OKF-required field)_: `concept` (default), `person`, `organization`, `technology`, `event`, `location`, `product`. Set automatically by IngestAgent during the analysis pass; absent on pages ingested before v0.9.0.

**`resource`** _(added in v0.9.0, OKF-optional field)_: the primary source URL for pages ingested from a URL source. Absent for local file sources and pre-v0.9.0 pages.

`resource` and `sources` are complementary, not duplicates:

| | `resource` | `sources` |
|---|---|---|
| Purpose | OKF external citation — one clean URL for agents and humans to follow | Synthadoc internal provenance — full audit record per contributing file |
| Cardinality | Single string (or absent) | Array — grows as more files are ingested into the same page |
| Contents | URL only | File path, SHA-256 hash, byte size, ingestion timestamp |
| Used for | OKF compatibility; agent consumption without Synthadoc-specific knowledge | Dedup, stale detection, cost audit trail |
| Local file sources | Absent | Present (file path + hash) |
| URL sources | Set to the source URL | Also present (URL + hash of URL string) |

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
5. Orchestrator instantiates IngestAgent
6. SkillAgent detects `.pdf`, lazy-loads `PdfSkill`, extracts text
7. IngestAgent Step 1 — Analysis: `_analyse()` extracts entities, tags, and a 3-sentence summary (cached under key `analyse-v1`)
8. IngestAgent Step 2 — Decision: LLM reads the full source text (bounded by `max_source_chars`) + BM25-retrieved candidate pages + `purpose.md` scope, decides per-page action (`create` / `update` / `flag` / `skip`). Pages with `status='active'` are protected — sources that conflict with them trigger `flag` rather than `update` (RULE 1b).
9. IngestAgent Step 3 — Write: applies actions; updates frontmatter; writes `[[wikilinks]]`; fires hooks
10. IngestAgent Step 4 — Overview: if any pages were created or updated, regenerates `wiki/overview.md`
11. Orchestrator calls `_guard_ingest_cost()` on the returned cost: soft warn → `logger.warning` only; hard gate → `cost_gate_exceeded` audit event + `fail_permanent` (job → DEAD). On success, job transitions to `completed`; `log.md` updated; `audit.db` record written

---

## 4. Agents

All agents are async Python classes. They receive a job context, write results to storage, and return a summary. Agents never call each other directly — they are dispatched by the Orchestrator.

### IngestAgent

Five-pass pipeline:

| Pass | Model | Purpose |
|------|-------|---------|
| 0 — Vision (optional) | Default | Extract text from image sources (`is_image=True`); requires a vision-capable provider |
| 0b — Key Data Extraction | None (regex) | Deterministic pre-processor: extracts numbers, percentages, currency amounts, ratios, formulas, underscore identifiers, and date ranges from source text via regex; appends them as a `[Key Data — extracted by pre-processor]` section before any LLM sees the text. Zero token cost; cannot hallucinate. Anchors the synthesis LLM to all quantitative candidates. |
| 1 — Analysis (`_analyse()`) | Default | Extract entities, tags, and a 3-sentence summary from raw text. Result cached under key `analyse-v1` keyed by SHA-256 of the text. |
| 2 — Candidate search | None (BM25) | Find existing wiki pages related to extracted entities |
| 3 — Decision | Default | LLM reads the full source text (bounded by `max_source_chars`) + BM25 candidates + `purpose.md` scope + status of each candidate page. Outputs per-page action: `create`, `update`, `flag`, `skip`. **RULE 1b:** a page with `status='active'` is human-reviewed and authoritative — when the source provides a conflicting value, date, formula, or conclusion, the action must be `flag`, not `update`. The only exception is a source that adds a topic the page does not yet mention at all. Decision cache version: `v2`. |
| 4 — Citation annotation (`_annotate_citations()`) | Default | For each page section being written, the LLM reads the section alongside the numbered source text and inserts `^[filename:L-L]` inline citation markers at the end of substantive paragraphs. Results cached by section SHA-256. Falls back gracefully (returns original section) on any LLM or parse failure — ingest always completes. Citations are recorded in `audit.db` `claim_citations` table. If no citation markers are present in the returned body, a `citation_pass4_no_markers` WARNING audit event is written — the page is still saved but the condition is flagged for re-ingest with a more capable model. Zero-citation results are not cached so a subsequent re-ingest can succeed. |
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

1. `len(candidates) < 3` — wiki has almost nothing on the topic. **Suppressed when TF fallback was used** (a small corpus with broad coverage may legitimately return fewer than 3 candidates — that is expected, not a gap).
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
| Citation presence (Check 5b) | Page body has ≥ 50 words and zero `^[filename:L-L]` citation markers → WARNING. Diagnostic only — does not block promotion to `active`. Indicates the annotation pass failed to produce markers, usually a model-compatibility issue (use Gemini 2.5 Flash or higher for reliable citation annotation). |

**Auto-resolution:** For contradictions, LintAgent asks the LLM to propose a resolution with a confidence score. If score ≥ `auto_resolve_confidence_threshold` (default 0.85), applies automatically. Below threshold, queues for human review.

**Index suggestion:** For orphan pages, LintAgent reads the page frontmatter and generates a ready-to-paste `wiki/index.md` entry: `- [[slug]] — tag1, tag2, tag3`.

**Orphan frontmatter sync:** After computing orphans, both `LintAgent.lint()` (server-side, via `POST /jobs/lint`) and `synthadoc lint report` (CLI, offline) write `orphan: true` or `orphan: false` to each eligible page's YAML frontmatter. This keeps the Obsidian Dataview query (`WHERE orphan = true`) in sync with the computed orphan state without requiring the server to be running after `lint report`.

**Auto-generated page exclusions:** The pages `index`, `dashboard`, `overview`, `log`, and `purpose` are excluded from both orphan detection and contradiction checking. Links from these pages do not count as real inbound references — a page linked only from `overview.md` is still reported as an orphan. These pages are also never flagged as contradicted by the ingest pipeline.

**Adversarial review _(v0.5.0)_:** After structural checks complete, `LintAgent` runs an independent LLM review of every non-excluded page concurrently via `asyncio.gather()` — a 100-page wiki completes in wall-clock time equal to one call. The adversarial provider is configured via `[agents].adversarial` (falls back to `[agents].default` if absent); using a different model family from the ingest model reduces self-serving bias. Results are stored as `lint_warnings: [{claim, concern}]` in each page's YAML frontmatter. The cap is `adversarial_max_per_page` (default 2). Rate-limit failures are caught per-page and stored as non-fatal entries. Skipped entirely when `--no-adversarial` is passed to `lint run`; in that case, existing `lint_warnings` are cleared from all pages.

### SkillAgent

Dispatches to the correct skill based on file extension, URL prefix, or intent keyword match. Manages 3-tier lazy loading. Returns `ExtractedContent` to IngestAgent.

When a source is a URL or an intent phrase (e.g. `search for: Dennis Ritchie`), IngestAgent skips the local file checks — there is no file to verify or hash. File-existence validation and SHA-256 dedup only apply to local file paths.

### ExportAgent

Serialises the wiki to one of five formats with zero additional LLM calls. Invoked via `synthadoc export --format <fmt>` or the Obsidian **Export Wiki** command.

| Format | Output |
|--------|--------|
| `llms.txt` | Active pages as a compact index (title + first-line summary) in the [llmstxt.org](https://llmstxt.org) spec; pages with `contradicted` or `stale` status appear in a **Needs Review** section |
| `llms-full.txt` | Full page content for all pages, separated by `---` dividers with status and confidence headers; no size limit |
| `graphml` | Directed wikilink graph — one node per page, one edge per `[[wikilink]]`; includes `label` (Gephi), `y:NodeLabel` (yEd), status, confidence, orphan flag, inbound link count, and routing branch per node |
| `json` | Full structured dump: content, tags, sources, claims (from audit DB), lifecycle history, routing branch memberships, per-page `ingest_cost_usd` and `ingest_tokens`, and total compilation cost |
| `okf` | [OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) bundle directory — one Markdown file per page with conformant YAML frontmatter (`type`, `title`, `description`, `resource`, `tags`, `timestamp`); `index.md` grouped by knowledge type; `log.md` lifecycle history; `[[wikilinks]]` rewritten to relative OKF paths |

**Status filter:** All formats accept `--status-filter active|contradicted|stale|archived|draft|all` (default `all`) to scope the export to a lifecycle subset. For `okf`, the accepted values are `all` (active + contradicted, the default) or `active` only — draft, stale, and archived pages are always excluded from OKF bundles regardless of the flag.

**OKF return type:** Unlike other formats (which return a single string), `okf` returns `dict[str, str]` — a map of relative file paths to file contents. The HTTP endpoint serialises this as a JSON manifest; the CLI writes the manifest as a directory tree. `--output` is required for `okf`.

**GraphML tool compatibility:** The file includes both a standard `label` data key (read by Gephi and Cytoscape) and a `y:ShapeNode/y:NodeLabel` element (read by yEd). No position data is embedded — run the tool's own layout algorithm after import.

### ActionAgent

Dispatches action-intent queries from the chat UI (e.g. "activate a draft page", "show lint report", "archive a stale page", "run scaffold"). Parses the user's free-text intent into a structured action via an LLM extraction prompt, then executes the action against the wiki and returns a human-readable result. When the intent is ambiguous (e.g. "activate a page" without specifying which), sets `needs_clarification=True` and returns a prompt and candidate list for the web UI to render as chip buttons.

### ScaffoldAgent

Generates and updates the wiki's structural pages. Reads all current wiki pages and asks the LLM to organise them into 5–8 domain-appropriate categories, then writes `wiki/index.md` (category index with wikilinks), `wiki/purpose.md` (scope statement), and `AGENTS.md` (ingest and query guidelines). Also stamps a `categories:` field on each page's YAML frontmatter. When `ROUTING.md` already exists, regenerates it to stay in sync with the updated index structure.

### RewriteAgent

Rewrites follow-up questions in multi-turn conversations into self-contained, standalone form before BM25 retrieval. Converts context-dependent phrases ("What came after that?", "Tell me more about his early life") into explicit questions ("What came after Alan Turing's work at Bletchley Park?") so keyword retrieval targets the correct pages without relying on conversation context. Only invoked when conversation history is non-empty. See also: [Multi-turn Conversation](#multi-turn-conversation).

### SummarizeAgent

Compresses the oldest conversation turns into a single `[Session summary: …]` assistant turn when a session exceeds `conversation_history_turns`. Prevents unbounded context growth across long sessions. Emits a `notice` SSE event the first time compression occurs so the user can see that earlier context was condensed. See also: [Multi-turn Conversation](#multi-turn-conversation).

### ContextAgent

Builds token-budgeted context packs for MCP tool consumers. See [Section 20 — Context Packs](#20-context-packs) for full detail.

### SearchDecomposeAgent

Decomposes a web search intent into 1–4 terse keyword search strings optimised for authoritative source retrieval. Uses a separate prompt from `QueryAgent`'s question decomposition — search decomposition asks "what distinct search strings would find the best sources?" (terse keyword phrases) rather than "what distinct questions does this ask?" (natural-language sub-questions). See [Web search fan-out](#web-search-fan-out) in the IngestAgent section.

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

**Compound identifier expansion:** When a token contains underscores, the tokenizer emits both the compound form and each component as separate tokens (`capex_growth` → `["capex_growth", "capex", "growth"]`). This expansion is applied at both index time and query time so that human-friendly queries match programmatic identifiers and vice versa. Leading/trailing underscores are stripped before splitting; no empty strings are emitted.

**TF fallback for small corpora:** When all BM25 scores in a result set are zero or negative (IDF collapse on a corpus of ≤ 2 documents, or a term present in every page), the search system falls back to normalised term frequency (TF) scoring: `TF(doc, query) = Σcount(term, doc) / len(doc_tokens)`. Results are returned in the same format as BM25 results with a `tf_fallback: True` flag on each `SearchResult`. This field is recorded in the audit trail and consumed by gap detection (see below).

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
| `POST` | `/lifecycle/transition` _(v0.6.0)_ | `{slug: str, to_state: str, reason?: str}` | `{slug, from_state, to_state, timestamp, cascade_links_removed_from: [str]}` _(cascade field added v1.0.2)_ |
| `GET` | `/query/stream` _(v0.7.0)_ | `?q=<question>&no_cache=<bool>&timeout_seconds=N` _(timeout added v0.8.0)_ | SSE stream of `data: <token>\n\n` events, terminated by `data: [DONE]\n\n` |
| `GET` | `/app` _(v0.7.0)_ | — | Serves the React SPA (web chat UI) |
| `GET` | `/sessions` _(v0.8.0)_ | — | `[{session_id, first_q, last_active, turn_count, questions: [str]}]` |
| `GET` | `/sessions/{session_id}/messages` _(v0.8.0)_ | — | `[{role, content, timestamp}]` |
| `GET` | `/graph` _(v1.0.0)_ | — | `{status, node_count, edge_count, cluster_count, nodes: [...], edges: [...]}` or `{status: "computing"}` on first call |

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
**Version:** 1.0.2

Each vault configures its server URL in plugin settings (default `http://127.0.0.1:7070`).

**Installation:** Build with `npm run build` in `obsidian-plugin/`, then copy `main.js` and
`manifest.json` to `<vault>/.obsidian/plugins/synthadoc/`. Enable in Settings → Community Plugins.
Reload the plugin (toggle off/on) after copying — a full Obsidian restart is not required.

**Reading View default:** `synthadoc plugin install` and `synthadoc plugin upgrade` write `"defaultViewMode": "preview"` to `.obsidian/app.json` after copying the plugin files. This causes Obsidian to open new notes in Reading View by default, which is required for `^[filename:L-L]` citation chips to render. Only `defaultViewMode` is written; all other keys in `app.json` are preserved. If `app.json` is malformed JSON the write is skipped and a warning is logged — the install still succeeds.

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
| `Synthadoc: Routing: manage ROUTING.md...` | Modal panel with three buttons. **Init** creates ROUTING.md from the current index.md branch structure (enabled only when ROUTING.md does not exist). **Validate** reports two things: dangling slugs (pages listed in ROUTING.md that no longer exist in the wiki) and unassigned slugs (pages that exist in index.md but are not listed in any ROUTING.md branch). Enabled only when ROUTING.md exists. **Clean** removes dangling slugs from ROUTING.md (enabled only when ROUTING.md exists). After each action the result appears inline with per-entry `[Branch] [[slug]]` detail rows. |
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
│   ├── run [-w wiki] [--scope contradictions|orphans|all] [--auto-resolve] [--no-adversarial] [--no-lifecycle] [--check-urls]
│   └── report [-w wiki]
├── jobs
│   ├── list [-w wiki] [--status pending|in_progress|completed|failed|skipped|dead|cancelled] [--sort created_at|status|operation] [--order asc|desc]
│   ├── status <id> [-w wiki]
│   ├── retry <id> [-w wiki]
│   ├── delete <id> [-w wiki]
│   ├── cancel [-w wiki] [--yes]
│   └── purge --older-than <days> [-w wiki]
├── routing
│   ├── init [-w wiki]                            — generate ROUTING.md from index.md branch structure
│   ├── validate [-w wiki]                        — report dangling slugs and cross-branch duplicates
│   └── clean [-w wiki]                           — remove dangling slugs from ROUTING.md
├── staging
│   └── policy [off|all|threshold] [--min-confidence high|medium|low] [-w wiki]
├── candidates
│   ├── list [-w wiki]
│   ├── promote <slug>|--all [-w wiki]
│   └── discard <slug>|--all [-w wiki]
├── context
│   └── build "<goal>" [-w wiki] [--tokens N] [--output <file>]
├── export -f <fmt> [-o <path>] [-s <state>] [-w wiki]    — llms.txt, llms-full.txt, graphml, json, okf
├── status [-w wiki]
├── lifecycle
│   ├── activate <slug> [-w wiki] [--reason "<str>"]
│   ├── archive  <slug> [-w wiki] [--reason "<str>"]
│   ├── restore  <slug> [-w wiki] [--reason "<str>"]
│   └── log      [slug] [-w wiki] [--state <state>]
├── audit
│   ├── history [-w wiki] [--limit N] [--json]
│   ├── cost [-w wiki] [--days N] [--json]
│   ├── queries [-w wiki] [--limit N] [--json]
│   ├── events [-w wiki] [--limit N] [--json]
│   ├── citations [-w wiki] [--page <slug>] [--source <file>] [--broken] [--json]
│   └── lifecycle
│       └── purge -w wiki (--before <date> | --keep-latest <n>)
├── backup [-w wiki] [--output <dir>] [--no-sources] [--no-exports] [--no-cache]
├── restore <backup.zip> [--name <wiki>] [--target <dir>] [--port <N>]
├── cache clear [-w wiki]
└── schedule
    ├── add --op "<cmd>" --cron "<expr>" [-w wiki]
    ├── list [-w wiki]
    ├── remove <id> [-w wiki]
    ├── apply [-w wiki]
    ├── run --op "<cmd>" [-w wiki]
    └── history [-w wiki] [-n N]
```

`synthadoc status -w <wiki>` now shows a per-state page count breakdown alongside the existing page total and job counts.

### `schedule` sub-commands

| Command | Description |
|---|---|
| `schedule add --op "<cmd>" --cron "<expr>"` | Register a single recurring job with the scheduler |
| `schedule apply` | Bulk-register all jobs declared in `[[schedule.jobs]]` in `config.toml`; idempotent alternative to running `schedule add` once per job |
| `schedule list` | List all registered jobs with their cron expression, next run time, last run time, and last result |
| `schedule remove <id>` | Remove a registered job by ID |
| `schedule run --op "<cmd>"` | Execute an operation immediately and record the result in the audit trail |
| `schedule history` | Show recent scheduled run history from the audit trail |

`schedule apply` is the recommended setup path when jobs are declared in `config.toml`. It reads the `[[schedule.jobs]]` array and registers every entry in one command, making schedule configuration reproducible and version-controllable:

```bash
# Declare jobs in .synthadoc/config.toml
# [[schedule.jobs]]
# op   = "ingest --batch raw_sources/"
# cron = "0 2 * * *"
#
# [[schedule.jobs]]
# op   = "lint run"
# cron = "0 3 * * 0"

# Register all declared jobs at once
synthadoc schedule apply -w my-wiki
```

### `query` options

| Flag | Default | Description |
|------|---------|-------------|
| `--save` | off | Save the answer as a new wiki page |
| `--no-stream` | off | Disable token-by-token streaming; print the full answer when complete. Use in scripts, pipes, or terminals that do not handle ANSI escape codes. |
| `--no-cache` | off | Bypass the query result cache and always call the LLM. |
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
| `ERR-WIKI-007` | Backup requires a newer `db_schema_version` than installed |
| `ERR-CFG-001` | Required API key environment variable not set |
| `ERR-CFG-002` | Provider name not recognised |
| `ERR-SKILL-001` | No skill matched the source string |
| `ERR-SKILL-002` | Required pip package for skill not installed |
| `ERR-SKILL-003` | URL returned 403 (bot/paywall protection) |
| `ERR-SKILL-004` | `TAVILY_API_KEY` not set for web search |
| `ERR-INGEST-001` | Source file or directory not found |
| `ERR-INGEST-002` | Source file exists but is empty |
| `ERR-INGEST-003` | `--batch` target is not a directory |
| `ERR-QUERY-001` | LLM synthesis timed out; retry the query |
| `ERR-JOB-001` | Job ID does not exist in `jobs.db` |
| `ERR-PROV-001` | Daily API quota exhausted for today |
| `ERR-PROV-002` | Coding tool CLI usage quota exhausted |
| `ERR-AGENT-001` | LLM agent call failed (empty response, bad JSON, timeout) |

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
default = { provider = "anthropic", model = "claude-opus-4-8" }
lint    = { model = "claude-haiku-4-5-20251001" }

[wikis]
research = "~/wikis/research"

[observability]
exporter      = "file"                    # or "otlp"
otlp_endpoint = "http://localhost:4317"   # used when exporter = "otlp"
```

### Provider switching

All eight supported providers (`anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `qwen`, `ollama`) share the same config key. Gemini, Groq, MiniMax, DeepSeek, and Qwen (DashScope) use OpenAI-compatible endpoints internally, so no custom provider class is needed — just set the provider name and supply the corresponding API key:

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
| `qwen` | `QWEN_API_KEY` | Yes — 1M free tokens (90-day trial), then paid DashScope | Model-dependent |
| `ollama` | _(none)_ | **Yes** — fully local; **GPU required** — CPU-only inference is too slow for interactive use | Model-dependent |

### Coding tool CLI providers — no API key needed

If you have an active **Claude Code** or **Opencode** subscription, you can use it as the LLM provider with no separate API key.

**Requirements:** the CLI tool must be installed and reachable on `PATH`:
- Claude Code: `claude` binary — install via `npm install -g @anthropic-ai/claude-code`
- Opencode: `opencode` binary — install via `npm install -g opencode`

**Configuration — set in `<wiki-root>/.synthadoc/config.toml`:**

```toml
[agents]
default = { provider = "claude-code", model = "claude-opus-4-8" }
lint    = { provider = "claude-code", model = "claude-haiku-4-5-20251001" }
```

For Opencode:

```toml
[agents]
default = { provider = "opencode", model = "anthropic/claude-opus-4-8" }
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
default = { provider = "anthropic", model = "claude-opus-4-8" }
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
# Citation pass (Pass 4) tuning — these two settings work together:
#   citation_source_lines — how many lines of the source the LLM sees when placing ^[...] markers.
#                           Increase if lint reports out_of_range on long sources (transcripts, PDFs).
#   citation_max_tokens   — output token budget for the annotated section returned by the LLM.
#                           Increase if you raise citation_source_lines and have long wiki sections.
# citation_source_lines = 400
# citation_max_tokens = 8192

[logs]
level        = "INFO"
max_file_mb  = 5
backup_count = 5

[hooks]
on_ingest_complete = "python hooks/git-auto-commit.py"                    # non-blocking
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
| `wiki.domain` | str | `"General"` | Topic scope of the wiki. Used in prompts to keep ingest focused. Example: `"Machine Learning"` or `"Quantum Computing"`. |
| `agents.default.provider` | str | `"gemini"` | LLM provider: `anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `qwen`, `ollama` |
| `agents.default.model` | str | `"gemini-2.5-flash"` | Model ID passed to the provider API |
| `agents.default.base_url` | str | `""` | Override the provider's API endpoint. Use this to point any OpenAI-compatible provider at a custom URL (e.g. a local proxy or a private deployment). |
| `agents.default.thinking` | str | `""` | Reasoning mode: `"disabled"` turns off chain-of-thought (faster, cheaper on MiniMax M3 and Qwen); `"enabled"` or `"adaptive"` turns it on. Empty string uses the provider's default. Applies to `minimax` and `qwen` (DashScope) providers; ignored by others. |
| `agents.ingest.provider` | str | (inherits default) | Override provider/model for the ingest agent only. Useful to use a cheap fast model for ingest while keeping a high-quality model for queries. |
| `agents.ingest.model` | str | (inherits default) | Model ID for the ingest agent override. |
| `agents.query.provider` | str | (inherits default) | Override provider/model for query answering only. |
| `agents.query.model` | str | (inherits default) | Model ID for the query agent override. |
| `agents.lint.provider` | str | (inherits default) | Override provider/model for the lint agent only. |
| `agents.lint.model` | str | (inherits default) | Model ID for the lint agent override. |
| `agents.adversarial.provider` | str | (inherits default) | Dedicated LLM provider for adversarial lint review. Falls back to `agents.default` when not set. Cross-model adversarial reduces self-serving bias — a different model family evaluates claims independently. |
| `agents.adversarial.model` | str | (inherits default) | Model ID for the adversarial reviewer. For maximum independence, choose a model from a different family than the ingest model. |
| `agents.llm_timeout_seconds` | int | `0` | Per-call LLM timeout in seconds; `0` = no limit. Set to e.g. `90` when using reasoning models (MiniMax-M2.5, DeepSeek-R1) that can exceed their internal generation budget silently. Restart required. |
| `agents.scaffold_max_tokens` | int | `8192` | Max output tokens for the scaffold (page generation) agent. Increase to `16384`+ when using reasoning models on large wikis where the default budget is exhausted. |
| `agents.query_max_tokens` | int | `8192` | Max output tokens for the query agent. Increase if reasoning models exhaust their budget before completing the answer. |
| `lint.adversarial_max_per_page` | int | `2` | Maximum adversarial warnings flagged per page. Raise to 3–5 for a thorough audit; lower to 1 to reduce noise on large wikis. |
| `lint.check_url_availability` | bool | `false` | When `true`, lint performs an HTTP HEAD check on every URL source and flags unreachable URLs. Adds network calls to each lint run; opt-in only. |
| `server.host` | str | `"127.0.0.1"` | Bind address. Change to `"0.0.0.0"` to expose the server on all interfaces (e.g. for LAN access). No built-in auth — restrict via firewall when exposing. |
| `server.port` | int | `7070` | HTTP listen port. Change when running multiple wikis simultaneously. |
| `ingest.max_pages_per_ingest` | int | `15` | Max pages one ingest job may create or update. |
| `ingest.chunk_size` | int | `1500` | Text chunk size in characters for BM25 indexing. |
| `ingest.chunk_overlap` | int | `150` | Overlap between consecutive chunks. |
| `ingest.fetch_timeout_seconds` | int | `30` | Seconds to wait for a URL response before failing the fetch. |
| `ingest.staging_policy` | str | `"off"` | Candidate staging gate: `"off"` = commit pages immediately; `"all"` = stage all new pages for review; `"threshold"` = stage only pages below `staging_confidence_min`. |
| `ingest.staging_confidence_min` | str | `"high"` | Minimum confidence to auto-commit when `staging_policy = "threshold"`. Values: `"high"`, `"medium"`, `"low"`. Pages below this threshold are held as candidates. |
| `query.gap_score_threshold` | float | `2.0` | BM25 score below which a knowledge gap is detected and `suggested_searches` are returned instead of (or alongside) an answer. Lower = more sensitive gap detection. |
| `query.context_token_budget` | int | `4000` | Token budget for context pack assembly. Increase for richer context on complex queries; decrease if hitting prompt size limits. |
| `queue.max_parallel_ingest` | int | `4` | Max concurrent ingest agents |
| `queue.max_retries` | int | `3` | Retries before job → dead |
| `queue.backoff_base_seconds` | int | `5` | Exponential backoff base (±20% jitter) |
| `cache.version` | str | `"4"` | Bump to invalidate all cached LLM responses without touching source code |
| `cost.soft_warn_usd` | float | `0.50` | Emit `logger.warning` in server log when per-job ingest cost exceeds this threshold; job continues normally |
| `cost.hard_gate_usd` | float | `2.00` | Permanently fail the ingest job (DEAD) and record a `cost_gate_exceeded` audit event when per-job cost exceeds this threshold |
| `cost.auto_resolve_confidence_threshold` | float | `0.85` | Auto-apply lint resolutions above this score |
| `chat.conversation_history_turns` | int | `5` | Number of prior conversation turns injected into each query prompt for multi-turn context. Set to `0` to disable conversation history (each query answered independently). |
| `chat.session_retention_days` | int | `30` | Days to retain chat session history in `audit.db`. Sessions older than this are pruned automatically. |
| `audit.lifecycle_retention_days` | int | `0` | Days to retain lifecycle events in `audit.db`. `0` = keep forever. When set, events older than this threshold are pruned at the end of each lint run. |
| `audit.url_staleness_days` | int | `0` | Days after which URL-sourced pages are automatically marked `stale` if the source URL has not been re-ingested. `0` = disabled. |
| `logs.level` | str | `"INFO"` | Console log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `logs.max_file_mb` | int | `5` | Rotate `synthadoc.log` at this size (MB) |
| `logs.backup_count` | int | `5` | Rotated log files to keep; total disk ≈ `max_file_mb × (backup_count + 1)` |
| `web_search.provider` | str | `"tavily"` | Web search provider (currently only `tavily` supported) |
| `web_search.max_results` | int | `20` | Maximum results fetched per web search query |
| `search.vector` | bool | `false` | Enable semantic re-ranking; downloads `BAAI/bge-small-en-v1.5` (~130 MB) once on first enable |
| `search.vector_top_candidates` | int | `20` | BM25 candidate pool size when vector re-ranking is active |
| `ingest.max_source_chars` | int | `32000` | Character limit applied to each source before the LLM call. Sources exceeding this limit are truncated; the page's `sources:` frontmatter entry gets `truncated: true` and lint emits a warning. Override per-run with `--max-source-chars N`. _(v1.0.0)_ |
| `ingest.citation_source_lines` | int | `400` | Number of source lines the LLM sees during Pass 4 (citation annotation). Increase if lint reports `out_of_range` on long sources such as transcripts or PDFs. Raise `citation_max_tokens` in proportion when increasing this value. |
| `ingest.citation_max_tokens` | int | `8192` | Output token budget for the annotated section returned by Pass 4. Increase when `citation_source_lines` is raised or wiki sections are long, to avoid truncated annotations. |
| `query.context_wiki_pct` | float | `0.60` | Fraction of the model context window reserved for wiki source pages. _(v1.0.0)_ |
| `query.context_history_pct` | float | `0.20` | Fraction reserved for conversation history. _(v1.0.0)_ |
| `query.context_system_pct` | float | `0.15` | Fraction reserved for system prompt and instructions. Parsed and validated but not yet enforced as a hard cap in v1.0.0. _(v1.0.0)_ |
| `query.context_index_pct` | float | `0.05` | Fraction reserved for the wiki index preamble. Parsed and validated but not yet enforced as a hard cap in v1.0.0. _(v1.0.0)_ |
| `query.context_window` | int | _(auto)_ | Override the built-in context window lookup for the configured model. Use when running a local or custom model whose window size is not in the built-in table. _(v1.0.0)_ |

---

## 11. Hook System

Hooks are shell commands executed when lifecycle events fire. They are configured in `.synthadoc/config.toml` under `[hooks]` and receive a JSON context object on stdin.

### Configuration

```toml
# .synthadoc/config.toml

[hooks]
on_ingest_complete = "python hooks/git-auto-commit.py"                     # non-blocking
on_lint_complete   = { cmd = "python hooks/notify.py", blocking = true }   # blocking
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

Four independent cache layers:

### Layer 1 — Vector embedding cache (`embeddings.db`) — optional

Stores fastembed vector embeddings for each wiki page, used to re-rank BM25 results by semantic similarity. Only active when `[search] vector = true` in `config.toml` and the `fastembed` optional dependency is installed (`pip install synthadoc[vectors]`). BM25 search is always computed in-memory and is never persisted to disk.

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

### Layer 3 — Query result cache (`cache.db` — `query_cache` table)

Stores full query answers keyed by `question + wiki_epoch + model`. The `wiki_epoch` is a monotonic counter incremented on every ingest or lifecycle state change, so any wiki update automatically invalidates all cached answers.

**Cache key:**

```python
def make_query_cache_key(question: str, epoch: int, model: str = "") -> str:
    normalized = " ".join(question.lower().split())   # collapse whitespace, lowercase
    payload = f"{normalized}|{epoch}|{model}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
```

**Invalidation triggers:**

| Trigger | Behavior |
|---------|----------|
| Any `ingest` or lifecycle change | `wiki_epoch` incremented → all query cache entries for prior epoch bypassed |
| `--no-cache` flag on query | Cache lookup skipped; fresh LLM call; result repopulated |
| `cache clear` | Deletes all rows from both `response_cache` and `query_cache` tables |

### Layer 4 — Provider prompt cache

Anthropic, OpenAI, and compatible providers cache stable prompt segments server-side. Long system prompts and `AGENTS.md` content hit this cache on repeated calls, giving 50–90% token savings.

**Target cache hit rate:** > 80% on repeated lint runs across unchanged pages.

---

## 13. Cost Guard

**Files:** `synthadoc/core/cost_guard.py`, `synthadoc/providers/pricing.py`

Cost tracking is live: `estimate_cost()` is called after each ingest and query operation and the result is written to `audit.db`. The `CostGuard` threshold enforcement is wired into the ingest pipeline: `Orchestrator._guard_ingest_cost()` is called after each ingest LLM call with the returned cost, before the job is marked complete.

### Thresholds

| Threshold | Default | Behaviour |
|-----------|---------|-----------|
| `soft_warn_usd` | $0.50 | `logger.warning` in server log; job continues normally |
| `hard_gate_usd` | $2.00 | Server/ingest path: records `cost_gate_exceeded` audit event + permanently fails job (DEAD). Interactive CLI: prompts `Proceed? [y/N]` |

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
| Anthropic | claude-opus-4-7 | $0.000005 | $0.000025 |
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

HTTP and MCP servers bind to `127.0.0.1` by default. The bind address is configurable via `server.host` in `config.toml` (e.g. `host = "0.0.0.0"` to expose on all interfaces for LAN access). No built-in authentication — restrict via firewall when exposing beyond loopback. Remote access without a reverse proxy is not recommended on shared or networked machines.

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
  assets/              ← primary resource dir; load with self.get_resource("format-notes.md")
    format-notes.md
  references/          ← secondary resource dir (also searched by get_resource)
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

**Skill discovery priority:** `extra_dirs` (passed at runtime) → `<wiki-root>/skills/` → `~/.synthadoc/skills/` → pip entry points (`synthadoc.skills` group) → built-ins. To distribute a skill as a pip package, declare an entry point pointing to the skill folder in your `pyproject.toml`.

### Writing a provider

Built-in providers: `anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `qwen`, `ollama`. For any provider that exposes an OpenAI-compatible API, no custom class is needed — the built-in `openai` provider with a custom `base_url` is sufficient.

For a fully proprietary API, subclass `LLMProvider` and wire it into `synthadoc/providers/__init__.py`:

```python
# SPDX-License-Identifier: MIT
from synthadoc.providers.base import LLMProvider, Message, CompletionResponse
from typing import Optional

class MyProvider(LLMProvider):
    supports_vision: bool = False   # set True only if the API accepts image inputs

    async def complete(
        self,
        messages: list[Message],
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        # Call your API …
        return CompletionResponse(
            text="…",
            input_tokens=N,
            output_tokens=M,
        )

    async def complete_stream(self, messages, system=None, temperature=0.0, max_tokens=4096):
        """Optional — override for streaming support."""
        async for token in your_api_stream(...):
            yield token
```

Add the provider name to `KNOWN_PROVIDERS` in `synthadoc/config.py` and add an `if name == "my_provider":` branch in `synthadoc/providers/__init__.py` that imports and returns an instance of your class.

### Writing a hook

Hooks fire after key operations. They can be in any language; the process receives JSON on stdin and must exit 0 on success.

**Available events:**

| Event | Fired after | JSON context fields |
|---|---|---|
| `on_ingest_complete` | Every completed ingest job | `event`, `wiki`, `source`, `pages_created`, `pages_updated`, `pages_flagged`, `tokens_used`, `cost_usd` |
| `on_lint_complete` | Every completed lint run | `event`, `wiki`, `contradictions_found`, `orphans` |

**Register hooks in `.synthadoc/config.toml`:**

```toml
[hooks]
on_ingest_complete = "hooks/notify.sh"                       # non-blocking (default)
on_lint_complete   = { cmd = "hooks/alert.sh", blocking = true }  # blocking: error aborts the run
```

**Example hook script:**

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
| `synthadoc routing validate` | Report dangling slugs and unassigned slugs (dry run) |
| `synthadoc routing clean` | Remove dangling slugs from ROUTING.md |

All commands accept `-w <wiki>` / `--wiki <wiki>` to target a specific wiki.

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

Every wiki page moves through a defined set of states that reflect its review status and the health of its source material. Pages start as `draft` — compiled but not yet validated — and advance to `active` when lint passes all checks. Subsequent changes to the source file on disk push the page to `stale`; when all local source files are missing from disk the page is transitioned to `archived` (if only some sources are missing it is transitioned to `stale` instead). Manual transitions follow a defined graph (see Transition rules below); only semantically valid paths are permitted. Lint and ingest write state directly and are not subject to the graph restriction.

### States

| State | Meaning | How to reach it |
|---|---|---|
| `draft` | Newly compiled, not yet lint-reviewed | Automatic on ingest |
| `active` | Lint-reviewed, current, trusted | Lint auto-promotes from `draft` |
| `contradicted` | Conflict detected | Lint detects contradiction between sources |
| `stale` | Source file changed since last ingest | Lint detects SHA-256 hash mismatch |
| `archived` | Source removed or explicitly retired | Lint auto-archives on missing source; or manual |

### Transition rules

Automated transitions (lint, ingest) write state directly and are not subject to the graph. User-driven transitions (CLI, HTTP API, MCP) are validated against `ALLOWED_LIFECYCLE_TRANSITIONS` in `synthadoc/storage/wiki.py`; invalid paths are rejected with HTTP 422 or an MCP error dict.

| From | To | Trigger | Notes |
|---|---|---|---|
| _(none)_ | `draft` | ingest | New page created by ingest |
| `draft` | `active` | lint, cli/api/mcp | Lint auto-promotes when all checks pass; or manual activate |
| `draft` | `archived` | cli/api/mcp | Abandon a draft without publishing |
| `active` | `contradicted` | lint, cli/api/mcp | Lint detects conflict automatically; or user manually flags |
| `active` | `stale` | lint | Local source: SHA-256 hash mismatch; URL source older than `url_staleness_days` |
| `active` | `archived` | lint, cli/api/mcp | Lint: local source missing or URL 404/410; or manual retire |
| `stale` | `draft` | cli/api/mcp | Revise stale content — puts page back in review queue |
| `stale` | `active` | cli/api/mcp | Re-validate without revision — user confirms content still accurate |
| `stale` | `archived` | lint, cli/api/mcp | Lint: source gone; or manual archive |
| `contradicted` | `draft` | cli/api/mcp | Revise contradicted content — resets to review queue |
| `contradicted` | `active` | cli/api/mcp | Resolve contradiction and re-activate directly |
| `contradicted` | `archived` | cli/api/mcp | Archive after reviewing the conflict |
| `archived` | `draft` | cli/api/mcp | Restore for revision — places page back in review queue |

Transitions not in this table are rejected. Notable blocked paths: `stale ↔ contradicted` (different issue types that should not be crossed directly), `archived → active/stale/contradicted` (must go through `draft` for re-review first), `draft → stale/contradicted` (unpublished pages cannot be in those states).

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

For **local file sources**: lint evaluates all local (non-URL) source paths listed in the page's frontmatter. If **all** of them are missing from disk, the page is transitioned to `archived`. If only **some** are missing — meaning valid content from at least one source still exists — the page is transitioned to `stale` instead, preserving it for re-ingest rather than discarding it. _(v1.0.2: previously any single missing source triggered an immediate archive.)_

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

#### Cascade link cleanup

Whenever a page transitions to `archived` — whether triggered manually (`synthadoc lifecycle archive`), via the Obsidian Lifecycle modal, the MCP `synthadoc_lifecycle` tool, or automatically by lint detecting a missing source — Synthadoc immediately scans all other active pages and removes every `[[archived-slug]]` wikilink pointing to the now-archived page.

- **Inline links** — `[[archived-slug]]` becomes plain text (the display text if an alias was used, otherwise the slug itself).
- **List-item links** — a list item whose only content is `[[archived-slug]]` is dropped entirely.
- **Archived pages are skipped** — pages already archived are not rewritten.
- **System pages are skipped** — index, overview, dashboard, log, and purpose pages are excluded.

The cleanup runs synchronously before the response is returned, so the wiki is consistent immediately. The CLI and MCP responses include a `cascade_links_removed_from` field listing the affected slugs. During `lint run`, cascade is batched once after all auto-archive transitions complete, and the count is added to `dangling_links_removed` in the lint report.

Lint's existing periodic dangling-link cleanup (`lint run --scope orphans`) remains in place as a safety net for any dead links that predate this feature or arrive through other paths.

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

The `synthadoc export` command serializes the wiki in five machine-readable formats, assembled server-side from cached data with zero additional LLM calls. Requires `synthadoc serve` to be running.

### Formats

**`llms.txt`** — Navigation index per the [llmstxt.org](https://llmstxt.org/) spec. Active pages appear under `## Pages` with a one-line description; contradicted and stale pages appear under `## Needs Review` with a reason note; archived pages are omitted entirely. With `--status active` only `## Pages` is emitted.

**`llms-full.txt`** — Flat content dump. Pages are separated by `---`. Each page opens with `Status: <state> | Confidence: <level> | Tags: ...`. Provenance footnotes (`^[source.txt:42-58]`) are preserved verbatim in the body. No size limit — the full wiki is always exported. For very large wikis a streaming export path is planned as a future enhancement.

**`graphml`** — Standard GraphML 1.1. Nodes = pages; edges = wikilinks extracted from page bodies. Node attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `label` | string | Human-readable page title — read by Gephi and Cytoscape as the display label |
| `title` | string | Same as `label`; retained for backwards compatibility |
| `status` | string | Lifecycle state (`draft`, `active`, `contradicted`, `stale`, `archived`) |
| `confidence` | string | Ingest confidence level |
| `orphan` | boolean | `true` if the page has zero inbound wikilinks |
| `citation_count` | int | Reserved; always `0` in current release |
| `inbound_link_count` | int | Number of other pages that link to this page |
| `routing_branch` | string | Branch name from ROUTING.md membership |

All edges carry `edge_type="wikilink"`. Self-links are suppressed. The file also embeds a `y:ShapeNode/y:NodeLabel` element (yEd namespace) so node labels render natively when the file is opened in **yEd Graph Editor**. No position data is embedded — run the tool's layout algorithm after import. Tested tools: yEd (Layout → Organic or Hierarchical), Gephi (enable labels via the Aα button in the bottom toolbar; run ForceAtlas2), Cytoscape (File → Import → Network from File).

**`json`** — Agent-ready structured dump. Each page object contains:

| Field | Description |
|-------|-------------|
| `claims[]` | Source file, line range, claim excerpt — from the claim provenance audit database |
| `lifecycle_history[]` | Every state transition with `from`, `to`, `timestamp`, `triggered_by`, `reason` |
| `ingest_cost_usd` | Cumulative LLM cost (USD) across all source files that contributed to this page |
| `ingest_tokens` | Cumulative token count across all ingest calls for this page |
| `sources[]` | Source file metadata: file, hash, size, ingested timestamp |
| `lint_warnings[]` | Adversarial review findings: `{claim, concern}` pairs |

Wiki-level fields: `total_compilation_cost_usd`, `routing.branch_memberships`, `exported_at`, `page_count`.

**`okf`** — [Open Knowledge Format v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) bundle directory. Unlike other formats, `okf` produces a **directory tree** rather than a single file. The bundle is directly consumable by any OKF-aware agent or tool without code changes.

Bundle layout:
```
<output-dir>/
  index.md        # OKF index — pages grouped by knowledge type
  log.md          # lifecycle change history, newest first
  wiki/
    <slug>.md     # one OKF concept file per wiki page
```

Each concept file carries a conformant frontmatter block:

```yaml
type: person                  # from WikiPage.type; fallback "concept" for old pages
title: Alan Turing
description: Father of theoretical computer science and pioneer of the Turing machine.
resource: https://example.com/turing-bio   # omitted for local-file sources
tags: mathematics, computation, cryptography
timestamp: '2026-04-22'       # WikiPage.updated ?? WikiPage.created
status: active                # Synthadoc extension — OKF consumers tolerate unknown fields
confidence: high              # Synthadoc extension
```

OKF conformance rules satisfied: (1) every `.md` has parseable frontmatter; (2) every frontmatter has a non-empty `type`; (3) reserved filenames follow spec structure. Synthadoc-specific fields (`status`, `confidence`) are preserved as extensions — the spec requires consumers to tolerate unknown keys.

`[[wikilinks]]` in page bodies are rewritten to OKF-style relative paths (`[Title](slug.md)`) so cross-links are valid within the bundle.

### CLI

```bash
synthadoc export --format <fmt> [--output <path>] [--status <state>] [--context-pack <name>] [--wiki <name>]
```

Outputs to stdout by default; `--output` writes to a file. For `--format okf`, `--output` is required and must be a directory path. `--status` filters pages by lifecycle state (`all` / `active` / `draft` / `stale` / `contradicted` / `archived`). For `--format okf`, only `all` (active + contradicted, the default) or `active` are meaningful — draft, stale, and archived pages are always excluded from OKF bundles.

### POST /export endpoint

Accepts `{ format, status_filter }`. Returns raw content with appropriate `Content-Type`:

| Format | Content-Type |
|--------|-------------|
| `llms.txt`, `llms-full.txt` | `text/plain; charset=utf-8` |
| `graphml` | `application/xml` |
| `json` | `application/json` |
| `okf` | `application/json` — a JSON object mapping relative file paths to file contents (`{"index.md": "...", "wiki/alan-turing.md": "..."}`) |

Returns 422 for unknown format. No LLM calls.

### Obsidian

**`Synthadoc: Export Wiki`** opens a modal with:
- A brief description panel explaining each format
- Format dropdown (json / llms.txt / llms-full.txt / graphml / okf)
- Output path field (full-width, pre-filled with today's date and correct extension, editable)
- Status filter dropdown (`all` / `active` / `draft` / `stale` / `contradicted` / `archived`)
- **Export** button — writes to the vault's `exports/` folder and opens the file automatically
- **View Graph** button (graphml only) — opens an inline Cytoscape.js graph preview before saving

---

## 25. Streaming Query and Query Cache

### SSE Streaming Query

`GET /query/stream?q=<question>[&session_id=<uuid>][&no_cache=true]` returns a Server-Sent Events stream. Each event is a JSON-encoded object:

```
data: {"event": "status", "data": {"phase": "retrieving"}}

data: {"event": "status", "data": {"phase": "synthesizing", "sources": 3}}

data: {"event": "token", "data": {"text": "Alan"}}

data: {"event": "token", "data": {"text": " Turing"}}

data: {"event": "citations", "data": {"citations": ["alan-turing", "enigma"]}}

data: {"event": "done", "data": {"next_hints": ["What came after Turing?", ...]}}
```

| Event | Payload | When |
|---|---|---|
| `status` | `{"phase": "retrieving"}` | Phase 1 starts |
| `status` | `{"phase": "synthesizing", "sources": N}` | Phase 2 starts |
| `token` | `{"text": "…"}` | Each LLM token |
| `citations` | `{"citations": […]}` | After last token |
| `gap` | `{"suggested_searches": […]}` | If knowledge gap detected |
| `clarify` | `{"prompt": "…", "candidates": ["slug-1", …], "action": "…"}` | Action agent needs disambiguation (e.g. which page to activate) |
| `notice` | `{"text": "…"}` | System message (e.g. conversation history was compressed) |
| `done` | `{"next_hints": […]}` | Stream complete |
| `error` | `{"message": "…"}` | On any exception |

The CLI `synthadoc query` renders tokens as they arrive using ANSI cursor control. Pass `--no-stream` to fall back to the blocking `POST /query` endpoint and print the full answer when complete.

The streaming path shares the same query decomposition, BM25 retrieval, and knowledge-gap detection as the blocking path. The only difference is delivery mechanism — SSE for streaming, plain JSON for blocking.

### Epoch-Based Query Result Cache

Query answers are cached in `cache.db` under a composite key:

```
cache_key = hash(
    normalised_question,
    wiki_epoch,
    cache_version
)
```

**Wiki epoch** is an integer stored in `cache.db` that increments on every event that changes wiki content:

| Event | Effect on epoch |
|-------|----------------|
| `ingest` completes (pages written) | epoch + 1 |
| `lifecycle transition` (any state change) | epoch + 1 |
| `cache clear` | epoch reset to 0 |

Because the epoch is part of the cache key, any structural change to the wiki automatically invalidates all cached query answers — there is no explicit expiry TTL. Answers cached before an ingest are never served after it.

**`--no-cache` flag:** bypasses `cache.get()` and `cache.set()` for the current call. The existing cache entry (if any) is left intact; it will be served on subsequent calls without `--no-cache`.

**`synthadoc cache clear`:** deletes all entries from `cache.db`, including both ingest response cache and query answer cache. The epoch is reset to 0.

### QueryAgent integration

`QueryAgent.query()` checks the cache before decomposing the question. On a hit, the cached `QueryResult` is returned immediately — no BM25 search, no LLM call. On a miss, the full pipeline runs and the result is written to cache before returning.

The streaming endpoint inverts this: if a cache hit exists, the cached answer is replayed as an SSE stream (one token per event, then `[DONE]`), giving the same streaming UX even for cached responses.

---

## 26. Web Chat UI and Session Management

### Architecture

The web chat UI is a React single-page application served at `GET /app` by the Synthadoc HTTP server. It communicates with the existing REST API — no additional server process or port is required.

**Serving:** The bundled static assets (`index.html`, `main.js`, `main.css`) are packaged with the `synthadoc` Python distribution under `synthadoc/web_ui/dist/`. The HTTP server mounts them at `/app` via a static file handler. The SPA's API calls target the same origin (`http://127.0.0.1:<port>`), so no CORS configuration is needed beyond what is already in place for the Obsidian plugin.

### Session Management

Each browser session is assigned a `session_id` (UUID) on `POST /sessions`. The server maintains a lightweight in-memory store per session:

| Field | Type | Description |
|---|---|---|
| `session_id` | UUID | Unique identifier for this browser session |
| `mode` | str | Session mode (`NEW_WIKI`, `EXPLORER`, `HEALTH_CHECK`, `POWER_USER`) |
| `cursor` | int | Current position in the hint pool for windowed rotation |
| `last_hints` | list[str] | Hints returned in the previous response (used for deduplication) |

**Session mode** is derived from the wiki's current state at `POST /sessions`:

| Mode | Condition | Hint behaviour |
|---|---|---|
| `NEW_WIKI` | `WikiStorage.count_pages() < 5` | Onboarding chips — guides user through first ingest |
| `EXPLORER` | ≥5 pages, no prior `chat_sessions` rows | Discovery chips — broad overview questions |
| `HEALTH_CHECK` | ≥5 pages, prior sessions, ≥1 `stale` page | Lifecycle chips — suggests running lint or reviewing stale pages |
| `POWER_USER` | ≥5 pages, prior sessions, no stale pages | Context-sensitive follow-up chips |

The mode is returned by `POST /sessions` and also visible as a badge in the UI header.

### Hint Engine

The `HintEngine` class (server-side, no LLM call) generates contextual chips:

**Initial hints** (`initial_hints(mode)` — shown before the first question):
3 fixed chips selected from the mode's priority hint set (e.g. `NEW_WIKI` → "How do I ingest my first document?").

**After-response hints** (`after_response_windowed(answer, mode, cursor, previous_hints)`):
Uses a sliding window over a deduplicated hint pool to rotate suggestions across sessions. The pool is built by placing the current mode's hints first, followed by other modes' hints (no duplicates). A `cursor` advances by 3 on each call so consecutive responses cycle through the full pool over time.

If the answer text matches a topic pattern (e.g. the word "stale" in the answer triggers "How do I run a lint check?"), topic-relevant hints override the window — unless they exactly match the previous response's hints, in which case the pool window is used instead. This prevents keyword-triggered hints from repeating on consecutive wiki-management answers.

Hint chips are rendered below each answer and in the empty-state panel before the first question. Clicking a chip populates the text box without auto-submitting.

### Multi-turn Conversation

Each `GET /query/stream` call may include a `session_id` (UUID from `POST /sessions`). When a session_id is present, the HTTP server loads conversation history from `audit.db` (up to `conversation_history_turns` most recent turns, default 5) and passes it to `QueryAgent.run_stream()`.

**Follow-up question rewriting.** When history is non-empty, a `RewriteAgent` rewrites the user's follow-up question into a self-contained form before BM25 retrieval. This converts context-dependent phrases ("What came after that?" or "Tell me more about his early life") into standalone questions ("What came after Alan Turing's work at Bletchley Park?") so keyword retrieval targets the right pages.

**History overflow compression.** When the accumulated session exceeds `conversation_history_turns`, a `SummarizeAgent` compresses the oldest turns into a single `[Session summary: …]` assistant turn. A `notice` SSE event is emitted the first time compression occurs in a session, so the user can see that earlier context was condensed.

**Clarify events.** When the action agent detects an action-intent query (e.g. "Activate a draft page") but cannot resolve which specific page the user means, it sets `needs_clarification=True` and returns a prompt and candidate list. The HTTP server emits a `clarify` SSE event instead of routing to the synthesis pipeline. The web UI renders this as numbered chip buttons (one per candidate page) plus a free-text hint, letting the user tap a chip or type a page name directly.

**History persistence.** Conversation turns are written to `audit.db` per session. This means history survives a server restart — the same session_id can resume where it left off. Sessions older than `session_max_age_hours` (default 24 h) are purged by the hourly background cleanup task.

### Session history sidebar

The left navigation bar in the web UI is driven by `GET /sessions` (returns up to 20 recent sessions, ordered by `last_active DESC`) rather than `localStorage`, so history is consistent across browser tabs and survives page refreshes.

**2-level collapsible tree:**
- Sessions with a single user turn appear as a flat entry showing the question text and relative timestamp.
- Sessions with two or more user turns render as a collapsible group: the root row shows the first question plus a turn count badge (e.g. `3 turns`); a **▸** chevron toggles expansion; expanded child rows show each follow-up question with a `↳` indent.

**Session restore:** clicking any session root or child turn calls `GET /sessions/{session_id}/messages` to hydrate the full message list, then sets the active `session_id` in the query stream hook so subsequent questions continue the same conversation thread.

**New Run:** the **+ New Run** button calls `POST /sessions` to allocate a fresh `session_id` and resets the chat window to the empty-state hero screen.

**API surface:**

| Endpoint | Description |
|---|---|
| `GET /sessions?limit=N` | Returns `[{session_id, mode, created_at, last_active, turns: [str]}]` — `turns` is the list of user message contents in chronological order |
| `GET /sessions/{session_id}/messages` | Returns `[{role, content}]` for every message in the session, oldest first |

**Configuration:**

```toml
[query]
conversation_history_turns = 5    # turns to include in each request (default: 5; 0 = disable history)
```

### CLI command

```
synthadoc web [-w wiki] [--port N]
```

Opens the default browser to `http://localhost:{port}/app`. The server must already be running (`synthadoc serve`). This command is a thin wrapper around the OS `open`/`start`/`xdg-open` call — it does not start a new server process.

---

## 27. MCP Server

Synthadoc exposes its core operations as an MCP (Model Context Protocol) server, allowing AI agents — Claude Desktop, Claude Code, n8n, LangGraph, or any MCP-compliant host — to read, write, and manage the wiki without running Synthadoc's own query LLM.

### Architecture

The MCP server is implemented with FastMCP and mounted at `/mcp/sse` on the existing HTTP server via ASGI mount. No extra port or process is required — the MCP endpoint and the HTTP REST API share the same Orchestrator singleton and storage layer.

```
synthadoc serve -w my-wiki --port 7070

  ┌────────────────────────────────────────────┐
  │  HTTP server (Starlette)  :7070            │
  │   GET /query/stream  →  QueryAgent         │
  │   POST /ingest       →  IngestAgent        │
  │   GET /app           →  Web Chat UI        │
  │   /mcp  (ASGI mount) →  FastMCP            │
  │     /mcp/sse         →  SSE transport      │
  └────────────────────────────────────────────┘
         ↑ shared Orchestrator + WikiStorage
```

### Transport options

| Client | Transport | Config mechanism |
|---|---|---|
| Claude Desktop | stdio | `command` + `args` in `mcpServers` JSON |
| Claude Code CLI | SSE (`--transport sse`) | `claude mcp add --transport sse <name> <url>` |
| n8n, LangGraph, custom agents | HTTP/SSE | Direct HTTP connection to `/mcp/sse` |

Claude Desktop does not support `"url"`-based HTTP connections in its `mcpServers` config — stdio is the only supported transport. Claude Code supports both SSE and stdio. The SSE endpoint path is exactly `/mcp/sse` (not `/mcp` or `/mcp/`).

The MCP and HTTP servers both bind to `127.0.0.1` — remote access requires an explicit reverse proxy (user-managed).

### Multi-wiki naming

When a wiki root is provided, the FastMCP server name is set to `synthadoc-{wiki-name}` (e.g. `synthadoc-history-of-computing` for a wiki rooted at `history-of-computing/`). This name appears in Claude Desktop's connected-servers UI and in `claude mcp list` output.

Every tool description is automatically prefixed with `Wiki: {wiki-name}. ` at server startup. This allows Claude to route tool calls correctly when multiple Synthadoc servers are connected simultaneously — Claude reads the prefix in the tool description and routes to the matching wiki.

For Claude Desktop, `mcpServers` key names must use underscores (e.g. `synthadoc_history_of_computing`) — hyphens cause a load failure.

### Tool reference

| Tool | Parameters | Returns | LLM cost |
|---|---|---|---|
| `synthadoc_search` | `terms: str` | `{results: [{slug, score, title, snippet}]}` | Claude only |
| `synthadoc_read_page` | `slug: str` | `{slug, title, content, status, type, tags, lint_warnings, sources}` or `{error, slug}` | Claude only |
| `synthadoc_list_pages` | `status?: str` (default `"all"`) | `{pages: [{slug, title, status, type, has_sources}], total: int}` | Neither |
| `synthadoc_context` | `goal: str`, `token_budget?: int` (default `10000`) | `{goal, token_budget, tokens_used, pages: [{slug, relevance, excerpt, source, confidence, tags, estimated_tokens}], omitted: [{slug, estimated_tokens}]}` | Neither |
| `synthadoc_export` | `format?: str` (default `"okf"`), `output_path?: str` (okf defaults to `<wiki>/exports/<name>-okf-<date>/`), `status_filter?: str` (default `"all"`) | okf writes folder to disk → `{format, output_path, files_written, pages}`. Other formats: with `output_path` → `{format, output_path, pages}`; without → `{format, content, pages}`. Formats: `okf`, `llms.txt`, `llms-full.txt`, `json`, `graphml` | Neither |
| `synthadoc_write_page` | `slug: str`, `content: str`, `title?: str` | `{slug, title, status}` or `{error, slug}` | Neither |
| `synthadoc_status` | *(none)* | `{pages: int, wiki: str}` | Neither |
| `synthadoc_jobs` | `status?: str` (default `"all"`) | `{jobs: [{id, operation, status, created, source?, error?}]}` | Neither |
| `synthadoc_lifecycle` | `slug: str`, `to_state: str`, `reason: str` | `{slug, from_state, to_state, reason, timestamp, cascade_links_removed_from: [str]}` or `{error, cascade_links_removed_from: []}` _(cascade field added v1.0.2)_ | Neither |
| `synthadoc_lint_report` | *(none)* | `{contradicted: [str], orphans: [str], adversarial_warnings: int, adversarial_pages: [str]}` | Neither |
| `synthadoc_ingest` | `source: str` | `{job_id, source}` | Synthadoc |
| `synthadoc_lint` | `scope?: str` (default `"all"`) | `{job_id, scope}` | Synthadoc |

Valid `to_state` values for `synthadoc_lifecycle`: `active`, `draft`, `stale`, `contradicted`, `archived`.

Valid `status` values for `synthadoc_jobs` and `synthadoc_list_pages`: `all`, `pending`, `running`, `completed`, `failed`, `skipped`, `cancelled`, `dead`. `running` maps to the internal `in_progress` state.

`synthadoc_write_page` clears `contradiction_note` and bumps the wiki epoch (invalidating the query cache). It does not change `status` — use `synthadoc_lifecycle` to transition state after editing.

`synthadoc_lint` enqueues a background LLM analysis job; use `synthadoc_jobs` to poll progress. `synthadoc_lint_report` is the zero-cost alternative — reads current contradiction/orphan state from wiki files instantly, no job enqueued.

`synthadoc_read_page` returns `sources` as `[{file, ingested}]` and `lint_warnings` as a list of adversarial warning strings — empty list when clean.

### Brain/memory architecture

The MCP integration separates reasoning from persistence:

| Layer | Role | What it handles |
|---|---|---|
| Claude (Desktop or Code) | **Brain** — reasoning, synthesis, editorial judgment | Tool chaining, cross-domain inference, writing quality |
| Synthadoc MCP | **Memory** — domain knowledge, lifecycle, audit | BM25 search, page storage, 5-state lifecycle, immutable event log |

Practical consequences:

- **No double-LLM cost** — `synthadoc_search` and `synthadoc_read_page` return raw data; Claude does the synthesis. Only `synthadoc_ingest` and `synthadoc_lint` call Synthadoc's configured LLM.
- **Claude handles editorial quality** — synthesising contradictions, deciding what is authoritative, drafting resolved content.
- **Synthadoc handles auditability** — every write goes through `WikiStorage.write_page()`; every lifecycle transition is recorded in `audit.db` with `triggered_by = mcp`, a timestamp, and the stated reason.
- **Dynamic vs. static hints** — Claude's next tool call is driven by its own reasoning (dynamic); Synthadoc's `HintEngine` in the web UI is static (predefined patterns). This gap is a feature: Claude handles the editorial reasoning that would require complex heuristics to encode statically.

### Contradiction resolution via MCP

The canonical use case is MCP-driven contradiction resolution (documented in the user quick-start guide, Step 9, Option 3):

```
synthadoc_read_page("grace-hopper")
  → returns page with status: contradicted, contradiction_note: "..."

synthadoc_write_page(slug="grace-hopper", content="<resolved text>")
  → clears contradiction_note, bumps epoch

synthadoc_lifecycle(slug="grace-hopper", to_state="active",
                   reason="Resolved: both views preserved, A-0 attribution corrected")
  → audit.db: slug=grace-hopper, from=contradicted, to=active, triggered_by=mcp
```

The audit trail records the same fields as a manual CLI transition — the MCP path is a first-class lifecycle actor.

### CLI flags

| Flag | Effect |
|---|---|
| `--mcp-only` | Start only the MCP endpoint; suppress HTTP REST API and web UI |
| `--http-only` | Start only the HTTP server; suppress the MCP mount |

Default (no flag): both MCP and HTTP start together on the same port.

---

## 28. Backup & Restore

The `synthadoc backup` and `synthadoc restore` commands package a running wiki domain into a portable compressed zip and re-register it on any machine.

### Architecture

All file I/O is handled by a dedicated backup engine (pure stdlib — no new pip dependencies). The CLI layer manages Typer commands, registry operations, and interactive prompts, reusing existing port-allocation and registry helpers from the installation subsystem.

### Zip structure

```
synthadoc-backup-<wiki>-<YYYYMMDD-HHMMSS>.zip
├── manifest.json          ← always present; last entry wins if duplicated
├── AGENTS.md              ← LLM agent instructions (if present)
├── ROUTING.md             ← query routing index (if present)
├── log.md                 ← human-readable activity log (if present)
├── *.txt                  ← all batch ingest files at wiki root (if present)
├── wiki/
│   ├── *.md
│   └── candidates/*.md
├── hooks/                 ← user hook scripts (always included)
├── .synthadoc/
│   ├── config.toml
│   ├── audit.db
│   ├── extracted/         ← text sidecars + PDF pagemaps (always included)
│   └── cache.db           ← included by default; skip with --no-cache
├── exports/               ← included by default; skip with --no-exports
└── raw_sources/           ← included by default; skip with --no-sources
```

Always excluded: `jobs.db`, `embeddings.db`, `server.pid`, `logs/`.

> **v0.9.3 fix:** `hooks/` and `.synthadoc/extracted/` were previously missing from backups. Omitting `extracted/` caused the Source Viewer and Provenance citation modal to show "Could not read source file" after restore.

### Manifest

Every backup contains a `manifest.json` at the zip root:

```json
{
  "synthadoc_version": "1.0.0",
  "db_schema_version": 1,
  "cache_version": "4",
  "wiki_name": "history-of-computing",
  "backed_up_at": "2026-06-24T10:30:00Z",
  "source_os": "windows",
  "source_hostname": "dev-machine",
  "page_count": 87,
  "includes_sources": true,
  "includes_exports": true,
  "includes_cache": true,
  "obsidian_plugin": true,
  "checksum_sha256": "abc123..."
}
```

`db_schema_version` is read from SQLite `PRAGMA user_version` in `audit.db`. The restore tool aborts if the backup's version exceeds the installed version. `checksum_sha256` is the SHA-256 of all non-manifest zip members in sorted name order.

### Restore conflict rules

| Situation | Behaviour |
|---|---|
| Name not in registry | Register normally |
| Name in registry, path exists | Hard stop — use `--name` to rename or `synthadoc uninstall` first |
| Name in registry, path gone (stale) | Proceed with a printed note; stale entry is overwritten |
| Demo wiki renamed via `--name` | Warn + `y/N` prompt (breaks `demo sync`) |
| Port taken | System suggests the next available port; user confirms or overrides |

### CLI commands

```
synthadoc backup -w <wiki> [--output <dir>] [--no-sources] [--no-exports] [--no-cache]

synthadoc restore <backup.zip> [--name <new-name>] [--target <dir>] [--port <port>]
```

`backup` creates a timestamped `ZIP_DEFLATED` archive in `--output` (default: current directory). `restore` extracts the archive to `--target/<wiki-name>/` (default: same directory as the zip), rewrites host-specific config values (port, domain name), updates the global registry, re-applies scheduled jobs, and auto-reinstalls the Obsidian plugin if `obsidian_plugin` is `true` in the manifest. Both commands print a summary on completion.

---

## 29. Pre-LLM Source Sanitizer

Every source document passes through a sanitizer immediately after text extraction, before any LLM call. The sanitizer removes six categories of content that could manipulate the LLM or degrade compilation quality:

| Category | Action | Warning logged? |
|---|---|---|
| Zero-width characters (U+200B, U+200C, U+200D, U+FEFF) | Removed silently | No |
| Bidi override characters (U+202A–U+202E, U+2066–U+2069) | Removed | Yes |
| HTML comments (`<!-- ... -->`) | Removed silently | No |
| Hidden CSS spans (`display:none`, `visibility:hidden`) | Removed silently | No |
| Base64 blobs ≥ 200 consecutive characters | Replaced with `[base64 content removed]` | Yes |
| Instruction-override phrases (8 patterns: "ignore previous instructions", "disregard the above", "override your system prompt", etc.) | Replaced with `[redacted]` | Always |

When content is removed and a warning is appropriate, the server logs a `WARN` entry:
```
[WARN] sanitizer stripped content from 'papers/survey.pdf': bidi overrides, instruction-override phrase
```

This is a pure pre-processing step with zero LLM cost. Truncation (if configured) is applied after sanitization, so the character budget is consumed by clean text only.

---

## 30. Per-Source Truncation Flag

Large source documents are truncated before they reach the LLM. By default the limit is **32,000 characters** (~8,000 tokens), raised from the prior hardcoded 8,000-character limit. When a source exceeds this limit, its compiled wiki page records a `truncated: true` flag in its `sources:` frontmatter entry.

### Configuration

```toml
[ingest]
max_source_chars = 32000   # default; raise for large PDFs or books
```

### Per-ingest override

The limit can be raised for a single ingest run without modifying the config:

```bash
synthadoc ingest papers/large-textbook.pdf --max-source-chars 128000
```

The same `max_source_chars` field is accepted by the HTTP `POST /jobs/ingest` body and the MCP `synthadoc_ingest` tool.

### Lint surfacing

`synthadoc lint` emits a warning for any page that has a truncated source:

```
[WARN] quantum-computing.md: source 'papers/large-survey.pdf' was truncated at ingest
       (source exceeded max_source_chars=32000 — 87,412 chars in source).
       To re-ingest with a higher limit (this source only):
         synthadoc ingest papers/large-survey.pdf --max-source-chars 128000
       To raise the limit for all future ingests:
         set [ingest] max_source_chars = 128000 in your config
```

---

## 31. Proportional Context Budget

Query context is allocated proportionally to the configured model's context window, replacing the prior hard cap. The default allocation:

| Slice | Default | Purpose |
|---|---|---|
| `context_wiki_pct` | 60% | Wiki page content (ranked by BM25 + vector score) |
| `context_history_pct` | 20% | Chat turn history (newest-first, oldest dropped when over budget) |
| `context_system_pct` | 15% | System prompt and purpose document |
| `context_index_pct` | 5% | `ROUTING.md` and search index |

Percentages must sum to ≤ 100. Configure in `[query]`:

```toml
[query]
context_window = 0         # 0 = auto-detect from known model map
context_wiki_pct      = 60
context_history_pct   = 20
context_system_pct    = 15
context_index_pct     = 5
```

> **Note:** `context_system_pct` and `context_index_pct` are parsed and validated but not yet enforced as hard caps in this release — the system prompt uses a conservative fixed limit, which is well within the configured 15% slice for all supported models. Full per-slice enforcement is planned for v1.1.

### Model context window map

Synthadoc ships a built-in prefix-matched table:

| Model | Context window |
|---|---|
| `claude-opus-4*`, `claude-sonnet-4*`, `claude-haiku-4*` | 200,000 tokens |
| `gpt-4o*`, `gpt-4-turbo*` | 128,000 tokens |
| `gpt-4` (exact) | 8,192 tokens |
| `gpt-3.5-turbo*` | 16,385 tokens |
| Unknown / fallback | 128,000 tokens |

Set `context_window = N` in config to override the map (useful for local Ollama models with non-standard context sizes).

At the defaults on a 200k-token model: wiki slice ≈ 480,000 chars — far more than any practical query needs. On constrained models, the budget scales down automatically so the same config works across model families.

---

## 32. Knowledge Graph

Synthadoc computes a wikilink graph across all active and draft pages during every lint run. The graph is stored in two tables in `audit.db`:

```sql
CREATE TABLE graph_nodes (
    slug        TEXT PRIMARY KEY,
    cluster_id  INTEGER NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE graph_edges (
    from_slug   TEXT NOT NULL,
    to_slug     TEXT NOT NULL,
    weight      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (from_slug, to_slug)
);
```

Edge weight equals the number of `[[wikilink]]` references from one page to another (most pairs: 1). Cluster IDs are assigned by Louvain community detection — pages that link densely to each other end up in the same cluster.

### REST API

**`GET /graph`** — returns the full graph with per-node enrichment:

```json
{
  "status": "ready",
  "node_count": 45,
  "edge_count": 123,
  "cluster_count": 4,
  "nodes": [
    {"slug": "quantum-error-correction", "title": "Quantum Error Correction",
     "type": "concept", "state": "active", "cluster_id": 2}
  ],
  "edges": [
    {"from": "quantum-error-correction", "to": "shor-algorithm", "weight": 1}
  ]
}
```

When the graph tables are empty (first call after upgrade, or before the first lint run), the server returns `{"status": "computing"}` and starts a background build immediately. The web UI polls every 2 seconds and renders the graph when the status becomes `"ready"`.

### Web UI

The **Graph** tab (alongside Chat in the top nav) renders a D3.js force-directed graph. Nodes are colored by cluster. Clicking a node opens a sidebar showing the page title, type and lifecycle state badges, cluster assignment, and an **"Ask about this →"** button that switches to the Chat tab with a pre-filled query.

Controls: zoom in/out (scroll or pinch), drag nodes, filter by page type.

---

## Customization

Synthadoc exposes four extension points — all hot-loaded, no server restart required.

### Custom skills (new file formats)

Subclass `BaseSkill` (Apache-2.0 — no AGPL obligation on your skill code), drop the folder in `<wiki-root>/skills/` or `~/.synthadoc/skills/`, and Synthadoc picks it up on the next ingest. Skills match by file extension or intent prefix and support any Unicode text, including CJK prefixes.

→ Full interface, manifest format, and examples: [§5 Skills System](#5-skills-system) and [§17 Plugin Development Guide](#17-plugin-development-guide)

### Custom LLM providers

Subclass `LLMProvider` from `synthadoc/providers/base.py` (Apache-2.0) and place the file in `~/.synthadoc/providers/` or the wiki `providers/` directory. Switch active provider with one config line.

→ Full interface and wiring instructions: [§10 Configuration — Provider switching](#10-configuration)

### Hooks

Shell scripts (any language) that fire on `on_ingest_complete` and `on_lint_complete`. Receive a JSON context on stdin. Set `blocking = true` to gate the operation on the hook's exit code — useful for CI pipelines and quality gates.

→ Full event schema, context JSON, and blocking behaviour: [§11 Hook System](#11-hook-system)

### Cache control

Three cache layers (embedding, LLM response, provider prompt cache) invalidate automatically on source-file change (SHA-256). Force a fresh call with `--force`, or wipe all cached responses with `synthadoc cache clear -w <wiki>`.

→ Layer-by-layer breakdown and invalidation rules: [§12 Cache System](#12-cache-system)

### Multi-Platform Agent Skill Files

Every Synthadoc wiki ships three companion files that give AI coding agents a complete, self-contained operating guide for the wiki:

| File | Platform |
|---|---|
| `AGENTS.md` | Codex CLI, OpenCode, and any agent that reads the AGENTS.md convention |
| `CLAUDE.md` | Claude Code (this session's tool) — highest-priority instruction source in Claude's hierarchy |
| `GEMINI.md` | Gemini CLI — relevant because Synthadoc's default LLM provider is `gemini-2.5-flash-lite` |

All three files share identical body content generated from the same template; they differ only in their H1 heading so each agent recognises its own file first. The body covers:

- **Domain guidelines** — LLM-generated bullet list of domain-specific ingest and query rules (produced by `scaffold`)
- **Quick reference table** — every common CLI command with the correct `synthadoc` syntax
- **Server startup** — how to start the server and verify it is running
- **Ingest examples** — local file, URL, YouTube, agent session `.jsonl`, force reingest, dry-run
- **Query** — basic and streaming query syntax; citation marker format
- **Lint** — when to run and what each check does
- **Lifecycle** — transition commands with state names
- **Page schema** — frontmatter structure with all fields
- **MCP tools table** — all 12 tools with purpose descriptions

**How the files are created and updated:**

1. `synthadoc init` — writes all three files with default domain guidelines and the wiki's configured port.
2. `synthadoc scaffold` — regenerates all three with LLM-produced domain guidelines derived from the current wiki state. The `scaffold` command prints a confirmation line for each file.

**Use cases:**

- Open Claude Code in a Synthadoc wiki directory and it immediately knows how to ingest, query, lint, and manage lifecycle — no additional setup. Claude Code can also start the server in background mode (`synthadoc serve -w <wiki> -b`), stop it cleanly, and orchestrate multi-step workflows, effectively acting as a control plane for the wiki.
- Gemini CLI reads `GEMINI.md` and can run `synthadoc` commands with the correct flags without asking the user for help.
- CI pipelines with Codex CLI use `AGENTS.md` to drive automated lint and lifecycle transitions on PR merge.
- Agent session files produced by Claude Code (`.jsonl` under `~/.claude/projects/`) can themselves be ingested into the wiki, capturing the reasoning behind design decisions alongside the source documents.

→ See [README.md — Interfaces & Integration](../README.md#interfaces--integration) for the feature comparison row and quick-start instructions.

---

## Appendix A — Release Feature Index

### v1.0.2

- **Cascade link cleanup on archive** — archiving any page immediately removes every `[[slug]]` wikilink pointing to it from all other active pages, without waiting for the next `lint run`. Inline links become plain text; list-item-only links are dropped entirely. The HTTP `POST /lifecycle/transition` and MCP `synthadoc_lifecycle` responses now include a `cascade_links_removed_from` field listing the rewritten page slugs. During `lint run`, cascade runs once after all auto-archive transitions complete and the count is included in the lint report's `dangling_links_removed` field. System pages (index, dashboard, purpose, log, overview) and already-archived pages are skipped. The existing dangling-link lint pass remains as a safety net for dead links that predate this release.
- **Multi-source partial-archive fix** — when a page has multiple local source files and only some are missing from disk, lint now transitions the page to `stale` (not `archived`), preserving it for re-ingest. The page is only archived when every local source file is gone. URL sources are not affected by this check.

### v1.0.1

- **Scaffold JSON extraction hardened** — replaced the greedy regex used to extract the LLM's JSON response with a brace-balanced parser; eliminates false-positive matches on `[[wikilink]]` syntax that previously caused `json.loads()` failures and silent scaffold corruption
- **Generated file validation** — scaffold now validates every LLM-generated file (index, purpose, AGENTS.md) for minimum length, required frontmatter, and `[[wikilink]]` presence before writing to disk; validation failure marks the job as failed with a structured error message rather than silently writing a malformed page
- **ROUTING.md regeneration validation** — `routing init` and scheduled routing regeneration now validate the regenerated file for minimum line count and anchor presence before applying it; prevents a corrupt or truncated ROUTING.md from entering the wiki
- **Scaffold failure reporting** — scaffold skip and failure reasons are now surfaced in the terminal output and job error field; previously silent failures (e.g. LLM timeout, JSON parse error) are now visible without tailing the JSON log
- **Install-time scaffold removed** — `synthadoc install` no longer runs the LLM scaffold call during installation; scaffold is a separate step (`synthadoc scaffold`) that the user runs after setting their API key, avoiding confusing API-key-not-set errors at install time
- **AquaFlow LLM evaluation** — 15-question M&A due-diligence benchmark across five models (MiniMax-Think M3, Claude Opus 4.8, Claude Sonnet 4.6, DeepSeek-R1, Qwen Plus); full report at `docs/example/aquaflow/evaluation/report/llm-query-benchmark.md`

### v1.0.0

- **Pre-LLM source sanitizer** — every source document passes through a sanitizer before any LLM call; removes six categories of potentially harmful content (zero-width characters, bidi overrides, HTML comments, hidden CSS spans, base64 blobs ≥ 200 chars, instruction-override phrases); a `WARN` log entry is emitted when bidi overrides or instruction-override phrases are stripped; zero LLM cost; applied before truncation so the character budget is consumed by clean text only
- **Per-source truncation flag** — default character limit raised from 8,000 to 32,000 characters per source (~8,000 tokens); truncated sources are flagged with `truncated: true` in the page's `sources:` frontmatter; `--max-source-chars N` CLI flag and matching `POST /jobs/ingest` body field and MCP `synthadoc_ingest` parameter override the limit per run; `synthadoc lint` emits a warning for any page with a truncated source and suggests the override command; configurable via `[ingest] max_source_chars` in `config.toml`
- **Proportional context budget** — query context is allocated proportionally to the configured model's context window; four configurable slices: `context_wiki_pct` (60%), `context_history_pct` (20%), `context_system_pct` (15%), `context_index_pct` (5%); built-in prefix-matched model context window table covers Claude 4, GPT-4o/turbo/3.5, and GPT-4; unknown models fall back to 128,000 tokens; `context_window = N` in `[query]` overrides the table for local or custom models
- **Knowledge graph** — wikilink graph computed across all active and draft pages during every lint run; stored in `graph_nodes` and `graph_edges` tables in `audit.db`; edge weight = number of `[[wikilink]]` references between two pages; cluster IDs assigned by Louvain community detection; `GET /graph` REST endpoint returns nodes with per-node enrichment (title, type, state, cluster) and edges; first call after upgrade triggers a background build and returns `{"status":"computing"}`; web UI **Graph** tab (D3.js force-directed graph) — nodes colored by cluster, click to see page details and an "Ask about this →" button that opens a pre-filled chat query
- **Citation accuracy & rendering improvements** — six correctness fixes to the ingest citation pipeline: (1) full source text passed to the decision LLM so citations can reference any line in the document; (2) `_annotate_citations` bugs A–F resolved (false-positive matches, off-by-one line ranges, duplicate markers, escaped bracket handling, multi-paragraph span errors, and source filename normalisation); (3) `_has_citations` check added — lint warns and suggests a model upgrade when a page has zero citation markers after synthesis; (4) `Key Data` section extraction hardened so numerical facts, rates, and formulas are preserved verbatim across the annotation pass; (5) `obsidianCitationsToGfm` rendering fixed in the web UI — citation superscripts now display correctly in the chat panel alongside streamed answers; (6) reading view set as the default Obsidian display mode for wiki pages

### v0.9.3

- **Backup now includes `hooks/` and `.synthadoc/extracted/`** — both directories were silently omitted from backups. `hooks/` contains user-customised hook scripts; `.synthadoc/extracted/` contains per-source text sidecars and PDF pagemaps written by the ingest agent. Without these, the Source Viewer and Provenance citation modal showed "Could not read source file" after restore.
- **PyPI publish workflow** — `publish.yml` triggers on GitHub Release, builds the wheel with hatchling, and uploads to PyPI via OIDC trusted publishing (no API token stored). `pip install synthadoc` now works.
- **Web UI bundled in pip package** — `synthadoc/data/web-ui/dist/` is now included in the wheel. `synthadoc web` previously returned 503 on pip-installed instances because the React dist was not packaged.
- **CI sync checks** — PRs now fail if `synthadoc/data/obsidian-plugin/`, `synthadoc/data/web-ui/`, or `README-pypi.md` are out of sync with their source. All sync-check steps use `shell: bash` for Windows runner compatibility.
- **`bump_version.py` extended** — now also updates `synthadoc/data/obsidian-plugin/manifest.json` alongside the source manifest, preventing version drift between the bundled copy and the plugin source.

### v0.9.2

- **`synthadoc/data/web-ui/dist/` packaged** — web UI dist files committed to the repo and bundled in the wheel via hatchling artifacts.
- **`scripts/sync_web_ui.py`** — helper script to sync `web-ui/dist/` into `synthadoc/data/web-ui/dist/` after `npm run build`.

### v0.9.1

- **PyPI metadata** — added `readme`, `keywords`, `classifiers`, and `[project.urls]` to `pyproject.toml` for correct PyPI rendering.
- **`README-pypi.md`** — generated from `README.md` by `scripts/prepare_pypi_readme.py`; strips `pypi-strip` blocks and rewrites relative links to absolute GitHub URLs.
- **Branch protection compatibility** — removed post-merge `build-plugin` CI job that pushed compiled plugin directly to `main`. Plugin sync is now enforced in PRs: CI fails if `synthadoc/data/obsidian-plugin/` is out of sync.

### v0.9.0 (Community Edition)

- **MCP server — 12 tools** — Synthadoc exposes `synthadoc_search`, `synthadoc_read_page`, `synthadoc_list_pages`, `synthadoc_write_page`, `synthadoc_status`, `synthadoc_jobs`, `synthadoc_lifecycle`, `synthadoc_lint_report`, `synthadoc_context`, `synthadoc_export`, `synthadoc_ingest`, and `synthadoc_lint` via the Model Context Protocol. Mounted at `/mcp/sse` on the existing HTTP server (no extra port or process). Tools share the same Orchestrator singleton as the HTTP REST API.
- **`synthadoc_write_page`** — lifecycle-aware content editing: updates page body, clears `contradiction_note`, bumps the wiki epoch (cache invalidation). Proper MCP alternative to writing wiki files directly — every edit goes through `WikiStorage.write_page()` and is query-cache-coherent.
- **Multi-wiki server naming** — FastMCP server name auto-set to `synthadoc-{wiki-name}` (e.g. `synthadoc-history-of-computing`). All tool descriptions prefixed with `Wiki: {wiki-name}.` at startup so Claude can route correctly when multiple Synthadoc servers are connected simultaneously.
- **Transport support** — stdio (Claude Desktop), SSE via `--transport sse` (Claude Code CLI), HTTP/SSE direct connection (n8n, LangGraph, custom agents). Claude Desktop requires underscores in `mcpServers` key names (hyphens cause load failure).
- **Brain/memory architecture** — Claude acts as the reasoning brain (editorial judgment, synthesis, tool chaining); Synthadoc MCP acts as persistent domain memory (BM25 search, 5-state lifecycle, immutable audit trail). `synthadoc_search` and `synthadoc_read_page` return raw data with no Synthadoc LLM call; only `synthadoc_ingest` and `synthadoc_lint` consume tokens from the configured provider.
- **`--mcp-only` / `--http-only` serve flags** — deploy MCP-only (no web UI or REST API) or HTTP-only (no MCP mount) for constrained environments.
- **OKF `type:` field** — IngestAgent now writes a `type:` frontmatter field on every compiled page (values: `concept`, `person`, `organization`, `technology`, `event`, `location`, `product`). The field is required by OKF v0.1 and enables type-grouped `index.md` in the export bundle. Pages ingested before v0.9.0 can be backfilled via `synthadoc demo sync` (demo wikis) or re-running `synthadoc ingest` (custom wikis).
- **`synthadoc demo sync` — optional wiki name** — running `synthadoc demo sync` without a wiki name argument syncs all registered demo wikis in one pass. The sync step also backfills `type:` on existing pages that were compiled before v0.9.0 without the field.
- **SSE shutdown stability** — a log filter installed on `uvicorn.error` at startup suppresses three benign error classes that appear when the server exits while SSE connections are open: `asyncio.CancelledError`, `KeyboardInterrupt`, and the `RuntimeError("Expected ASGI message 'http.response.body'…")` that Starlette's error middleware raises after cancellation. Actual errors during normal operation are unaffected.
### v0.8.0 (Community Edition)

- **Multi-turn conversation** — the web chat UI maintains conversation history across turns within a session. History is stored in `audit.db` per session and loaded server-side on each request (up to `conversation_history_turns` turns, default 5). Follow-up questions are rewritten into standalone form by a dedicated rewrite component before BM25 retrieval, so context-dependent phrases ("What came after that?") resolve correctly. When the session exceeds the turn limit, a summarization component compresses the oldest turns into a `[Session summary]` entry; a `notice` SSE event is emitted the first time compression occurs.
- **Clarify event** — when an action-intent query is ambiguous (e.g. "activate a draft page" without specifying which page), the server emits a `clarify` SSE event with a disambiguation prompt and candidate page list instead of routing to the synthesis pipeline. The web UI renders candidates as numbered chip buttons; the user can tap a chip or type a page name to complete the action.
- **Two new SSE events** — `clarify` (`{prompt, candidates, action}`) for action disambiguation; `notice` (`{text}`) for system messages such as history compression.
- **Configuration** — `[chat] conversation_history_turns = 5` controls how many prior turns are included in each request. Set to `0` to disable conversation history. `clarify_lookback = 5` controls how many prior assistant turns to scan when detecting a clarify continuation (chip click after an ambiguous action query); configurable independently of `conversation_history_turns`.
- **MiniMax M3 support** — `provider = "minimax"` with `model = "MiniMax-Text-01"` or `"MiniMax-M3"` (thinking mode configurable; off by default).
- **Settings gear** — web UI chat window now has a ⚙ gear button that opens a popover to configure the per-request query timeout (10–600 s, default 60 s). Value persisted in `localStorage`.
- **Query timeout** — `GET /query/stream` accepts `?timeout_seconds=N`; a `TimeoutError` emits an SSE `error` event to the browser.
- **Session history sidebar** — the left navigation bar is now server-driven (`GET /sessions`) and shows sessions as a 2-level collapsible tree. Multi-turn sessions display a turn count badge and expand to show each follow-up question. Clicking any item restores the full conversation history via `GET /sessions/{id}/messages`. Two new API endpoints: `GET /sessions` and `GET /sessions/{session_id}/messages`.
- **Job status and list actions** — the Action Agent now handles `job_status` and `job_list` intent queries. `job_status` with a job ID returns a detailed job card; without an ID it returns a table of all jobs and emits a `clarify` event so the user can pick one via chip. `job_list` accepts an optional multi-status filter (e.g. "show failed and skipped jobs") and includes an Error column when any listed job has a non-null error. Built-in `hints.json` extended with job-status and job-list hints for POWER_USER mode.
- **Multi-chip clarify continuation** — clarify chip replies (bare UUIDs) are now reliably routed back to the Action Agent across multiple chip clicks. The server tags every clarify message with a `[clarify] ` prefix in the audit log; `detect()` scans back `clarify_lookback` assistant turns to find an open clarify context.
- **Qwen provider routing** — `qwen-<letter>` model names (e.g. `qwen-plus`, `qwen-max`) route to DashScope cloud API regardless of other config; all other Qwen models (e.g. `qwen3:8b`, `qwen3.5`) route to local Ollama. This decouples cloud/local routing from `QWEN_API_KEY` presence.

### v0.7.0 (Community Edition)

- **Streaming query output** — `synthadoc query` streams the LLM answer token-by-token via Server-Sent Events (SSE); the CLI renders tokens as they arrive. `--no-stream` reverts to blocking mode for scripts and pipes. `GET /query/stream` SSE endpoint; the streaming path reuses all existing decomposition, BM25, and knowledge-gap logic.
- **Epoch-based query result cache** — query answers are cached in `cache.db` under a composite key of normalised question + wiki epoch + cache version. The wiki epoch increments on every ingest completion and every lifecycle transition, so cached answers are always consistent with current wiki content. `--no-cache` bypasses the cache per call without evicting the entry. `synthadoc cache clear` resets the epoch and removes all entries.
- **Web chat UI** — React SPA served at `GET /app` by the existing HTTP server (no extra port or process). Features: session-aware mode detection (`NEW_WIKI` / `EXPLORER` / `HEALTH_CHECK` / `POWER_USER`) based on wiki page count, prior session history, and stale-page presence; streaming answers via SSE; citation links; knowledge-gap callouts; contextual hint chips with windowed pool rotation; and multi-turn conversation history. Server maintains a lightweight in-memory session store (session_id, mode, hint cursor, last_hints).
- **Session management and hint engine** — hint chip sets are derived from wiki index headings (new mode), recent citation graph (explorer mode), and uncovered BM25 top pages (power-user mode). Mode badge displayed in the UI header.
- **Obsidian plugin streaming** — the Query command streams the answer into the modal as tokens arrive, matching the CLI and web UI streaming experience. No change to the Obsidian command count.
- **`synthadoc web` CLI command** — opens the default browser to `http://localhost:{port}/app`; thin wrapper around OS open/start/xdg-open; server must already be running. The web UI is local-only; network access and authentication are not available in the Community Edition.
- **Action Agent** — regex pre-filter + LLM extraction layer that detects action-intent queries ("run lint", "schedule ingest every night", "what pages are orphans?") and dispatches them to live Synthadoc operations without going through the query pipeline. Supports: `lint`, `lint_report`, `wiki_status`, `ingest`, `scaffold`, `schedule_add`, `schedule_list`, `schedule_history`, `lifecycle_activate`, `lifecycle_archive`, `lifecycle_restore`. Returns structured `ActionResult` rendered directly in the web UI and CLI.
- **Expanded hint coverage** — built-in `hints.json` extended with lifecycle action hints ("Activate a draft page", "Archive a stale page", "Restore an archived page to draft"), orphan/contradiction/adversarial patterns, and "Show wiki status" in EXPLORER and HEALTH_CHECK modes.

### v0.6.0 (Community Edition)

- **5-state lifecycle machine** — every wiki page tracks a `draft | active | contradicted | stale | archived` state in two new `audit.db` tables: `page_states` (fast current-state index, slug PK) and `lifecycle_events` (immutable audit log of every transition with slug, from/to state, reason, triggered_by, and timestamp)
- **Ingest creates draft pages** — all new pages are created with `status: draft` instead of `active`; pages must pass a lint run to be promoted
- **LintAgent lifecycle checks** — four automated checks run at the end of every lint pass: archived detection (source file missing → `archived`), stale detection (source hash mismatch → `stale`), draft promotion (draft + no active issues → `active`), manual-edit sync (frontmatter `status` ≠ DB → reconcile); skipped when `--no-lifecycle` is passed
- **Auto-retention** — `[audit] lifecycle_retention_days = N` in `config.toml` prunes old `lifecycle_events` at the end of each lint run; `0` = keep forever (default)
- **Lifecycle CLI** — `synthadoc lifecycle activate/archive/restore/log`, `synthadoc status` extended with per-state counts, `synthadoc audit lifecycle purge --before / --keep-latest`
- **Lifecycle HTTP API** — `GET /lifecycle/status`, `GET /lifecycle/events`, `POST /lifecycle/transition`
- **Lifecycle Obsidian plugin** — `Synthadoc: Manage Page Lifecycle` command opens `LifecycleModal`: sortable, filterable, paginated table of all pages with current state and last transition; valid transition action buttons per row; `ReasonModal` prompts for reason before committing; draft/stale badge links on lint modal and jobs panel open the table pre-filtered
- **Export formats** — `synthadoc export --format <fmt>` serializes the wiki in four formats assembled server-side with zero LLM calls: `llms.txt` (navigation index per llmstxt.org spec — active pages in `## Pages`, contradicted/stale in `## Needs Review`, archived omitted); `llms-full.txt` (flat content dump with `---` separators, provenance footnotes preserved verbatim, no size limit); `graphml` (standard GraphML 1.1 — node attributes include `label`/`title`, `status`, `confidence`, `orphan`, `inbound_link_count`, `routing_branch`; edges=wikilinks; dual-label support: `label` key for Gephi/Cytoscape, `y:NodeLabel` for yEd; no position data — run tool layout after import); `json` (agent-ready dump with `claims[]`, `lifecycle_history[]`, per-page `ingest_cost_usd` and `ingest_tokens`, `total_compilation_cost_usd`, `routing.branch_memberships`); all formats accept `--status` filter (`all`/`active`/`draft`/`stale`/`contradicted`/`archived`); `POST /export` endpoint accepts `{format, status_filter}`; Obsidian **Export Wiki** command — format dropdown, full-width output path, status filter, Export button, View Graph inline preview button (graphml only)


### v0.5.0 (Community Edition)

- **Adversarial review** — concurrent independent LLM review of every wiki page after lint runs; flags overstated claims, unsupported assertions, and high-confidence statements the source material does not support; results stored as `lint_warnings: [{claim, concern}]` in page frontmatter; surfaced in redesigned 3-tab `Lint: report` modal (Contradictions / Orphans / Adversarial) and redesigned `synthadoc lint report` CLI output; configured via `[agents].adversarial` and `[lint].adversarial_max_per_page` (default 2) in `config.toml`; skipped with `synthadoc lint run --no-adversarial` (also clears stale warnings); cross-model review — a different model family from the ingest model reduces self-serving bias; concurrent via `asyncio.gather()` — a 100-page wiki completes in the same wall-clock time as one call; per-page rate-limit failures are non-fatal
- **Claim-level provenance** — during ingest, Pass 4 (`_annotate_citations()`) reads each page section alongside numbered source text and inserts `^[filename:L-L]` inline citation markers at the end of substantive paragraphs; markers map compiled claims to exact source line ranges; stored in the page body, recorded in `audit.db` `claim_citations` table, and validated by lint; local source sidecars written to `.synthadoc/extracted/` (plain-text `.txt` for all file types; pagemap JSON for PDFs to resolve line numbers to PDF page numbers); in Obsidian (Reading View only) markers render as interactive citation chips — one click opens the Source Viewer showing the referenced lines with ±5 lines of context; PDF sources show a page-jump button; `GET /provenance/citations` endpoint powers the **View Page Provenance** modal (sortable, paginated citation table); `synthadoc audit citations` CLI queries the same table with `--page` and `--broken` filters
- **Routing Obsidian plugin** — `Synthadoc: Routing: manage ROUTING.md...` command palette entry opens a modal panel with three buttons: **Init** creates ROUTING.md from the current index.md branch structure (enabled only when ROUTING.md does not exist), **Validate** reports dangling slugs, **Clean** removes dangling slugs from ROUTING.md; after each action results appear inline
- **Candidates Staging Obsidian plugin** — `Synthadoc: Staging: manage staging policy...` and `Synthadoc: Candidates: review candidate pages...` command palette entries; Staging modal shows policy state with segmented controls; Candidates modal shows a paginated table with promote/discard bulk and per-row actions
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

### v0.1.0 (Community Edition)

- **3 agents** — IngestAgent (two-step cached synthesis), QueryAgent (BM25 + LLM), LintAgent (contradiction + orphan detection + auto-resolution)
- **9 built-in skills** — PDF, URL, Markdown/TXT, DOCX, PPTX, XLSX/CSV, Image (vision), Web search (Tavily), YouTube transcript
- **Folder-based skill system** — each skill is a self-contained folder with a `SKILL.md` manifest; intent-based dispatch alongside extension matching; drop a folder in `skills/` to add a new format without touching core code
- **2 access surfaces** — CLI (thin HTTP client), HTTP REST API
- **Obsidian plugin** — ingest (file picker, URL, all sources, web search), query modal, lint report, jobs list — all from the command palette; ribbon shows engine health + page count
- **8 LLM providers** — Anthropic, OpenAI, Gemini (free tier), Groq (free tier), MiniMax (paid, multimodal), DeepSeek (paid, very cheap text-only), Qwen (paid DashScope cloud), Ollama (local); switch with one config line
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

