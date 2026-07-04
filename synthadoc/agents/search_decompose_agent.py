# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import logging
import re

from synthadoc.agents._utils import parse_json_string_array
from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_MAX_SUB_QUERIES = 4
_MAX_QUERY_CHARS = 2000

# Reject suggestions that use the site: search operator with a local filename
# extension rather than a real web domain (e.g. "site:purpose.md ...").
# This happens when the LLM sees a filename in the domain_context and
# hallucinates it as a web domain.
_LOCAL_SITE_RE = re.compile(
    r"^site:[^\s/]*\.(md|txt|pdf|json|yaml|toml|csv|py|js|ts)\b",
    re.IGNORECASE,
)

# Reject Wikipedia URLs — they block automated ingest (403/bot detection),
# and the prompt already instructs the LLM not to suggest them, but it sometimes
# ignores the instruction.
_WIKIPEDIA_RE = re.compile(
    r"(?:https?://)?(?:\w+\.)?wikipedia\.org/",
    re.IGNORECASE,
)


class SearchDecomposeAgent:
    """Decomposes a knowledge gap into actionable ingest suggestions.

    Each suggestion is either a terse keyword search query or a well-known
    authoritative URL (Wikipedia, official docs, etc.) for the topic.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def decompose(self, query: str, domain_context: str = "") -> list[str]:
        """Return a list of search queries and/or well-known URLs for the gap topic.

        Items that start with https?:// are direct URLs; others are search queries
        that the ingest pipeline will treat as 'search for: {item}'.
        Returns [query] on any failure so callers always get a usable list.
        """
        truncated = query[:_MAX_QUERY_CHARS]
        domain_hint = (
            f"Wiki domain context (constrain suggestions to this domain): {domain_context}\n\n"
            if domain_context else ""
        )
        try:
            resp = await self._provider.complete(
                messages=[Message(role="user", content=(
                    "You are an ingest suggestion generator for a personal knowledge wiki. "
                    f"{domain_hint}"
                    "Given the topic below, suggest up to 4 ways to enrich the wiki. "
                    "For each suggestion, choose ONE of:\n"
                    "  • A terse keyword search query (3-7 words) — just the query text, no prefix\n"
                    "  • A well-known authoritative URL (official docs, company page, "
                    "    GitHub repo, etc.) — return the full https:// URL if one obviously exists. "
                    "    Do NOT suggest Wikipedia URLs — they block automated access.\n"
                    "Prefer a direct URL for specific well-known entities (people, organisations, "
                    "technologies) when an official non-Wikipedia page exists. "
                    "Otherwise use a search query. "
                    "Simple topics should return 1-2 items; complex topics up to 4. "
                    "Return a JSON array of strings only. No explanation.\n\n"
                    f"Topic: {truncated}"
                ))],
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "search decompose failed (%s: %s) — falling back to original query",
                type(exc).__name__, exc,
            )
            return [query]
        filtered = parse_json_string_array(resp.text, _MAX_SUB_QUERIES) or []
        filtered = [
            s for s in filtered
            if not _LOCAL_SITE_RE.match(s.strip()) and not _WIKIPEDIA_RE.search(s)
        ]
        if filtered:
            if len(filtered) == 1:
                logger.info("web search is simple — no decomposition (1 query)")
            else:
                logger.info(
                    "web search decomposed into %d queries: %s",
                    len(filtered),
                    " | ".join(f'"{q}"' for q in filtered),
                )
            return filtered
        logger.warning(
            "search decompose failed (invalid JSON array) — falling back to original query"
        )
        return [query]
