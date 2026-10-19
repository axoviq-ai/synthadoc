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


# ── _sync_demo_wiki: raw_sources superseded-binary removal ───────────────────

@pytest.fixture()
def fake_demo_tree(tmp_path, monkeypatch):
    """Demo template and installed wiki with a superseded binary source file.

    Template raw_sources/:
      notes.md      — unchanged
      data.csv      — new file not in the wiki
      report.md     — replacement for report.pdf (same stem, new ext)

    Installed wiki raw_sources/:
      notes.md      — unchanged
      report.pdf    — superseded
      user-added.txt — user-created; must never be touched
    """
    import json
    import synthadoc.cli.install as install_mod

    tmpl_src = tmp_path / "tmpl" / "raw_sources"
    tmpl_src.mkdir(parents=True)
    (tmpl_src / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (tmpl_src / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmpl_src / "report.md").write_text("# Report\n", encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    wiki_src = wiki_dir / "raw_sources"
    wiki_src.mkdir(parents=True)
    (wiki_src / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (wiki_src / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    (wiki_src / "user-added.txt").write_text("my custom data\n", encoding="utf-8")

    reg_file = tmp_path / "wikis.json"
    reg_file.write_text(
        json.dumps({"test-demo": {"path": str(wiki_dir), "demo": "test-demo", "installed": "2026-10-01", "port": 7070}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(install_mod, "_REGISTRY", reg_file)
    monkeypatch.setattr(install_mod, "_DEMOS", {"test-demo": tmp_path / "tmpl"})

    return {"wiki_dir": wiki_dir, "wiki_src": wiki_src}


class TestSyncDemoRawSources:
    def _sync(self, fake_demo_tree):
        from synthadoc.cli.templates import _sync_demo_wiki
        import synthadoc.cli.install as install_mod
        wiki_dir = fake_demo_tree["wiki_dir"]
        demo_template = install_mod._DEMOS["test-demo"]
        return _sync_demo_wiki(wiki_root=wiki_dir, demo_template=demo_template, force=False)

    def test_superseded_binary_removed(self, fake_demo_tree):
        self._sync(fake_demo_tree)
        assert not (fake_demo_tree["wiki_src"] / "report.pdf").exists()

    def test_replacement_file_added(self, fake_demo_tree):
        self._sync(fake_demo_tree)
        assert (fake_demo_tree["wiki_src"] / "report.md").exists()

    def test_new_template_file_added(self, fake_demo_tree):
        self._sync(fake_demo_tree)
        assert (fake_demo_tree["wiki_src"] / "data.csv").exists()

    def test_unchanged_file_preserved(self, fake_demo_tree):
        self._sync(fake_demo_tree)
        assert (fake_demo_tree["wiki_src"] / "notes.md").exists()

    def test_user_added_file_never_touched(self, fake_demo_tree):
        self._sync(fake_demo_tree)
        assert (fake_demo_tree["wiki_src"] / "user-added.txt").exists()

    def test_removal_reported_in_changelog(self, fake_demo_tree):
        updated = self._sync(fake_demo_tree)
        assert any("report.pdf" in line for line in updated)


# ── Docker / registry-absent fallback ────────────────────────────────────────

import json as _json
import os


class TestDockerFallback:
    """templates sync falls back to SYNTHADOC_WIKI when the registry is absent."""

    def _make_docker_wiki(self, tmp_path, *, template_ref=None, demo_name=None):
        """Minimal wiki with optional origin.json — simulates a Docker volume mount."""
        wiki_root = tmp_path / "wiki"
        wiki_dir = wiki_root / "wiki"
        wiki_dir.mkdir(parents=True)
        dot_sd = wiki_root / ".synthadoc"
        dot_sd.mkdir()
        (dot_sd / "config.toml").write_text("[server]\nport = 7070\n", encoding="utf-8")
        (wiki_root / "ROUTING.md").write_text("# OLD ROUTING\n", encoding="utf-8")
        (wiki_root / "seeds.md").write_text("# Old getting started\n", encoding="utf-8")
        for fname in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            (wiki_root / fname).write_text(
                f"# {fname} — wiki\n\n- Old guideline\n", encoding="utf-8"
            )
        (wiki_dir / "purpose.md").write_text(
            "---\ntitle: Purpose\n---\n\n# Purpose\n\n**Include:** investment.\n",
            encoding="utf-8",
        )
        (wiki_dir / "index.md").write_text(
            "---\ntitle: Index\n---\n\n# Index\n", encoding="utf-8"
        )
        if template_ref is not None or demo_name is not None:
            if template_ref:
                origin = {"type": "template", "ref": template_ref, "installed": "2026-01-01"}
            else:
                origin = {"type": "demo", "name": demo_name, "installed": "2026-01-01"}
            (dot_sd / "origin.json").write_text(
                _json.dumps(origin, indent=2), encoding="utf-8"
            )
        else:
            # custom wiki — no origin.json
            pass
        return wiki_root

    def test_env_var_used_when_registry_empty(
        self, fake_template_root, tmp_path, monkeypatch
    ):
        wiki_root = self._make_docker_wiki(tmp_path, template_ref="finance/investment")
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0, result.output
        assert "SEC EDGAR" in (wiki_root / "seeds.md").read_text(encoding="utf-8")

    def test_cwd_used_when_env_absent(
        self, fake_template_root, tmp_path, monkeypatch
    ):
        wiki_root = self._make_docker_wiki(tmp_path, template_ref="finance/investment")
        monkeypatch.delenv("SYNTHADOC_WIKI", raising=False)
        monkeypatch.chdir(wiki_root)
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0, result.output
        assert "SEC EDGAR" in (wiki_root / "seeds.md").read_text(encoding="utf-8")

    def test_invalid_ref_in_origin_gives_clear_error(
        self, tmp_path, monkeypatch
    ):
        wiki_root = self._make_docker_wiki(tmp_path, template_ref="finance/nonexistent")
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code != 0
        assert "nonexistent" in result.output
        assert "origin.json" in result.output

    def test_custom_wiki_no_origin_skips_cleanly(
        self, tmp_path, monkeypatch
    ):
        wiki_root = self._make_docker_wiki(tmp_path)  # no origin.json
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0
        combined = result.output.lower()
        assert "nothing to sync" in combined or "no template" in combined


# ── templates set-origin ──────────────────────────────────────────────────────

class TestSetOrigin:
    def test_set_origin_template_writes_file(self, fake_template_root, tmp_path, monkeypatch):
        wiki_root = tmp_path / "wiki"
        (wiki_root / ".synthadoc").mkdir(parents=True)
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._read_registry", return_value={}):
            result = runner.invoke(app, ["templates", "set-origin", "finance/investment"])
        assert result.exit_code == 0, result.output
        origin = _json.loads((wiki_root / ".synthadoc" / "origin.json").read_text())
        assert origin["type"] == "template"
        assert origin["ref"] == "finance/investment"

    def test_set_origin_rejects_unknown_template(self, tmp_path, monkeypatch):
        wiki_root = tmp_path / "wiki"
        (wiki_root / ".synthadoc").mkdir(parents=True)
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._read_registry", return_value={}):
            result = runner.invoke(app, ["templates", "set-origin", "finance/doesnotexist"])
        assert result.exit_code != 0
        assert "doesnotexist" in result.output

    def test_set_origin_demo(self, tmp_path, monkeypatch):
        wiki_root = tmp_path / "wiki"
        (wiki_root / ".synthadoc").mkdir(parents=True)
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._DEMOS", {"history-of-computing": Path("/fake")}), \
             patch("synthadoc.cli.install._read_registry", return_value={}):
            result = runner.invoke(app, ["templates", "set-origin", "history-of-computing"])
        assert result.exit_code == 0, result.output
        origin = _json.loads((wiki_root / ".synthadoc" / "origin.json").read_text())
        assert origin["type"] == "demo"
        assert origin["name"] == "history-of-computing"

    def test_set_origin_rejects_unknown_demo(self, tmp_path, monkeypatch):
        wiki_root = tmp_path / "wiki"
        (wiki_root / ".synthadoc").mkdir(parents=True)
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._DEMOS", {}), \
             patch("synthadoc.cli.install._read_registry", return_value={}):
            result = runner.invoke(app, ["templates", "set-origin", "no-such-demo"])
        assert result.exit_code != 0


# ── _read_origin ─────────────────────────────────────────────────────────────

class TestReadOrigin:
    def test_missing_file_returns_empty(self, tmp_path):
        from synthadoc.cli.templates import _read_origin
        assert _read_origin(tmp_path) == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        from synthadoc.cli.templates import _read_origin
        dot_sd = tmp_path / ".synthadoc"
        dot_sd.mkdir()
        (dot_sd / "origin.json").write_text("{invalid json", encoding="utf-8")
        assert _read_origin(tmp_path) == {}

    def test_valid_template_origin(self, tmp_path):
        from synthadoc.cli.templates import _read_origin
        dot_sd = tmp_path / ".synthadoc"
        dot_sd.mkdir()
        (dot_sd / "origin.json").write_text(
            '{"type": "template", "ref": "finance/investment", "installed": "2026-01-01"}',
            encoding="utf-8",
        )
        origin = _read_origin(tmp_path)
        assert origin["type"] == "template"
        assert origin["ref"] == "finance/investment"


# ── Additional Docker fallback edge cases ─────────────────────────────────────

class TestDockerFallbackEdgeCases:
    """Boundary cases around _fallback_wiki_root and _do_sync_from_origin."""

    def _make_docker_wiki(self, tmp_path, *, template_ref=None, demo_name=None):
        wiki_root = tmp_path / "wiki"
        (wiki_root / "wiki").mkdir(parents=True)
        dot_sd = wiki_root / ".synthadoc"
        dot_sd.mkdir()
        (dot_sd / "config.toml").write_text("[server]\nport = 7070\n", encoding="utf-8")
        (wiki_root / "ROUTING.md").write_text("# OLD ROUTING\n", encoding="utf-8")
        (wiki_root / "seeds.md").write_text("# Old getting started\n", encoding="utf-8")
        for fname in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            (wiki_root / fname).write_text(f"# {fname} — wiki\n\n- Old\n", encoding="utf-8")
        (wiki_root / "wiki" / "purpose.md").write_text(
            "---\ntitle: Purpose\n---\n\n# Purpose\n", encoding="utf-8"
        )
        (wiki_root / "wiki" / "index.md").write_text(
            "---\ntitle: Index\n---\n\n# Index\n", encoding="utf-8"
        )
        if template_ref is not None:
            (dot_sd / "origin.json").write_text(
                _json.dumps({"type": "template", "ref": template_ref, "installed": "2026-01-01"}, indent=2),
                encoding="utf-8",
            )
        elif demo_name is not None:
            (dot_sd / "origin.json").write_text(
                _json.dumps({"type": "demo", "name": demo_name, "installed": "2026-01-01"}, indent=2),
                encoding="utf-8",
            )
        return wiki_root

    def test_env_var_nonexistent_dir_falls_through_to_cwd(
        self, fake_template_root, tmp_path, monkeypatch
    ):
        """SYNTHADOC_WIKI pointing to a missing directory → falls through to CWD."""
        wiki_root = self._make_docker_wiki(tmp_path, template_ref="finance/investment")
        monkeypatch.setenv("SYNTHADOC_WIKI", str(tmp_path / "nonexistent"))
        monkeypatch.chdir(wiki_root)
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0, result.output
        assert "SEC EDGAR" in (wiki_root / "seeds.md").read_text(encoding="utf-8")

    def test_neither_env_nor_cwd_exits_cleanly(self, tmp_path, monkeypatch):
        """No SYNTHADOC_WIKI, no wiki in CWD → exit 0 with 'Nothing to sync'."""
        monkeypatch.delenv("SYNTHADOC_WIKI", raising=False)
        monkeypatch.chdir(tmp_path)  # no .synthadoc/config.toml here
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0
        combined = result.output.lower()
        assert "nothing to sync" in combined or "no template" in combined

    def test_demo_origin_syncs_in_docker(self, tmp_path, monkeypatch):
        """Docker path with demo origin.json routes to _sync_demo_wiki."""
        wiki_root = self._make_docker_wiki(tmp_path, demo_name="history-of-computing")
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        fake_demo_path = tmp_path / "fake-demo"
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {"history-of-computing": fake_demo_path}), \
             patch("synthadoc.cli.templates._sync_demo_wiki", return_value=["  + wiki/article.md"]) as mock_sync:
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code == 0, result.output
        mock_sync.assert_called_once()

    def test_invalid_demo_in_origin_gives_clear_error(self, tmp_path, monkeypatch):
        """origin.json references a demo that no longer exists → clear error."""
        wiki_root = self._make_docker_wiki(tmp_path, demo_name="removed-demo")
        monkeypatch.setenv("SYNTHADOC_WIKI", str(wiki_root))
        with patch("synthadoc.cli.install._read_registry", return_value={}), \
             patch("synthadoc.cli.install._DEMOS", {}):
            result = runner.invoke(app, ["templates", "sync"])
        assert result.exit_code != 0
        assert "removed-demo" in result.output
        assert "origin.json" in result.output


# ── set-origin edge cases ─────────────────────────────────────────────────────

class TestSetOriginEdgeCases:
    def test_no_wiki_root_exits_with_error(self, tmp_path, monkeypatch):
        """set-origin fails clearly when no wiki root can be resolved."""
        monkeypatch.delenv("SYNTHADOC_WIKI", raising=False)
        monkeypatch.chdir(tmp_path)  # no .synthadoc/config.toml
        with patch("synthadoc.cli.install._read_registry", return_value={}):
            result = runner.invoke(app, ["templates", "set-origin", "finance/investment"])
        assert result.exit_code != 0
        assert "SYNTHADOC_WIKI" in result.output or "wiki directory" in result.output


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
