---
title: Synthadoc Lint Guide
keywords: [lint, contradiction, orphan, dangling, citation, adversarial, stale, lifecycle, url]
---

# Synthadoc Lint Guide

The lint command checks your wiki for quality issues across six categories.

## The Six Lint Checks

| Check | What it detects |
|---|---|
| **Contradictions** | Pages flagged as contradicted because two sources conflict |
| **Orphan pages** | Pages with no inbound wikilinks (isolated knowledge nodes) |
| **Dangling links** | Broken `[[wikilinks]]` pointing to deleted or renamed pages |
| **Citation validation** | `^[file:L-L]` markers referencing invalid files or line ranges |
| **Adversarial review** | LLM pass that flags overstated claims or factual contradictions |
| **Lifecycle checks** | Detects stale pages, promotes drafts, archives unavailable sources |

## Obsidian Plugin and Web UI

**Obsidian (run lint):** Open the Command Palette (`Ctrl/Cmd+P`) → **Synthadoc: Lint: run…**. A panel opens where you can toggle individual checks (contradictions, orphans, dangling links, adversarial review, lifecycle) and click **Run**. Progress streams into the panel as checks complete.

**Obsidian (view report):** Open the Command Palette → **Synthadoc: Lint: report**. The modal shows the current issues with action buttons — resolve contradictions, link orphans, or repair citations without leaving Obsidian.

**Web UI:** In the web chat, type: `"run lint and show me the report"`. Synthadoc runs all checks and returns a summary with per-category counts and affected page slugs.

## Running Lint

```bash
# Run all checks
synthadoc lint run

# Run a specific check only
synthadoc lint run --scope contradictions
synthadoc lint run --scope orphans
synthadoc lint run --scope stale
synthadoc lint run --scope all
```

## Check Details

### Contradictions
Pages flagged as contradicted during ingest because two sources conflict. Use `--auto-resolve` to attempt automatic merging:

```bash
synthadoc lint run --scope contradictions --auto-resolve
```

### Orphan Pages
Pages with no inbound wikilinks from other pages. These are isolated knowledge nodes that may be missing connections. Index, overview, dashboard, and log pages are excluded.

### Dangling Links
Broken `[[wikilinks]]` that point to deleted or renamed pages.

### Citation Validation
Checks that all `^[file:L-L]` citation markers reference valid files and line ranges.

### Adversarial Review
An LLM pass that flags overstated claims or factual contradictions within page content. Runs by default; skip with `--no-adversarial`.

### Lifecycle Checks
- Detects stale pages (source file hash changed or URL past freshness threshold)
- Promotes draft pages to active when they pass all checks
- Archives pages whose source files are deleted or URLs return 404/410
- Optionally validates source URLs via HTTP HEAD with `--check-urls`

Skip lifecycle checks with `--no-lifecycle`.

**Note:** `lint run --scope stale` detects new staleness but does **not** resolve pages already marked stale. To resolve a stale page, re-ingest its source file: `synthadoc ingest raw_sources/<file>`. Lint will then promote the re-ingested draft to active.

## Useful Flags

| Flag | Description |
|---|---|
| `--auto-resolve` | Attempt to auto-merge contradicted pages |
| `--no-adversarial` | Skip the LLM adversarial review pass |
| `--no-lifecycle` | Skip draft/stale/archived detection |
| `--check-urls` | Validate source URLs via HTTP HEAD requests |
| `-w / --wiki` | Specify wiki name or path |

## Viewing Current Issues (No Server Required)

To see a report of current contradictions and orphan pages without running a full lint job:

```bash
synthadoc lint report
```
