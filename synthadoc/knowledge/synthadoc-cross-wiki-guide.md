---
title: Synthadoc Cross-Wiki Guide
keywords: [cross-wiki, cross wiki, federation, multi-wiki, multiple wikis, cross-wiki query, cross wiki query, wiki federation, routing, CROSS_WIKI_ROUTING, cross-wiki routing, wiki-name, citation pills, globe toggle, fan-out, coordinator wiki]
---

# Synthadoc Cross-Wiki Guide

Cross-wiki queries let you ask a single question across multiple Synthadoc wikis and receive one unified, synthesised answer. The coordinator automatically routes the question to relevant wikis and merges results.

---

## Prerequisites

You need at least two wikis installed and registered. Each wiki is automatically registered when you run `synthadoc install`:

```bash
synthadoc install finance-wiki --target ~/wikis
synthadoc install legal-wiki   --target ~/wikis
```

Use `--template <category/domain>` to apply a domain-specific starter (run `synthadoc templates list` to browse all 30 available templates).

---

## Step 1 — Start the servers

Cross-wiki queries fan out only to **running** wikis. Start the wikis you want to include:

```bash
# Start all registered wikis in the background
synthadoc serve --all                    # one at a time, stops before ~60% memory use
synthadoc serve --all --max-memory 6GB   # cap total memory of started wikis (unit required)

# Or start specific wikis only
synthadoc serve -w finance-wiki --background
synthadoc serve -w legal-wiki   --background
```

Check which wikis are running:

```bash
synthadoc status --all
# Example output:
# wiki           port   status    pages
# finance-wiki   7070   running   142
# legal-wiki     7071   running    38
# ops-wiki       7072   stopped    —
```

A wiki showing `stopped` cannot be queried until started.

---

## Step 2 — Run a cross-wiki query

```bash
# CLI — from any registered wiki
synthadoc query --cross-wiki "What are our M&A covenants and deployment runbooks?" -w finance-wiki

# Web UI — open the chat for any wiki, then click the 🌐 globe toggle
synthadoc web -w finance-wiki
```

The `-w` flag identifies the **coordinator** wiki (any registered wiki works). The `--cross-wiki` flag fans the question out across all running registered wikis.

### Web UI

1. Open `synthadoc web -w <any-wiki>`
2. Click the **🌐 globe toggle** at the right end of the input bar to enable cross-wiki mode (your choice persists between sessions)
3. A narrow context bar above the conversation shows which wikis will be queried; after the response it shows which responded and which (if any) were offline

---

## Step 3 — Reading citation pills

Cross-wiki answers use a two-part citation format: `[[wiki-name::PageTitle]]`

```
[[finance-wiki::Valuation Methods]]
[[legal-wiki::NDA Template]]
```

In the web UI these render as two-part pills: `[wiki-name]  Page Title`. In the CLI output they appear as inline wikilink syntax.

---

## Step 4 — Configuring routing (optional)

By default the coordinator selects relevant wikis automatically using the LLM and each wiki's `purpose.md` summary. For predictable, keyword-driven routing create an override file:

```bash
# Generate the routing file from your registry
synthadoc cross-wiki routing init

# Print current contents
synthadoc cross-wiki routing show

# Open in $EDITOR
synthadoc cross-wiki routing edit
```

The file lives at `~/.synthadoc/CROSS_WIKI_ROUTING.md`. Example:

```markdown
## finance
wikis: finance-wiki, banking-wiki
keywords: M&A, covenant, valuation, investment

## legal
wikis: legal-wiki
keywords: contract, NDA, compliance, regulatory

## default
wikis: finance-wiki, legal-wiki, ops-wiki
keywords:
```

The first section whose `keywords:` list contains a word from the query is used; if none match, the `default` section applies. When the file is absent the system falls back to LLM auto-routing.

---

## When a wiki is offline

The answer is still synthesised from the available wikis. The context bar (web UI) or stderr (CLI) shows which wikis were offline:

```
🌐 Searched: finance-wiki · legal-wiki  ·  ⚠ ops-wiki offline
```

To restore a stopped wiki:

```bash
synthadoc serve -w ops-wiki --background
synthadoc status --all
```

Then re-run your query.

---

## Common questions

**Q: Can I limit which wikis are queried?**
Start only the wikis you want to include — stopped wikis are excluded automatically. Or add a named routing rule in `CROSS_WIKI_ROUTING.md` that routes your topic keywords to a specific subset.

**Q: Can I use cross-wiki from the Obsidian plugin?**
Not directly — the Obsidian plugin queries one wiki at a time. Use `synthadoc web` or the CLI `--cross-wiki` flag for cross-wiki queries.

**Q: Does cross-wiki work with the MCP server?**
Yes — the `synthadoc_query` MCP tool accepts a `cross_wiki: true` parameter that fans the question across running registered wikis.
