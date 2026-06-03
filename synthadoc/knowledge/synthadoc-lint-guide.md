---
title: Synthadoc Lint Guide
keywords: [lint, check, validate, quality, warning, contradiction, orphan, dangling, link, citation, adversarial, review, stale, lifecycle, url, broken]
---

# Synthadoc Lint Guide

The lint command checks your wiki for quality issues across six categories.

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

## What Lint Checks

### 1. Contradictions
Pages flagged as contradicted during ingest because two sources conflict. Use `--auto-resolve` to attempt automatic merging:

```bash
synthadoc lint run --scope contradictions --auto-resolve
```

### 2. Orphan Pages
Pages with no inbound wikilinks from other pages. These are isolated knowledge nodes that may be missing connections. Index, overview, dashboard, and log pages are excluded.

### 3. Dangling Links
Broken `[[wikilinks]]` that point to deleted or renamed pages.

### 4. Citation Validation
Checks that all `^[file:L-L]` citation markers reference valid files and line ranges.

### 5. Adversarial Review
An LLM pass that flags overstated claims or factual contradictions within page content. Runs by default; skip with `--no-adversarial`.

### 6. Lifecycle Checks
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

## Viewing Lint History

```bash
synthadoc lint history
```
