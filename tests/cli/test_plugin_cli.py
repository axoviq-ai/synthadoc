# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from synthadoc.cli.main import app
from synthadoc.cli.plugin import _update_community_plugins, _install_dataview

runner = CliRunner()


def _make_plugin_src(tmp_path: Path) -> Path:
    """Create a fake obsidian-plugin source directory with stub files."""
    src = tmp_path / "obsidian-plugin"
    src.mkdir()
    for fname in ("main.js", "manifest.json", "styles.css"):
        (src / fname).write_text(f"// {fname}", encoding="utf-8")
    return src


def _make_wiki(tmp_path: Path, name: str = "mywiki") -> Path:
    """Create a minimal wiki directory with a config.toml."""
    wiki = tmp_path / name
    wiki.mkdir()
    cfg_dir = wiki / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("[server]\nhost = '127.0.0.1'\nport = 7070\n", encoding="utf-8")
    return wiki


# ── plugin install ────────────────────────────────────────────────────────────

def test_plugin_install_copies_files(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path)

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="mywiki"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki),
    ):
        result = runner.invoke(app, ["plugin", "install", "mywiki"])

    assert result.exit_code == 0, result.output
    dest = wiki / ".obsidian" / "plugins" / "synthadoc"
    assert (dest / "main.js").exists()
    assert (dest / "manifest.json").exists()
    assert (dest / "styles.css").exists()
    assert (dest / "data.json").exists()


def test_plugin_install_writes_server_url(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path)

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="mywiki"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki),
    ):
        runner.invoke(app, ["plugin", "install", "mywiki"])

    data = json.loads((wiki / ".obsidian" / "plugins" / "synthadoc" / "data.json").read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7070"


def test_plugin_install_missing_wiki_path(tmp_path):
    src = _make_plugin_src(tmp_path)
    missing = tmp_path / "ghost"

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="ghost"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=missing),
    ):
        result = runner.invoke(app, ["plugin", "install", "ghost"])

    assert result.exit_code != 0


def test_plugin_install_missing_plugin_src(tmp_path):
    wiki = _make_wiki(tmp_path)
    absent_src = tmp_path / "no-such-dir"

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", absent_src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="mywiki"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki),
    ):
        result = runner.invoke(app, ["plugin", "install", "mywiki"])

    assert result.exit_code != 0
    assert "plugin data not found" in result.output


# ── plugin upgrade ────────────────────────────────────────────────────────────

def test_plugin_upgrade_no_registry(tmp_path):
    src = _make_plugin_src(tmp_path)

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin._read_registry", return_value={}),
    ):
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code == 0
    assert "No wikis registered" in result.output


def test_plugin_upgrade_single_wiki(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path, "alpha")
    registry = {"alpha": {"path": str(wiki)}}

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin._read_registry", return_value=registry),
    ):
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    dest = wiki / ".obsidian" / "plugins" / "synthadoc"
    assert (dest / "main.js").exists()
    assert (dest / "data.json").exists()


def test_plugin_upgrade_multiple_wikis(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki_a = _make_wiki(tmp_path, "alpha")
    wiki_b = _make_wiki(tmp_path, "beta")
    registry = {
        "alpha": {"path": str(wiki_a)},
        "beta": {"path": str(wiki_b)},
    }

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin._read_registry", return_value=registry),
    ):
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code == 0, result.output
    assert "2 wiki" in result.output
    for wiki in (wiki_a, wiki_b):
        assert (wiki / ".obsidian" / "plugins" / "synthadoc" / "main.js").exists()


def test_plugin_upgrade_stale_registry_entry(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path, "good")
    registry = {
        "good": {"path": str(wiki)},
        "ghost": {"path": str(tmp_path / "ghost")},
    }

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin._read_registry", return_value=registry),
    ):
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code == 0, result.output
    assert "ghost" in result.output
    assert "good" in result.output


def test_plugin_upgrade_missing_plugin_src(tmp_path):
    absent_src = tmp_path / "no-such-dir"
    wiki = _make_wiki(tmp_path)
    registry = {"mywiki": {"path": str(wiki)}}

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", absent_src),
        patch("synthadoc.cli.plugin._read_registry", return_value=registry),
    ):
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code != 0
    assert "plugin data not found" in result.output


# ── _update_community_plugins ─────────────────────────────────────────────────

def test_update_community_plugins_creates_file(tmp_path):
    wiki = _make_wiki(tmp_path)
    _update_community_plugins(wiki, "synthadoc")
    cp = wiki / ".obsidian" / "community-plugins.json"
    assert cp.exists()
    assert json.loads(cp.read_text()) == ["synthadoc"]


def test_update_community_plugins_adds_to_existing(tmp_path):
    wiki = _make_wiki(tmp_path)
    obsidian_dir = wiki / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    (obsidian_dir / "community-plugins.json").write_text('["dataview"]', encoding="utf-8")
    _update_community_plugins(wiki, "synthadoc")
    result = json.loads((obsidian_dir / "community-plugins.json").read_text())
    assert "dataview" in result
    assert "synthadoc" in result


def test_update_community_plugins_idempotent(tmp_path):
    wiki = _make_wiki(tmp_path)
    _update_community_plugins(wiki, "synthadoc")
    _update_community_plugins(wiki, "synthadoc")
    cp = wiki / ".obsidian" / "community-plugins.json"
    assert json.loads(cp.read_text()).count("synthadoc") == 1


# ── _install_dataview ─────────────────────────────────────────────────────────

def _make_mock_response(content: bytes = b"// js", status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


def test_install_dataview_downloads_files(tmp_path):
    wiki = _make_wiki(tmp_path)
    with patch("synthadoc.cli.plugin.httpx") as mock_httpx:
        mock_httpx.get.return_value = _make_mock_response()
        result = _install_dataview(wiki)
    assert result == "installed"
    assert (wiki / ".obsidian" / "plugins" / "dataview" / "main.js").exists()


def test_install_dataview_skipped_when_already_present(tmp_path):
    wiki = _make_wiki(tmp_path)
    dest = wiki / ".obsidian" / "plugins" / "dataview"
    dest.mkdir(parents=True)
    (dest / "main.js").write_text("// existing", encoding="utf-8")
    with patch("synthadoc.cli.plugin.httpx") as mock_httpx:
        result = _install_dataview(wiki)
    mock_httpx.get.assert_not_called()
    assert result == "skipped"


def test_install_dataview_returns_failed_on_network_error(tmp_path):
    wiki = _make_wiki(tmp_path)
    with patch("synthadoc.cli.plugin.httpx") as mock_httpx:
        mock_httpx.get.side_effect = Exception("network error")
        result = _install_dataview(wiki)
    assert result == "failed"


# ── plugin install — integration with new helpers ─────────────────────────────

def test_plugin_install_updates_community_plugins_json(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path)

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="mywiki"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki),
        patch("synthadoc.cli.plugin._install_dataview", return_value="skipped"),
    ):
        result = runner.invoke(app, ["plugin", "install", "mywiki"])

    assert result.exit_code == 0, result.output
    cp = wiki / ".obsidian" / "community-plugins.json"
    assert cp.exists()
    enabled = json.loads(cp.read_text())
    assert "synthadoc" in enabled


def test_plugin_install_shows_dataview_installed_message(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path)

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="mywiki"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki),
        patch("synthadoc.cli.plugin._install_dataview", return_value="installed"),
    ):
        result = runner.invoke(app, ["plugin", "install", "mywiki"])

    assert result.exit_code == 0, result.output
    assert "installed Dataview" in result.output


def test_plugin_install_shows_dataview_failed_warning(tmp_path):
    src = _make_plugin_src(tmp_path)
    wiki = _make_wiki(tmp_path)

    with (
        patch("synthadoc.cli.plugin._PLUGIN_SRC", src),
        patch("synthadoc.cli.plugin.resolve_wiki", return_value="mywiki"),
        patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki),
        patch("synthadoc.cli.plugin._install_dataview", return_value="failed"),
    ):
        result = runner.invoke(app, ["plugin", "install", "mywiki"])

    assert result.exit_code == 0, result.output
    assert "Dataview download failed" in result.output
