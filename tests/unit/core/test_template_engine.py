# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from synthadoc.core.template_engine import (
    apply_template,
    get_template_description,
    get_template_guidelines,
    get_template_path,
    list_templates,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_templates(tmp_path, monkeypatch):
    """Patch _TEMPLATES_ROOT to point at a small in-memory template tree."""
    import synthadoc.core.template_engine as te

    root = tmp_path / "templates"
    # finance/investment
    inv = root / "finance" / "investment"
    (inv).mkdir(parents=True)
    (inv / "description.txt").write_text("Investment research and portfolio management\n", encoding="utf-8")
    (inv / "guidelines.md").write_text(
        "- Focus on primary sources: SEC filings, earnings calls\n"
        "- Track investment thesis per position\n"
        "- Cross-link company pages with deal pages\n"
        "- Flag financial model assumptions clearly\n"
        "- Note source date on all market data\n",
        encoding="utf-8",
    )
    (inv / "routing.md").write_text(
        "# ROUTING\n\n## companies\n- acme-corp\n\n## deals\n- acme-acquisition\n\n## models\n- dcf-model\n",
        encoding="utf-8",
    )
    wiki_dir = inv / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "purpose.md").write_text("---\ntitle: Purpose\nstatus: active\nconfidence: high\ntype: concept\nsources: []\n---\n\n# Purpose\n\n**Include:** investment research.\n\n**Exclude:** personal finance.\n", encoding="utf-8")
    (wiki_dir / "index.md").write_text("---\ntitle: Index\nstatus: active\nconfidence: high\ntype: concept\nsources: []\n---\n\n# Index\n\n- [[companies]]\n- [[deals]]\n", encoding="utf-8")
    (wiki_dir / "seeds.md").write_text("---\ntitle: Getting Started\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n\n# Getting Started\n\nSearch for annual reports.\n", encoding="utf-8")
    (wiki_dir / "companies.md").write_text("---\ntitle: Companies\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n\n# Companies\n\nPortfolio companies.\n", encoding="utf-8")

    # technology/software-dev
    sw = root / "technology" / "software-dev"
    sw.mkdir(parents=True)
    (sw / "description.txt").write_text("Software engineering docs and decision records\n", encoding="utf-8")
    (sw / "guidelines.md").write_text(
        "- Document architecture decisions in ADR format\n"
        "- Cross-link components with their runbooks\n"
        "- Track deprecations explicitly\n"
        "- Note API versioning in all endpoint pages\n"
        "- Link PRs and issues to decision pages\n",
        encoding="utf-8",
    )
    (sw / "routing.md").write_text(
        "# ROUTING\n\n## architecture\n- adrs\n\n## components\n- services\n\n## operations\n- runbooks\n",
        encoding="utf-8",
    )
    sw_wiki = sw / "wiki"
    sw_wiki.mkdir()
    (sw_wiki / "purpose.md").write_text("---\ntitle: Purpose\nstatus: active\nconfidence: high\ntype: concept\nsources: []\n---\n\n# Purpose\n\n**Include:** software docs.\n\n**Exclude:** non-technical content.\n", encoding="utf-8")
    (sw_wiki / "index.md").write_text("---\ntitle: Index\nstatus: active\nconfidence: high\ntype: concept\nsources: []\n---\n\n# Index\n\n- [[adrs]]\n", encoding="utf-8")
    (sw_wiki / "seeds.md").write_text("---\ntitle: Getting Started\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n\n# Getting Started\n\nIngest your repo's README.\n", encoding="utf-8")
    (sw_wiki / "adrs.md").write_text("---\ntitle: ADRs\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n\n# Architecture Decision Records\n\nList of decisions.\n", encoding="utf-8")

    monkeypatch.setattr(te, "_TEMPLATES_ROOT", root)
    return root


@pytest.fixture()
def blank_wiki(tmp_path):
    """Minimal wiki structure produced by init_wiki()."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (tmp_path / "wiki" / "purpose.md").write_text("---\ntitle: Purpose\n---\n\n# Purpose\n\nGeneric.\n", encoding="utf-8")
    (tmp_path / "wiki" / "index.md").write_text("---\ntitle: Index\n---\n\n# Index\n", encoding="utf-8")
    (tmp_path / ".synthadoc").mkdir()
    (tmp_path / ".synthadoc" / "config.toml").write_text("[wiki]\ndomain = \"Test\"\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md — Test Wiki\n\nGeneric.\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md — Test Wiki\n\nGeneric.\n", encoding="utf-8")
    (tmp_path / "GEMINI.md").write_text("# GEMINI.md — Test Wiki\n\nGeneric.\n", encoding="utf-8")
    return tmp_path


# ── list_templates ──────────────────────────────────────────────────────────

def test_list_templates_returns_category_mapping(fake_templates):
    result = list_templates()
    assert "finance" in result
    assert "technology" in result
    assert "investment" in result["finance"]
    assert "software-dev" in result["technology"]


def test_list_templates_sorted(fake_templates):
    result = list_templates()
    cats = list(result.keys())
    assert cats == sorted(cats)
    for domains in result.values():
        assert domains == sorted(domains)


# ── get_template_path ───────────────────────────────────────────────────────

def test_get_template_path_valid(fake_templates):
    p = get_template_path("finance/investment")
    assert p.is_dir()
    assert (p / "guidelines.md").exists()


def test_get_template_path_unknown_category(fake_templates):
    with pytest.raises(ValueError, match="Unknown template"):
        get_template_path("unknown/domain")


def test_get_template_path_unknown_domain(fake_templates):
    with pytest.raises(ValueError, match="Unknown template"):
        get_template_path("finance/unknown")


def test_get_template_path_rejects_traversal(fake_templates):
    with pytest.raises(ValueError, match="Invalid"):
        get_template_path("../etc/passwd")


def test_get_template_path_rejects_absolute(fake_templates):
    with pytest.raises(ValueError, match="Invalid"):
        get_template_path("/etc/finance/investment")


def test_get_template_path_rejects_dotslash(fake_templates):
    with pytest.raises(ValueError, match="Invalid"):
        get_template_path("./finance/investment")


def test_get_template_path_rejects_bad_format(fake_templates):
    with pytest.raises(ValueError, match="Invalid"):
        get_template_path("Finance/Investment")   # uppercase not allowed


# ── get_template_description / get_template_guidelines ─────────────────────

def test_get_template_description(fake_templates):
    desc = get_template_description("finance/investment")
    assert "Investment" in desc


def test_get_template_guidelines(fake_templates):
    gl = get_template_guidelines("finance/investment")
    assert "SEC filings" in gl
    assert gl.count("- ") >= 5


# ── apply_template ──────────────────────────────────────────────────────────

def test_apply_template_writes_routing(fake_templates, blank_wiki):
    apply_template(blank_wiki, "finance/investment")
    routing = (blank_wiki / "ROUTING.md").read_text(encoding="utf-8")
    assert "# ROUTING" in routing
    assert "companies" in routing


def test_apply_template_overwrites_purpose(fake_templates, blank_wiki):
    apply_template(blank_wiki, "finance/investment")
    content = (blank_wiki / "wiki" / "purpose.md").read_text(encoding="utf-8")
    assert "investment research" in content.lower()


def test_apply_template_overwrites_index(fake_templates, blank_wiki):
    apply_template(blank_wiki, "finance/investment")
    content = (blank_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "[[companies]]" in content or "[[deals]]" in content


def test_apply_template_copies_stubs_additively(fake_templates, blank_wiki):
    apply_template(blank_wiki, "finance/investment")
    assert (blank_wiki / "wiki" / "companies.md").exists()
    assert (blank_wiki / "wiki" / "seeds.md").exists()


def test_apply_template_does_not_overwrite_user_pages(fake_templates, blank_wiki):
    user_page = blank_wiki / "wiki" / "my-custom-page.md"
    user_page.write_text("# My Custom Page\n\nUser content.\n", encoding="utf-8")
    apply_template(blank_wiki, "finance/investment")
    assert user_page.read_text(encoding="utf-8") == "# My Custom Page\n\nUser content.\n"


def test_apply_template_does_not_import_cli(fake_templates, blank_wiki):
    """Verify no cli module is imported by template_engine (no core→cli dependency)."""
    import sys
    before = set(sys.modules.keys())
    apply_template(blank_wiki, "finance/investment")
    after = set(sys.modules.keys())
    new_mods = after - before
    cli_mods = [m for m in new_mods if "synthadoc.cli" in m]
    assert cli_mods == [], f"apply_template imported cli modules: {cli_mods}"
