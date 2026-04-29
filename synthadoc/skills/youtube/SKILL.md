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
caption system — no API key or audio download required.

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

Each YouTube URL returned by Tavily is then ingested by this skill.

## Limitations

- Only works for videos that have captions (auto-generated or manually added).
  If no captions are available the source is skipped with a warning.
- Private or deleted videos are skipped gracefully.
