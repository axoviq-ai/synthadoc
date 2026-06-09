# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations
import logging
from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = (
    "You are a query rewriter for a knowledge retrieval system. "
    "Given a conversation history and a follow-up question, rewrite the follow-up "
    "as a fully self-contained question that can be understood without the history. "
    "If the question is already self-contained, return it exactly as given. "
    "Return ONLY the rewritten question — no explanation, no punctuation changes."
)


class RewriteAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def rewrite(self, question: str, history: list[dict]) -> str:
        """Return a standalone version of *question* using *history* for context.

        Returns *question* unchanged when history is empty (no LLM call).
        Falls back to *question* on any LLM error.
        """
        if not history:
            return question
        history_text = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in history
        )
        prompt = (
            f"Conversation history:\n{history_text}\n\n"
            f"Follow-up question: {question}\n\n"
            "Rewritten standalone question:"
        )
        try:
            resp = await self._provider.complete(
                messages=[Message(role="user", content=prompt)],
                system=_REWRITE_SYSTEM,
                temperature=0.0,
            )
            rewritten = resp.text.strip()
            return rewritten if rewritten else question
        except Exception as exc:
            logger.warning("RewriteAgent failed, using original question: %s", exc)
            return question
