---
name: docx
version: "1.0"
description: Extract text from Microsoft Word documents
entry:
  script: scripts/main.py
  class: DocxSkill
triggers:
  extensions:
    - ".docx"
  intents:
    - "word document"
    - "docx"
requires:
  - python-docx
author: axoviq.com
license: AGPL-3.0-or-later
---

# DOCX Skill

Extracts paragraph text from `.docx` files using `python-docx`.

## Setup

```bash
pip install python-docx
```

## Standalone usage

```python
import asyncio
from synthadoc.skills.docx.scripts.main import DocxSkill

skill = DocxSkill()

async def main():
    result = await skill.extract("/path/to/document.docx")
    print(result.text)      # all paragraphs joined as plain text

asyncio.run(main())
```

## When this skill is used

- Source path ends with `.docx`
- User intent contains: `word document`, `docx`
