# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Paul Chen / axoviq.com
# Plugin interface — third-party providers may extend these base classes under any licence.
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Union

# Message is defined in skills/base.py so skills remain standalone-importable
# without pulling in the providers package. Re-exported here for backward compat.
from synthadoc.skills.base import Message  # noqa: F401


@dataclass
class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    supports_vision: bool = True  # override to False for text-only providers

    @abstractmethod
    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse: ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("embedding not supported by this provider")

    async def complete_stream(
        self, messages: list[Message], system: Optional[str] = None,
        temperature: float = 0.0, max_tokens: int = 4096
    ) -> AsyncGenerator[str, None]:
        """Yield token strings as an async generator. Override in subclasses."""
        raise NotImplementedError("streaming not supported by this provider")
        if False:  # make this a generator
            yield ""
