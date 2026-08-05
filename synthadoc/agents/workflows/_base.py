# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

SseEventFn = Callable[[str, dict], Awaitable[None]]


@dataclass
class WorkflowContext:
    """Runtime context threaded through every agentic workflow."""

    session_id: str
    wiki_root: Path
    queue: "JobQueue | None"  # type: ignore[name-defined]
    store: "WikiStorage | None"  # type: ignore[name-defined]
    audit_db: "AuditDB | None"  # type: ignore[name-defined]
    send_sse_event: SseEventFn
    confirm_registry: dict[str, asyncio.Event]
    confirm_result_registry: dict[str, bool]


class AgenticWorkflow(ABC):
    """Abstract base class for all agentic workflows."""

    @abstractmethod
    async def build_system_prompt(self) -> str:
        """Return the system prompt for the LLM."""
        ...

    @abstractmethod
    def build_initial_message(self, user_input: str) -> str:
        """Return the first user message sent to the LLM."""
        ...

    @abstractmethod
    def get_tool_fns(
        self, ctx: WorkflowContext
    ) -> dict[str, Callable[..., Awaitable[dict]]]:
        """Return a mapping of tool name → async callable for this workflow."""
        ...
