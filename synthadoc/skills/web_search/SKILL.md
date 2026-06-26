---
name: web_search
version: "1.0"
description: Search the web and ingest results as wiki pages
entry:
  script: scripts/main.py
  class: WebSearchSkill
triggers:
  extensions: []
  intents:
    - "search for"
    - "find on the web"
    - "look up"
    - "web search"
    - "browse"
    - "youtube"
    - "查找"
    - "搜索"
    - "网络搜索"
    - "在网上查"
    - "查一下"
requires:
  - tavily-python
author: axoviq.com
license: AGPL-3.0-or-later
---

# Web Search Skill

Accepts a natural language query, calls the Tavily AI search API, and
returns the top matching URLs. Your agent receives those URLs and decides
what to do with them — fetch each one, display them, pass them to another
skill, etc.

## Setup

**1. Install the dependency:**
```bash
pip install tavily-python
```

**2. Set your Tavily API key** (free tier: 1,000 searches/month — sign up at
https://tavily.com, no credit card required):
```bash
# macOS / Linux
export TAVILY_API_KEY="tvly-your-key-here"

# Windows (Command Prompt)
set TAVILY_API_KEY=tvly-your-key-here

# Windows (PowerShell)
$env:TAVILY_API_KEY = "tvly-your-key-here"
```

**3. Optional — cap the number of results** (default: 20):
```bash
export SYNTHADOC_WEB_SEARCH_MAX_RESULTS=10
```

## Standalone usage

```python
import asyncio
from synthadoc.skills.web_search.scripts.main import WebSearchSkill

skill = WebSearchSkill()

async def main():
    result = await skill.extract("search for: transformer architecture papers")
    urls = result.metadata["child_sources"]   # list[str] — top matching URLs
    query = result.metadata["query"]          # "transformer architecture papers"
    print(f"Found {len(urls)} URLs for '{query}':")
    for url in urls:
        print(" ", url)

asyncio.run(main())
```

`result.text` is always empty — the skill is a discovery step that returns
URLs, not page content. Pass the URLs to the `url` or `youtube` skill (or
your own HTTP client) to fetch content.

## Intent prefixes

The skill strips a leading intent phrase before sending the query to Tavily:

| Input | Query sent to Tavily |
|---|---|
| `search for: RAG evaluation` | `RAG evaluation` |
| `find on the web: LLM benchmarks` | `LLM benchmarks` |
| `look up quantum computing` | `quantum computing` |
| `youtube: Karpathy transformers` | `Karpathy transformers` (YouTube only) |
| `搜索: 深度学习架构` | `深度学习架构` |

YouTube-specific prefixes (`youtube:`, `search youtube:`, `youtube video:`,
etc.) restrict the Tavily search to `youtube.com` and `youtu.be`.

CJK intent phrases supported: 查找, 搜索, 网络搜索, 在网上查, 查一下

## Domain filtering

A built-in blocklist skips sites that block automated HTTP clients:
`reddit.com`, `medium.com`, `quora.com`, `twitter.com`/`x.com`,
`linkedin.com`, `wikipedia.org`, IEEE Xplore, ACM DL, and common
subscription-only academic publishers.

If `SYNTHADOC_WIKI_ROOT` is set, the skill also loads
`$SYNTHADOC_WIKI_ROOT/.synthadoc/blocked_domains.json` (a JSON array of
domain strings) to extend the blocklist at runtime.

## Scripts

- `scripts/main.py` — `WebSearchSkill`: intent parsing, domain filtering,
  returns `child_sources` in metadata
- `scripts/fetcher.py` — thin async wrapper around `AsyncTavilyClient`

## Assets

- `assets/search-providers.json` — search provider registry (currently Tavily)

## Using with full Synthadoc

When running inside Synthadoc, the Orchestrator reads `child_sources` from
the result metadata and automatically enqueues each URL as a separate ingest
job, which are then processed by the `url` or `youtube` skill. No additional
setup is required beyond the env vars above.
