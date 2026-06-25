# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner
from synthadoc.cli.main import app
from synthadoc.core.backup_engine import read_manifest

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


def test_backup_sources_included_by_default(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    (wiki_root / "raw_sources").mkdir()
    (wiki_root / "raw_sources" / "doc.pdf").write_bytes(b"pdf")
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, ["backup", "-w", "my-wiki", "--output", str(out_dir)])
    zip_path = list(out_dir.glob("*.zip"))[0]
    with zipfile.ZipFile(zip_path) as zf:
        assert any("raw_sources" in n for n in zf.namelist())


def test_backup_no_sources_flag(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    (wiki_root / "raw_sources").mkdir()
    (wiki_root / "raw_sources" / "doc.pdf").write_bytes(b"pdf")
    out_dir = tmp_path / "backups"
    with _patch_resolve_wiki(), _patch_registry(wiki_root):
        runner.invoke(app, [
            "backup", "-w", "my-wiki", "--output", str(out_dir), "--no-sources",
        ])
    zip_path = list(out_dir.glob("*.zip"))[0]
    with zipfile.ZipFile(zip_path) as zf:
        assert not any("raw_sources" in n for n in zf.namelist())


def test_backup_missing_wiki_exits_nonzero(tmp_path):
    with _patch_resolve_wiki(), \
         patch("synthadoc.cli.backup.resolve_wiki_path", return_value=tmp_path / "nonexistent"):
        result = runner.invoke(app, ["backup", "-w", "missing"])
    assert result.exit_code != 0


# ── restore command ────────────────────────────────────────────────────────────

def _make_backup_zip(wiki_root: Path, out_dir: Path) -> Path:
    """Helper: create a real backup zip for restore tests."""
    from synthadoc.core.backup_engine import create_backup
    return create_backup(
        wiki_root=wiki_root,
        output_dir=out_dir,
        wiki_name="my-wiki",
        synthadoc_version="1.0.0",
        db_schema_version=1,
        cache_version="4",
    )


def _patch_registry_for_restore():
    return patch("synthadoc.cli.backup._read_registry", return_value={})


def _patch_write_registry():
    return patch("synthadoc.cli.backup._write_registry")


def _patch_reserved_ports():
    return patch("synthadoc.cli.backup._get_reserved_ports", return_value=set())


def _patch_schedule_apply():
    return patch("synthadoc.cli.backup._apply_schedules")


def test_restore_extracts_wiki_pages(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    assert result.exit_code == 0, result.output
    assert (restore_dir / "my-wiki" / "wiki" / "page1.md").exists()


def test_restore_updates_port_in_config(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply():
        runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    cfg = (restore_dir / "my-wiki" / ".synthadoc" / "config.toml").read_text(encoding="utf-8")
    assert "port = 7071" in cfg


def test_restore_registers_in_registry(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    written = {}

    def capture_registry(data):
        written.update(data)

    with _patch_registry_for_restore(), \
         patch("synthadoc.cli.backup._write_registry", side_effect=capture_registry), \
         _patch_reserved_ports(), _patch_schedule_apply():
        runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    assert "my-wiki" in written
    assert written["my-wiki"]["port"] == 7071


def test_restore_name_conflict_exits_nonzero(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    # Use a path that actually exists so the conflict check blocks the restore
    existing_live_path = tmp_path / "existing-live-wiki"
    existing_live_path.mkdir()
    existing_registry = {"my-wiki": {"path": str(existing_live_path), "port": 7070}}
    with patch("synthadoc.cli.backup._read_registry", return_value=existing_registry), \
         _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    assert result.exit_code != 0


def test_restore_stale_registry_entry_proceeds(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    # Registry points to a path that no longer exists (user deleted or renamed the folder)
    existing_registry = {"my-wiki": {"path": str(tmp_path / "my-wiki-old"), "port": 7070}}
    with patch("synthadoc.cli.backup._read_registry", return_value=existing_registry), \
         _patch_write_registry(), _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    assert result.exit_code == 0, result.output
    assert (restore_dir / "my-wiki" / "wiki" / "page1.md").exists()


def test_restore_stale_registry_reuses_original_port(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    # Stale entry holds port 7070 — should NOT block the restore from reusing it
    existing_registry = {"my-wiki": {"path": str(tmp_path / "my-wiki-old"), "port": 7070}}
    written = {}

    def capture_registry(data):
        written.update(data)

    with patch("synthadoc.cli.backup._read_registry", return_value=existing_registry), \
         patch("synthadoc.cli.backup._write_registry", side_effect=capture_registry), \
         patch("synthadoc.cli.backup._get_reserved_ports", return_value={7070}), \
         _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7070",
        ])
    assert result.exit_code == 0, result.output
    assert written.get("my-wiki", {}).get("port") == 7070


def test_restore_with_name_override(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path), "--name", "renamed-wiki",
            "--target", str(restore_dir), "--port", "7071",
        ])
    assert result.exit_code == 0, result.output
    assert (restore_dir / "renamed-wiki" / "wiki" / "page1.md").exists()


def test_restore_defaults_target_to_zip_parent(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_dir = tmp_path / "zips"
    zip_path = _make_backup_zip(wiki_root, zip_dir)
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, ["restore", str(zip_path), "--port", "7071"])
    assert result.exit_code == 0, result.output
    # Wiki should be restored inside the zip's parent directory
    assert (zip_dir / "my-wiki" / "wiki" / "page1.md").exists()
    assert "Restoring to:" in result.output


def test_restore_bad_target_shows_clean_error(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path),
            "--target", "C:\\bad\x00path",   # null byte → invalid on Windows
            "--port", "7071",
        ])
    assert result.exit_code != 0


def test_restore_missing_zip_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["restore", str(tmp_path / "nonexistent.zip")])
    assert result.exit_code != 0


def test_restore_corrupt_checksum_exits_nonzero(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")
    # Corrupt the manifest checksum by appending a second entry — duplicate-name
    # warning from zipfile is intentional here.
    import json, warnings, zipfile as zf_mod
    manifest = read_manifest(zip_path)
    manifest["checksum_sha256"] = "deadbeef" * 8
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zf_mod.ZipFile(zip_path, "a") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
    result = runner.invoke(app, [
        "restore", str(zip_path), "--target", str(tmp_path / "r"), "--port", "7070",
    ])
    assert result.exit_code != 0


def _make_backup_zip_with_plugin(wiki_root: Path, out_dir: Path) -> Path:
    """Create a backup from a wiki that has the Obsidian plugin installed."""
    plugin_dir = wiki_root / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "main.js").write_text("// plugin", encoding="utf-8")
    from synthadoc.core.backup_engine import create_backup
    return create_backup(
        wiki_root=wiki_root,
        output_dir=out_dir,
        wiki_name="my-wiki",
        synthadoc_version="1.0.0",
        db_schema_version=1,
        cache_version="4",
    )


def test_restore_auto_installs_plugin_when_manifest_flag_set(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip_with_plugin(wiki_root, tmp_path / "zips")
    restore_dir = tmp_path / "restore"
    fake_src = tmp_path / "plugin-src"
    fake_src.mkdir()
    (fake_src / "main.js").write_text("// plugin", encoding="utf-8")
    (fake_src / "manifest.json").write_text('{"id":"synthadoc"}', encoding="utf-8")
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply(), \
         patch("synthadoc.cli.plugin._PLUGIN_SRC", fake_src):
        result = runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    assert result.exit_code == 0, result.output
    plugin_dir = restore_dir / "my-wiki" / ".obsidian" / "plugins" / "synthadoc"
    assert plugin_dir.exists()
    assert "Obsidian plugin reinstalled" in result.output


def test_restore_does_not_install_plugin_when_manifest_flag_false(tmp_path):
    wiki_root = _make_wiki(tmp_path)
    zip_path = _make_backup_zip(wiki_root, tmp_path / "zips")  # no plugin → flag is False
    restore_dir = tmp_path / "restore"
    with _patch_registry_for_restore(), _patch_write_registry(), \
         _patch_reserved_ports(), _patch_schedule_apply():
        result = runner.invoke(app, [
            "restore", str(zip_path), "--target", str(restore_dir), "--port", "7071",
        ])
    assert result.exit_code == 0, result.output
    plugin_dir = restore_dir / "my-wiki" / ".obsidian" / "plugins" / "synthadoc"
    assert not plugin_dir.exists()
    assert "Obsidian plugin reinstalled" not in result.output
