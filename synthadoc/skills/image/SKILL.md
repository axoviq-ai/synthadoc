---
name: image
version: "1.0"
description: Extract text from images using a vision LLM
entry:
  script: scripts/main.py
  class: ImageSkill
triggers:
  extensions:
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".webp"
    - ".gif"
    - ".tiff"
  intents:
    - "image"
    - "screenshot"
    - "diagram"
    - "photo"
requires: []   # no pip packages; a vision LLM provider must be passed at construction time
author: axoviq.com
license: AGPL-3.0-or-later
---

# Image Skill

Base64-encodes the image and passes it to a vision-capable LLM that extracts
all text and key information. Returns the LLM's response as `result.text`.

## Setup

No pip dependency — the skill uses only the Python standard library plus a
LLM provider you supply at construction time. The provider can be any object
that implements the `complete()` interface (see below).

## Standalone usage

```python
import asyncio
from synthadoc.skills.image.scripts.main import ImageSkill

# ImageSkill REQUIRES a vision-capable provider — calling extract() without
# one raises ValueError immediately.
skill = ImageSkill(provider=my_provider)

async def main():
    result = await skill.extract("/path/to/screenshot.png")
    print(result.text)          # extracted text from the image
    print(result.metadata)      # {"tokens_input": N, "tokens_output": N}

asyncio.run(main())
```

**Provider interface** — any object with this async method:

```python
async def complete(
    messages: list,             # list of Message objects from synthadoc.skills.base
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> object                     # must have .text (str), .input_tokens (int), .output_tokens (int)
```

Build the provider with any vision-capable model. `Message` is importable
from `synthadoc.skills.base` — no dependency on `synthadoc.providers`:

```python
from synthadoc.skills.base import Message
```

**Supported image formats:** `.png`, `.jpg`/`.jpeg`, `.webp`, `.gif`, `.tiff`

## When this skill is used

- Source path ends with `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, or `.tiff`
- User intent contains: `image`, `screenshot`, `diagram`, `photo`
