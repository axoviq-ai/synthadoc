# tests/test_template_completeness.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Parametrized completeness check: every template folder has all required files
with content that meets the quality floor.

Run this test after Tasks 6-11 to verify all 30 templates are complete.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from synthadoc.core.template_engine import list_templates, _TEMPLATES_ROOT

# Build the parametrize list from the real filesystem
_ALL_REFS = [
    f"{cat}/{dom}"
    for cat, doms in list_templates().items()
    for dom in doms
]

# Expected 30 templates across 9 categories
_EXPECTED_CATEGORIES = {
    "finance": ["investment", "mortgage", "banking", "accounting"],
    "technology": ["software-dev", "devops", "ai-ml", "data-engineering"],
    "healthcare": ["clinical", "pharmaceutical", "public-health"],
    "legal": ["legal-ops", "compliance", "ip-management"],
    "research": ["academic", "science-lab", "market-research"],
    "operations": ["manufacturing-qc", "facility-management", "supply-chain"],
    "education": ["course-design", "personal-learning", "corporate-training"],
    "real-estate": ["investment", "property-management", "development"],
    "business": ["product-management", "marketing", "hr-people", "project-management"],
}


def test_all_30_templates_present():
    """Ensure every expected template folder exists."""
    missing = []
    for cat, domains in _EXPECTED_CATEGORIES.items():
        for dom in domains:
            p = _TEMPLATES_ROOT / cat / dom
            if not p.is_dir():
                missing.append(f"{cat}/{dom}")
    assert not missing, f"Missing template folders:\n" + "\n".join(f"  {m}" for m in missing)


@pytest.mark.parametrize("template_ref", _ALL_REFS)
class TestTemplateCompleteness:

    def _path(self, template_ref: str) -> Path:
        return _TEMPLATES_ROOT / template_ref

    def test_description_txt_exists_and_nonempty(self, template_ref):
        p = self._path(template_ref) / "description.txt"
        assert p.exists(), f"{template_ref}: description.txt missing"
        assert len(p.read_text(encoding="utf-8").strip()) > 10, f"{template_ref}: description.txt too short"

    def test_guidelines_md_has_5_or_more_bullets(self, template_ref):
        p = self._path(template_ref) / "guidelines.md"
        assert p.exists(), f"{template_ref}: guidelines.md missing"
        bullets = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("- ")]
        assert len(bullets) >= 5, f"{template_ref}: only {len(bullets)} guideline bullets (need ≥5)"

    def test_routing_md_has_3_or_more_sections(self, template_ref):
        p = self._path(template_ref) / "routing.md"
        assert p.exists(), f"{template_ref}: routing.md missing"
        sections = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("## ")]
        assert len(sections) >= 3, f"{template_ref}: only {len(sections)} routing sections (need ≥3)"

    def test_wiki_purpose_md_exists_and_nonempty(self, template_ref):
        p = self._path(template_ref) / "wiki" / "purpose.md"
        assert p.exists(), f"{template_ref}: wiki/purpose.md missing"
        assert len(p.read_text(encoding="utf-8").strip()) > 50

    def test_wiki_index_md_exists_and_nonempty(self, template_ref):
        p = self._path(template_ref) / "wiki" / "index.md"
        assert p.exists(), f"{template_ref}: wiki/index.md missing"
        assert len(p.read_text(encoding="utf-8").strip()) > 50

    def test_wiki_seeds_md_exists_and_nonempty(self, template_ref):
        p = self._path(template_ref) / "wiki" / "seeds.md"
        assert p.exists(), f"{template_ref}: wiki/seeds.md missing"
        assert len(p.read_text(encoding="utf-8").strip()) > 100

    def test_wiki_has_at_least_2_additional_stubs(self, template_ref):
        wiki_dir = self._path(template_ref) / "wiki"
        reserved = {"purpose.md", "index.md", "seeds.md"}
        stubs = [f for f in wiki_dir.glob("*.md") if f.name not in reserved]
        assert len(stubs) >= 2, f"{template_ref}: only {len(stubs)} stub pages beyond purpose/index/seeds (need ≥2)"

    def test_all_stubs_have_valid_frontmatter(self, template_ref):
        wiki_dir = self._path(template_ref) / "wiki"
        reserved = {"purpose.md", "index.md"}
        bad = []
        for stub in wiki_dir.glob("*.md"):
            if stub.name in reserved:
                continue
            text = stub.read_text(encoding="utf-8")
            if not text.startswith("---"):
                bad.append(f"{stub.name}: no frontmatter")
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                bad.append(f"{stub.name}: malformed frontmatter")
                continue
            try:
                fm = yaml.safe_load(parts[1])
            except yaml.YAMLError as e:
                bad.append(f"{stub.name}: YAML error: {e}")
                continue
            for required_key in ("title", "status", "confidence"):
                if required_key not in fm:
                    bad.append(f"{stub.name}: missing '{required_key}' in frontmatter")
        assert not bad, f"{template_ref} frontmatter issues:\n" + "\n".join(f"  {b}" for b in bad)
