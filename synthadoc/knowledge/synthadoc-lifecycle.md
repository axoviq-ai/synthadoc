---
title: Synthadoc Lifecycle States
keywords: [lifecycle, status, state, active, stale, archive, archived, draft, candidate, candidates, contradicted, contradictions, outdated, review, promote, transition]
---

# Synthadoc Lifecycle States

Every wiki page moves through a five-state lifecycle. Transitions are logged in the audit trail with the trigger source (ingest, lint, user, or manual edit).

## The Five States

| State | Meaning |
|---|---|
| **draft** | Newly created or re-ingested after going stale. Awaiting lint review. |
| **active** | Lint passed. Primary content state — included in exports and query results. |
| **contradicted** | Flagged during ingest or lint due to conflicting source material. |
| **stale** | Source file has changed (hash mismatch) or URL has not been re-ingested beyond the freshness threshold. |
| **archived** | Source file deleted or URL unavailable (404/410). Page is kept but excluded from active exports. |

## How Pages Transition

- **draft → active**: Lint passes with no issues
- **active → stale**: Source file hash changes, or URL exceeds freshness threshold
- **active/stale → archived**: Source file deleted or URL returns 404/410
- **contradicted → active**: Lint auto-resolve merges conflicting content

## Candidates Staging

Before a source is turned into a wiki page, it passes through candidates staging:

- The ingest agent scores and ranks candidate extracts from the source
- Only high-quality, in-scope candidates are promoted to wiki pages
- Candidates can be reviewed with `synthadoc candidates list`

## Marking a Page as Active

**Option 1 — Direct CLI promotion (single page):**

```bash
synthadoc lifecycle activate PAGE_SLUG --reason "manual review passed"
```

This immediately moves the named page from draft (or stale) to active. The `--reason` flag is required.

**Option 2 — Promote all drafts at once via lint:**

```bash
synthadoc lint run --scope lifecycle
```

Runs lifecycle checks across the whole wiki and promotes any draft or stale pages that pass.

**Option 3 — Re-ingest the source (automatic promotion):**

```bash
synthadoc ingest --force PATH_OR_URL
```

Re-ingesting the source triggers an automatic lint pass. If the page passes, it transitions from draft to active automatically.

## Archiving a Page

Pages are archived automatically when their source becomes unavailable. To archive manually, edit the page frontmatter and set `status: archived`.

## Checking Lifecycle Health

For a quick overview of all lifecycle state counts at once, use the status command:

```bash
synthadoc status
```

This prints a summary like:

```
Page lifecycle:
  draft          3  <- run `synthadoc lint run` to promote
  active         42
  stale          5  <- re-ingest needed
  contradicted   2  <- review required
  archived       1
```

To find and act on specific states:

```bash
# List stale pages and schedule re-ingest
synthadoc lint run --scope stale

# List contradicted pages needing review
synthadoc lint run --scope contradictions

# Promote drafts / re-check stale pages
synthadoc lint run --scope lifecycle

# Show lifecycle event history for all pages (transitions log)
synthadoc lifecycle log

# Filter history by state — shows which pages entered that state and when
synthadoc lifecycle log --state stale
synthadoc lifecycle log --state archived
synthadoc lifecycle log --state contradicted
synthadoc lifecycle log --state active
synthadoc lifecycle log --state draft

# Limit output
synthadoc lifecycle log --state stale --limit 20

# History for a single page
synthadoc lifecycle log <slug>
```
