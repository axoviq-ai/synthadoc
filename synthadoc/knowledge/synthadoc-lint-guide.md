---
title: Synthadoc Lint Guide
keywords: [lint, check, validate, quality, warning, contradiction, orphan, dangling, link, citation, adversarial, review, stale, lifecycle, url, broken]
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
