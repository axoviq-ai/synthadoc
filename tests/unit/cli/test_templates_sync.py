# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for ``synthadoc templates sync`` and its internal helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synthadoc.cli.main import app
from synthadoc.cli._utils import _is_stub

runner = CliRunner()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_template_root(tmp_path, monkeypatch):
    """A minimal template tree for finance/investment patched into template_engine."""
    import synthadoc.core.template_engine as te

    root = tmp_path / "templates"
    inv = root / "finance" / "investment"
    inv.mkdir(parents=True)

    (inv / "description.txt").write_text("Investment research\n", encoding="utf-8")
    (inv / "guidelines.md").write_text(
        "- Source SEC filings\n- Cross-link companies\n- Flag assumptions\n"
        "- Note source dates\n- Review quarterly\n",
        encoding="utf-8",
    )
    (inv / "routing.md").write_text("# ROUTING\n\n## companies\n- acme\n", encoding="utf-8")
    (inv / "seeds.md").write_text(
        "# Getting Started — Investment\n\nSearch SEC EDGAR for 10-K filings.\n",
        encoding="utf-8",
    )

    wiki_dir = inv / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "purpose.md").write_text(
        "---\ntitle: Purpose\nstatus: active\nconfidence: high\ntype: concept\nsources: []\n---\n"
        "\n# Purpose\n\n**Include:** investment research.\n\n**Exclude:** personal finance.\n",
        encoding="utf-8",
    )
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Index\nstatus: active\nconfidence: high\ntype: concept\nsources: []\n---\n"
        "\n# Index\n\n- [[companies]]\n",
        encoding="utf-8",
    )
    (wiki_dir / "companies.md").write_text(
        "---\ntitle: Companies\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n"
        "\n# Companies\n\nPortfolio companies.\n",
        encoding="utf-8",
    )

    raw_dir = inv / "raw_sources" / "portfolios"
    raw_dir.mkdir(parents=True)
    (raw_dir / "template-portfolio.md").write_text(
        "# Portfolio Intake\n\n- **Wiki:** <wiki>\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(te, "_TEMPLATES_ROOT", root)
    return root


@pytest.fixture()
def installed_template_wiki(tmp_path):
    """Simulate an installed finance/investment wiki with one stub and one populated page."""
    wiki_root = tmp_path / "my-wiki"
    wiki_dir = wiki_root / "wiki"
    wiki_dir.mkdir(parents=True)
    (wiki_root / ".synthadoc").mkdir()

    # System files (outdated versions)
    (wiki_root / "ROUTING.md").write_text("# OLD ROUTING\n", encoding="utf-8")
    (wiki_root / "seeds.md").write_text("# Old getting started\n", encoding="utf-8")
    (wiki_root / "AGENTS.md").write_text(
        "# AGENTS.md — my-wiki\n\n- Old guideline A\n- Old guideline B\n",
        encoding="utf-8",
    )
    (wiki_root / "CLAUDE.md").write_text(
        "# CLAUDE.md — my-wiki\n\n- Old guideline A\n- Old guideline B\n",
        encoding="utf-8",
    )
    (wiki_root / "GEMINI.md").write_text(
        "# GEMINI.md — my-wiki\n\n- Old guideline A\n- Old guideline B\n",
        encoding="utf-8",
    )

    # Wiki pages
    (wiki_dir / "purpose.md").write_text(
        "---\ntitle: Purpose\n---\n\n# Purpose\n\n**Include:** investment research.\n",
        encoding="utf-8",
    )
    (wiki_dir / "index.md").write_text(
        "---\ntitle: Index\n---\n\n# Index\n",
        encoding="utf-8",
    )
    # Stub — never ingested
    (wiki_dir / "companies.md").write_text(
        "---\ntitle: Companies\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n"
        "\n# Companies\n\nOld stub body.\n",
        encoding="utf-8",
    )
    # Populated — user has ingested content
    (wiki_dir / "deals.md").write_text(
        "---\ntitle: Deals\nstatus: active\nconfidence: high\ntype: concept\nsources: [deal-memo-2026]\n---\n"
        "\n# Deals\n\nUser-authored deal notes.\n",
        encoding="utf-8",
    )

    # Existing intake form
    raw_dir = wiki_root / "raw_sources" / "portfolios"
    raw_dir.mkdir(parents=True)
    (raw_dir / "template-portfolio.md").write_text(
        "# Portfolio Intake\n\n- **Wiki:** old-<wiki>\n",
        encoding="utf-8",
    )
    # User-created fill (no template- prefix — must never be touched)
    (raw_dir / "my-acme-portfolio.md").write_text(
        "# ACME Portfolio\n\n- **Wiki:** my-wiki\n",
        encoding="utf-8",
    )

    return wiki_root


def _fake_registry(wiki_root: Path):
    return {
        "my-wiki": {
            "path": str(wiki_root),
            "category": "finance",
            "template": "investment",
            "installed": "2026-01-01",
            "port": 7070,
        }
    }


# ── _is_stub ──────────────────────────────────────────────────────────────────

class TestIsStub:
    def test_stub_page(self, tmp_path):
        p = tmp_path / "stub.md"
        p.write_text(
            "---\ntitle: T\nstatus: draft\nconfidence: low\nsources: []\n---\n\n# T\n",
            encoding="utf-8",
        )
        assert _is_stub(p) is True

    def test_populated_page_with_sources(self, tmp_path):
        p = tmp_path / "pop.md"
        p.write_text(
            "---\ntitle: T\nstatus: active\nconfidence: high\nsources: [my-source]\n---\n\n# T\nContent.\n",
            encoding="utf-8",
        )
        assert _is_stub(p) is False

    def test_low_confidence_but_has_sources(self, tmp_path):
        """Low confidence alone is not enough — sources must also be empty."""
        p = tmp_path / "partial.md"
        p.write_text(
            "---\ntitle: T\nstatus: draft\nconfidence: low\nsources: [some-source]\n---\n\n# T\n",
            encoding="utf-8",
        )
        assert _is_stub(p) is False

    def test_empty_sources_but_not_low_confidence(self, tmp_path):
        """Empty sources alone is not enough — confidence must also be low."""
        p = tmp_path / "partial2.md"
        p.write_text(
            "---\ntitle: T\nstatus: active\nconfidence: medium\nsources: []\n---\n\n# T\n",
            encoding="utf-8",
        )
        assert _is_stub(p) is False


# ── _sync_template_wiki ───────────────────────────────────────────────────────

class TestSyncTemplateWiki:
    def _run(self, fake_template_root, installed_template_wiki, force=False):
        from synthadoc.cli.templates import _sync_template_wiki
        return _sync_template_wiki(
            wiki_root=installed_template_wiki,
            template_ref="finance/investment",
            wiki_name="my-wiki",
            force=force,
        )

    def test_seeds_md_updated(self, fake_template_root, installed_template_wiki):
        updated = self._run(fake_template_root, installed_template_wiki)
        content = (installed_template_wiki / "seeds.md").read_text(encoding="utf-8")
        assert "SEC EDGAR" in content
        assert any("seeds.md" in line for line in updated)

    def test_routing_md_updated(self, fake_template_root, installed_template_wiki):
        updated = self._run(fake_template_root, installed_template_wiki)
        content = (installed_template_wiki / "ROUTING.md").read_text(encoding="utf-8")
        assert "acme" in content
        assert "OLD ROUTING" not in content
        assert any("ROUTING.md" in line for line in updated)

    def test_agents_guidelines_updated(self, fake_template_root, installed_template_wiki):
        updated = self._run(fake_template_root, installed_template_wiki)
        agents = (installed_template_wiki / "AGENTS.md").read_text(encoding="utf-8")
        # Header line preserved
        assert agents.startswith("# AGENTS.md — my-wiki")
        # Body replaced with new guidelines
        assert "Source SEC filings" in agents
        assert "Old guideline A" not in agents
        assert any("AGENTS.md" in line for line in updated)

    def test_claude_gemini_also_updated(self, fake_template_root, installed_template_wiki):
        self._run(fake_template_root, installed_template_wiki)
        for fname in ("CLAUDE.md", "GEMINI.md"):
            content = (installed_template_wiki / fname).read_text(encoding="utf-8")
            assert "Source SEC filings" in content
            assert "Old guideline" not in content

    def test_header_line_preserved_in_agent_files(self, fake_template_root, installed_template_wiki):
        self._run(fake_template_root, installed_template_wiki)
        for fname, prefix in [("AGENTS.md", "# AGENTS.md"), ("CLAUDE.md", "# CLAUDE.md"), ("GEMINI.md", "# GEMINI.md")]:
            first_line = (installed_template_wiki / fname).read_text(encoding="utf-8").split("\n")[0]
            assert first_line.startswith(prefix)
            assert "my-wiki" in first_line

    def test_template_intake_form_updated(self, fake_template_root, installed_template_wiki):
        updated = self._run(fake_template_root, installed_template_wiki)
        content = (installed_template_wiki / "raw_sources" / "portfolios" / "template-portfolio.md").read_text(encoding="utf-8")
        # <wiki> substituted with wiki_name
        assert "my-wiki" in content
        assert "<wiki>" not in content
        assert any("template-portfolio.md" in line for line in updated)

    def test_user_raw_sources_never_touched(self, fake_template_root, installed_template_wiki):
        original = (installed_template_wiki / "raw_sources" / "portfolios" / "my-acme-portfolio.md").read_text(encoding="utf-8")
        self._run(fake_template_root, installed_template_wiki)
        after = (installed_template_wiki / "raw_sources" / "portfolios" / "my-acme-portfolio.md").read_text(encoding="utf-8")
        assert after == original

    def test_new_stub_added_additively(self, fake_template_root, installed_template_wiki):
        """A stub in the template that doesn't exist in the installed wiki is added."""
        # Add a new stub to the fake template
        import synthadoc.core.template_engine as te
        (te._TEMPLATES_ROOT / "finance" / "investment" / "wiki" / "models.md").write_text(
            "---\ntitle: Models\nstatus: draft\nconfidence: low\ntype: concept\nsources: []\n---\n\n# Models\n\nValuation models.\n",
            encoding="utf-8",
        )
        updated = self._run(fake_template_root, installed_template_wiki)
        assert (installed_template_wiki / "wiki" / "models.md").exists()
        assert any("wiki/models.md" in line and line.strip().startswith("+") for line in updated)

    def test_existing_stub_not_overwritten_without_force(self, fake_template_root, installed_template_wiki):
        original = (installed_template_wiki / "wiki" / "companies.md").read_text(encoding="utf-8")
        self._run(fake_template_root, installed_template_wiki, force=False)
        after = (installed_template_wiki / "wiki" / "companies.md").read_text(encoding="utf-8")
        assert after == original

    def test_force_updates_stub_pages(self, fake_template_root, installed_template_wiki):
        updated = self._run(fake_template_root, installed_template_wiki, force=True)
        content = (installed_template_wiki / "wiki" / "companies.md").read_text(encoding="utf-8")
        assert "Portfolio companies." in content  # template version
        assert "Old stub body." not in content
        assert any("companies.md" in line and "refreshed" in line for line in updated)

    def test_force_never_overwrites_populated_pages(self, fake_template_root, installed_template_wiki):
        original = (installed_template_wiki / "wiki" / "deals.md").read_text(encoding="utf-8")
        self._run(fake_template_root, installed_template_wiki, force=True)
        after = (installed_template_wiki / "wiki" / "deals.md").read_text(encoding="utf-8")
        assert after == original  # populated page untouched even with --force

    def test_no_changes_when_already_up_to_date(self, fake_template_root, installed_template_wiki):
        """Second sync should report nothing changed."""
        self._run(fake_template_root, installed_template_wiki)
        # Run again — everything is now current
        updated = self._run(fake_template_root, installed_template_wiki)
        system_files = [l for l in updated if any(f in l for f in ("seeds.md", "ROUTING.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"))]
        assert system_files == [], f"Second sync should not re-update system files: {system_files}"


# ── CLI integration ───────────────────────────────────────────────────────────

class TestSyncCLI:
    def test_sync_named_template_wiki(self, fake_template_root, installed_template_wiki):
        registry = _fake_registry(installed_template_wiki)
        with patch("synthadoc.cli.install._read_registry", return_value=registry):
            result = runner.invoke(app, ["templates", "sync", "my-wiki"])
        assert result.exit_code == 0
        assert "my-wiki" in result.output

    def test_sync_unknown_wiki_exits_nonzero(self):
        with patch("synthadoc.cli.install._read_registry", return_value={}):
            result = runner.invoke(app, ["templates", "sync", "nonexistent"])
        assert result.exit_code != 0

    def test_sync_all_when_no_name_given(self, fake_template_root, installed_template_wiki):
        registry = _fake_registry(installed_template_wiki)
        with patch("synthadoc.cli.install._read_registry", return_value=registry):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0

    def test_sync_no_template_wikis_exits_cleanly(self):
        plain = {"plain-wiki": {"path": "/some/path", "installed": "2026-01-01", "port": 7070}}
        with patch("synthadoc.cli.install._read_registry", return_value=plain), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0
        assert "Nothing to sync" in result.output or "No template" in result.output

    def test_force_flag_accepted(self, fake_template_root, installed_template_wiki):
        registry = _fake_registry(installed_template_wiki)
        with patch("synthadoc.cli.install._read_registry", return_value=registry):
            result = runner.invoke(app, ["templates", "sync", "my-wiki", "--force"])
        assert result.exit_code == 0


# ── demo sync deprecation ─────────────────────────────────────────────────────

class TestDemoSyncDeprecation:
    def test_demo_sync_emits_deprecation_warning(self, fake_template_root, installed_template_wiki):
        registry = _fake_registry(installed_template_wiki)
        with patch("synthadoc.cli.install._read_registry", return_value=registry):
            result = runner.invoke(app, ["demo", "sync", "my-wiki"])
        # Deprecation warning appears somewhere in the combined output
        assert "deprecated" in result.output.lower()
        assert "templates sync" in result.output

    def test_demo_sync_still_works(self, fake_template_root, installed_template_wiki):
        """Deprecated command delegates to templates sync and produces correct output."""
        registry = _fake_registry(installed_template_wiki)
        with patch("synthadoc.cli.install._read_registry", return_value=registry):
            result = runner.invoke(app, ["demo", "sync", "my-wiki"])
        assert result.exit_code == 0
        assert "my-wiki" in result.output
