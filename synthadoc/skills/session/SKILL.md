---
name: session
version: "1.0"
description: Extract conversation turns from AI session history files (.jsonl)
entry:
  script: scripts/main.py
  class: SessionSkill
triggers:
  extensions:
    - ".jsonl"
  intents:
    - "claude session"
    - "codex session"
    - "cursor session"
    - "ai session"
    - "session history"
requires: []
author: axoviq.com
license: AGPL-3.0-or-later
---

# Session Skill

Extracts human-readable conversation turns from AI coding session history files
(`.jsonl`). Supports two formats:

- **Claude Code** — the JSONL format written by Anthropic's Claude Code CLI
  (`~/.claude/projects/<hash>/<session-id>.jsonl`)
- **Codex / Cursor** — the simpler `{"role": ..., "content": ...}` per-line format
  used by OpenAI Codex and Cursor IDE sessions

Format is detected automatically from the first parseable line.

## What gets extracted

Only substantive conversation turns are kept:

| Content type | Action |
|---|---|
| User text messages | Kept if ≥ 3 words |
| Assistant text responses | Kept if ≥ 20 words |
| Assistant thinking blocks | Skipped (internal reasoning, not final output) |
| Tool use / tool result blocks | Skipped (avoids leaking file contents or credentials) |
| Image / attachment blocks | Skipped |
| Sub-agent scaffolding (`isSidechain: true`) | Skipped (internal sub-agent turns) |
| Session metadata lines | Skipped (`permission-mode`, `file-history-snapshot`, `system`, `last-prompt`) |

The extracted text is then passed through Synthadoc's standard pre-LLM source sanitizer
(zero-width characters, bidi overrides, HTML comments, hidden CSS spans, base64 blobs,
instruction-override phrases), exactly like PDF, DOCX, URL, and every other source type.

## Output format

Each turn is labelled `[USER]` or `[ASSISTANT]` and separated by `---`:

```
[USER]
How do I implement a sliding window algorithm?

---

[ASSISTANT]
A sliding window algorithm maintains a contiguous subarray (the "window") …
```

## `suggested_slug`

The skill returns a `suggested_slug` in metadata derived from the session file's
modification time and the first substantive user message:

```
session-2026-07-15-how-do-i-implement-a-sliding
```

## Limitations

- **No chunking in v1.1** — very long sessions are truncated at the
  `max_source_chars` limit (default 400 000 chars). Multi-session archives
  should be split into individual `.jsonl` files before ingesting.
- **Tool output excluded** — tool result blocks (shell output, file reads, etc.)
  are stripped. This is intentional: it avoids leaking file contents and
  credentials into the wiki.
- **Format auto-detection** — detection inspects the first 30 parseable lines.
  Corrupt or empty files produce an empty `ExtractedContent`.
- **No deduplication across ingest runs** — re-ingesting the same session file
  creates or updates the same wiki page (standard ingest dedup applies via
  source hash).

## When this skill is used

- Source path ends with `.jsonl`
- Intent phrases: `"claude session"`, `"codex session"`, `"cursor session"`,
  `"ai session"`, `"session history"`

## Standalone usage

```python
import asyncio
from synthadoc.skills.session.scripts.main import SessionSkill

skill = SessionSkill()

async def main():
    result = await skill.extract("/path/to/session.jsonl")
    print(result.text)       # [USER]\n...\n\n---\n\n[ASSISTANT]\n...
    print(result.metadata)   # {"format": "claude_code", "turn_count": 42, "suggested_slug": "..."}

asyncio.run(main())
```
