---
name: youtube
version: "1.0"
description: Extract transcripts from YouTube videos via the YouTube caption system
entry:
  script: scripts/main.py
  class: YoutubeSkill
triggers:
  extensions:
    - "https://www.youtube.com/"
    - "https://youtu.be/"
    - "https://www.youtubekids.com/"
  intents: []
requires:
  - youtube-transcript-api
author: axoviq.com
license: AGPL-3.0-or-later
---

# YouTube Skill

Extracts the transcript (captions) from a YouTube video using the YouTube
caption system — no API key or audio download required. Optionally uses a
vision-capable LLM to produce a structured summary (Overview, Topics,
Key takeaways) before the raw transcript.

## Setup

```bash
pip install youtube-transcript-api
```

## Standalone usage

**Transcript only** (no LLM required):

```python
import asyncio
from synthadoc.skills.youtube.scripts.main import YoutubeSkill

skill = YoutubeSkill()          # no provider — returns raw timestamped transcript

async def main():
    result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    print(result.text)          # "[0:00] text [0:04] text ..."
    print(result.metadata)      # {"video_id": "...", "title": "...", "url": "..."}

asyncio.run(main())
```

**With LLM summarization** (pass any provider that implements `complete()`):

```python
skill = YoutubeSkill(provider=my_provider)
result = await skill.extract(url)
# result.text contains:
#   ## Executive Summary
#   <Overview / Topics / Key takeaways>
#
#   ## Transcript
#   [0:00] ...
```

The provider must implement:
```python
async def complete(messages, system=None, temperature=0.0, max_tokens=4096)
    -> object with .text (str), .input_tokens (int), .output_tokens (int)
```

`Message` (used to build the `messages` list) is importable from
`synthadoc.skills.base`:
```python
from synthadoc.skills.base import Message
```

## When this skill is used

- Source starts with `https://www.youtube.com/`, `https://youtu.be/`, or
  `https://www.youtubekids.com/`

To search YouTube by topic instead of ingesting a specific URL, use the web
search skill — it filters Tavily results to YouTube domains automatically:

```bash
synthadoc ingest "youtube Moore's Law"
synthadoc ingest "youtube kids: Sesame Street"
synthadoc ingest "search for youtube: history of computing"
```

## Limitations

- Only works for videos that have captions (auto-generated or manually added).
  If no captions are available the source is skipped with a warning.
- Private or deleted videos are skipped gracefully.
