---
title: Synthadoc Ingest Guide
keywords: [ingest, import, pdf, docx, pptx, xlsx, csv, markdown, txt, youtube, re-ingest, reingest, reprocess, manifest, rescan, png, jpg]
---

# Synthadoc Ingest Guide

## Everything You Can Ingest

Synthadoc accepts six categories of input — local files, images, web pages, YouTube videos, and web search results:

| Category | Supported formats / how to use |
|---|---|
| **Documents** | `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv` |
| **Images** | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff` |
| **Text / Markdown** | `.md`, `.txt` |
| **Web pages** | Any `http://` or `https://` URL |
| **YouTube videos** | YouTube URL — transcript is extracted automatically |
| **Web search** | Intent phrase: `search for: <topic>`, `find on the web: <topic>`, `look up: <topic>`, or `web search: <topic>` |

## Basic Ingest Commands

```bash
# Ingest a local file
synthadoc ingest path/to/document.pdf

# Ingest a web page
synthadoc ingest https://example.com/article

# Ingest a YouTube video (transcript extracted automatically)
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

## Re-ingesting a Source with --force

The `--force` flag bypasses deduplication and re-ingests a source even if it has not changed.

Basic syntax:

```bash
synthadoc ingest --force path/to/document.pdf
synthadoc ingest --force https://example.com/updated-article
```

Use `--force` when:
- The source file content has changed and you want to update the wiki page
- You want to reprocess a URL that was already ingested
- You suspect the cached analysis is stale

The `--force` flag works with all source types — local files, URLs, YouTube videos, and web search. It does not affect other jobs in the queue.

## Scheduled Ingest

Use the `schedule` command to run ingest automatically on a recurring basis:

```bash
synthadoc schedule add --cron "0 6 * * *" ingest --batch sources/
```

See `synthadoc schedule --help` for full options.
