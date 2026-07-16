# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

logger = logging.getLogger(__name__)

_MIN_ASSISTANT_WORDS = 20
_MIN_USER_WORDS = 3
_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_CLAUDE_CODE_TYPES = frozenset(
    ("user", "assistant", "permission-mode", "file-history-snapshot", "system", "last-prompt", "attachment")
)
_SKIP_BLOCK_TYPES = frozenset(("tool_use", "tool_result", "thinking", "image"))


def _detect_format(lines: list[str]) -> str:
    """Return 'claude_code', 'codex', or 'unknown' based on first parseable lines."""
    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        if "message" in obj and obj.get("type") in _CLAUDE_CODE_TYPES:
            return "claude_code"
        if "role" in obj and "message" not in obj and "type" not in obj:
            return "codex"
    return "unknown"


def _extract_text_content(content) -> str:
    """Extract plain text from a content value that may be str or list of blocks."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in _SKIP_BLOCK_TYPES:
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    parts.append(text)
        return "\n\n".join(parts)
    return ""


def _is_substantive(role: str, text: str) -> bool:
    """Return True if the turn meets the minimum word-count threshold."""
    word_count = len(text.split())
    if role == "assistant":
        return word_count >= _MIN_ASSISTANT_WORDS
    return word_count >= _MIN_USER_WORDS


def _parse_claude_code(lines: list[str]) -> list[tuple[str, str]]:
    """Parse Claude Code JSONL format into (role, text) pairs."""
    turns: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("isSidechain"):
            continue
        if obj.get("type") not in ("user", "assistant"):
            continue
        msg = obj.get("message", {})
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", obj.get("type", ""))
        content = msg.get("content", "")
        text = _extract_text_content(content)
        if text:
            turns.append((role, text))
    return turns


def _parse_codex(lines: list[str]) -> list[tuple[str, str]]:
    """Parse Codex/Cursor JSONL format into (role, text) pairs."""
    turns: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        role = obj.get("role", "")
        if role not in ("user", "assistant", "human"):
            continue
        content = obj.get("content", "")
        text = _extract_text_content(content)
        if text:
            turns.append((role, text))
    return turns


def _make_slug(path: Path, turns: list[tuple[str, str]]) -> str:
    """Generate a suggested slug: session-YYYY-MM-DD-<topic-from-first-user-turn>."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        date_str = mtime.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        date_str = "session"

    topic = ""
    for role, text in turns:
        if role in ("user", "human"):
            words = re.sub(r"[^a-zA-Z0-9 ]", " ", text).split()[:6]
            candidate = _SLUG_CLEAN_RE.sub("-", " ".join(w.lower() for w in words if w)).strip("-")
            if len(candidate.split("-")) >= 2:
                topic = candidate
                break

    slug = f"session-{date_str}"
    if topic:
        slug = f"{slug}-{topic}"
    return slug[:80]


class SessionSkill(BaseSkill):
    meta = SkillMeta(
        name="session",
        description="Extract conversation turns from AI session history files (.jsonl)",
        extensions=[".jsonl"],
    )

    async def extract(self, source: str) -> ExtractedContent:
        path = Path(source)
        if not path.exists():
            logger.warning("session: file not found: %s", source)
            return ExtractedContent(text="", source_path=source, metadata={})

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("session: could not read %s: %s", source, exc)
            return ExtractedContent(text="", source_path=source, metadata={})

        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if not lines:
            return ExtractedContent(text="", source_path=source, metadata={"empty": True})

        fmt = _detect_format(lines)
        raw_turns = _parse_claude_code(lines) if fmt == "claude_code" else _parse_codex(lines)

        turns = [(role, text) for role, text in raw_turns if _is_substantive(role, text)]

        if not turns:
            logger.warning("session: no substantive turns extracted from %s", source)
            return ExtractedContent(
                text="",
                source_path=source,
                metadata={"format": fmt, "empty": True},
            )

        blocks = []
        for role, text in turns:
            label = "[USER]" if role in ("user", "human") else "[ASSISTANT]"
            blocks.append(f"{label}\n{text}")
        output = "\n\n---\n\n".join(blocks)

        return ExtractedContent(
            text=output,
            source_path=source,
            metadata={
                "format": fmt,
                "turn_count": len(turns),
                "suggested_slug": _make_slug(path, turns),
            },
        )
