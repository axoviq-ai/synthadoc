# Synthadoc

```
      .-+###############+-.
    .##                   ##.
   ##    .----.   .----.    ##
  ##    /######\ /######\    ##
  ##    |######| |######|    ##
  ##    | [SD] | | wiki |    ##
  ##    |######| |######|    ##
  ##    \######/ \######/    ##
   ##    '----'   '----'    ##
    '##                   ##'
      '-+###############+-'

       S Y N T H A D O C
    Community Edition  v1.0.1
  ────────────────────────────────
  Domain-agnostic LLM wiki engine
```

[![CI](https://github.com/axoviq-ai/synthadoc/actions/workflows/ci.yml/badge.svg)](https://github.com/axoviq-ai/synthadoc/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.coverage&label=Coverage&suffix=%25&color=brightgreen)](https://github.com/axoviq-ai/synthadoc/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://github.com/axoviq-ai/synthadoc/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-yellow.svg)](https://www.python.org/)
[![Agents](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.agents&label=AI%20agents&color=crimson)](https://github.com/axoviq-ai/synthadoc/tree/main/synthadoc/agents)
[![Skills](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.skills&label=Skills&color=purple)](https://github.com/axoviq-ai/synthadoc/tree/main/synthadoc/skills)
[![Hooks](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.hooks&label=Hook%20events&color=teal)](https://github.com/axoviq-ai/synthadoc/tree/main/hooks)
[![CLI](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.cli_commands&label=CLI%20commands&color=darkblue)](https://github.com/axoviq-ai/synthadoc)
[![Obsidian](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.obsidian_commands&label=Obsidian%20commands&color=blueviolet)](https://github.com/axoviq-ai/synthadoc/tree/main/obsidian-plugin)
[![MCP](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fbadges%2Fdocs%2Fbadges.json&query=%24.mcp_tools&label=MCP%20tools&color=orange)](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-i--connect-claude-via-mcp)
[![Version](https://img.shields.io/badge/Community%20Edition-v1.0.1-brightgreen.svg)](https://github.com/axoviq-ai/synthadoc)

**Document version: v1.0.1**

**Engineered for solo users and enterprises alike, providing a domain-specific knowledge base that scales seamlessly while maintaining accuracy through autonomous self-optimization.**

> Built for individuals, small teams, and large organizations who need a knowledge base that stays accurate as documents accumulate.

Synthadoc reads your raw source documents — PDFs, spreadsheets, PPTs, web pages, images, videos, Word files, TXTs — and uses an LLM to synthesize them into a persistent, structured wiki. Cross-references are built automatically, contradictions are detected and surfaced, orphan pages are flagged, and every answer cites its sources. Outputs are stored as local Markdown files, ensuring seamless integration and autonomous management within [Obsidian](https://obsidian.md) or any wiki-compliant ecosystem.

---

[![Watch the Synthadoc demo](https://img.youtube.com/vi/rIGO6zi9XQE/maxresdefault.jpg)](https://www.youtube.com/watch?v=rIGO6zi9XQE)

▶ [From Documents to Wiki — demo walkthrough](https://www.youtube.com/watch?v=rIGO6zi9XQE) · Also watch: [Four Interfaces: CLI, Obsidian, Web UI & MCP](https://youtu.be/ue_kHhG0iog)

---

## Table of Contents

- [Who Is It For?](#who-is-it-for)
- [Inspiration and Vision](#inspiration-and-vision)
- [Problems Addressed](#problems-addressed)
- [Why Synthadoc?](#why-synthadoc)
- [Architecture](#architecture)
- [What's Included](#whats-included)
- [Installation](#installation)
- [Quick-Start Guide](#quick-start-guide)
- [Creating Your Own Wiki](#creating-your-own-wiki)
- [Configuration](#configuration)
- [Command Reference by Use Case](#command-reference-by-use-case)
- [Administrative Reference](#administrative-reference)
- [Understanding Logs and the Audit Trail](#understanding-logs-and-the-audit-trail)
- [Customization](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#customization)
- [Links](#links)

---

## Who Is It For?

Synthadoc scales from a single researcher to a company-wide knowledge platform:

| Team size               | Typical use case                                                                                                                                                                                                                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Solo / 1–2 people**  | Personal research wiki, freelance knowledge base, indie hacker documentation - run it free on Gemini Flash or a local Ollama model with zero ongoing cost                                                                                                                                           |
| **Small team (3–20)**  | Centralized internal knowledge base for startups and departments that aggregates diverse individual data sources into a unified, high-integrity wiki. The system automatically resolves contradictions and scales autonomously, ensuring organizational intelligence grows in tandem with your team |
| **Medium / enterprise** | Compliance-sensitive knowledge bases that must stay local; per-department wikis on separate ports; audit trail for every ingest and cost event; hook system for CI/CD integration; OpenTelemetry for ops dashboards                                                                                 |

No cloud account. No vendor lock-in. The wiki is plain Markdown — open it in any editor, back it up with git, sync it with any cloud drive.

---

## Inspiration and Vision

> *"The LLM should be able to maintain a wiki for you."*
> — Andrej Karpathy, [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Most knowledge-management tools retrieve and summarize at query time. Synthadoc inverts this: it **compiles knowledge at ingest time**. Every new source enriches and cross-links the entire corpus, not just appends a new chunk. The wiki is the artifact — readable, editable, and browsable without any tool running.

**Long-term alignment:**

| Direction                | How Synthadoc moves there                                                                                                                                                                                               |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent orchestration      | Orchestrator dispatches parallel ingest, query, and lint sub-agents with cost guards and retry backoff                                                                                                       |
| Sub-agent skills/plugins | Featuring a 3-tier lazy-load capability system, the platform allows for the injection of custom skills and hooks via a plug-and-play interface, ensuring core stability is never compromised during extension           |
| LLM wiki vs. RAG         | Pre-compiled structured knowledge beats query-time synthesis for contradiction detection, graph traversal, and offline access                                                                                           |
| CLI / HTTP               | A unified interface via CLI and RESTful endpoints, the system streamlines full-spectrum integration: from data ingestion and querying to automated linting, security auditing, and job orchestration                    |
| Local-first              | All data stays on your machine; localhost-only network binding; no cloud dependency except the LLM API itself                                                                                                           |
| Provider choice          | LLM backends including free-tier Gemini and Groq, paid Anthropic/OpenAI/DeepSeek/MiniMax/Qwen (DashScope), local Ollama and Qwen, and coding-tool CLI providers (Claude Code, Opencode) — no API key required if you already have a subscription |

---

## Problems Addressed

RAG retrieves document chunks at query time. Synthadoc **compiles** knowledge at ingest — synthesising sources into a linked, audited wiki graph so contradictions are caught, claims are traced to sources, and the artifact survives outside the tool.

| Problem | Synthadoc approach |
| --- | --- |
| **Contradictions blended silently** | Ingest-time conflict detection; page flagged `status: contradicted`; auto-resolve or queue for human review |
| **No links between related content** | `[[wikilinks]]` auto-built on every ingest pass; force-directed graph with Louvain clustering in web UI |
| **Orphan pages never surfaced** | Lint reports unreferenced pages with ready-to-paste index entries |
| **LLM output can be overconfident** | Adversarial second-LLM pass flags overstated claims, unsupported superlatives, and contestable facts per page |
| **Claims lack source traceability** | `^[file:L-L]` citation on every claim; Source Viewer in Obsidian; PDF page resolution; broken-citation lint |
| **Knowledge lifecycle invisible** | 5-state machine (`draft → active → contradicted / stale → archived`); auto-transitions via lint; immutable event log |
| **Repeat ingest is expensive** | 3-layer cache (embedding, LLM, provider prompt) — repeat lint on unchanged pages costs near-zero tokens |
| **Knowledge locked in proprietary tools** | Plain Markdown + YAML frontmatter; OKF v0.1 compatible; fully offline-readable in any editor |
| **Wiki structure drifts with growth** | `scaffold` regenerates index, AGENTS.md, and purpose.md from current wiki state without touching linked pages |
| **Migration requires full re-ingestion** | Single-zip backup + restore with port/domain rewriting; no re-ingestion needed |
| **Cost and compliance exposure** | Localhost-only; per-job token+cost log; configurable soft-warn and hard-gate thresholds |

> **Citation quality:** Generated pages include inline citations linking every claim to its source lines. Pages without citations trigger a model-compatibility warning — use Gemini 2.5 Flash or higher for reliable citation annotation.
>
> **Active page protection:** Pages promoted to `active` status are protected — sources that contradict them are flagged for review rather than overwriting the human-reviewed content.

---

## Why Synthadoc?

Every **Yes** below is a built-in feature — no add-ons or upgrades required.

### Knowledge Quality

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
| --- | --- | --- | --- | --- |
| **Ingest-time synthesis** — sources compiled into the wiki at ingest; not re-summarised at query time | **Yes** | No | Partial | No |
| **Contradiction detection & resolution** — conflicting claims flagged `status: contradicted`; auto-resolve available; full conflict history | **Yes** | No | No | No |
| **Adversarial claim review** — concurrent second-LLM pass flags overstated claims, unsupported superlatives, and contestable facts per page | **Yes** | No | No | No |
| **Claim-level provenance** — `^[file:L-L]` citation on every claim; Source Viewer in Obsidian; PDF page resolution; broken-citation lint | **Yes** | No | Partial | No |
| **5-state lifecycle machine** — `draft → active → contradicted / stale → archived`; auto-transitions via lint; immutable event log | **Yes** | No | No | No |
| **Pre-LLM source sanitizer** — strips zero-width chars, bidi overrides, hidden HTML, and instruction-override phrases before any LLM call | **Yes** | No | No | No |

### Knowledge Structure

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
| --- | --- | --- | --- | --- |
| **Wikilink graph + D3 visualisation** — `[[wikilinks]]` auto-built at ingest; force-directed graph in web UI; nodes coloured by Louvain cluster; click node to query | **Yes** | No | Partial | No |
| **Orphan page detection** — unreferenced pages surfaced by lint with ready-to-paste index entries | **Yes** | No | No | No |
| **Query-scoped routing** — ROUTING.md maps wiki branches to page slugs; queries auto-select relevant branches; new pages auto-slotted | **Yes** | No | No | No |
| **Candidates staging** — ingest pages to a staging area first; review, promote, or discard before they enter the live wiki | **Yes** | No | No | No |
| **Scaffold automation** — regenerates index categories, AGENTS.md, and purpose.md from current wiki state; protected pages never overwritten | **Yes** | No | No | No |

### Search & Query

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
| --- | --- | --- | --- | --- |
| **Query decomposition + gap detection** — compound questions split into parallel BM25 sub-queries; thin results trigger a knowledge-gap callout with suggested web searches | **Yes** | Partial | No | No |
| **BM25 TF fallback + compound identifier search** — reliable results on small corpora (IDF collapse → TF fallback); underscore identifiers expanded at index and query time so `capex growth` matches `capex_growth` | **Yes** | No | No | No |
| **Web search → wiki pages** — Tavily search fans out into parallel URL ingest jobs; gap callout in web UI suggests searches inline | **Yes** | No | No | No |
| **Semantic re-ranking** — optional vector re-ranking (`BAAI/bge-small-en-v1.5`) improves recall on conceptually related queries; BM25 stays as fallback | **Yes** (optional) | Varies | No | No |
| **Streaming output + query cache** — token-by-token streaming; cache key = question + wiki version; auto-invalidates on ingest or lifecycle change | **Yes** | Partial | Partial | Partial |
| **Proportional context budget** — sources allocated proportionally to model context window (60 % wiki / 20 % history / 15 % system / 5 % index); replaces fixed top-N cap | **Yes** | No | No | No |

### Interfaces & Integration

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
| --- | --- | --- | --- | --- |
| **Obsidian integration** — native plugin: ingest modal, streaming query, lint report, lifecycle controls, context pack builder, provenance viewer, export modal; Reading View set as default on install so citation chips are visible immediately | **Yes** | No | No | No |
| **Web chat UI** — `synthadoc web`: streaming answers, session sidebar, multi-turn history, knowledge-gap callouts, knowledge graph tab | **Yes** | No | Yes | Yes |
| **MCP server** — 12 tools; Claude Desktop (stdio), Claude Code (SSE), n8n/LangGraph (HTTP/SSE); brain+memory architecture; no double-LLM cost for reads | **Yes** | No | No | No |
| **Context packs** — goal → sub-questions → token-budget evidence pack; REST + MCP callable; paste into any LLM chat as grounded context | **Yes** | No | No | No |
| **Export formats** — `llms.txt`, `llms-full.txt`, GraphML, JSON (provenance + lifecycle), OKF v0.1 bundle; lifecycle-filtered; zero extra LLM calls | **Yes** | No | Partial | No |

### Content Sources

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
| --- | --- | --- | --- | --- |
| **Multi-format ingest** — PDF, DOCX, PPTX, XLSX/CSV, Markdown, TXT, images (vision), web URLs, YouTube transcripts | **Yes** | Varies | Partial | Partial |
| **Web search decomposition** — broad topics decomposed into focused Tavily keyword searches; results merged and deduplicated | **Yes** | No | No | Partial |
| **YouTube transcript ingest** — timestamped transcript + executive summary; no API key; auto-generated captions supported | **Yes** | No | Yes | No |
| **Multilingual / CJK queries** — Chinese, Japanese, Korean — no false knowledge gaps | **Yes** | Limited | No | No |
| **Multiple LLM providers + coding tools** — Gemini, Groq, Qwen, MiniMax, DeepSeek, Anthropic, OpenAI, Ollama; Claude Code and Opencode (no API key needed) | **Yes** | No | No | No |

### Operations & Trust

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
| --- | --- | --- | --- | --- |
| **Local-first + offline artifact** — source documents never leave your machine; compiled wiki is plain Markdown, fully readable offline in any editor without the server | **Yes** | Varies | No | No |
| **Portable backup / restore** — single zip: wiki pages + audit/lifecycle DB + config; port and domain rewriting on restore; migrate machines without re-ingesting | **Yes** | No — re-ingest required | No — AI metadata lost | No |
| **Cost guard + full audit trail** — per-job token + cost log; soft-warn and hard-gate thresholds; `audit citations` validates every claim citation; immutable event log | **Yes** | No | No | No |
| **Resumable job queue + retry** — every ingest/lint job persisted with status and error; batch a hundred documents and resume after a crash | **Yes** | No | No | No |
| **Custom skills + CI hooks** — subclass `BaseSkill` for new file formats; 2 hook events on ingest and lint complete; blocking hooks can gate operations | **Yes** | Limited | No | No |
| **Per-source truncation flag** — `--max-source-chars` caps any source (PDF, DOCX, web page, plain text) before the LLM call; truncated sources flagged with `truncated: true` in frontmatter and warned in lint output | **Yes** | No | No | No |
| **Multi-wiki isolation** — each wiki on its own port with independent config, audit trail, and job queue; switch with `synthadoc use` | **Yes** | No | Partial | No |

### Business value

| Value | How |
| --- | --- |
| **Faster onboarding** | New team members query the wiki instead of digging through documents |
| **Audit trail** | Every ingest recorded in `audit.db` with source hash, token count, and timestamp |
| **Cost control** | Configurable thresholds; 3-layer cache reduces repeat spend |
| **Compliance** | Local-first — source documents and compiled knowledge never leave your machine |
| **Extensibility** | Hooks fire on every event; custom skills load without a server restart |

---

## Architecture

![Synthadoc Architecture](https://raw.githubusercontent.com/axoviq-ai/synthadoc/main/docs/png/architecture.png)

For full architecture details, data models, API reference, and plugin development guide see **[docs/design.md](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md)**.

---

## What's Included

See [docs/design.md — Appendix A: Release Feature Index](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#appendix-a--release-feature-index) for a full feature list by version.

---

## Installation

### Production

**Prerequisites:** Python 3.11+. No Node.js, no Git, no build steps.

```bash
pip install synthadoc
synthadoc --version   # confirm it works
```

The Obsidian plugin is bundled inside the package. New wikis created with `synthadoc install` have it installed automatically. If you are upgrading an existing Synthadoc installation, run `synthadoc plugin upgrade` to push the updated plugin binary to all registered wikis.

---

### Development

For developers modifying the Python engine, running the test suite, or developing the Obsidian plugin TypeScript.

**Additional prerequisites:** Git (any). Node.js 18+ only if modifying the plugin TypeScript source.

#### Step 1 — Clone and install

```bash
git clone https://github.com/axoviq-ai/synthadoc.git
cd synthadoc
pip install -e ".[dev]"
```

`[dev]` adds `pytest`, `respx`, and the other test dependencies. Tests require a source checkout — they are not included in the pip wheel.

#### Step 2 — Run the test suite

```bash
pytest --ignore=tests/performance/ -q
```

Expected: all tests pass, 0 failures. Performance benchmarks (optional):

```bash
pytest tests/performance/ -v --benchmark-disable
```

#### Step 3 — Obsidian plugin development (optional)

The compiled plugin is bundled with the package and kept up to date by CI — no build step is needed to work on the Python side or run tests.

If you modify the TypeScript source under `obsidian-plugin/src/`, recompile and sync it into the Python package manually:

```bash
cd obsidian-plugin
npm install           # first time only, or after package.json changes
# edit src/main.ts or other source files
npm run build         # compile TypeScript → main.js (also syncs to synthadoc/data/obsidian-plugin/)
npm test              # run Vitest unit tests
cd ..
```

---

### Set your API keys

**At least one LLM API key is required** — unless you use Claude Code or Opencode as your provider (no separate API key needed — see [Coding tool CLI providers](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#coding-tool-cli-providers--no-api-key-needed)).

Synthadoc defaults to **Gemini Flash** — free tier, no credit card, 1 million tokens per day. Get a key at **aistudio.google.com/app/apikey** (click "Create API key").

| Provider         | Free tier                                                | Vision          | Get key                                                           |
| ---------------- | -------------------------------------------------------- | --------------- | ----------------------------------------------------------------- |
| **Gemini Flash** | Yes — 15 RPM / 1M tokens/day, no credit card            | Yes             | [aistudio.google.com](https://aistudio.google.com/app/apikey)    |
| Groq             | Yes — rate-limited                                       | No              | [console.groq.com](https://console.groq.com/keys)                |
| Ollama           | Yes — runs locally, no key (**GPU required**)            | Model-dependent | [ollama.com](https://ollama.com)                                  |
| Qwen             | Yes — 1M free tokens (90-day trial), then paid DashScope | Model-dependent | [bailian.console.aliyun.com](https://bailian.console.aliyun.com/) |
| MiniMax          | No — pay-per-token                                       | Yes             | [platform.minimax.io](https://platform.minimax.io/)               |
| DeepSeek         | No — pay-per-token (very cheap text rates)               | No              | [platform.deepseek.com](https://platform.deepseek.com/api_keys)  |
| Anthropic        | No                                                       | Yes             | [console.anthropic.com](https://console.anthropic.com/)           |
| OpenAI           | No                                                       | Yes             | [platform.openai.com](https://platform.openai.com/api-keys)      |
| **Claude Code**  | Included with subscription — no API key                  | No              | Set `provider = "claude-code"` in config.toml                    |
| **Opencode**     | Included with subscription — no API key                  | No              | Set `provider = "opencode"` in config.toml                       |

```bash
# macOS / Linux — add to ~/.bashrc or ~/.zshrc to persist
export GEMINI_API_KEY=AIza…          # default — free tier, 1M tokens/day
export GROQ_API_KEY=gsk_…            # alternative free tier — 100K tokens/day
export ANTHROPIC_API_KEY=sk-ant-…    # paid — highest quality
export OPENAI_API_KEY=sk-…           # paid
export MINIMAX_API_KEY=…             # paid — text rates (image support)
export DEEPSEEK_API_KEY=…            # paid — text rates (no image support)
export QWEN_API_KEY=…                # DashScope cloud — 1M free tokens trial
export TAVILY_API_KEY=tvly-…         # web search (optional)

# Windows cmd — current session only
set GEMINI_API_KEY=AIza…
set GROQ_API_KEY=gsk_…
set ANTHROPIC_API_KEY=sk-ant-…
set OPENAI_API_KEY=sk-…
set MINIMAX_API_KEY=…
set DEEPSEEK_API_KEY=…
set QWEN_API_KEY=…
set TAVILY_API_KEY=tvly-…

```

Web search uses **Tavily** (`TAVILY_API_KEY`) — optional, only needed for `synthadoc ingest "search for: …"` jobs. Get a free key at [tavily.com](https://tavily.com).

---

### Install a wiki and start the engine

A **wiki** is a self-contained knowledge base — a folder of Markdown pages maintained and cross-referenced automatically by Synthadoc. The fastest way to get started is the **History of Computing** demo (13 pre-built pages, no LLM API key required to browse).

```bash
# Linux / macOS
synthadoc install history-of-computing --target ~/wikis --demo

# Windows (cmd.exe)
synthadoc install history-of-computing --target %USERPROFILE%\wikis --demo
```

Then start the engine:

```bash
# Foreground — logs stream to the console
synthadoc serve -w history-of-computing

# Background — releases the terminal
synthadoc serve -w history-of-computing --background
```

The server binds to `http://127.0.0.1:7070` (localhost-only). Leave it running while you work — the Obsidian plugin, CLI ingest commands, and query commands all talk to it.

To switch LLM provider, edit `[agents]` in `<wiki-root>/.synthadoc/config.toml` and restart `synthadoc serve`. See [Appendix — Switching LLM providers](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-c--switching-llm-providers) for step-by-step instructions.

To stop a background server:

```bash
# Linux / macOS
kill <PID>

# Windows (cmd)
taskkill /PID <PID> /F
```

The PID is printed on start and saved to `<wiki-root>/.synthadoc/server.pid`.

**Upgrading:** after updating synthadoc (via `pip install --upgrade synthadoc` or `git pull`), restart the server to pick up the new code, then run these to keep registered wikis in sync:

```bash
synthadoc plugin upgrade         # push updated Obsidian plugin binary to all registered wikis
synthadoc demo sync --force      # demo-installed wikis — update pages and pick up citation markers
```

Neither command requires the server to be running.

---

## Quick-Start Guide

The **History of Computing** demo includes 13 pre-built pages, raw source files covering clean-merge, contradiction, and orphan scenarios, and a full walkthrough of key Synthadoc feature.

**Full step-by-step walkthrough: [docs/user-quick-start-guide.md](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md)**

The guide covers:

1. Verify the demo server started (banner, health check)
2. Install the Synthadoc plugin (auto-installs Dataview) and open the vault
3. Review wiki structure and key files (index, purpose, AGENTS.md, dashboard)
4. Query the pre-built wiki — including knowledge gap detection
5. Batch ingest all demo source files
6. Run lint — auto-promote clean pages to active
7. Manage page lifecycle — 5-state machine (draft → active → stale/contradicted/archived), manual transitions, immutable audit trail
8. Resolve a contradiction
9. Fix an orphan page
10. Run the adversarial lint pass — flag overstated claims across all pages
11. Web search ingestion with automatic decomposition
12. Ingest a YouTube video
13. Enrich the wiki with scaffold (regenerate/update index, purpose, AGENTS.md)
14. Audit features (token cost, history, events)
15. Schedule recurring operations
16. Set up query-scoped routing with ROUTING.md
17. Stage and review candidate pages before promoting them
18. Build a context pack for grounded LLM prompts
19. Verify claim provenance — source-line citations, broken citation audit, global provenance table
20. Export your wiki — llms.txt, llms-full.txt, GraphML wikilink graph, agent-ready JSON with provenance and lifecycle history, OKF v0.1 bundle for zero-code agent consumption
21. Use the web chat UI — streaming answers, session-aware hint chips, citations in-browser
22. Query caching — understand how answers are cached and how to bypass with `--no-cache`
23. Backup and restore — create a portable wiki zip, restore on a different machine
24. Knowledge graph — build the wikilink graph, explore clusters in the web UI Graph tab, click a node to query it

---

## Creating Your Own Wiki

Unlike the demo (which ships with pre-built pages), your own wiki starts from a domain description and grows as you feed it sources:

```bash
synthadoc install market-condition-canada --target ~/wikis --domain "Market conditions and trends in Canada"
synthadoc use market-condition-canada   # set as the default wiki — no -w needed from here on
synthadoc status                        # confirm the wiki registered correctly (should show 0 pages)
```

Before starting the server, open `~/wikis/market-condition-canada/.synthadoc/config.toml` and set your LLM provider — see [Appendix C in the Quick-Start Guide](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-c--switching-llm-providers) for the full provider list and API key setup. Then start:

```bash
synthadoc serve
```

`--domain` is a free-text description of the subject area — the LLM uses it to generate three domain-aware starter files via scaffold:

| File                | Purpose                                                                     |
| ------------------- | --------------------------------------------------------------------------- |
| `wiki/index.md`     | Table of contents — domain-relevant categories with `[[wikilinks]]`        |
| `wiki/purpose.md`   | Scope declaration — tells the ingest agent what belongs and what to ignore |
| `AGENTS.md`         | LLM behaviour guidelines — tone, terminology, and synthesis style          |

`wiki/dashboard.md` is also created during install (a static template — not LLM-generated). `ROUTING.md` is optional and generated separately via `synthadoc routing init` after pages accumulate.

Before ingesting any content, run scaffold once to build a clean starting index and purpose files based on your domain:

```bash
synthadoc scaffold
```

`synthadoc install` also copies both the Synthadoc plugin and the Dataview plugin directly into the vault's plugins folder, pre-enables them, and sets the correct server URL — no separate plugin step is required. Open the wiki folder in Obsidian — both plugins are active immediately, no manual toggling needed.

The Quick-Start Guide covers the full Obsidian setup in detail — see [docs/user-quick-start-guide.md](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md).

**Local Web UI** — once the server is running, you can also query the wiki from your browser without Obsidian:

```bash
synthadoc web
```

This opens a local chat interface at `http://localhost:{port}/app`. The Web UI is local-only and is **not accessible from the network** — authentication and authorisation are not configured by default in the Community Edition.

**Recommended growth loop:**

**1. Seed with web searches** — pull in real content for the topics you care about:

```bash
synthadoc ingest "search for: Economy, employment and labour market analysis in Toronto GTA"
synthadoc ingest "search for: Bank of Canada interest rate outlook 2025"
synthadoc jobs list   # watch progress
```

Each search fans out into up to 20 parallel URL ingest jobs. Both query and web search automatically decompose broad inputs into focused parallel sub-tasks — see [Quick-Start Guide](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#compound-and-multi-part-queries) for examples.

**2. Review candidates (optional quality gate)** — enable staging before large ingest batches so pages below your confidence threshold wait for review rather than entering BM25 immediately:

```bash
synthadoc staging policy threshold   # pages below high confidence → wiki/candidates/
synthadoc candidates list            # see what's waiting
synthadoc candidates promote early-internet-history   # approve individually
synthadoc candidates promote --all   # or approve everything at once
synthadoc candidates discard punch-card-era           # discard pages that don't belong
```

Skip this step if you trust all your sources — `staging policy off` is the default.

**3. Re-run scaffold** — after pages accumulate, scaffold regenerates a richer index that reflects actual content. Pages already linked in `index.md` are never overwritten:

```bash
synthadoc scaffold
```

**4. Lint and query** — check for contradictions, flag overstated claims, verify citations, and confirm the wiki answers your questions:

```bash
synthadoc lint run                          # full lint: structural checks + adversarial pass (default)
synthadoc lint run --no-adversarial         # structural only — skip the adversarial LLM review
synthadoc lint report                       # view all issues including citation violations (Check 5)
synthadoc audit citations --broken          # list claim citations that failed validation
synthadoc query "What are the current employment trends in the Toronto GTA?"
```

**5. Set up routing** — once the wiki spans distinct topic areas, routing narrows each query to the relevant branch, cutting latency and reducing noise in synthesis:

```bash
synthadoc routing init   # generate ROUTING.md from current index.md (one-time)
```

From this point, queries automatically scope to the 1–2 most relevant topic branches. New pages created by ingest are auto-slotted into `ROUTING.md` — no manual maintenance needed. See [Appendix H in the Quick-Start Guide](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-h--bm25-routing-performance-benchmarks) for latency benchmarks across corpus sizes.

**6. Build a context pack** — assemble cited wiki excerpts within a token budget for use in an external agent prompt:

```bash
synthadoc context build "Toronto GTA real estate market" --tokens 4000
```

Returns ranked page excerpts with relevance scores, confidence levels, and source paths — no synthesis. The `POST /context/build` REST endpoint and `synthadoc_context` MCP tool make this callable from any agent pipeline. To connect Claude Code to your wiki's MCP server:

```bash
# Replace 7070 with the port shown when you ran synthadoc serve
claude mcp add --transport sse synthadoc-market-condition-canada http://127.0.0.1:7070/mcp/sse
```

Then ask Claude Code: *"Build a context pack on Toronto GTA real estate market"* and it will call `synthadoc_context` automatically. See [docs/design.md — Context packs](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#context-packs) for the knowledge backend pattern.

**7. Schedule recurring updates** — keep the wiki fresh and the routing table clean automatically:

```bash
synthadoc schedule add --op "ingest --batch raw_sources/" --cron "0 2 * * *"
synthadoc schedule add --op "lint run"      --cron "0 3 * * 0"
synthadoc schedule add --op "scaffold"      --cron "0 4 * * 0"
synthadoc schedule add --op "routing clean" --cron "0 5 * * 0"
```

Run order matters: lint first (removes dead wikilinks), scaffold next (regenerates index), routing clean last (prunes ROUTING.md entries for deleted pages).

### Semantic re-ranking (vector search)

BM25 keyword search is the default. Optional vector re-ranking (`BAAI/bge-small-en-v1.5` cosine similarity) improves recall on conceptually related queries — enable it by installing `fastembed` and setting `[search] vector = true` in config. The ~130 MB model is downloaded once; BM25 stays active as fallback.

See [docs/design.md — Semantic re-ranking](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#semantic-re-ranking) for configuration options and performance notes.

### Knowledge gap workflow

When a query returns thin or empty results, the wiki doesn't yet cover the topic. Fill the gap with a targeted web search ingest, wait for jobs, then re-query. Each ingest cycle makes the wiki denser — future queries need the web less.

See [docs/design.md — Knowledge gap workflow](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#knowledge-gap-workflow) for the full pattern.

See [docs/design.md](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md) for a full description of how ingest, contradiction detection, and orphan tracking work under the hood.

---

## Configuration

You do not need to configure anything to run the demo. The demo wiki ships with its own settings and sensible built-in defaults cover everything else. Set your API key env var, run `synthadoc serve`, and go.

For the full configuration reference — layer precedence, global vs. per-project config, all keys and defaults — see [Appendix E — Configuration](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-e--configuration) in the Quick-Start Guide, or [docs/design.md — Configuration](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#configuration) for the complete technical reference.

---

## Command Reference by Use Case

### Setting up a wiki

```bash
# Create a new wiki (LLM scaffold runs automatically; port is auto-assigned to avoid conflicts)
synthadoc install my-wiki --target ~/wikis --domain "Machine Learning"

# Pin a specific port manually
synthadoc install my-wiki --target ~/wikis --domain "Machine Learning" --port 7071

# Install the demo (includes pre-built pages and raw sources — no LLM call needed)
synthadoc install history-of-computing --target ~/wikis --demo

# List available demo templates
synthadoc demo list

# Sync new source files into an existing demo install (additive only, no overwrites)
synthadoc demo sync history-of-computing

# Update existing demo pages from the latest template (overwrites demo pages)
synthadoc demo sync history-of-computing --force

# Install the Obsidian plugin directly into the active Obsidian vault
synthadoc plugin install history-of-computing
```

### Switching the active wiki

```bash
# Set a wiki as the default so -w is not required for any subsequent command
synthadoc use my-wiki

# Check which wiki is currently active
synthadoc use

# Clear the saved default (revert to requiring -w on every command)
synthadoc use --clear
```

### Refreshing wiki scaffold

After install, you can re-run the LLM scaffold at any time to regenerate domain-specific content (index categories, AGENTS.md guidelines, purpose.md scope). Pages already linked in `index.md` are protected and preserved.

```bash
# Regenerate scaffold for an existing wiki
synthadoc scaffold -w my-wiki

# Schedule weekly refresh (runs every Sunday at 4 AM)
synthadoc schedule add --op "scaffold" --cron "0 4 * * 0" -w my-wiki
```

`config.toml` and `dashboard.md` are never modified by `scaffold`.

### Running the server

```bash
# Start HTTP API + job worker (foreground — terminal stays attached)
synthadoc serve -w my-wiki

# Detach to background — banner shown, then shell is released
# All logs go to <wiki>/.synthadoc/logs/synthadoc.log
synthadoc serve -w my-wiki --background

# Custom port
synthadoc serve -w my-wiki --port 7071

# Verbose debug logging to console
synthadoc serve -w my-wiki --verbose
```

### Ingesting sources

```bash
# Single file or URL
synthadoc ingest report.pdf -w my-wiki
synthadoc ingest https://example.com/article -w my-wiki

# Entire folder (parallel, up to max_parallel_ingest at a time)
synthadoc ingest --batch raw_sources/ -w my-wiki

# Manifest file — ingest a curated list of sources in one shot.
# sources.txt: one entry per line; each line is either an absolute file path
# (PDF, DOCX, PPTX, MD, …) or a URL. Blank lines and # comments are ignored.
# Each entry becomes a separate job in the queue, processed sequentially.
#
# Example sources.txt:
#   /home/user/docs/research-paper.pdf
#   /home/user/slides/keynote.pptx
#   https://en.wikipedia.org/wiki/Alan_Turing
#   # this line is ignored
synthadoc ingest --file sources.txt -w my-wiki

# Force re-ingest (bypass deduplication and cache)
synthadoc ingest --force report.pdf -w my-wiki

# Web search — triggers a Tavily search, then ingests each result URL as a child job.
# Prefix the query with any recognised intent: "search for:", "find on the web:",
# "look up:", or "web search:"  (prefix is stripped before the search is sent)
# Requires TAVILY_API_KEY to be set.
#
# Note: web search content is NOT saved to raw_sources/. The flow is direct:
#   query → Tavily → URLs → each URL fetched → wiki pages written
# raw_sources/ is for user-provided local files (PDF, DOCX, PPTX, etc.) only.
# The wiki pages themselves are the persistent output of a web search.
synthadoc ingest "search for: Bank of Canada interest rate decisions 2024" -w my-wiki
synthadoc ingest "find on the web: unemployment trends Ontario Q1 2025" -w my-wiki

# Limit how many URLs are enqueued (default 20, overrides [web_search] max_results)
synthadoc ingest "search for: quantum computing basics" --max-results 5 -w my-wiki

# Multiple web searches at once via a manifest file
# web-searches.txt:
#   search for: Bank of Canada interest rate decisions 2024
#   find on the web: unemployment trends Ontario Q1 2025
#   look up: Toronto housing market affordability index
synthadoc ingest --file web-searches.txt -w my-wiki

# YouTube video — transcript extracted automatically, no API key needed.
# The video must have captions (auto-generated or manual).
# Check: open the video on YouTube → ... → Show transcript.
synthadoc ingest "https://www.youtube.com/watch?v=O5nskjZ_GoI" -w my-wiki
synthadoc ingest "https://youtu.be/O5nskjZ_GoI" -w my-wiki

# YouTube URLs returned by web search are also routed automatically:
# if Tavily returns a YouTube URL, the transcript is ingested instead of the page HTML.
synthadoc ingest "search for: history of computing lecture" -w my-wiki
```

Each YouTube wiki page opens with an **executive summary** — what the video is about,
the main topics covered, and the key takeaway — followed by the full timestamped transcript
for precise citation.

### Querying

```bash
# Ask a question — answer streams token-by-token as the LLM generates it
synthadoc query "What is Moore's Law?" -w my-wiki

# Blocking mode (no streaming) — useful in scripts or pipes
synthadoc query "What is Moore's Law?" --no-stream -w my-wiki

# Skip the cache — always call the LLM even if the answer is cached
synthadoc query "What is Moore's Law?" --no-cache -w my-wiki

# Save the answer as a new wiki page
synthadoc query "What is Moore's Law?" --save -w my-wiki
```

Query answers are **cached automatically** by question content and wiki version. Repeated identical questions return instantly from cache. The cache invalidates automatically when you ingest new content or change a page's lifecycle state.

### Web Chat UI

```bash
# Open the browser-based chat interface for a wiki
synthadoc web -w my-wiki
```

→ Full walkthrough (session modes, multi-turn conversation, session history sidebar): [Quick-Start Guide — Step 22](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#step-22--use-the-web-chat-ui)

### Linting

```bash
# Run a full lint pass (enqueues job)
synthadoc lint run -w my-wiki

# Only contradictions
synthadoc lint run --scope contradictions -w my-wiki

# Auto-apply high-confidence resolutions
synthadoc lint run --auto-resolve -w my-wiki

# Skip adversarial review (structural checks only; also clears existing warnings)
synthadoc lint run --no-adversarial -w my-wiki

# Skip lifecycle checks (structural and adversarial checks only)
synthadoc lint run --no-lifecycle -w my-wiki

# Instant report (reads wiki files directly, no server needed)
synthadoc lint report -w my-wiki
```

### Managing page lifecycle

```bash
# Show page counts by lifecycle state
synthadoc status -w my-wiki

# Promote a draft page to active after manual review
synthadoc lifecycle activate <slug> -w my-wiki --reason "reviewed and verified"

# Archive a page whose source has been superseded
synthadoc lifecycle archive <slug> -w my-wiki --reason "replaced by updated source"

# Restore an archived page back to draft for re-review
synthadoc lifecycle restore <slug> -w my-wiki --reason "source re-added"

# View full state history for a page (or all pages)
synthadoc lifecycle log <slug> -w my-wiki
synthadoc lifecycle log -w my-wiki

# Purge old lifecycle events to reclaim audit.db space
synthadoc audit lifecycle purge -w my-wiki --before 2026-01-01
synthadoc audit lifecycle purge -w my-wiki --keep-latest 100
```

### Monitoring jobs

```bash
# List all jobs (oldest first by default)
synthadoc jobs list -w my-wiki

# Sort column — created_at (default) | status | operation
synthadoc jobs list --sort created_at -w my-wiki   # oldest first (default)
synthadoc jobs list --sort status -w my-wiki        # alphabetical by status
synthadoc jobs list --sort operation -w my-wiki     # alphabetical by operation type

# Sort direction — asc (default) | desc
synthadoc jobs list --order desc -w my-wiki                     # newest first
synthadoc jobs list --sort status --order desc -w my-wiki       # status Z→A

# Filter by status — pending | in_progress | completed | failed | skipped | dead | cancelled
synthadoc jobs list --status pending -w my-wiki
synthadoc jobs list --status failed -w my-wiki
synthadoc jobs list --status dead -w my-wiki

# Combine sort, order, and status freely
synthadoc jobs list --status failed --sort created_at --order desc -w my-wiki

# Single job detail
synthadoc jobs status <job-id> -w my-wiki

# Retry a dead job
synthadoc jobs retry <job-id> -w my-wiki

# Cancel all pending jobs at once (e.g. after a bad batch ingest)
synthadoc jobs cancel -w my-wiki        # prompts for confirmation
synthadoc jobs cancel --yes -w my-wiki  # skip confirmation

# Remove old records
synthadoc jobs purge --older-than 30 -w my-wiki
```

### Inspecting ingest results

```bash
# Preview how a source will be analysed without writing pages
synthadoc ingest report.pdf --analyse-only -w my-wiki
# → {"entities": [...], "tags": [...], "summary": "..."}
```

### Audit trail

```bash
# Ingest history: timestamp, source file, wiki page, tokens, cost
synthadoc audit history -w my-wiki            # last 50 records
synthadoc audit history -n 100 -w my-wiki     # last 100 records
synthadoc audit history --json -w my-wiki     # raw JSON for scripting

# Token usage: totals + daily breakdown
synthadoc audit cost -w my-wiki               # last 30 days
synthadoc audit cost --days 7 -w my-wiki      # last 7 days

# Audit events: contradictions found, auto-resolutions, cost gate triggers
synthadoc audit events -w my-wiki             # last 100 events
synthadoc audit events --json -w my-wiki      # raw JSON for scripting

# Claim citations: source-line provenance for every annotated claim
synthadoc audit citations -w my-wiki                    # all citations (last 50)
synthadoc audit citations --page alan-turing -w my-wiki # citations for one page
synthadoc audit citations --source turing.pdf -w my-wiki # citations from one source
synthadoc audit citations --broken -w my-wiki           # validation failures only
synthadoc audit citations --json -w my-wiki             # raw JSON for scripting
```

### Scheduling recurring jobs

Relative paths in `--op` (e.g. `raw_sources/`) are resolved against the **wiki root directory**, not the working directory of the shell that runs the schedule. This means they work correctly even when the OS scheduler fires the task with a different working directory (e.g. `C:\Windows\System32` on Windows).

```bash
# Register a nightly ingest
synthadoc schedule add --op "ingest --batch raw_sources/" --cron "0 2 * * *" -w my-wiki

# Weekly lint
synthadoc schedule add --op "lint run" --cron "0 3 * * 0" -w my-wiki

# Bulk-register all jobs declared in [[schedule.jobs]] in config.toml (alternative to schedule add)
# See docs/design.md § "schedule sub-commands" for the config.toml format
synthadoc schedule apply -w my-wiki

# List scheduled jobs (shows schedule, next run, last run, last result)
synthadoc schedule list -w my-wiki

# Remove a scheduled job
synthadoc schedule remove <id> -w my-wiki

# Run a scheduled operation immediately and record the result in the audit trail
synthadoc schedule run --op "lint run" -w my-wiki

# Show recent scheduled run history
synthadoc schedule history -w my-wiki
synthadoc schedule history --limit 50 -w my-wiki
```

**Cron expression format:** `minute  hour  day-of-month  month  day-of-week`

| Field | Range | Examples |
|-------|-------|---------|
| minute | 0–59 | `0` = on the hour |
| hour | 0–23 | `2` = 2 AM, `22` = 10 PM |
| day of month | 1–31 | `*` = every day |
| month | 1–12 | `*` = every month |
| day of week | 0–6 | `0` = Sunday, `1` = Monday |

Common schedules:

| Expression | Meaning |
|------------|---------|
| `0 2 * * *` | Every day at 2 AM |
| `0 22 * * *` | Every night at 10 PM |
| `0 3 * * 0` | Every Sunday at 3 AM |
| `0 */6 * * *` | Every 6 hours |
| `30 8 * * 1-5` | Weekdays at 8:30 AM |

### Routing

ROUTING.md maps wiki branches to page slugs so queries and ingest jobs are scoped to the relevant section of the wiki. Create it once from your existing `index.md`, then let Synthadoc maintain it automatically as new pages are added.

```bash
# Bootstrap ROUTING.md from current index.md branch structure (run once)
synthadoc routing init -w my-wiki

# Report dangling slugs (pages listed in ROUTING.md that no longer exist)
synthadoc routing validate -w my-wiki

# Auto-remove dangling slugs from ROUTING.md
synthadoc routing clean -w my-wiki
```

### Candidates staging

When staging is enabled, ingest writes new pages to `wiki/candidates/` for human review instead of the main wiki. Useful when you want to approve AI-generated pages before they become canonical.

```bash
# Show current staging policy
synthadoc staging policy -w my-wiki

# Route all new pages to staging (review everything)
synthadoc staging policy all -w my-wiki

# Only stage pages below a confidence threshold (auto-promote high-confidence)
synthadoc staging policy threshold --min-confidence high -w my-wiki

# Turn staging off (pages go directly to wiki/)
synthadoc staging policy off -w my-wiki

# List candidate pages awaiting review
synthadoc candidates list -w my-wiki

# Promote a specific page (moves it from candidates/ to wiki/)
synthadoc candidates promote my-page-slug -w my-wiki

# Promote all candidates at once
synthadoc candidates promote --all -w my-wiki

# Discard a specific candidate
synthadoc candidates discard my-page-slug -w my-wiki

# Discard all candidates
synthadoc candidates discard --all -w my-wiki
```

### Context packs

A context pack decomposes a goal into sub-questions, runs parallel BM25 searches, and packs the highest-scoring excerpts into a single cited Markdown document within a token budget.

**Typical use cases:**

- Paste into an external LLM chat (Claude.ai, ChatGPT) as grounded context before asking a question
- Save next to a document you are writing as a cited research brief
- Pipe into another CLI tool that reads Markdown

```bash
# Print to terminal — inspect, copy, or pipe
synthadoc context build "How did transistors change computing?" -w my-wiki

# Copy to clipboard and paste into an LLM chat (macOS)
synthadoc context build "early computing pioneers" -w my-wiki | pbcopy

# Custom token budget (default 4000)
synthadoc context build "Early programming languages" --tokens 8000 -w my-wiki

# Save next to a document you are writing
synthadoc context build "Rise of microprocessors" --output ~/drafts/computing-brief.md -w my-wiki
```

### Exporting

Export your wiki in machine-readable formats for RAG pipelines, LLM context windows, graph analysis tools, and OKF-compliant agents. All formats are assembled server-side with zero additional LLM calls. Requires `synthadoc serve` to be running.

```bash
# Active pages as LLM context (llms.txt spec)
synthadoc export --format llms.txt --status active -w my-wiki

# Full content dump with provenance footnotes preserved
synthadoc export --format llms-full.txt --output exports/wiki-full.txt -w my-wiki

# Export wikilink graph as GraphML — open in yEd, Gephi, or Cytoscape
synthadoc export --format graphml --output exports/wiki.graphml -w my-wiki

# Agent-ready JSON with provenance, lifecycle history, and compilation cost
synthadoc export --format json --output exports/wiki.json -w my-wiki

# OKF v0.1 bundle — consumable by any OKF-aware agent without code changes
# Write outside the wiki folder to avoid Obsidian picking up bundle files as source
synthadoc export --format okf --output ~/exports/my-wiki-okf/ -w my-wiki
```

**Flags:** `--format/-f` (required: `llms.txt`, `llms-full.txt`, `graphml`, `json`, `okf`), `--output/-o` (file path, or directory for `okf`; omit for stdout), `--status/-s` (`all`/`active`/`draft`/`stale`/`contradicted`/`archived`).

> **OKF export requires `--output`** — the bundle is a directory tree, not a single file.

> **OKF default pages:** `--format okf` with `--status all` (the default) includes only `active` and `contradicted` pages. Draft and stale are excluded — they carry unverified content. Contradicted pages appear with `status: contradicted` in their frontmatter and a `> **Contradiction:** …` blockquote in the body.

> **Tip:** Keep the OKF bundle **outside** your wiki folder. The output path can be any absolute or relative path — `--output ~/exports/my-wiki-okf/` or `--output ../okf-bundles/my-wiki/` both work. Placing it inside the wiki folder risks Obsidian or the ingestor picking up the bundle files as source documents.

In Obsidian: command palette → **Synthadoc: Export Wiki** — choose format and status filter, then click **Export**. For all formats except `okf`, the file is saved to the vault's `exports/` folder and opened automatically. For `okf`, the output path defaults to `~/exports/{vault-name}-okf-{date}/` outside the vault and is written via the filesystem. For GraphML, a **View Graph** button renders an inline preview.

### Backup & Restore

```bash
# Backup to the current directory
synthadoc backup -w my-wiki

# Backup to a specific directory, excluding raw source files to reduce size
synthadoc backup -w my-wiki --output ~/backups --no-sources

# Restore to the same folder as the zip (default)
synthadoc restore synthadoc-backup-my-wiki-20260624-103000.zip

# Restore under a different name to a specific location on a specific port
synthadoc restore backup.zip --name my-wiki-staging --target ~/wikis --port 7071
```

→ Flags, use-case table, what is and isn't backed up, and post-restore checklist: [Quick-Start Guide — Appendix J](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-j--backup--restore)

### Removing a wiki

Stop the server for that wiki before uninstalling — the serve process must not be running
when the directory is deleted.

```bash
# Stop the background server (PID is in <wiki-root>/.synthadoc/server.pid)
kill $(cat ~/wikis/my-wiki/.synthadoc/server.pid)          # Linux / macOS
taskkill /PID <pid> /F                                      # Windows

# Then uninstall — two-step confirmation required, no --yes escape
synthadoc uninstall my-wiki
```

For Obsidian plugin commands see [Appendix A — Obsidian Plugin Command Reference](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md#appendix-a--obsidian-plugin-commands) in the Quick-Start Guide.

---

## Administrative Reference

### Health and status

```bash
# Wiki statistics: pages, queue depth, cache hit rate
synthadoc status -w my-wiki

# Liveness probe (useful in scripts and monitoring)
# Port is per-wiki — check [server] port in <wiki-root>/.synthadoc/config.toml
# Default is 7070; each additional wiki uses its own port (7071, 7072, …)
curl http://127.0.0.1:7070/health
```

Expected `status` output:

```
Wiki:         /home/user/wikis/my-wiki
Pages:        34
  active         34
  draft           0
  stale           0
  contradicted    0
  archived        0
Jobs pending: 0
Jobs total:   12
```

### Logs

Synthadoc writes three log artefacts per wiki:

| File            | Location                          | Format                  | Use                                                                 |
| --------------- | --------------------------------- | ----------------------- | ------------------------------------------------------------------- |
| `log.md`        | `<wiki-root>/log.md`              | Human-readable Markdown | Read inside Obsidian; shows every ingest, contradiction, lint event |
| `synthadoc.log` | `<wiki-root>/.synthadoc/logs/`    | JSON lines (rotating)   | Structured debug/ops log; grep or pipe to jq                        |
| `audit.db`      | `<wiki-root>/.synthadoc/audit.db` | SQLite (append-only)    | Source hashes, cost records, job history                            |

**Tailing the JSON log:**

```bash
# Tail and pretty-print with jq
tail -f .synthadoc/logs/synthadoc.log | jq .

# Filter to errors only
tail -f .synthadoc/logs/synthadoc.log | jq 'select(.level == "ERROR")'

# Filter to a specific job
# job_id is present only on records logged in job context (ingest/lint workers)
tail -f .synthadoc/logs/synthadoc.log | jq 'select(.job_id == "abc123")'
```

**Log rotation:** When `synthadoc.log` reaches `max_file_mb`, it is renamed to `synthadoc.log.1`; the previous `.1` becomes `.2`; files beyond `backup_count` are deleted. Total disk ≈ `max_file_mb × (backup_count + 1)`.

**Changing log level at runtime:** Edit `[logs] level` in `.synthadoc/config.toml` and restart `synthadoc serve`. Or pass `--verbose` to get `DEBUG` for one session without editing config.

### Audit trail

```bash
synthadoc audit history -w my-wiki          # table: timestamp, source file, wiki page, tokens, cost
synthadoc audit history -n 100 -w my-wiki   # last 100 records (default 50)
synthadoc audit history --json -w my-wiki   # raw JSON for scripting

synthadoc audit cost -w my-wiki             # total tokens + daily breakdown, last 30 days
synthadoc audit cost --days 7 -w my-wiki    # weekly view
synthadoc audit cost --json -w my-wiki      # {total_tokens, total_cost_usd, daily: [...]}

synthadoc audit events -w my-wiki           # table: timestamp, job_id, event type, metadata
synthadoc audit events --json -w my-wiki    # raw JSON

synthadoc audit citations -w my-wiki                     # all claim citations (last 50)
synthadoc audit citations --page alan-turing -w my-wiki  # citations for one page
synthadoc audit citations --source turing.pdf -w my-wiki # citations from one source file
synthadoc audit citations --broken -w my-wiki            # validation failures only
synthadoc audit citations --json -w my-wiki              # raw JSON for scripting
```

> **Note:** Per-model cost tracking is live from v0.2.0 — pricing tables cover all 7 API providers. Token counts and USD cost are recorded for every ingest and query operation in `audit.db`.

> **Lifecycle transitions** are also recorded in `audit.db` — every state change (slug, from/to state, triggered_by, reason, timestamp) is permanently stored as an immutable audit event. Query the log with `synthadoc lifecycle log` or `GET /lifecycle/events`.

### Cache management

```bash
# Remove all cached LLM responses
# Output: "Cache cleared: N entries removed."
synthadoc cache clear -w my-wiki
```

Cache invalidation happens automatically when:

- A source file's SHA-256 hash changes (content changed)
- The internal cache version is bumped (after prompt template edits)
- `--force` is passed to ingest

### OpenTelemetry integration

By default, traces and metrics are written to `<wiki-root>/.synthadoc/logs/traces.jsonl`. To send to any OTLP backend (Jaeger, Grafana Tempo, Honeycomb, Datadog):

```toml
# ~/.synthadoc/config.toml
[observability]
exporter      = "otlp"
otlp_endpoint = "http://localhost:4317"
```

### Debugging

```bash
# Start server with DEBUG console logging
synthadoc serve -w my-wiki --verbose

# Check for configuration problems
synthadoc status -w my-wiki     # prints pre-flight warnings

# View recent job failures
synthadoc jobs list --status failed -w my-wiki
synthadoc jobs status <job-id> -w my-wiki    # shows error message + traceback

# Force a re-ingest to rule out cache issues
synthadoc ingest --force problem.pdf -w my-wiki
```

---

## Understanding Logs and the Audit Trail

Synthadoc writes three log artefacts per wiki: `log.md` (human-readable Markdown, open in Obsidian), `synthadoc.log` (JSON lines, rotate-by-size, grep with `jq`), and `audit.db` (append-only SQLite — source hashes, cost records, job history).

For the full field reference, log levels, rotation config, OTel integration, and audit query examples see [docs/design.md — Logs and Audit Trail](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#logs-and-audit-trail).

---

## Customization

Custom skills, LLM providers, hooks, cache control, and per-wiki AGENTS.md are documented in [docs/design.md — Customization](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#customization).

---

## Links

- Design document: [docs/design.md](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md)
- Customization: [docs/design.md — Customization](https://github.com/axoviq-ai/synthadoc/blob/main/docs/design.md#customization)
- Quick-Start Guide: [docs/user-quick-start-guide.md](https://github.com/axoviq-ai/synthadoc/blob/main/docs/user-quick-start-guide.md)
- GitHub: [axoviq-ai/synthadoc](https://github.com/axoviq-ai/synthadoc)
