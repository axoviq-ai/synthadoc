---
title: Synthadoc Ingest Guide
keywords: [ingest, source, import, file, format, type, pdf, docx, pptx, xlsx, csv, markdown, txt, url, youtube, web, search, batch, bulk, force, schedule, manifest, rescan]
---

# Synthadoc Ingest Guide

## Supported File Types

Synthadoc can ingest the following local file formats:

- **Documents**: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`
- **Images**: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`
- **Text and Markdown**: `.md`, `.txt`

## Supported Web Sources

- **HTTP/HTTPS URLs** — any public web page
- **YouTube videos** — Synthadoc extracts the transcript automatically
- **Web search queries** — use intent phrases: `search for: <topic>`, `find on the web: <topic>`, `look up: <topic>`, or `web search: <topic>`

## Basic Ingest Commands

```bash
# Ingest a single file
synthadoc ingest path/to/document.pdf

# Ingest a URL
synthadoc ingest https://example.com/article

# Ingest a YouTube video
synthadoc ingest https://www.youtube.com/watch?v=VIDEO_ID

# Web search ingest
synthadoc ingest "search for: history of computing"
```

## Batch and Bulk Ingest

```bash
# Ingest an entire directory of files
synthadoc ingest --batch path/to/folder/

# Ingest from a manifest file (one URL/path per line)
synthadoc ingest --file sources.txt
```

A manifest file can mix file paths, URLs, YouTube links, and intent phrases — one per line.

## Useful Flags

| Flag | Description |
|---|---|
| `--force` | Bypass deduplication and re-ingest even if the source is unchanged |
| `--analyse-only` | Run analysis without writing wiki pages (dry run) |
| `--max-results N` | Limit web search results (default: 20) |
| `-w / --wiki` | Specify wiki name or path |

## Re-ingesting a Source

To re-ingest a source whose content has changed:

```bash
synthadoc ingest --force https://example.com/updated-article
```

## Scheduled Ingest

Use the `schedule` command to run ingest automatically on a recurring basis:

```bash
synthadoc schedule add --cron "0 6 * * *" ingest --batch sources/
```

See `synthadoc schedule --help` for full options.
