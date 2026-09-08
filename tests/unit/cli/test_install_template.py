# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from typer.testing import CliRunner

from synthadoc.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def mock_registry(tmp_path, monkeypatch):
    """Redirect registry to a temp file and prevent real filesystem writes."""
    reg_file = tmp_path / "wikis.json"
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", reg_file)
    return reg_file


@pytest.fixture()
def mock_init_wiki(tmp_path):
    """Patch init_wiki to create a minimal wiki structure."""
    def _fake_init(dest: Path, domain: str, port: int = 7070):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "wiki").mkdir()
        (dest / "wiki" / "purpose.md").write_text("---\ntitle: Purpose\n---\n\nGeneric.\n", encoding="utf-8")
        (dest / "wiki" / "index.md").write_text("---\ntitle: Index\n---\n\n# Index\n", encoding="utf-8")
        (dest / ".synthadoc").mkdir()
        (dest / ".synthadoc" / "config.toml").write_text(f"[wiki]\ndomain = \"{domain}\"\n\n[server]\nport = {port}\n", encoding="utf-8")
        (dest / "AGENTS.md").write_text(f"# AGENTS.md\n\nGeneric.\n", encoding="utf-8")
        (dest / "CLAUDE.md").write_text(f"# CLAUDE.md\n\nGeneric.\n", encoding="utf-8")
        (dest / "GEMINI.md").write_text(f"# GEMINI.md\n\nGeneric.\n", encoding="utf-8")
    return _fake_init


def test_install_template_calls_apply_template(tmp_path, mock_init_wiki):
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki), \
         patch("synthadoc.cli.install.apply_template") as mock_apply, \
         patch("synthadoc.cli.install.get_template_guidelines", return_value="- Bullet one\n- Bullet two\n- Bullet three\n- Bullet four\n- Bullet five\n"), \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install.Scheduler") as mock_sched_cls, \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path), "--template", "finance/investment"])
    assert result.exit_code == 0, result.output
    mock_apply.assert_called_once()
    args = mock_apply.call_args
    assert args[0][1] == "finance/investment"


def test_install_template_registry_has_category_and_template_fields(tmp_path, mock_init_wiki, mock_registry):
    import json
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki), \
         patch("synthadoc.cli.install.apply_template"), \
         patch("synthadoc.cli.install.get_template_guidelines", return_value="- a\n- b\n- c\n- d\n- e\n"), \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install.Scheduler"), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path), "--template", "finance/investment"])
    registry = json.loads(mock_registry.read_text(encoding="utf-8"))
    assert "my-wiki" in registry
    assert registry["my-wiki"]["category"] == "finance"
    assert registry["my-wiki"]["template"] == "investment"


def test_install_no_template_no_category_field(tmp_path, mock_init_wiki, mock_registry):
    import json
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki), \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path)])
    registry = json.loads(mock_registry.read_text(encoding="utf-8"))
    assert "category" not in registry.get("my-wiki", {})
    assert "template" not in registry.get("my-wiki", {})


def test_install_template_and_demo_together_errors(tmp_path):
    result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path), "--template", "finance/investment", "--demo"])
    assert result.exit_code != 0
    assert "--demo and --template" in result.output or "cannot be used together" in result.output


def test_install_unknown_template_errors(tmp_path, mock_init_wiki):
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki), \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070):
        result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path), "--template", "unknown/domain"])
    assert result.exit_code != 0


def test_install_template_passes_wiki_name_to_apply_template(tmp_path, mock_init_wiki):
    """install passes the wiki name as wiki_name= so <wiki> is substituted in seeds."""
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki), \
         patch("synthadoc.cli.install.apply_template") as mock_apply, \
         patch("synthadoc.cli.install.get_template_guidelines", return_value="- a\n- b\n- c\n- d\n- e\n"), \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install.Scheduler"), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        runner.invoke(app, ["install", "my-portfolio", "--target", str(tmp_path), "--template", "finance/investment"])
    _, kwargs = mock_apply.call_args
    assert kwargs.get("wiki_name") == "my-portfolio"


def test_install_template_demo_path_unaffected(tmp_path, mock_init_wiki):
    """--demo path must not be broken by the template changes."""
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki), \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        result = runner.invoke(app, ["install", "history-of-computing", "--target", str(tmp_path), "--demo"])
    # Demo path either succeeds or fails with "demo not found" — never crashes on template code
    assert "template" not in result.output.lower() or result.exit_code == 0
