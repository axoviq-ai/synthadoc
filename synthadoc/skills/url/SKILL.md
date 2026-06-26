---
name: url
version: "1.0"
description: Fetch and extract text from web URLs
entry:
  script: scripts/main.py
  class: UrlSkill
triggers:
  extensions:
    - "https://"
    - "http://"
  intents:
    - "fetch url"
    - "web page"
    - "website"
requires:
  - httpx
  - beautifulsoup4
author: axoviq.com
license: AGPL-3.0-or-later
---

# URL Skill

Fetches a web URL using `httpx`, strips navigation/script/style tags with
`BeautifulSoup`, and returns clean body text. PDF URLs are extracted with
`pypdf` (primary) and `pdfminer.six` (fallback).

## Setup

```bash
pip install httpx beautifulsoup4

# Optional — needed only if you ingest PDF URLs:
pip install pypdf pdfminer.six
```

## Standalone usage

```python
import asyncio
from synthadoc.skills.url.scripts.main import UrlSkill

skill = UrlSkill()

async def main():
    result = await skill.extract("https://example.com/article")
    print(result.text)          # clean body text
    print(result.metadata)      # {"url": "https://..."}

asyncio.run(main())
```

`DomainBlockedException` is raised when the site returns HTTP 401, 403, or
429. Catch it to log and skip the domain:

```python
from synthadoc.skills.base import DomainBlockedException

try:
    result = await skill.extract(url)
except DomainBlockedException as e:
    print(f"Blocked: {e.domain} (HTTP {e.status_code})")
```

## When this skill is used

- Source starts with `https://` or `http://`
- User intent contains: `fetch url`, `web page`, `website`
