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
returns the top matching URLs as child sources. The IngestAgent fans those
URLs out as individual ingest jobs; each URL is then fetched and compiled
into a wiki page by the url or youtube skill.

## Status

**Implemented.** Requires `TAVILY_API_KEY` (free tier: 1000 searches/month —
sign up at https://tavily.com).

Set the key before running:
```
export TAVILY_API_KEY=<your-key>
```

Control result volume with `SYNTHADOC_WEB_SEARCH_MAX_RESULTS` (default: 20).

## When this skill is used

- Source string matches an intent prefix: `search for`, `find on the web`,
  `look up`, `web search`, `browse`
- YouTube-specific prefixes (`youtube:`, `search youtube:`, `youtube video:`,
  etc.) restrict the Tavily search to `youtube.com` and `youtu.be`
- CJK intent phrases: 查找, 搜索, 网络搜索, 在网上查, 查一下
- No file extension — purely intent-driven

## End-to-end flow

```
synthadoc ingest "search for: transformer architecture papers"
  → WebSearchSkill strips intent prefix → query: "transformer architecture papers"
  → Tavily API → top N URLs
  → filter static blocked domains (reddit, medium, paywalls, etc.)
  → filter dynamic blocked domains (.synthadoc/blocked_domains.json)
  → return child_sources = [url1, url2, ...]
  → Orchestrator enqueues each URL as a separate ingest job
  → UrlSkill / YoutubeSkill scrape each one → wiki pages created
```

## Scripts

- `scripts/main.py` — `WebSearchSkill`: intent parsing, domain filtering,
  child source fan-out
- `scripts/fetcher.py` — thin async wrapper around `AsyncTavilyClient`

## Assets

- `assets/search-providers.json` — search provider registry (currently Tavily)
