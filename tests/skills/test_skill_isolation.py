# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Standalone-isolation tests for synthadoc/skills/.

These tests verify that every built-in skill can be imported and instantiated
using *only* the synthadoc/skills/ subtree — no synthadoc.core, synthadoc.agents,
synthadoc.providers, synthadoc.errors, or any other Synthadoc component.

This is the prerequisite for the use case where skills are installed into an
external agent environment (e.g. Claude Code) without the full Synthadoc package.
"""
import importlib
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

# Non-skills synthadoc modules that must be absent to prove isolation.
_BLOCKED_PREFIXES = (
    "synthadoc.core",
    "synthadoc.agents",
    "synthadoc.providers",
    "synthadoc.errors",
    "synthadoc.config",
    "synthadoc.storage",
    "synthadoc.cli",
    "synthadoc.integration",
    "synthadoc.observability",
    "synthadoc.demos",
)


@contextmanager
def _skills_only():
    """Context manager that blocks all non-skills synthadoc modules.

    Any attempt to import a blocked module raises ImportError, exactly as
    it would in an environment where only synthadoc/skills/ is present.
    Existing cached imports are temporarily hidden for the duration.
    """
    blocked_keys = [k for k in sys.modules if any(k == p or k.startswith(p + ".") for p in _BLOCKED_PREFIXES)]
    saved = {k: sys.modules.pop(k) for k in blocked_keys}

    class _BlockingFinder:
        @staticmethod
        def find_module(name, path=None):
            if any(name == p or name.startswith(p + ".") for p in _BLOCKED_PREFIXES):
                return _BlockingFinder
            return None

        @staticmethod
        def load_module(name):
            raise ImportError(
                f"Isolation violation: skill imported '{name}' which is outside synthadoc/skills/. "
                f"Move the dependency into skills/base.py or make it a lazy import."
            )

    sys.meta_path.insert(0, _BlockingFinder)
    try:
        yield
    finally:
        sys.meta_path.remove(_BlockingFinder)
        sys.modules.update(saved)


# ── base.py is self-contained ──────────────────────────────────────────────────

def test_skills_base_imports_without_synthadoc_core():
    # Verify skills/base.py is already importable and exposes the full contract.
    # We do NOT force a fresh import here — doing so would create a new class
    # object for DomainBlockedException that diverges from the one cached in
    # synthadoc.errors, breaking isinstance() checks in subsequent tests.
    with _skills_only():
        mod = importlib.import_module("synthadoc.skills.base")
        assert hasattr(mod, "BaseSkill")
        assert hasattr(mod, "ExtractedContent")
        assert hasattr(mod, "Message")
        assert hasattr(mod, "DomainBlockedException")
        assert hasattr(mod, "SkillMeta")


# ── One test per skill: import + instantiate ───────────────────────────────────

def test_markdown_skill_isolated():
    with _skills_only():
        sys.modules.pop("synthadoc.skills.markdown.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.markdown.scripts.main")
        skill = mod.MarkdownSkill()
        assert skill is not None


def test_pdf_skill_isolated():
    with _skills_only():
        sys.modules.pop("synthadoc.skills.pdf.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.pdf.scripts.main")
        skill = mod.PdfSkill()
        assert skill is not None


def test_docx_skill_isolated():
    with _skills_only():
        sys.modules.pop("synthadoc.skills.docx.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.docx.scripts.main")
        skill = mod.DocxSkill()
        assert skill is not None


def test_pptx_skill_isolated():
    with _skills_only():
        sys.modules.pop("synthadoc.skills.pptx.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.pptx.scripts.main")
        skill = mod.PptxSkill()
        assert skill is not None


def test_xlsx_skill_isolated():
    with _skills_only():
        sys.modules.pop("synthadoc.skills.xlsx.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.xlsx.scripts.main")
        skill = mod.XlsxSkill()
        assert skill is not None


def test_url_skill_isolated():
    """url skill must not import synthadoc.errors.DomainBlockedException."""
    with _skills_only():
        sys.modules.pop("synthadoc.skills.url.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.url.scripts.main")
        skill = mod.UrlSkill()
        assert skill is not None
        # DomainBlockedException must come from skills/base, not synthadoc.errors
        from synthadoc.skills.base import DomainBlockedException
        assert mod.DomainBlockedException is DomainBlockedException


def test_web_search_skill_isolated():
    with _skills_only():
        sys.modules.pop("synthadoc.skills.web_search.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.web_search.scripts.main")
        skill = mod.WebSearchSkill()
        assert skill is not None


def test_image_skill_isolated():
    """image skill must not import synthadoc.providers.base.Message at module level."""
    with _skills_only():
        sys.modules.pop("synthadoc.skills.image.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.image.scripts.main")
        skill = mod.ImageSkill()
        assert skill is not None


def test_youtube_skill_isolated():
    """youtube skill must not import synthadoc.providers.base.Message at module level."""
    with _skills_only():
        sys.modules.pop("synthadoc.skills.youtube.scripts.main", None)
        mod = importlib.import_module("synthadoc.skills.youtube.scripts.main")
        skill = mod.YoutubeSkill()
        assert skill is not None


# ── Message from skills/base is compatible with provider.complete() ────────────

def test_message_from_skills_base_works_with_mock_provider():
    """Skills calling provider.complete(messages=[Message(...)]) must work when
    Message comes from skills/base — not providers/base."""
    from synthadoc.skills.base import Message, ExtractedContent
    import asyncio

    mock_provider = MagicMock()
    mock_provider.supports_vision = True
    mock_response = MagicMock()
    mock_response.text = "extracted text"
    mock_response.input_tokens = 100
    mock_response.output_tokens = 50
    mock_provider.complete = AsyncMock(return_value=mock_response)

    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"

    # Provider receives the message — duck typing means class origin doesn't matter
    async def _run():
        return await mock_provider.complete(messages=[msg])

    result = asyncio.run(_run())
    assert result.text == "extracted text"


# ── DomainBlockedException identity: same class from both import paths ──────────

def test_domain_blocked_exception_same_class_via_errors_and_skills():
    """The orchestrator imports DomainBlockedException from synthadoc.errors.
    Skills import from synthadoc.skills.base. They must be the same class
    so isinstance() checks in the orchestrator still catch skill exceptions."""
    from synthadoc.errors import DomainBlockedException as ErrDBE
    from synthadoc.skills.base import DomainBlockedException as SkillDBE
    assert ErrDBE is SkillDBE, (
        "DomainBlockedException from errors and skills/base must be the same "
        "class object — otherwise the orchestrator's isinstance() check fails."
    )


def test_domain_blocked_exception_attributes():
    from synthadoc.skills.base import DomainBlockedException
    exc = DomainBlockedException(domain="example.com", url="https://example.com/page", status_code=403)
    assert exc.domain == "example.com"
    assert exc.url == "https://example.com/page"
    assert exc.status_code == 403
    assert "ERR-SKILL-003" in str(exc)
    assert "example.com" in str(exc)
