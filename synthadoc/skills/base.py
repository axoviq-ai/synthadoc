# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Paul Chen / axoviq.com
# Plugin interface — third-party skills may extend these base classes under any licence.
# This file is intentionally stdlib-only so skills/ can operate without the rest of
# the synthadoc package (e.g. when installed standalone into Claude Code or another agent).
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass
class Message:
    """Minimal LLM message contract used by vision and summarisation skills.

    Keeping this here (not in synthadoc.providers) means skills that call an
    LLM (image, youtube) can do so without importing the full providers package.
    synthadoc.providers.base re-exports this class so all existing code is
    unaffected.
    """
    role: str
    content: Union[str, list]  # list for vision: [{"type": "image", ...}, ...]


class DomainBlockedException(Exception):
    """Raised by UrlSkill when a site returns a bot-blocking HTTP status.

    Defined here (not in synthadoc.errors) so the url skill stays decoupled
    from Synthadoc core.  synthadoc.errors re-exports this class so the
    orchestrator's isinstance() check continues to work unchanged.
    """
    def __init__(self, domain: str, url: str, status_code: int) -> None:
        self.domain = domain
        self.url = url
        self.status_code = status_code
        super().__init__(
            f"[ERR-SKILL-003] Domain auto-blocked ({status_code}): {domain} — "
            f"site blocked automated access. Future URLs from this domain will be skipped."
        )


@dataclass
class Triggers:
    extensions: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)


@dataclass
class SkillMeta:
    name: str
    description: str
    # New structured fields
    version: str = "1.0"
    entry_script: str = "scripts/main.py"
    entry_class: str = ""
    triggers: Triggers = field(default_factory=Triggers)
    requires: list[str] = field(default_factory=list)
    skill_dir: Optional[Path] = None
    # Deprecated: kept for backwards compat with old flat-file skill classes
    extensions: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.triggers.extensions and self.extensions:
            self.triggers = Triggers(extensions=list(self.extensions), intents=self.triggers.intents)
        if not self.entry_class:
            self.entry_class = "".join(p.title() for p in self.name.split("_")) + "Skill"


@dataclass
class ExtractedContent:
    text: str
    source_path: str
    metadata: dict = field(default_factory=dict)


class BaseSkill(ABC):
    skill_dir: Optional[Path] = None
    _resources_dir: Optional[Path] = None  # deprecated; use skill_dir

    def __init__(self):
        self._resource_cache: dict[str, str] = {}

    def get_resource(self, name: str) -> str:
        """Tier 3: search assets/ then references/ lazily. Falls back to _resources_dir."""
        if name in self._resource_cache:
            return self._resource_cache[name]
        # New folder-based lookup
        if self.skill_dir is not None:
            for subdir in ("assets", "references"):
                candidate = self.skill_dir / subdir / name
                if candidate.exists():
                    self._resource_cache[name] = candidate.read_text(encoding="utf-8")
                    return self._resource_cache[name]
        # Legacy fallback for old-style skills using _resources_dir
        if self._resources_dir is not None:
            legacy = self._resources_dir / name
            if legacy.exists():
                self._resource_cache[name] = legacy.read_text(encoding="utf-8")
                return self._resource_cache[name]
        raise FileNotFoundError(
            f"Resource '{name}' not found in assets/, references/, or resources/ "
            f"(skill_dir={self.skill_dir})"
        )

    @abstractmethod
    async def extract(self, source: str) -> ExtractedContent: ...
