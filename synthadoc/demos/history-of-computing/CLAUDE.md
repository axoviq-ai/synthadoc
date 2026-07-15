# CLAUDE.md — History of Computing Wiki

This wiki is managed by [Synthadoc](https://github.com/axoviq-ai/synthadoc).
It covers: **History of Computing**.

## Domain Guidelines
- Summarize key claims, dates, and chronological context from each source
- Cross-reference related figures, architectures, and eras using [[page-name]] wikilink syntax
- Flag contradictions between sources — especially conflicting attribution or dates — with ⚠ markers
- Preserve temporal precision: dates and "first" claims are load-bearing facts in this domain

## Quick Reference

| Action | Command |
|---|---|
| Start server | `synthadoc serve -w <wiki>` |
| Check status | `synthadoc status` |
| Ingest a file | `synthadoc ingest --source <path> -w <wiki>` |
| Ingest a URL | `synthadoc ingest --source https://... -w <wiki>` |
| Query | `synthadoc query "your question" -w <wiki>` |
| Run lint | `synthadoc lint run -w <wiki>` |
| Export wiki | `synthadoc export --format llms-full -w <wiki>` |

Replace `<wiki>` with your wiki name (the directory name, not the domain).

## Server

The Synthadoc server must be running before any ingest, query, or lint operation.
Default address: `http://127.0.0.1:7070`

```bash
synthadoc serve -w <wiki>   # start (keep this terminal open)
synthadoc status             # verify it is running — shows active wiki and port
```

## Ingest

Supported sources: local files (md, pdf, docx, pptx, xlsx, csv, txt, png/jpg/webp),
web URLs, YouTube video URLs, and agent session files (.jsonl).

```bash
# Local file
synthadoc ingest --source raw_sources/report.pdf -w <wiki>

# Web URL
synthadoc ingest --source https://example.com/article -w <wiki>

# YouTube video (transcript extracted automatically)
synthadoc ingest --source "https://www.youtube.com/watch?v=<id>" -w <wiki>

# Agent session history (Claude Code, Codex CLI, Cursor .jsonl files)
synthadoc ingest --source ~/.claude/projects/<hash>/<session>.jsonl -w <wiki>

# Re-ingest with a larger source window (when lint reports truncated sources)
synthadoc ingest --source <path> --force --max-source-chars 64000 -w <wiki>

# Analyse source without writing to wiki (dry-run)
synthadoc ingest --source <path> --analyse-only -w <wiki>
```

## Query

```bash
synthadoc query "your question here" -w <wiki>
synthadoc query --stream "your question" -w <wiki>   # streaming output
```

Answers include `^[source:line]` citation markers. Use only wiki content — do not
supplement with outside knowledge unless the wiki explicitly says it does not cover the topic.

## Lint

Run after major ingests or weekly to keep the wiki healthy:

```bash
synthadoc lint run -w <wiki>
```

Checks: orphan pages, dangling links, truncated sources, contradictions, adversarial
review, citation accuracy. Automatically archives pages whose source files have been deleted.
After archiving, cascade cleanup removes all `[[slug]]` links pointing to the archived page.

## Lifecycle

```bash
synthadoc lifecycle activate --slug <slug> -w <wiki>   # draft → active
synthadoc lifecycle archive  --slug <slug> -w <wiki>   # active → archived (cascade cleanup runs)
synthadoc lifecycle restore  --slug <slug> -w <wiki>   # archived → active
synthadoc lifecycle log      -w <wiki>                  # full audit trail
```

## Page Schema

Every wiki page has YAML frontmatter:

```yaml
title: "Page Title"
status: active        # draft | active | stale | archived
confidence: high      # high | medium | low
type: concept         # concept | person | event | technology | organization | place
sources:
  - file: raw_sources/report.pdf
    hash: <sha256>
    ingested: "2026-07-15"
```

Cross-link related pages with `[[slug]]` syntax. Slugs are kebab-case filenames without `.md`.

## MCP Tools

When Synthadoc is connected as an MCP server the following tools are available:

| Tool | Purpose |
|---|---|
| `synthadoc_query` | Ask a question; returns a cited answer |
| `synthadoc_ingest` | Add a source document or URL |
| `synthadoc_search` | Full-text search across wiki pages |
| `synthadoc_context` | Build a context pack for a topic |
| `synthadoc_write` | Create or update a page directly |
| `synthadoc_lifecycle` | Transition a page's lifecycle state |
| `synthadoc_lint_run` | Run a lint pass |
| `synthadoc_lint_report` | Retrieve the latest lint report |
| `synthadoc_jobs` | List recent jobs and their status |
| `synthadoc_status` | Check server and wiki status |
| `synthadoc_export` | Export wiki in various formats |
| `synthadoc_graph` | Retrieve the knowledge graph |
