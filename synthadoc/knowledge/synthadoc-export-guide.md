---
title: Synthadoc Export Guide
keywords: [export, llms, llms.txt, graphml, graphml export, json, download, context pack]
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
```

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
