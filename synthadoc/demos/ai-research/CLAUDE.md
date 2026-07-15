# CLAUDE.md — AI Research Wiki

This wiki is managed by [Synthadoc](https://github.com/axoviq-ai/synthadoc).
It covers: **AI Research**.

## Domain Guidelines
- Focus on AI/ML research: architectures, training methods, benchmarks, key papers, and researchers
- Summarize key claims, methods, and results — prioritize technical precision over breadth
- Cross-reference related concepts using [[page-name]] wikilink syntax
- When a source updates or refines a prior result, flag contradictions rather than silently overwriting
- Skip sources that are purely promotional, news aggregators, or outside AI/ML research scope

## Quick Reference

| Action | Command |
|---|---|
| Start server | `synthadoc serve -w <wiki>` |
| Check status | `synthadoc status -w <wiki>` |
| Ingest a file | `synthadoc ingest raw_sources/report.pdf -w <wiki>` |
| Ingest a URL | `synthadoc ingest https://example.com/article -w <wiki>` |
| Query | `synthadoc query "your question" -w <wiki>` |
| Run lint | `synthadoc lint run -w <wiki>` |
| View lint report | `synthadoc lint report -w <wiki>` |
| Export (LLM text) | `synthadoc export -f llms-full.txt -w <wiki>` |
| Export (JSON) | `synthadoc export -f json -w <wiki>` |
| Export (OKF bundle) | `synthadoc export -f okf -o ./export-dir -w <wiki>` |

Replace `<wiki>` with your wiki name (the directory name, not the domain).

## Server

The Synthadoc server must be running before any ingest, query, or lint operation.
Default address: `http://127.0.0.1:7070`

```bash
synthadoc serve -w <wiki>       # start (keep this terminal open)
synthadoc serve -w <wiki> -b    # start in background (logs go to wiki log file)
synthadoc status -w <wiki>      # verify it is running — shows active wiki and port
```

## Ingest

Source is a positional argument. Supported sources: local files (md, pdf, docx, pptx,
xlsx, csv, txt, png/jpg/webp), web URLs, YouTube video URLs, and agent session files (.jsonl).

```bash
# Local file
synthadoc ingest raw_sources/report.pdf -w <wiki>

# Web URL
synthadoc ingest https://example.com/article -w <wiki>

# YouTube video (transcript extracted automatically)
synthadoc ingest "https://www.youtube.com/watch?v=<id>" -w <wiki>

# Agent session history (Claude Code, Codex CLI, Cursor .jsonl files)
synthadoc ingest ~/.claude/projects/<hash>/<session>.jsonl -w <wiki>

# Ingest all files in a directory
synthadoc ingest raw_sources/ --batch -w <wiki>

# Re-ingest with a larger source window (when lint reports truncated sources)
synthadoc ingest raw_sources/report.pdf --force --max-source-chars 64000 -w <wiki>

# Analyse source without writing to wiki (dry-run)
synthadoc ingest raw_sources/report.pdf --analyse-only -w <wiki>
```

## Query

Streaming output is on by default. Use `--no-stream` for scripts or pipes.

```bash
synthadoc query "your question here" -w <wiki>          # streaming (default)
synthadoc query "your question here" --no-stream -w <wiki>   # blocking, pipe-safe
synthadoc query "your question here" --save -w <wiki>   # save answer as a wiki page
```

Answers include `^[source:line]` citation markers. Use only wiki content — do not
supplement with outside knowledge unless the wiki explicitly says it does not cover the topic.

## Lint

Run after major ingests or weekly to keep the wiki healthy:

```bash
synthadoc lint run -w <wiki>       # run a full lint pass (server must be running)
synthadoc lint report -w <wiki>    # show the latest report without running a new pass
```

Checks: orphan pages, dangling links, truncated sources, contradictions, adversarial
review, citation accuracy. Automatically archives pages whose source files have been deleted.
After archiving, cascade cleanup removes all `[[slug]]` links pointing to the archived page.

## Lifecycle

Slug is a positional argument. `--reason` is required for all transitions.

```bash
synthadoc lifecycle activate <slug> --reason "reviewed and verified" -w <wiki>
# draft → active

synthadoc lifecycle archive <slug> --reason "superseded by newer source" -w <wiki>
# active → archived (cascade cleanup removes all [[slug]] links)

synthadoc lifecycle restore <slug> --reason "re-opening for update" -w <wiki>
# archived → draft (ready for re-ingest and re-activation)

synthadoc lifecycle log -w <wiki>
# full audit trail of all lifecycle events
```

## Export

Server does **not** need to be running for export. Output defaults to stdout; use `-o`
to write to a file or directory.

```bash
# Plain text for LLM context windows (active pages only)
synthadoc export -f llms.txt -w <wiki>

# Full text with frontmatter included
synthadoc export -f llms-full.txt -o wiki-export.txt -w <wiki>

# Graph structure (import into Gephi, yEd, etc.)
synthadoc export -f graphml -o wiki-graph.graphml -w <wiki>

# JSON with full provenance and lifecycle metadata
synthadoc export -f json -o wiki-export.json -w <wiki>

# OKF bundle (Open Knowledge Format — interoperable with other tools)
synthadoc export -f okf -o ./okf-export/ -w <wiki>

# Export only active pages
synthadoc export -f llms-full.txt --status active -w <wiki>

# Export only pages in a named context pack
synthadoc export -f json --context-pack "Q3 Review" -w <wiki>
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
