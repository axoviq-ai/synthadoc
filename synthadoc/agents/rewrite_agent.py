# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations
import logging
from synthadoc.agents._base import BaseAgent
from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = (
    "You are a query rewriter for a knowledge retrieval system. "
    "Given a conversation history and a follow-up question, rewrite the follow-up "
    "as a fully self-contained question that can be understood without the history. "
    "If the question is already self-contained, return it exactly as given. "
    "Return ONLY the rewritten question — no explanation, no punctuation changes."
)


class RewriteAgent(BaseAgent):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider)

    async def _run(self, question: str, history: list[dict]) -> str:
        """Return a standalone version of *question* using *history* for context.

        Called by the inherited ``BaseAgent.run()`` wrapper.
        Returns *question* unchanged when history is empty (no LLM call).
        Returns ``""`` when the LLM response is empty; the caller should
        fall back to the original question (``rewritten or question``).
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
        resp = await self._provider.complete(
            messages=[Message(role="user", content=prompt)],
            system=_REWRITE_SYSTEM,
            temperature=0.0,
        )
        return resp.text.strip()

    def _safe_default(self) -> str:
        """Return empty string when ``_run`` raises; caller falls back to original question."""
        return ""
