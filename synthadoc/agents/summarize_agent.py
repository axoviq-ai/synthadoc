# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations
import logging
from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_SUMMARIZE_SYSTEM = (
    "Summarize the following conversation excerpt in 2-3 sentences. "
    "Preserve key facts, wiki page names, decisions made, and any unresolved questions. "
    "Be concise. Return only the summary text."
)


class SummarizeAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def summarize(self, messages: list[dict]) -> str:
        """Return a 2-3 sentence summary of *messages*.

        Returns empty string when messages is empty or on LLM error.
        """
        if not messages:
            return ""
        conversation = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in messages
        )
        try:
            resp = await self._provider.complete(
                messages=[Message(role="user", content=conversation)],
                system=_SUMMARIZE_SYSTEM,
                temperature=0.0,
            )
            return resp.text.strip()
        except Exception as exc:
            logger.warning("SummarizeAgent failed: %s", exc)
            return ""
