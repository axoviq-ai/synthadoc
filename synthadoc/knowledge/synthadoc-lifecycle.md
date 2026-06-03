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

To manually promote a draft or stale page to active:

```bash
synthadoc lint run --scope lifecycle
```

Or re-ingest the source to trigger automatic promotion:

```bash
synthadoc ingest --force <source>
```

## Archiving a Page

Pages are archived automatically when their source becomes unavailable. To archive manually, edit the page frontmatter and set `status: archived`.

## Checking Lifecycle Health

```bash
# Show all stale pages
synthadoc lint run --scope stale

# Show all pages with contradictions
synthadoc lint run --scope contradictions
```
