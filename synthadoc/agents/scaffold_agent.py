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
from synthadoc.cli._init import _AGENT_INSTRUCTION_BODY

logger = logging.getLogger(__name__)

SCAFFOLD_MARKER = "<!-- synthadoc:scaffold -->"
_SCAFFOLD_RETRY_LIMIT = 3
_META_SLUGS = frozenset({"index", "overview", "purpose", "dashboard", "log"})

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_FM_STRIP_RE = re.compile(r"^---\s*\n.*?\n---\s*\n+", re.DOTALL)
_H1_STRIP_RE = re.compile(r"^#[^#][^\n]*\n+")
_SECTION_SPLIT_RE = re.compile(r"(^## .+$)", re.MULTILINE)


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


def _extract_first_json_object(text: str) -> str | None:
    """Extract the first brace-balanced JSON object from text.

    Unlike a greedy regex, this handles trailing prose that contains braces
    (e.g. MiniMax adding "…see {field} for details" after the JSON object).
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_scaffold_json(raw: str) -> dict | None:
    """Try progressively looser strategies to extract the scaffold JSON object."""
    # 1. Direct parse
    try:
        return _coerce_scaffold_dict(json.loads(raw))
    except json.JSONDecodeError:
        pass
    # 2. Brace-balanced extraction — handles trailing prose with {braces}
    extracted = _extract_first_json_object(raw)
    if extracted:
        try:
            return _coerce_scaffold_dict(json.loads(extracted))
        except json.JSONDecodeError:
            pass
    # 3. Fix the most common MiniMax JSON defect: missing comma between adjacent
    #    array objects ("} {" → "}, {") then retry on raw and on extracted
    fixed = re.sub(r"}\s*\n(\s*){", r"},\n\1{", raw)
    try:
        return _coerce_scaffold_dict(json.loads(fixed))
    except json.JSONDecodeError:
        pass
    if extracted:
        fixed_extracted = re.sub(r"}\s*\n(\s*){", r"},\n\1{", extracted)
        try:
            return _coerce_scaffold_dict(json.loads(fixed_extracted))
        except json.JSONDecodeError:
            pass
    # 4. Strip trailing commas — some models emit "value," before "}" or "]"
    def _strip_trailing_commas(s: str) -> str:
        return re.sub(r",(\s*[}\]])", r"\1", s)
    try:
        return _coerce_scaffold_dict(json.loads(_strip_trailing_commas(raw)))
    except json.JSONDecodeError:
        pass
    if extracted:
        try:
            return _coerce_scaffold_dict(json.loads(_strip_trailing_commas(extracted)))
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
  "domain_label": "precise human-readable domain name inferred from the wiki content (e.g. 'History of Computing', not 'General' or 'My Wiki')",
  "categories": [
    {{
      "heading": "Category Name",
      "description": "what pages go in this category",
      "slugs": ["slug-one", "slug-two"]
    }},
    ...
  ],
  "agents_guidelines": "3 domain-specific ingest and query guidelines, one per line — write each guideline as a plain sentence on its own line with no bullet or dash symbol (the renderer adds the bullet)",
  "purpose_overview": "2-3 sentences describing the domain, its importance, and what this wiki is for",
  "purpose_include": "3-5 items listing the types of topics, concepts, and artefacts that belong in this wiki, one per line, no bullet symbols",
  "purpose_exclude": "3-5 items listing what is explicitly out of scope, one per line, no bullet symbols",
  "purpose_audience": "1-2 sentences describing who will use this wiki and how",
  "purpose_use_cases": "3-5 primary questions or tasks this wiki is meant to answer, one per line, no bullet symbols",
  "dashboard_intro": "one sentence describing what this wiki tracks"
}}

The "slugs" array must contain the kebab-case page slugs that belong in each category.
{slugs_instruction}If a category has no known pages yet, use an empty array.
Never include system/meta pages in any "slugs" array: index, overview, purpose, dashboard, log.
These are auto-generated wiki infrastructure pages — they must not appear as category entries.
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

_AGENTS_MD_TEMPLATE = "# AGENTS.md — {domain} Wiki\n\n" + _AGENT_INSTRUCTION_BODY
_CLAUDE_MD_TEMPLATE = "# CLAUDE.md — {domain} Wiki\n\n" + _AGENT_INSTRUCTION_BODY
_GEMINI_MD_TEMPLATE = "# GEMINI.md — {domain} Wiki\n\n" + _AGENT_INSTRUCTION_BODY

_PURPOSE_MD_TEMPLATE = """\
---
title: Wiki Purpose — {domain}
status: active
confidence: high
created: '{created}'
aliases: []
categories:
- Overview & Orientation
tags: []
orphan: false
sources: []
---

# Wiki Purpose — {domain}

## Overview

<!-- synthadoc:scaffold -->

{overview}

## What Belongs in This Wiki

<!-- synthadoc:scaffold -->

{include}
- AI coding session transcripts (`.jsonl` files from Claude Code, Codex, Cursor) — captures software development decisions, debugging sessions, and technical problem-solving

## What Is Out of Scope

<!-- synthadoc:scaffold -->

{exclude}

## Intended Audience

<!-- synthadoc:scaffold -->

{audience}

## Primary Use Cases

<!-- synthadoc:scaffold -->

{use_cases}
"""


def _parse_sections(content: str) -> list[tuple[str, str]]:
    """Split content on ## headings → [(heading, body), ...].

    The first entry always has heading='' and holds the pre-heading preamble
    (frontmatter + H1 + any content before the first ## heading).
    """
    parts = _SECTION_SPLIT_RE.split(content)
    result: list[tuple[str, str]] = [("", parts[0])]
    for i in range(1, len(parts), 2):
        result.append((parts[i], parts[i + 1] if i + 1 < len(parts) else ""))
    return result


def preserve_user_zone(existing_content: str, new_scaffold_content: str) -> str:
    """Preserve user content above SCAFFOLD_MARKER on scaffold regeneration.

    **Single-marker mode** (index.md, or a legacy purpose.md with exactly one
    marker): the marker sits below the H1.  Everything above the marker is the
    user zone; everything below is replaced with the new scaffold body.

    **Multi-marker mode** (purpose.md with a marker inside each ## section):
    each section is merged independently.  Within a section, content the user
    wrote *above* the marker is preserved; content *below* the marker is
    replaced with fresh LLM output.  Sections without a marker are replaced
    entirely by the template content (marker added); sections present in the
    existing file but absent from the template are kept unchanged.  Sections
    present in the new scaffold but absent from the existing file are appended.

    If the existing file has no marker at all it is fully replaced — this is
    the correct behaviour for the very first scaffold run on an existing wiki.
    """
    if SCAFFOLD_MARKER not in existing_content:
        return new_scaffold_content

    if existing_content.count(SCAFFOLD_MARKER) == 1:
        # ── Single-marker mode ─────────────────────────────────────────────
        user_zone = existing_content.split(SCAFFOLD_MARKER)[0].rstrip()
        body = _FM_STRIP_RE.sub("", new_scaffold_content, count=1)
        body = _H1_STRIP_RE.sub("", body, count=1)
        body = body.lstrip()
        if body.startswith(SCAFFOLD_MARKER):
            body = body[len(SCAFFOLD_MARKER):].lstrip()
        return f"{user_zone}\n\n{SCAFFOLD_MARKER}\n\n{body}"

    # ── Multi-marker mode ──────────────────────────────────────────────────
    # Build heading → fresh LLM content map from the new scaffold.
    new_content_map: dict[str, str] = {}
    for heading, body in _parse_sections(new_scaffold_content):
        if not heading:
            continue
        after = body.split(SCAFFOLD_MARKER, 1)[1].strip() if SCAFFOLD_MARKER in body else body.strip()
        new_content_map[heading] = after

    parts: list[str] = []
    for heading, body in _parse_sections(existing_content):
        if not heading:
            parts.append(body)  # preamble (frontmatter + H1) — always preserved
            continue
        if SCAFFOLD_MARKER not in body:
            fresh = new_content_map.get(heading, "")
            if fresh:
                # No marker present → scaffold owns this section; replace with template content.
                parts.append(f"{heading}\n\n{SCAFFOLD_MARKER}\n\n{fresh}\n\n")
            else:
                # Section not in the new scaffold template → user-added, keep as-is.
                parts.append(heading + body)
            continue
        user_zone = body.split(SCAFFOLD_MARKER, 1)[0].strip()
        fresh = new_content_map.get(heading, "").strip()
        if user_zone:
            parts.append(f"{heading}\n\n{user_zone}\n\n{SCAFFOLD_MARKER}\n\n{fresh}\n\n")
        else:
            parts.append(f"{heading}\n\n{SCAFFOLD_MARKER}\n\n{fresh}\n\n")

    # Append sections from new scaffold absent in the existing file.
    existing_headings = {h for h, _ in _parse_sections(existing_content) if h}
    for heading, body in _parse_sections(new_scaffold_content):
        if heading and heading not in existing_headings:
            fresh = body.split(SCAFFOLD_MARKER, 1)[1].strip() if SCAFFOLD_MARKER in body else body.strip()
            parts.append(f"{heading}\n\n{SCAFFOLD_MARKER}\n\n{fresh}\n\n")

    return "".join(parts)


@dataclass
class ScaffoldResult:
    index_md: str
    agents_md: str
    claude_md: str
    gemini_md: str
    purpose_md: str
    dashboard_intro: str


def _validate_routing_md(content: str) -> None:
    """Raise ValueError if a scaffold-regenerated ROUTING.md has format issues.

    Called in orchestrator._run_scaffold() after RoutingIndex.save() so the
    job fails with a clear message rather than silently writing a broken file.
    """
    issues: list[str] = []
    if not re.search(r"^## .+", content, re.MULTILINE):
        issues.append("ROUTING.md: no branch headings (## ...) found")
    if "[[" not in content:
        issues.append("ROUTING.md: no [[slug]] entries found")
    if issues:
        raise ValueError(
            "ScaffoldAgent: regenerated ROUTING.md has format issues:\n"
            + "\n".join(f"  - {i}" for i in issues)
        )


def _validate_scaffold_result(result: "ScaffoldResult", domain: str) -> None:
    """Raise ValueError listing every format issue found in the scaffold output.

    Called before returning from scaffold() so callers (install and server job)
    both see a clean failure with an actionable issue list.
    """
    issues: list[str] = []

    # index.md checks
    if not result.index_md.startswith("---"):
        issues.append("index.md: missing YAML frontmatter")
    if f"# {domain}" not in result.index_md:
        issues.append("index.md: H1 title does not include the domain name")
    if "[[" not in result.index_md:
        issues.append("index.md: no [[wikilinks]] — LLM returned no category slugs")

    # AGENTS.md checks — verify key sections from the comprehensive template
    for section in ("## Domain Guidelines", "## Quick Reference", "## Ingest", "## Query"):
        if section not in result.agents_md:
            issues.append(f"AGENTS.md: missing '{section}' section")

    # purpose.md checks
    if "## Overview" not in result.purpose_md:
        issues.append("purpose.md: missing '## Overview' section")
    if domain not in result.purpose_md:
        issues.append("purpose.md: domain name not present in body")

    if issues:
        raise ValueError(
            "ScaffoldAgent: generated files have format issues:\n"
            + "\n".join(f"  - {i}" for i in issues)
        )


class ScaffoldAgent:
    def __init__(self, provider: LLMProvider, max_tokens: int = 8192) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def scaffold(
        self,
        domain: str,
        protected_slugs: Optional[list[str]] = None,
        port: int = 7070,
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

            is_last = attempt + 1 == _SCAFFOLD_RETRY_LIMIT
            if is_last:
                logger.warning(
                    "ScaffoldAgent: JSON parse failed on attempt %d (final) — giving up. "
                    "Malformed response: %.2000s",
                    attempt + 1, raw,
                )
            else:
                logger.warning(
                    "ScaffoldAgent: JSON parse failed on attempt %d — asking model to self-correct. "
                    "Malformed response: %.500s",
                    attempt + 1, raw,
                )
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

        # Prefer the LLM-identified label so a wiki whose config still says
        # "General" gets the correct domain name in all generated titles.
        effective_domain = (data.get("domain_label") or "").strip() or domain

        agents_md, claude_md, gemini_md = self._build_skill_files(effective_domain, data, port)
        scaffold = ScaffoldResult(
            index_md=self._build_index_md(effective_domain, data),
            agents_md=agents_md,
            claude_md=claude_md,
            gemini_md=gemini_md,
            purpose_md=self._build_purpose_md(effective_domain, data),
            dashboard_intro=data.get("dashboard_intro", f"A wiki tracking {effective_domain} knowledge."),
        )
        _validate_scaffold_result(scaffold, effective_domain)
        return scaffold

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
                if slug and slug not in _META_SLUGS:
                    lines.append(f"- [[{slug}]]")
            if slugs:
                lines.append("")
        lines.append("")
        return "\n".join(lines)

    _CONTRADICTION_BULLET = "- Flag contradictions between sources with ⚠ markers"

    def _build_skill_files(
        self, domain: str, data: dict, port: int
    ) -> tuple[str, str, str]:
        """Return (agents_md, claude_md, gemini_md) from LLM scaffold data."""
        raw_guidelines = data.get("agents_guidelines", "Summarize key claims.")
        bullets = []
        for line in raw_guidelines.splitlines():
            line = line.strip().lstrip("-•* ")
            if line:
                bullets.append(f"- {line}")
        if not bullets:
            bullets = [f"- {raw_guidelines}"]
        # Always include the ⚠ contradiction-marker convention — it's a
        # Synthadoc-wide standard, not domain-specific, so the LLM may omit it.
        if "⚠" not in "\n".join(bullets):
            bullets.append(self._CONTRADICTION_BULLET)
        guidelines = "\n".join(bullets)
        kwargs = dict(domain=domain, guidelines=guidelines, port=port)
        return (
            _AGENTS_MD_TEMPLATE.format(**kwargs),
            _CLAUDE_MD_TEMPLATE.format(**kwargs),
            _GEMINI_MD_TEMPLATE.format(**kwargs),
        )

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
            created=date.today().isoformat(),
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
