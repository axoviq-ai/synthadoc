# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import zipfile
from pathlib import Path
import pytest
from synthadoc.core.backup_engine import (
    create_backup,
    read_manifest,
    validate_manifest,
    verify_checksum,
    extract_backup,
    rewrite_config,
)


@pytest.fixture
def wiki_root(tmp_path):
    root = tmp_path / "my-wiki"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "page1.md").write_text("# Page 1", encoding="utf-8")
    (root / "wiki" / "candidates").mkdir()
    (root / "wiki" / "candidates" / "cand1.md").write_text("# Candidate", encoding="utf-8")
    sd = root / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text(
        '[wiki]\ndomain = "my-wiki"\n[server]\nport = 7070\n', encoding="utf-8"
    )
    (sd / "audit.db").write_bytes(b"SQLite fake")
    (sd / "cache.db").write_bytes(b"cache fake")
    (root / "exports").mkdir()
    (root / "exports" / "wiki.json").write_text("{}", encoding="utf-8")
    (root / "raw_sources").mkdir()
    (root / "raw_sources" / "doc.pdf").write_bytes(b"PDF fake")
    return root


def _make_backup(wiki_root, tmp_path, **kwargs):
    return create_backup(
        wiki_root=wiki_root,
        output_dir=tmp_path / "out",
        wiki_name="my-wiki",
        synthadoc_version="1.0.0",
        db_schema_version=1,
        cache_version="4",
        **kwargs,
    )


# ── create_backup ─────────────────────────────────────────────────────────────

def test_create_backup_returns_zip(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
    assert "my-wiki" in zip_path.name


def test_create_backup_is_compressed(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_DEFLATED


def test_create_backup_contains_wiki_pages(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "wiki/page1.md" in names
    assert "wiki/candidates/cand1.md" in names


def test_create_backup_includes_root_config_files(wiki_root, tmp_path):
    (wiki_root / "AGENTS.md").write_text("# Agents", encoding="utf-8")
    (wiki_root / "ROUTING.md").write_text("# Routing", encoding="utf-8")
    (wiki_root / "log.md").write_text("# Log", encoding="utf-8")
    (wiki_root / "sources.txt").write_text("https://example.com\n", encoding="utf-8")
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "AGENTS.md" in names
    assert "ROUTING.md" in names
    assert "log.md" in names
    assert "sources.txt" in names


def test_create_backup_skips_absent_root_config_files(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "AGENTS.md" not in names
    assert "ROUTING.md" not in names
    assert "log.md" not in names
    assert "sources.txt" not in names


def test_create_backup_contains_config_and_audit_db(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert ".synthadoc/config.toml" in names
    assert ".synthadoc/audit.db" in names


def test_create_backup_excludes_jobs_db(wiki_root, tmp_path):
    (wiki_root / ".synthadoc" / "jobs.db").write_bytes(b"jobs")
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/jobs.db" not in zf.namelist()


def test_create_backup_excludes_embeddings_db(wiki_root, tmp_path):
    (wiki_root / ".synthadoc" / "embeddings.db").write_bytes(b"embed")
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/embeddings.db" not in zf.namelist()


def test_create_backup_excludes_server_pid(wiki_root, tmp_path):
    (wiki_root / ".synthadoc" / "server.pid").write_text("12345", encoding="utf-8")
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/server.pid" not in zf.namelist()


def test_create_backup_includes_cache_by_default(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/cache.db" in zf.namelist()


def test_create_backup_excludes_cache_when_no_cache(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path, include_cache=False)
    with zipfile.ZipFile(zip_path) as zf:
        assert ".synthadoc/cache.db" not in zf.namelist()


def test_create_backup_includes_exports_by_default(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert any("exports" in n for n in zf.namelist())


def test_create_backup_excludes_exports_when_disabled(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path, include_exports=False)
    with zipfile.ZipFile(zip_path) as zf:
        assert not any("exports" in n for n in zf.namelist())


def test_create_backup_excludes_raw_sources_by_default(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert not any("raw_sources" in n for n in zf.namelist())


def test_create_backup_includes_raw_sources_when_requested(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path, include_sources=True)
    with zipfile.ZipFile(zip_path) as zf:
        assert any("raw_sources" in n for n in zf.namelist())


# ── manifest ──────────────────────────────────────────────────────────────────

def test_manifest_contains_required_fields(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    m = read_manifest(zip_path)
    for field in ("synthadoc_version", "db_schema_version", "cache_version",
                  "wiki_name", "backed_up_at", "source_os", "source_hostname",
                  "page_count", "includes_sources", "includes_exports",
                  "includes_cache", "checksum_sha256"):
        assert field in m, f"Missing field: {field}"


def test_manifest_wiki_name_matches(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    assert read_manifest(zip_path)["wiki_name"] == "my-wiki"


def test_manifest_page_count(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    assert read_manifest(zip_path)["page_count"] == 1  # scaffold slugs (index, purpose…) excluded


def test_manifest_includes_flags_correct(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path, include_sources=True, include_cache=False)
    m = read_manifest(zip_path)
    assert m["includes_sources"] is True
    assert m["includes_cache"] is False


def test_manifest_obsidian_plugin_false_when_absent(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    assert read_manifest(zip_path)["obsidian_plugin"] is False


def test_manifest_obsidian_plugin_true_when_present(wiki_root, tmp_path):
    plugin_dir = wiki_root / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "main.js").write_text("// plugin", encoding="utf-8")
    zip_path = _make_backup(wiki_root, tmp_path)
    assert read_manifest(zip_path)["obsidian_plugin"] is True


def test_read_manifest_raises_on_missing_manifest(tmp_path):
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("somefile.txt", "content")
    with pytest.raises(ValueError, match="No manifest.json"):
        read_manifest(zip_path)


# ── checksum ──────────────────────────────────────────────────────────────────

def test_checksum_validates_good_backup(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    m = read_manifest(zip_path)
    assert verify_checksum(zip_path, m["checksum_sha256"])


def test_checksum_empty_string_always_passes(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    assert verify_checksum(zip_path, "")


def test_checksum_wrong_value_fails(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    assert not verify_checksum(zip_path, "deadbeef" * 8)


# ── validate_manifest ─────────────────────────────────────────────────────────

def test_validate_manifest_same_version_ok():
    validate_manifest({"db_schema_version": 1}, current_db_schema_version=1)


def test_validate_manifest_older_backup_ok():
    validate_manifest({"db_schema_version": 0}, current_db_schema_version=1)


def test_validate_manifest_newer_backup_raises():
    with pytest.raises(ValueError, match="Upgrade Synthadoc"):
        validate_manifest({"db_schema_version": 99}, current_db_schema_version=1)


# ── extract_backup ────────────────────────────────────────────────────────────

def test_extract_backup_creates_expected_files(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    extracted = extract_backup(zip_path, tmp_path / "restore", "my-wiki")
    assert (extracted / "wiki" / "page1.md").exists()
    assert (extracted / ".synthadoc" / "config.toml").exists()


def test_extract_backup_does_not_place_manifest_in_wiki(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    extracted = extract_backup(zip_path, tmp_path / "restore", "my-wiki")
    assert not (extracted / "manifest.json").exists()


def test_extract_backup_supports_name_override(wiki_root, tmp_path):
    zip_path = _make_backup(wiki_root, tmp_path)
    extracted = extract_backup(zip_path, tmp_path / "restore", "renamed-wiki")
    assert extracted.name == "renamed-wiki"
    assert (extracted / "wiki" / "page1.md").exists()


# ── rewrite_config ────────────────────────────────────────────────────────────

def test_rewrite_config_updates_port(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[server]\nport = 7070\n[wiki]\ndomain = "test"\n', encoding="utf-8")
    rewrite_config(cfg, 7071)
    text = cfg.read_text(encoding="utf-8")
    assert "port = 7071" in text
    assert "port = 7070" not in text


def test_rewrite_config_updates_domain(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[wiki]\ndomain = "old"\n[server]\nport = 7070\n', encoding="utf-8")
    rewrite_config(cfg, 7070, new_domain="new")
    text = cfg.read_text(encoding="utf-8")
    assert 'domain = "new"' in text
    assert 'domain = "old"' not in text


def test_rewrite_config_preserves_schedule_jobs(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[server]\nport = 7070\n[[schedule.jobs]]\nop = "lint"\ncron = "0 0 * * *"\n',
        encoding="utf-8",
    )
    rewrite_config(cfg, 7071)
    text = cfg.read_text(encoding="utf-8")
    assert "port = 7071" in text
    assert '[[schedule.jobs]]' in text
    assert '"lint"' in text


def test_rewrite_config_no_domain_change_when_none(tmp_path):
    cfg = tmp_path / "config.toml"
    original = '[wiki]\ndomain = "keep-me"\n[server]\nport = 7070\n'
    cfg.write_text(original, encoding="utf-8")
    rewrite_config(cfg, 7071, new_domain=None)
    assert 'domain = "keep-me"' in cfg.read_text(encoding="utf-8")
