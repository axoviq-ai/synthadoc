---
title: Synthadoc Export Guide
keywords: [export, llms, llms.txt, graphml, graphml export, json, okf, okf bundle, open knowledge format, download, context pack]
---

# Synthadoc Export Guide

Synthadoc can export your wiki in several formats for use with AI tools, graph analysis, or external processing.

## Export Formats

| Format | Flag | Description |
|---|---|---|
| **llms.txt** | `--format llms.txt` | Summary format: active pages + "Needs Review" section. Optimised for feeding to LLMs. |
| **llms-full.txt** | `--format llms-full.txt` | Complete page content including status, confidence, tags, and body. |
| **GraphML** | `--format graphml` | Directed graph where wikilinks are edges. Includes citation counts, routing branches, orphan/inbound-link metadata. Open in Gephi or yEd. |
| **JSON** | `--format json` | Full dump: pages, citations, lifecycle history, cost data, routing. |
| **OKF** | `--format okf` | [OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) bundle directory — one Markdown file per page, consumable by any OKF-aware agent without code changes. Requires `--output <directory>`. |

## Obsidian Plugin

Open the Command Palette (`Ctrl/Cmd+P`) → **Synthadoc: Export Wiki**.

The modal shows a format dropdown, an output path field (pre-filled with today's date and the correct extension), and a status filter. Click **Export**. For all formats except `okf`, the file is saved inside the vault and opened automatically. For `okf`, the output path defaults to `~/exports/{vault-name}-okf-{date}/` outside the vault.

When **GraphML** is selected, a **View Graph** button appears for an inline preview before saving.

## Basic Export Commands

```bash
# Export as llms.txt (default, prints to stdout)
synthadoc export --format llms.txt

# Export to a file
synthadoc export --format llms.txt --output wiki-export.txt

# Export full content
synthadoc export --format llms-full.txt --output wiki-full.txt

# Export as graph
synthadoc export --format graphml --output wiki-graph.graphml

# Export as JSON
synthadoc export --format json --output wiki-data.json

# Export as OKF v0.2 bundle (--output is required; must be a directory path)
synthadoc export --format okf --output ~/exports/my-wiki-okf/
```

## OKF Bundle Export

The `okf` format produces a directory tree that any [OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-aware agent or tool can read without knowing anything about Synthadoc. Each wiki page becomes a conformant Markdown file; `[[wikilinks]]` are rewritten to relative paths; an `index.md` groups pages by knowledge type.

```bash
# Active + contradicted pages (default — draft and stale excluded)
synthadoc export --format okf --output ~/exports/my-wiki-okf/

# Active pages only (cleanest trusted bundle)
synthadoc export --format okf --status active --output ~/exports/my-wiki-okf/
```

> **`--output` is required for OKF** — the bundle is a directory, not a single file.

> **Keep the bundle outside your wiki folder.** Files inside the vault are candidates for ingest; an OKF bundle contains derived Markdown that would be re-ingested as source material if left there.

## Filtering by Lifecycle State

Use `--status` to export only pages in a specific lifecycle state:

```bash
# Export only active pages
synthadoc export --format llms.txt --status active

# Export active and draft pages
synthadoc export --format llms.txt --status draft

# Export all pages regardless of state
synthadoc export --format llms-full.txt --status all
```

Valid status values: `all`, `active`, `draft`, `stale`, `contradicted`, `archived`.

## Context Packs

Export a named subset of pages defined as a context pack:

```bash
synthadoc export --format llms.txt --context-pack my-pack
```

Context packs are defined in your `ROUTING.md` file.
