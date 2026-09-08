from pathlib import Path
from synthadoc.cli._utils import _patch_toml, _toml_value


def test_toml_value_string():
    assert _toml_value("all") == '"all"'


def test_toml_value_bool():
    assert _toml_value(True) == "true"
    assert _toml_value(False) == "false"


def test_toml_value_int():
    assert _toml_value(42) == "42"


def test_patch_toml_creates_section_when_missing(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[server]\nport = 7070\n", encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    text = cfg.read_text(encoding="utf-8")
    assert "[ingest]" in text
    assert 'staging_policy = "all"' in text
    assert "port = 7070" in text   # existing content untouched


def test_patch_toml_updates_existing_key(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[ingest]\nstaging_policy = "off"\n', encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    text = cfg.read_text(encoding="utf-8")
    assert text.count("staging_policy") == 1
    assert 'staging_policy = "all"' in text


def test_patch_toml_creates_file_when_absent(tmp_path):
    cfg = tmp_path / "config.toml"
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    text = cfg.read_text(encoding="utf-8")
    assert "[ingest]" in text
    assert 'staging_policy = "all"' in text


def test_patch_toml_preserves_comments(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("# top comment\n[ingest]\n# inline comment\nmax_pages = 15\n", encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    text = cfg.read_text(encoding="utf-8")
    assert "# top comment" in text
    assert "# inline comment" in text
    assert "max_pages = 15" in text


def test_patch_toml_handles_multiple_pairs(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[ingest]\nstaging_policy = "off"\n', encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "all", "staging_confidence_min": "high"})
    text = cfg.read_text(encoding="utf-8")
    assert text.count("staging_policy") == 1
    assert 'staging_policy = "all"' in text
    assert 'staging_confidence_min = "high"' in text
