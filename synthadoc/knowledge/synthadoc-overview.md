---
title: Synthadoc Overview
keywords: [overview, introduction, features, open source, community, free, providers, capabilities, product]
---

# Synthadoc Overview

**Synthadoc** is an open-source, domain-agnostic LLM wiki engine (Community Edition, AGPL-3.0). It reads your raw source documents — PDFs, spreadsheets, Word files, presentations, images, web pages, YouTube videos, plain text — and uses an LLM to compile them into a persistent, structured wiki of Markdown files stored locally on your machine.

Unlike traditional retrieval-augmented generation (RAG) tools that synthesize at query time, Synthadoc **compiles** knowledge at ingest time. Every new source enriches and cross-links the entire corpus. The wiki is the artifact — browsable in [Obsidian](https://obsidian.md) or any text editor without any server running.

---

## Who is it for?

| Scale | Typical use |
|---|---|
| **Solo / 1–2 people** | Personal research wiki, freelance knowledge base — run free on Gemini Flash or Groq, no credit card |
| **Small team (3–20)** | Centralised internal wiki; autonomous contradiction resolution as the team grows |
| **Enterprise** | Compliance-sensitive, locally hosted knowledge bases; per-department wikis; audit trail for every event |

---

## What Synthadoc ingests

- **Local files:** PDF, DOCX, PPTX, XLSX, CSV
- **Images:** PNG, JPG, JPEG, WEBP, GIF, TIFF (vision LLM extraction)
- **Text / Markdown:** MD, TXT
- **Web pages:** any HTTP/HTTPS URL
- **YouTube videos:** automatic transcript extraction, no API key required
- **Web search:** intent phrases like `search for: topic` (requires Tavily API key)

---

## Core capabilities

**Contradiction detection** — when two sources conflict, the page is flagged `status: contradicted` rather than silently blending the claims.

**5-state lifecycle machine** — every page moves through `draft → active → contradicted / stale / archived` with an immutable audit trail. New pages start as `draft`; lint auto-promotes clean pages to `active`; local file changes detected via SHA-256 hash trigger `stale`.

**Adversarial lint** — a concurrent second-LLM pass reviews every page for overstated claims, unsupported superlatives, and contested figures. Using a different model family from the primary LLM produces the strongest signal.

**Claim-level provenance** — a `^[filename:L-L]` citation is inserted on every substantive paragraph during ingest, linking compiled claims to the exact source lines. In Obsidian these render as clickable chips with a Source Viewer; PDFs resolve to the correct page number automatically.

**Orphan page detection** — pages with no inbound `[[wikilinks]]` are surfaced by lint with ready-to-paste index entry suggestions.

**Query decomposition** — complex questions are split into focused sub-questions, searched in parallel via BM25 (with optional vector re-ranking), and synthesised into a single cited answer that streams token-by-token.

**Knowledge gap detection** — when the wiki lacks coverage for a topic, Synthadoc detects this and suggests `search for:` ingest commands to fill the gap.

**Query result caching** — identical questions return instantly from cache. The cache key includes the wiki epoch (version counter), so it auto-invalidates on any ingest or lifecycle change.

**Web chat UI** — `synthadoc web` opens a multi-turn browser chat with streaming answers, citation links, knowledge-gap callouts, and adaptive hint chips.

**Obsidian plugin** — query modal, ingest modal, jobs list, lifecycle management, lint report, candidates review, routing management, export wiki, and claim provenance viewer, all in the Command Palette.

**Export formats** — `llms.txt` (compact index for AI consumption), `llms-full.txt` (full content), `graphml` (wikilink graph for yEd / Gephi), `json` (full dump with claims, lifecycle history, per-page cost).

**Scheduling** — register cron-based recurring jobs (nightly ingest, weekly lint, weekly scaffold) via `synthadoc schedule add`.

**Candidates staging** — new pages can land in a staging area for review before influencing queries and lint.

**Context packs** — a goal decomposes into sub-questions, retrieves the highest-scoring pages, and assembles a token-bounded cited Markdown bundle for feeding to external LLMs.

---

## LLM providers supported

| Provider | Free tier | Notes |
|---|---|---|
| **Gemini Flash** | Yes — 1M tokens/day, no credit card | Default provider |
| Groq | Yes — rate-limited | |
| Ollama | Yes — runs locally, no key | |
| MiniMax | Paid | |
| DeepSeek | Paid — very low text rates | |
| Anthropic | Paid | |
| OpenAI | Paid | |
| Claude Code | No separate key needed | Uses your existing subscription |
| Opencode | No separate key needed | Uses your existing subscription |

Configure in `<wiki-root>/.synthadoc/config.toml` under `[agents]`.

---

## How Synthadoc compares to RAG

| Concern | Typical RAG | Synthadoc |
|---|---|---|
| Contradicting sources | Silently blended | Detected, flagged `contradicted`, preserved with citations |
| Knowledge graph | None | `[[wikilinks]]` built at ingest time; visible in Obsidian Graph view |
| Orphan content | Invisible | Surfaced by lint with index entry suggestions |
| Content accuracy | No review | Adversarial second-LLM pass per page |
| Claim traceability | None | `^[file:L-L]` citation on every paragraph |
| Page lifecycle | All content equal | 5-state machine with immutable audit trail |
| Offline access | Requires server | Wiki is plain Markdown — readable without any tool running |
| Cost control | None | Per-job token + USD audit log; configurable cost gates; 3-layer cache |
| Vendor lock-in | Often proprietary | Plain Markdown + YAML frontmatter; open in any editor |
