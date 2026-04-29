# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Tavily search client wrapper for web_search skill."""
from __future__ import annotations


async def search_tavily(
    query: str,
    max_results: int,
    api_key: str,
    include_domains: list[str] | None = None,
) -> dict:
    """Call Tavily search API and return raw response dict."""
    from tavily import AsyncTavilyClient
    client = AsyncTavilyClient(api_key=api_key)
    kwargs: dict = {"max_results": max_results}
    if include_domains:
        kwargs["include_domains"] = include_domains
    return await client.search(query, **kwargs)
