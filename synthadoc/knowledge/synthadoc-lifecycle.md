---
title: Synthadoc Lifecycle States
keywords: [lifecycle, status, stale, archive, archived, draft, contradicted, contradictions, activate, restore]
---

# Synthadoc Lifecycle States

Every wiki page moves through a five-state lifecycle. Transitions are logged in the audit trail with the trigger source (ingest, lint, user, or manual edit).

## The Five States

| State | Meaning |
|---|---|
| **draft** | Newly created or re-ingested after going stale. Awaiting lint review. |
| **active** | Lint passed. Primary content state — included in exports and query results. |
| **contradicted** | Flagged during ingest or lint due to conflicting source material. |
| **stale** | Source file has changed (hash mismatch) or URL has not been re-ingested beyond the freshness threshold. Re-ingest the source file to resolve. |
| **archived** | Excluded from active exports and query results. Page content is retained. |

## How Pages Transition Automatically

- **draft → active**: Lint passes with no issues
- **active → stale**: Source file hash changes, or URL exceeds freshness threshold
- **active/stale/draft → archived**: Source file deleted or URL returns 404/410 (requires `--check-urls`)
- **contradicted → active**: Lint auto-resolve merges conflicting content

## Manually Transitioning Pages

### Via the web UI chat

Ask naturally — no page name required. Synthadoc will present matching pages as clickable chips:

```
"Archive an active page"
"Activate a draft page"
"Restore an archived page"
```

To target a specific page, include the slug or title:

```
"Archive the alan-turing page"
"Activate alan-turing"
```

### Via the CLI

```bash
# Promote a draft page to active
synthadoc lifecycle activate <slug> --reason "manual review passed"

# Archive a page
synthadoc lifecycle archive <slug> --reason "source removed"

# Restore an archived page to draft
synthadoc lifecycle restore <slug> --reason "source re-added"
```

The `--reason` flag is required for all three commands. All commands require `synthadoc serve` to be running.

## Resolving Stale Pages

A stale page means its source file has changed on disk since it was last ingested. Running `synthadoc lint run --scope stale` only **detects** new staleness — it does not resolve pages that are already stale.

To resolve a stale page:

1. **Re-ingest the source file** — this updates the hash, resets the page to draft, and lint will then promote it to active:
   ```bash
   synthadoc ingest raw_sources/<source-file>
   synthadoc lint run
   ```

2. **Or manually activate it** (if the source content is unchanged and you trust the current page):
   ```bash
   synthadoc lifecycle activate <slug> --reason "source unchanged, manual confirm"
   ```

## Running Lifecycle Checks Automatically

Lifecycle checks run as part of the default lint pass:

```bash
# Full lint — runs stale/archive detection, draft promotion, and all other checks
synthadoc lint run

# Stale and archive detection only — detects NEW stale pages, does not resolve existing ones
synthadoc lint run --scope stale

# Skip lifecycle checks entirely
synthadoc lint run --no-lifecycle

# Also validate URL sources via HTTP HEAD (adds network calls)
synthadoc lint run --check-urls
```

## Checking Lifecycle Health

For a quick overview of all lifecycle state counts:

```bash
synthadoc status
```

Output:

```
Page lifecycle:
  draft          3  <- run `synthadoc lint run` to promote
  active         42
  stale          5  <- re-ingest source file to resolve (see "Resolving Stale Pages" above)
  contradicted   2  <- review required
  archived       1
```

## Viewing Lifecycle Event History

```bash
# Show all lifecycle events (all pages)
synthadoc lifecycle log

# Filter by state — shows which pages entered that state and when
synthadoc lifecycle log --state stale
synthadoc lifecycle log --state archived
synthadoc lifecycle log --state contradicted
synthadoc lifecycle log --state active
synthadoc lifecycle log --state draft

# History for a single page
synthadoc lifecycle log <slug>

# Limit output
synthadoc lifecycle log --state stale --limit 20
```
