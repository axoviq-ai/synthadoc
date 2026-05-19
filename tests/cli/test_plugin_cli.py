# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from synthadoc.cli.main import app

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
    assert "obsidian-plugin" in result.output


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
    assert "obsidian-plugin" in result.output
