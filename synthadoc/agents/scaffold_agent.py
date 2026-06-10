# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

SCAFFOLD_MARKER = "<!-- synthadoc:scaffold -->"
_SCAFFOLD_RETRY_LIMIT = 2

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_FM_STRIP_RE = re.compile(r"^---\s*\n.*?\n---\s*\n+", re.DOTALL)
_H1_STRIP_RE = re.compile(r"^#[^#][^\n]*\n+")


def _coerce_scaffold_dict(value: object) -> dict | None:
    """Coerce a parsed JSON value to the expected scaffold dict shape.

    Some models (e.g. MiniMax) return the top-level array directly or wrap the
    dict inside a single-element array.  Accept and normalise both.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        # [{"categories": [...], ...}] — single wrapped dict
        if value and isinstance(value[0], dict) and "categories" in value[0]:
            return value[0]
        # [{"heading": ..., "slugs": [...]}] — categories array returned directly
        if value and isinstance(value[0], dict) and "heading" in value[0]:
            return {"categories": value}
    return None


def _parse_scaffold_json(raw: str) -> dict | None:
    """Try progressively looser strategies to extract the scaffold JSON object."""
    # 1. Direct parse
    try:
        return _coerce_scaffold_dict(json.loads(raw))
    except json.JSONDecodeError:
        pass
    # 2. Find the outermost {...} block
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return _coerce_scaffold_dict(json.loads(m.group(0)))
        except json.JSONDecodeError:
            pass
    # 3. Fix the most common MiniMax JSON defect: missing comma between adjacent
    #    array objects ("} {" → "}, {") then retry
    fixed = re.sub(r"}\s*\n(\s*){", r"},\n\1{", raw)
    try:
        return _coerce_scaffold_dict(json.loads(fixed))
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", fixed, re.DOTALL)
    if m:
        try:
            return _coerce_scaffold_dict(json.loads(m.group(0)))
        except json.JSONDecodeError:
            pass
    return None

_SYSTEM_PROMPT = (
    "You are a knowledge management assistant helping to set up a domain-specific wiki. "
    "Return ONLY valid JSON — no markdown fences, no explanation."
)

_SCAFFOLD_PROMPT = """\
Set up a knowledge wiki for the domain: {domain}

{protected_section}Generate a scaffold with 5-8 categories appropriate for this domain.

Return ONLY valid JSON:
{{
  "categories": [
    {{
      "heading": "Category Name",
      "description": "what pages go in this category",
      "slugs": ["slug-one", "slug-two"]
    }},
    ...
  ],
  "agents_guidelines": "2-4 bullet points of domain-specific ingest and query guidelines (plain text, not markdown list syntax)",
  "purpose_overview": "2-3 sentences describing the domain, its importance, and what this wiki is for",
  "purpose_include": "3-5 bullet points (plain text, not markdown) listing the types of topics, concepts, and artefacts that belong in this wiki",
  "purpose_exclude": "3-5 bullet points (plain text, not markdown) listing what is explicitly out of scope",
  "purpose_audience": "1-2 sentences describing who will use this wiki and how",
  "purpose_use_cases": "3-5 bullet points (plain text, not markdown) of the primary questions or tasks this wiki is meant to answer",
  "dashboard_intro": "one sentence describing what this wiki tracks"
}}

The "slugs" array must contain the kebab-case page slugs that belong in each category.
{slugs_instruction}If a category has no known pages yet, use an empty array.
"""

_INDEX_FRONTMATTER = """\
---
title: Index
tags: [index]
status: active
confidence: high
created: '{created}'
sources: []
---

"""

_AGENTS_MD_TEMPLATE = """\
# AGENTS.md — {domain} Wiki

## Purpose
This wiki captures knowledge about: {domain}.

## Ingest Guidelines
{guidelines}

## Query Guidelines
- Answer using only wiki content
- Always cite sources using `[[page-name]]` link syntax
"""

_PURPOSE_MD_TEMPLATE = """\
# Wiki Purpose — {domain}

## Overview

{overview}

## What Belongs in This Wiki

{include}

## What Is Out of Scope

{exclude}

## Intended Audience

{audience}

## Primary Use Cases

{use_cases}
"""


def preserve_user_zone(existing_content: str, new_scaffold_content: str) -> str:
    """Return index.md content preserving the user zone above SCAFFOLD_MARKER.

    If the marker is absent, returns new_scaffold_content unchanged (full rewrite).
    When the marker is present the existing file already has its own frontmatter
    and h1 title, so strip both from new_scaffold_content before injecting.
    """
    if SCAFFOLD_MARKER not in existing_content:
        return new_scaffold_content
    user_zone = existing_content.split(SCAFFOLD_MARKER)[0].rstrip()
    body = _FM_STRIP_RE.sub("", new_scaffold_content, count=1)
    body = _H1_STRIP_RE.sub("", body, count=1)
    return f"{user_zone}\n\n{SCAFFOLD_MARKER}\n\n{body.lstrip()}"


@dataclass
class ScaffoldResult:
    index_md: str
    agents_md: str
    purpose_md: str
    dashboard_intro: str


class ScaffoldAgent:
    def __init__(self, provider: LLMProvider, max_tokens: int = 8192) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def scaffold(
        self,
        domain: str,
        protected_slugs: Optional[list[str]] = None,
    ) -> ScaffoldResult:
        protected_section = ""
        slugs_instruction = ""
        if protected_slugs:
            slugs_list = ", ".join(protected_slugs)
            protected_section = (
                f"IMPORTANT: The following page slugs already exist in the wiki: {slugs_list}\n\n"
            )
            slugs_instruction = (
                "Assign each of the existing slugs listed above into the most appropriate "
                'category\'s "slugs" array. Every protected slug must appear in exactly one category. '
            )

        prompt = _SCAFFOLD_PROMPT.format(
            domain=domain,
            protected_section=protected_section,
            slugs_instruction=slugs_instruction,
        )

        messages: list[Message] = [Message(role="user", content=prompt)]
        data: dict | None = None
        last_exc: Exception | None = None

        for attempt in range(_SCAFFOLD_RETRY_LIMIT):
            resp = await self._provider.complete(
                messages=messages,
                system=_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=self._max_tokens,
            )
            raw = resp.text.strip()
            m = _FENCE_RE.search(raw)
            if m:
                raw = m.group(1)

            data = _parse_scaffold_json(raw)
            if data is not None:
                break

            # First attempt failed — ask the model to fix its own output
            logger.warning(
                "ScaffoldAgent: JSON parse failed on attempt %d — asking model to self-correct",
                attempt + 1,
            )
            logger.debug("ScaffoldAgent: malformed raw response: %.500s", raw)
            messages = messages + [
                Message(role="assistant", content=resp.text),
                Message(role="user", content=(
                    "The JSON you returned is not valid. "
                    "Return ONLY the corrected JSON with no additional text."
                )),
            ]
            last_exc = ValueError(f"ScaffoldAgent: unparseable scaffold JSON after {attempt + 1} attempt(s)")

        if data is None:
            raise last_exc or ValueError("ScaffoldAgent: unparseable scaffold JSON")

        return ScaffoldResult(
            index_md=self._build_index_md(domain, data),
            agents_md=self._build_agents_md(domain, data),
            purpose_md=self._build_purpose_md(domain, data),
            dashboard_intro=data.get("dashboard_intro", f"A wiki tracking {domain} knowledge."),
        )

    def _build_index_md(self, domain: str, data: dict) -> str:
        today = date.today().isoformat()
        lines = [_INDEX_FRONTMATTER.format(created=today)]
        lines.append(f"# {domain} — Index\n")
        for cat in data.get("categories", []):
            heading = cat.get("heading", "General")
            desc = cat.get("description", "")
            slugs = cat.get("slugs", [])
            lines.append(f"\n## {heading}")
            if desc:
                lines.append(f"*{desc}*\n")
            for slug in slugs:
                if slug:
                    lines.append(f"- [[{slug}]]")
            if slugs:
                lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _build_agents_md(self, domain: str, data: dict) -> str:
        raw_guidelines = data.get("agents_guidelines", "Summarize key claims.")
        # Normalise to bullet list
        bullets = []
        for line in raw_guidelines.splitlines():
            line = line.strip().lstrip("-•* ")
            if line:
                bullets.append(f"- {line}")
        guidelines = "\n".join(bullets) if bullets else f"- {raw_guidelines}"
        return _AGENTS_MD_TEMPLATE.format(domain=domain, guidelines=guidelines)

    def _build_purpose_md(self, domain: str, data: dict) -> str:
        def _bullets(raw: str | list, fallback: str) -> str:
            if isinstance(raw, list):
                items = [str(i).strip().lstrip("-•* ") for i in raw if str(i).strip()]
            else:
                items = [
                    line.strip().lstrip("-•* ")
                    for line in str(raw).splitlines()
                    if line.strip()
                ]
            if not items:
                items = [fallback]
            return "\n".join(f"- {i}" for i in items)

        return _PURPOSE_MD_TEMPLATE.format(
            domain=domain,
            overview=data.get("purpose_overview", f"This wiki captures knowledge about {domain}."),
            include=_bullets(
                data.get("purpose_include", ""),
                f"Topics directly related to {domain}.",
            ),
            exclude=_bullets(
                data.get("purpose_exclude", ""),
                "Unrelated domains and off-topic material.",
            ),
            audience=data.get("purpose_audience", f"Anyone working with or researching {domain}."),
            use_cases=_bullets(
                data.get("purpose_use_cases", ""),
                f"Answer questions about {domain}.",
            ),
        )
