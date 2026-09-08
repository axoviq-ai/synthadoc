# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from synthadoc.cli.main import app

runner = CliRunner()

# ── Fake template data ────────────────────────────────────────────────────────

_FAKE_TEMPLATES: dict[str, list[str]] = {
    "business": ["strategy"],
    "education": ["curriculum"],
    "finance": ["investment", "private-equity"],
    "healthcare": ["clinical-research"],
    "legal": ["contracts"],
    "operations": ["supply-chain"],
    "real-estate": ["property"],
    "research": ["academic"],
    "technology": ["ai-ml", "software-dev"],
}

_FAKE_DESCS: dict[str, str] = {
    "business/strategy": "Business strategy and competitive intelligence",
    "education/curriculum": "Curriculum design and learning outcomes",
    "finance/investment": "Investment research and portfolio management",
    "finance/private-equity": "Private equity deal tracking and analysis",
    "healthcare/clinical-research": "Clinical research protocols and study tracking",
    "legal/contracts": "Contract management and legal research",
    "operations/supply-chain": "Supply chain operations and vendor management",
    "real-estate/property": "Real estate property research and valuation",
    "research/academic": "Academic research literature and citations",
    "technology/ai-ml": "Machine learning research and experiment tracking",
    "technology/software-dev": "Software engineering docs and decision records",
}


def _fake_desc(ref: str) -> str:
    return _FAKE_DESCS.get(ref, ref)


def _invoke_with_fake_templates(*args, **kwargs):
    """Helper: invoke the CLI with list_templates and get_template_description mocked."""
    with patch("synthadoc.core.template_engine.list_templates", return_value=_FAKE_TEMPLATES), \
         patch("synthadoc.core.template_engine.get_template_description", side_effect=_fake_desc), \
         patch("synthadoc.cli.install._read_registry", return_value={}):
        return runner.invoke(app, ["templates", "list"])


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_templates_list_contains_demos_header():
    result = _invoke_with_fake_templates()
    assert result.exit_code == 0, result.output
    assert "Demo" in result.output or "demo" in result.output


def test_templates_list_contains_templates_header():
    result = _invoke_with_fake_templates()
    assert result.exit_code == 0, result.output
    assert "Template" in result.output or "template" in result.output


def test_templates_list_shows_known_categories():
    result = _invoke_with_fake_templates()
    assert result.exit_code == 0
    # At least three of the 9 categories must appear
    categories = ["finance", "technology", "healthcare", "legal",
                  "research", "operations", "education", "real-estate", "business"]
    found = [c for c in categories if c in result.output]
    assert len(found) >= 3, f"Only found categories: {found}\nOutput:\n{result.output}"


def test_templates_list_shows_domains():
    result = _invoke_with_fake_templates()
    assert result.exit_code == 0, result.output
    assert "investment" in result.output
    assert "software-dev" in result.output


def test_templates_list_shows_description():
    result = _invoke_with_fake_templates()
    assert result.exit_code == 0, result.output
    # Description text includes "portfolio" or "research"
    assert "portfolio" in result.output.lower() or "research" in result.output.lower()


def test_templates_list_shows_install_hint():
    result = _invoke_with_fake_templates()
    assert result.exit_code == 0, result.output
    assert "--template" in result.output
    assert "synthadoc install" in result.output


def test_templates_list_empty_shows_no_templates_message():
    """When no templates are installed, a clear message is shown instead of nothing."""
    with patch("synthadoc.core.template_engine.list_templates", return_value={}), \
         patch("synthadoc.cli.install._read_registry", return_value={}):
        result = runner.invoke(app, ["templates", "list"])
    assert result.exit_code == 0, result.output
    assert "No templates" in result.output or "no templates" in result.output.lower()
    # Install hint still appears even with no templates
    assert "synthadoc install" in result.output
