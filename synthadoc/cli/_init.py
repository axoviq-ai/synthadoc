# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from pathlib import Path

_AGENT_INSTRUCTION_BODY = """\
This wiki is managed by [Synthadoc](https://github.com/axoviq-ai/synthadoc).
It covers: **{domain}**.

## Domain Guidelines
{guidelines}

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
Default address: `http://127.0.0.1:{port}`

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
"""

_DEFAULT_GUIDELINES = """\
- Summarize key claims and findings from each source
- Cross-link related concepts using [[page-name]] wikilink syntax
- Maintain consistent terminology across pages
- Flag contradictions between sources with ⚠ markers\
"""

_AGENTS_MD = "# AGENTS.md — {domain} Wiki\n\n" + _AGENT_INSTRUCTION_BODY
_CLAUDE_MD = "# CLAUDE.md — {domain} Wiki\n\n" + _AGENT_INSTRUCTION_BODY
_GEMINI_MD = "# GEMINI.md — {domain} Wiki\n\n" + _AGENT_INSTRUCTION_BODY

_CONFIG_TOML = """\
# synthadoc per-project configuration

[wiki]
domain = "{domain}"

[server]
port = {port}  # change this if running multiple wikis simultaneously
# host = "0.0.0.0"  # bind to all interfaces — no built-in auth, restrict via firewall
# job_timeout_seconds = 600  # max seconds a single job runs before being killed (default: 600)

[agents]
default = {{ provider = "gemini", model = "gemini-2.5-flash-lite" }}
# Alternatives (uncomment and restart to switch):
# default = {{ provider = "gemini",    model = "gemini-2.5-flash" }}         # free tier: 10 RPM / 250 RPD
# default = {{ provider = "gemini",    model = "gemini-1.5-flash" }}         # free tier: 15 RPM / 1,500 RPD
# default = {{ provider = "minimax",   model = "MiniMax-M2.5" }}             # paid, cheapest text-only ($0.15/M in)
# default = {{ provider = "minimax",   model = "MiniMax-M3",  thinking = "disabled" }}  # paid, M3 with thinking off (faster, cheaper)
# default = {{ provider = "groq",      model = "llama-3.3-70b-versatile" }}  # free tier, 100K tokens/day
# default = {{ provider = "anthropic", model = "claude-sonnet-4-6" }}        # paid, high quality
# default = {{ provider = "anthropic", model = "claude-opus-4-8" }}          # paid, highest quality (most capable)
# default = {{ provider = "deepseek",  model = "deepseek-chat" }}             # paid, very cheap ($0.14/M in); text-only, no vision
# default = {{ provider = "ollama",    model = "llama3.2" }}                  # fully local, no API key; requires GPU — CPU-only is too slow for interactive use
# default = {{ provider = "qwen",      model = "qwen-plus" }}                 # DashScope cloud API — set QWEN_API_KEY (https://bailian.console.aliyun.com/)
# default = {{ provider = "claude-code" }}                                    # no API key — uses your Claude Code subscription
# default = {{ provider = "opencode" }}                                       # no API key — uses your Opencode subscription
#
# LLM call timeout — useful for reasoning models (e.g. MiniMax-M2.5, MiniMax-M3 with thinking enabled) that can
# spend 2+ minutes on a single prompt and return an empty response instead of
# raising an error.  Setting this causes synthadoc to fail fast with a clear
# log message so you know to adjust the model or prompt size.
# 0 = no limit (provider default).  Restart the server after changing.
# llm_timeout_seconds = 90
#
# Output token budget for the scaffold JSON generated at the start of each ingest.
# Raise if ingest fails with "unparseable scaffold JSON" on wikis with many pages
# or very long agents_guidelines / purpose fields.
scaffold_max_tokens = 32768
#
# Output token budget for query synthesis (the answer returned to the user).
# Raise if answers are cut off mid-sentence with long-context reasoning models.
query_max_tokens = 8192

[ingest]
max_pages_per_ingest = 15
# Citation pass (Pass 4) tuning — these two settings work together:
#   citation_source_lines — how many lines of the source the LLM sees when placing ^[...] markers.
#                           Increase if lint reports out_of_range on long sources (transcripts, PDFs).
#   citation_max_tokens   — output token budget for the annotated section returned by the LLM.
#                           Increase if you raise citation_source_lines and have long wiki sections.
citation_source_lines = 400
citation_max_tokens = 8192

[cost]
soft_warn_usd = 0.50
hard_gate_usd = 2.00

[logs]
# Console log level shown in the terminal when running 'synthadoc serve'.
# DEBUG | INFO | WARNING | ERROR  (default: INFO)
level = "INFO"

# Rotating log file settings for .synthadoc/logs/synthadoc.log
# max_file_mb  — size limit per file before rotation (default: 5 MB)
# backup_count — number of rotated files to keep, so total ≈ max_file_mb × backup_count
#                e.g. 5 MB × 5 = ~25 MB maximum on disk
max_file_mb  = 5
backup_count = 5

[lint]
# Maximum number of adversarial concerns flagged per page (default: 2).
# Raise to 3-5 for a more thorough review; lower to 1 for a tighter signal-to-noise ratio.
adversarial_max_per_page = 2
# Maximum number of pages reviewed concurrently during adversarial pass (default: 8).
# Lower to 2-4 on free-tier or rate-limited LLM providers; raise to 16+ on paid tiers.
adversarial_concurrency = 8

[search]
vector = false             # set to true to enable semantic re-ranking (downloads ~130 MB model once)
vector_top_candidates = 20

[chat]
# Number of recent conversation turns kept in memory for multi-turn queries (0 = disabled).
conversation_history_turns = 5
# Days before inactive sessions are pruned from the audit log.
session_retention_days = 30
# How many assistant turns to scan back to find an open clarify context.
# Increase if users pick chips from a long multi-step clarify list; lower to
# avoid routing unrelated follow-ups through the action agent.
# clarify_lookback = 5
"""

_GITIGNORE = ".synthadoc/\n__pycache__/\n*.pyc\n.env\n"

_PURPOSE_MD = """\
# Wiki Purpose

This wiki covers: {domain}.

Include: topics directly related to {domain}.
Also accepted: AI coding session transcripts (.jsonl files from Claude Code, Codex, Cursor).
Exclude: unrelated domains. When in doubt, ingest and review.
"""

_DASHBOARD_MD = """\
---
title: Dashboard
tags: [dashboard]
status: active
confidence: high
created: '{created}'
sources: []
---

# {domain} — Dashboard

> Requires the **Dataview** community plugin (Settings → Community plugins → Browse → "Dataview").

---

## Contradicted pages — need review

```dataview
TABLE dateformat(created, "MMM dd, yyyy HH:mm:ss") AS "Created", status, confidence
FROM "wiki"
WHERE status = "contradicted"
SORT created DESC
```

*These pages were flagged during ingest as conflicting with a newer source.
Open each one, resolve the conflict, then change `status` to `active`.*

---

## Orphan pages — no inbound links

```dataview
TABLE dateformat(created, "MMM dd, yyyy HH:mm:ss") AS "Created", status
FROM "wiki"
WHERE orphan = true
SORT created DESC
```

*These pages exist but nothing links to them.
Orphan status is set by `synthadoc lint run` — run it first to populate this list.
Add `[[page-name]]` to a related content page to integrate it into the graph.*

---

## Recently added

```dataview
TABLE dateformat(created, "MMM dd, yyyy HH:mm:ss") AS "Added", status, confidence
FROM "wiki"
WHERE file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT created DESC
LIMIT 10
```

---

## Recently updated

```dataview
TABLE dateformat(date(updated), "MMM dd, yyyy HH:mm:ss") AS "Updated", status, confidence
FROM "wiki"
WHERE updated
  AND file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT date(updated) DESC
LIMIT 10
```

*Pages that have been re-ingested with new source material since their initial creation.*

---

## Recently archived

```dataview
TABLE dateformat(file.mtime, "MMM dd, yyyy HH:mm:ss") AS "Archived", confidence
FROM "wiki"
WHERE status = "archived"
SORT file.mtime DESC
LIMIT 10
```

*Pages retired from active use. To restore a page, change `status` back to `active`.*
"""


def init_wiki(root: Path, domain: str = "General", port: int = 7070) -> None:
    from datetime import date
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "raw_sources").mkdir(exist_ok=True)
    (root / "hooks").mkdir(exist_ok=True)
    (root / ".synthadoc" / "logs").mkdir(parents=True, exist_ok=True)
    (root / ".obsidian").mkdir(exist_ok=True)
    (root / ".obsidian" / "app.json").write_text(
        '{\n  "userIgnoreFilters": [\n    "raw_sources"\n  ]\n}\n',
        encoding="utf-8", newline="\n")
    _skill_file_kwargs = dict(domain=domain, guidelines=_DEFAULT_GUIDELINES, port=port)
    (root / "AGENTS.md").write_text(
        _AGENTS_MD.format(**_skill_file_kwargs), encoding="utf-8", newline="\n")
    (root / "CLAUDE.md").write_text(
        _CLAUDE_MD.format(**_skill_file_kwargs), encoding="utf-8", newline="\n")
    (root / "GEMINI.md").write_text(
        _GEMINI_MD.format(**_skill_file_kwargs), encoding="utf-8", newline="\n")
    (root / "wiki" / "index.md").write_text(
        "# Index\n\n", encoding="utf-8", newline="\n")
    (root / "wiki" / "purpose.md").write_text(
        _PURPOSE_MD.format(domain=domain), encoding="utf-8", newline="\n")
    (root / "wiki" / "dashboard.md").write_text(
        _DASHBOARD_MD.format(domain=domain, created=date.today().isoformat()),
        encoding="utf-8", newline="\n")
    (root / "log.md").write_text(
        "# Activity Log\n\n", encoding="utf-8", newline="\n")
    (root / ".synthadoc" / "config.toml").write_text(
        _CONFIG_TOML.format(domain=domain, port=port),
        encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text(_GITIGNORE, encoding="utf-8", newline="\n")
