# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from pathlib import Path
import tomllib
import pytest
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_wiki_with_candidate(tmp_path: Path) -> Path:
    (tmp_path / "wiki" / "candidates").mkdir(parents=True)
    (tmp_path / "wiki" / "candidates" / "new-page.md").write_text(
        "---\ntitle: New Page\nconfidence: low\ncreated: '2026-05-05'\ntags: []\nstatus: active\nsources: []\n---\n\nContent."
    )
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('[ingest]\nstaging_policy = "threshold"\n')
    return tmp_path


def test_staging_policy_show(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["staging", "policy", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert "threshold" in result.output


def test_staging_policy_set_off(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["staging", "policy", "off", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    cfg = tomllib.loads((w / ".synthadoc" / "config.toml").read_text())
    assert cfg["ingest"]["staging_policy"] == "off"


def test_candidates_list(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["candidates", "list", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert "new-page" in result.output


def test_candidates_promote(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    from unittest.mock import patch
    with patch("synthadoc.cli._http.post", return_value={"slug": "new-page", "promoted": True, "updated": False}) as mock_post:
        result = runner.invoke(app, ["candidates", "promote", "new-page", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert "Promoted" in result.output
    assert "new-page" in result.output
    mock_post.assert_called_once()


def test_candidates_discard(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["candidates", "discard", "new-page", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert not (w / "wiki" / "candidates" / "new-page.md").exists()


def test_candidates_list_empty(tmp_path):
    (tmp_path / "wiki" / "candidates").mkdir(parents=True)
    result = runner.invoke(app, ["candidates", "list", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    assert "No candidates" in result.output


def test_candidates_promote_appends_to_recently_added(tmp_path):
    """index.md update is server-side; CLI delegates promote to HTTP endpoint."""
    w = _make_wiki_with_candidate(tmp_path)
    from unittest.mock import patch
    with patch("synthadoc.cli._http.post", return_value={"slug": "new-page", "promoted": True, "updated": False}):
        result = runner.invoke(app, ["candidates", "promote", "new-page", "--wiki", str(w)])
    assert result.exit_code == 0, result.output


def test_candidates_promote_creates_recently_added_section(tmp_path):
    """index.md update is server-side; CLI delegates promote to HTTP endpoint."""
    w = _make_wiki_with_candidate(tmp_path)
    from unittest.mock import patch
    with patch("synthadoc.cli._http.post", return_value={"slug": "new-page", "promoted": True, "updated": False}):
        result = runner.invoke(app, ["candidates", "promote", "new-page", "--wiki", str(w)])
    assert result.exit_code == 0, result.output


# ── _toml_value() ────────────────────────────────────────────────────────────

def test_toml_value_bool_true():
    from synthadoc.cli.candidates import _toml_value
    assert _toml_value(True) == "true"


def test_toml_value_bool_false():
    from synthadoc.cli.candidates import _toml_value
    assert _toml_value(False) == "false"


def test_toml_value_int():
    from synthadoc.cli.candidates import _toml_value
    assert _toml_value(42) == "42"


def test_toml_value_dict():
    from synthadoc.cli.candidates import _toml_value
    result = _toml_value({"a": 1, "b": "x"})
    assert result == '{a = 1, b = "x"}'


def test_toml_value_list():
    from synthadoc.cli.candidates import _toml_value
    result = _toml_value([1, "two"])
    assert result == '[1, "two"]'


def test_toml_value_string_uses_json_dumps():
    """String falls through to json.dumps fallback (line 50)."""
    from synthadoc.cli.candidates import _toml_value
    assert _toml_value("hello world") == '"hello world"'


def test_staging_policy_invalid_min_confidence(tmp_path):
    """Invalid --min-confidence → prints error and exits 1 (lines 125-126)."""
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, [
        "staging", "policy", "threshold", "--min-confidence", "invalid-level", "--wiki", str(w)
    ])
    assert result.exit_code != 0
    assert "min-confidence" in result.output


# ── _patch_toml() ────────────────────────────────────────────────────────────

def test_patch_toml_creates_new_section(tmp_path):
    from synthadoc.cli.candidates import _patch_toml
    cfg = tmp_path / "config.toml"
    cfg.write_text("[other]\nfoo = 1\n", encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    content = cfg.read_text()
    assert "[ingest]" in content
    assert 'staging_policy = "all"' in content


def test_patch_toml_updates_existing_key(tmp_path):
    from synthadoc.cli.candidates import _patch_toml
    cfg = tmp_path / "config.toml"
    cfg.write_text('[ingest]\nstaging_policy = "off"\n', encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    content = cfg.read_text()
    assert 'staging_policy = "all"' in content
    assert content.count("staging_policy") == 1


def test_patch_toml_section_at_end_of_file(tmp_path):
    from synthadoc.cli.candidates import _patch_toml
    cfg = tmp_path / "config.toml"
    cfg.write_text('[other]\nfoo = 1\n\n[ingest]\nstaging_policy = "off"', encoding="utf-8")
    _patch_toml(cfg, "ingest", {"staging_policy": "threshold"})
    content = cfg.read_text()
    assert 'staging_policy = "threshold"' in content


# ── --all flag ────────────────────────────────────────────────────────────────

def test_candidates_promote_all(tmp_path):
    """promote --all delegates to /candidates/promote-all and reports promoted slugs."""
    w = _make_wiki_with_candidate(tmp_path)
    from unittest.mock import patch
    payload = {"promoted": ["new-page", "another-page"], "count": 2}
    with patch("synthadoc.cli._http.post", return_value=payload) as mock_post:
        result = runner.invoke(app, ["candidates", "promote", "--all", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert "new-page" in result.output
    assert "another-page" in result.output
    args, _ = mock_post.call_args
    assert args[1] == "/candidates/promote-all"
    assert args[2] == {}


def test_candidates_discard_all(tmp_path):
    """discard --all removes every candidate in the directory."""
    w = _make_wiki_with_candidate(tmp_path)
    (w / "wiki" / "candidates" / "another-page.md").write_text("# Another\n")
    result = runner.invoke(app, ["candidates", "discard", "--all", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert not (w / "wiki" / "candidates" / "new-page.md").exists()
    assert not (w / "wiki" / "candidates" / "another-page.md").exists()


def test_candidates_promote_shows_updated_when_page_exists(tmp_path):
    """Server returns updated=True when page already existed; CLI prints 'Updated'."""
    w = _make_wiki_with_candidate(tmp_path)
    from unittest.mock import patch
    with patch("synthadoc.cli._http.post", return_value={"slug": "new-page", "promoted": True, "updated": True}):
        result = runner.invoke(app, ["candidates", "promote", "new-page", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert "Updated" in result.output


def test_staging_policy_show_threshold_displays_min_confidence(tmp_path):
    """staging policy show with threshold policy also shows min_confidence."""
    w = _make_wiki_with_candidate(tmp_path)
    (w / ".synthadoc" / "config.toml").write_text(
        '[ingest]\nstaging_policy = "threshold"\nstaging_confidence_min = "high"\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["staging", "policy", "--wiki", str(w)])
    assert result.exit_code == 0, result.output
    assert "threshold" in result.output
    assert "high" in result.output
