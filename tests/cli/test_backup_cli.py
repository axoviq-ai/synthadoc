# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_wiki(tmp_path: Path) -> Path:
    root = tmp_path / "my-wiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "page1.md").write_text("# Page 1", encoding="utf-8")
    (root / ".synthadoc").mkdir()
    (root / ".synthadoc" / "config.toml").write_text(
        '[wiki]\ndomain = "my-wiki"\n[server]\nport = 7070\n', encoding="utf-8"
    )
    (root / ".synthadoc" / "audit.db").write_bytes(b"db")
    return root


def _patch_registry(wiki_root):
    return patch(
        "synthadoc.cli.backup.resolve_wiki_path",
        return_value=wiki_root,
    )


def _patch_resolve_wiki(name="my-wiki"):
    return patch("synthadoc.cli.backup.resolve_wiki", return_value=name)


# ── backup command ─────────────────────────────────────────────────────────────

def test_backup_creates_zip_in_output_dir(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        result = runner.invoke(app, [
            "backup", "-w", "my-wiki", "--output", str(out_dir),
        ])
    assert result.exit_code == 0, result.output
    zips = list(out_dir.glob("synthadoc-backup-*.zip"))
    assert len(zips) == 1


def test_backup_zip_name_contains_wiki_name(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, ["backup", "-w", "my-wiki", "--output", str(out_dir)])
    zips = list(out_dir.glob("*.zip"))
    assert zips and "my-wiki" in zips[0].name


def test_backup_output_contains_config(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, ["backup", "-w", "my-wiki", "--output", str(out_dir)])
    zip_path = list(out_dir.glob("*.zip"))[0]
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/config.toml" in zf.namelist()


def test_backup_no_cache_flag(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    (wiki_root / ".synthadoc" / "cache.db").write_bytes(b"cache")
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, ["backup", "-w", "my-wiki", "--output", str(out_dir), "--no-cache"])
    zip_path = list(out_dir.glob("*.zip"))[0]
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/cache.db" not in zf.namelist()


def test_backup_no_exports_flag(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    (wiki_root / "exports").mkdir()
    (wiki_root / "exports" / "wiki.json").write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, ["backup", "-w", "my-wiki", "--output", str(out_dir), "--no-exports"])
    zip_path = list(out_dir.glob("*.zip"))[0]
    with zipfile.ZipFile(zip_path) as zf:
        assert not any("exports" in n for n in zf.namelist())


def test_backup_include_sources_flag(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    (wiki_root / "raw_sources").mkdir()
    (wiki_root / "raw_sources" / "doc.pdf").write_bytes(b"pdf")
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, [
            "backup", "-w", "my-wiki", "--output", str(out_dir), "--include-sources",
        ])
    zip_path = list(out_dir.glob("*.zip"))[0]
    with zipfile.ZipFile(zip_path) as zf:
        assert any("raw_sources" in n for n in zf.namelist())


def test_backup_missing_wiki_exits_nonzero(tmp_path):
    with _patch_resolve_wiki(), \
         patch("synthadoc.cli.backup.resolve_wiki_path", return_value=tmp_path / "nonexistent"):
        result = runner.invoke(app, ["backup", "-w", "missing"])
    assert result.exit_code != 0
