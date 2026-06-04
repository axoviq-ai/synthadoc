---
title: Synthadoc Overview
keywords: [synthadoc, overview, about, introduction, features, open source, community, free, providers, wiki engine, knowledge base, capabilities, product]
---

# Synthadoc Overview

**Synthadoc** is an open-source, domain-agnostic LLM wiki engine. It reads your raw source documents — PDFs, spreadsheets, Word files, presentations, images, web pages, YouTube videos, plain text — and uses an LLM to compile them into a persistent, structured wiki of Markdown files. The wiki is stored locally, browsable in [Obsidian](https://obsidian.md) without any server running, and queryable via CLI or a browser-based chat UI.

Current release: **Community Edition v0.6.0** (AGPL-3.0).

---

## The core idea

Most knowledge tools retrieve and summarize at query time. Synthadoc **compiles** knowledge at ingest time. Every new source enriches and cross-links the entire corpus rather than appending an isolated chunk. The wiki is the artifact — readable, editable, and accurate whether or not a server is running.

---

## Who is it for?

| Scale | Typical use |
|---|---|
| **Solo / 1–2 people** | Personal research wiki, freelance knowledge base — run free on Gemini Flash or Groq with no credit card |
| **Small team (3–20)** | Centralised internal wiki for startups and departments; autonomous contradiction resolution as the team grows |
| **Enterprise** | Compliance-sensitive knowledge bases that must stay local; per-department wikis; audit trail for every ingest and cost event |

---

## What Synthadoc does

### Accepts six categories of input
- **Local files:** `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`
- **Images:** `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`
- **Text / Markdown:** `.md`, `.txt`
- **Web pages:** any `http://` or `https://` URL
- **YouTube videos:** automatic transcript extraction, no API key required
- **Web search:** intent phrases like `search for: topic` or `find on the web: topic` (requires Tavily API key)

### Compiles and maintains a wiki
Ingested sources are synthesised by the LLM into structured Markdown pages with YAML frontmatter (`status`, `confidence`, `tags`, `sources[]`). Cross-references are built automatically as `[[wikilinks]]`.

### Detects problems automatically
- **Contradictions** — when two sources conflict, the page is flagged `status: contradicted` instead of silently blending the claims
- **Orphan pages** — pages with no inbound links are surfaced by lint with ready-to-paste index entries
- **Stale pages** — if a local source file changes on disk (SHA-256 mismatch), the page is marked `stale` on the next lint run

### 5-state lifecycle machine
Every page moves through `draft → active → contradicted / stale / archived` with a full, immutable audit trail. New pages start as `draft`; lint auto-promotes clean pages to `active`. Every state change is recorded with who triggered it and why.

### Adversarial lint (second-LLM review)
Every lint run includes a concurrent second-LLM pass that plays devil's advocate: it flags overstated claims, unsupported superlatives, and contested figures the primary model accepted too readily. Pointing the adversarial pass at a *different* model family produces the strongest signal.

### Claim-level provenance
During ingest, a citation annotation pass inserts `^[filename:L-L]` markers on every substantive paragraph, linking compiled claims to the exact source lines. In Obsidian, these render as clickable chips that open a Source Viewer; for PDFs, Synthadoc resolves the page number automatically.

### Queries with decomposition
Complex questions are decomposed into focused sub-questions, searched in parallel via BM25 (with optional vector re-ranking), then synthesised into a single cited answer. Output streams token-by-token to the terminal.

### Knowledge gap detection
When the wiki lacks coverage for a topic, Synthadoc detects this automatically and suggests `search for:` ingest commands to fill the gap.

### Query result caching
Identical questions against the same wiki return instantly from cache. The cache key includes the wiki epoch (version counter), so it invalidates automatically on any ingest or lifecycle change.

### Web chat UI
`synthadoc web` opens a browser-based multi-turn chat interface with streaming answers, citation links, knowledge-gap callouts, and adaptive hint chips.

### Obsidian integration
The bundled Obsidian plugin adds: query modal, ingest modal, jobs list, lifecycle management panel, lint report, candidates review, staging policy, routing management, export wiki, and claim provenance viewer — all accessible via the Command Palette.

### Export formats
| Format | Description |
|---|---|
| `llms.txt` | Compact active-page index per the llmstxt.org spec; ideal for feeding AI assistants |
| `llms-full.txt` | Full page content with provenance footnotes preserved |
| `graphml` | Directed wikilink graph; open in yEd, Gephi, or Cytoscape |
| `json` | Full dump including claims with source line ranges, lifecycle history, per-page cost |

---

## LLM providers supported

| Provider | Free tier | Notes |
|---|---|---|
| **Gemini Flash** | Yes — 15 RPM / 1M tokens/day, no credit card | Default provider |
| Groq | Yes — rate-limited | |
| Ollama | Yes — runs locally | |
| MiniMax | Paid | |
| DeepSeek | Paid | Very low text rates |
| Anthropic | Paid | Highest quality |
| OpenAI | Paid | |
| Claude Code | No key needed | Uses your existing subscription |
| Opencode | No key needed | Uses your existing subscription |

Configure the provider in `<wiki-root>/.synthadoc/config.toml`:

```toml
[agents]
default = { provider = "anthropic", model = "claude-sonnet-4-6" }
```

---

## Getting started (two commands)

```bash
# Install a demo wiki on the History of Computing topic
synthadoc install history-of-computing --domain "History of Computing"

# Start the engine
synthadoc serve -w history-of-computing
```

Then query it:

```bash
synthadoc query "How did Alan Turing influence modern computers?"
```

See the **User Quick-Start Guide** for the full demo walk-through.

---

## Key CLI commands at a glance

| Command | What it does |
|---|---|
| `synthadoc install <name>` | Register a new wiki |
| `synthadoc serve -w <name>` | Start the engine |
| `synthadoc ingest <source>` | Ingest a document, URL, or search query |
| `synthadoc query "<question>"` | Ask the wiki a question (streaming) |
| `synthadoc lint run` | Check quality and promote draft pages |
| `synthadoc lint report` | Show current contradictions, orphans, warnings |
| `synthadoc status` | Show wiki page counts by lifecycle state |
| `synthadoc web` | Open the browser-based chat UI |
| `synthadoc export --format llms.txt` | Export for AI consumption |
| `synthadoc use <name>` | Set the active wiki (omit `-w` on all commands) |

---

## What makes it different from RAG

| Concern | Typical RAG | Synthadoc |
|---|---|---|
| Contradicting sources | Silently blended | Detected, flagged `contradicted`, preserved with citations |
| Knowledge graph | None | `[[wikilinks]]` built at ingest time; visible in Obsidian Graph view |
| Orphan content | Invisible | Surfaced by lint with index entry suggestions |
| Content accuracy | No review | Adversarial second-LLM pass per page |
| Claim traceability | None | `^[file:L-L]` citation on every paragraph |
| Page lifecycle | All content equal | 5-state machine with immutable audit trail |
| Offline access | Requires server | Wiki is plain Markdown — browse without any tool running |
| Cost control | None | Per-job token + USD audit log; configurable cost gates; 3-layer cache |
