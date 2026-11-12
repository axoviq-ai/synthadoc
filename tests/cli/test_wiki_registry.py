# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_read_registry_all_empty(tmp_path):
    reg_path = tmp_path / "wikis.json"
    with patch("synthadoc.cli._wiki._REGISTRY", reg_path):
        from synthadoc.cli._wiki import read_registry_all
        assert read_registry_all() == {}


def test_read_registry_all_returns_dict(tmp_path):
    reg = {"wiki-a": {"path": "/x", "port": 7070, "purpose_summary": "finance"}}
    reg_path = tmp_path / "wikis.json"
    reg_path.write_text(json.dumps(reg))
    with patch("synthadoc.cli._wiki._REGISTRY", reg_path):
        from synthadoc.cli._wiki import read_registry_all
        result = read_registry_all()
        assert result["wiki-a"]["purpose_summary"] == "finance"


def test_extract_purpose_summary_no_frontmatter(tmp_path):
    """Returns first 500 chars of body when there is no YAML frontmatter."""
    wiki_root = tmp_path
    (wiki_root / "wiki").mkdir()
    (wiki_root / "wiki" / "purpose.md").write_text(
        "# My Wiki\n\nThis is the purpose.\n" * 50,
        encoding="utf-8",
    )
    from synthadoc.cli._wiki import extract_purpose_summary
    result = extract_purpose_summary(wiki_root)
    assert len(result) <= 500
    assert result.startswith("# My Wiki")


def test_extract_purpose_summary_strips_frontmatter(tmp_path):
    """YAML frontmatter is stripped; only body text is returned."""
    wiki_root = tmp_path
    (wiki_root / "wiki").mkdir()
    body = "# Purpose\n\nThis wiki covers AI research.\n"
    content = f"---\ntitle: Test\nstatus: active\n---\n{body}"
    (wiki_root / "wiki" / "purpose.md").write_text(content, encoding="utf-8")
    from synthadoc.cli._wiki import extract_purpose_summary
    result = extract_purpose_summary(wiki_root)
    assert "title:" not in result
    assert "# Purpose" in result


def test_extract_purpose_summary_missing_file(tmp_path):
    """Returns empty string when purpose.md does not exist."""
    wiki_root = tmp_path
    (wiki_root / "wiki").mkdir()
    from synthadoc.cli._wiki import extract_purpose_summary
    result = extract_purpose_summary(wiki_root)
    assert result == ""


def test_probe_port_returns_false_on_exception(tmp_path):
    """probe_port returns False when httpx raises any exception."""
    from synthadoc.cli._wiki import probe_port
    # Port 1 is always refused on non-root
    result = probe_port(1, timeout=0.1)
    assert result is False


# ── _docker_wiki_hint path/port tests ────────────────────────────────────────

def test_docker_wiki_hint_uses_cwd_path_and_port_for_non_serve_command(tmp_path):
    """_docker_wiki_hint must show actual wiki path and port, not hardcoded placeholders.

    This covers ingest, lint, status, etc. — any command that calls
    _raise_wiki_not_registered rather than serve's own error handler.
    """
    wiki_root = tmp_path / "my-wiki"
    wiki_root.mkdir()
    sd = wiki_root / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text("[server]\nport = 8042\n", encoding="utf-8")

    reg_path = tmp_path / "wikis.json"
    reg_path.write_text(json.dumps({}))  # registry exists but wiki not in it

    import synthadoc.cli._wiki as _wiki_mod

    with (
        patch.object(_wiki_mod, "_REGISTRY", reg_path),
        patch.object(_wiki_mod, "_fallback_wiki_root", return_value=wiki_root),
    ):
        hint = _wiki_mod._docker_wiki_hint("my-wiki")

    # The path appears JSON-encoded in the hint (backslashes doubled on Windows),
    # so compare against json.dumps output with surrounding quotes stripped.
    path_in_json = json.dumps(str(wiki_root.resolve()))[1:-1]
    assert path_in_json in hint, "hint must include actual wiki path"
    assert "8042" in hint, "hint must include actual server port"
    assert "7070" not in hint, "hint must not use hardcoded placeholder port"


def test_docker_wiki_hint_placeholder_when_no_wiki_in_cwd(tmp_path):
    """When CWD is not a wiki directory, hint falls back to template values."""
    reg_path = tmp_path / "wikis.json"
    reg_path.write_text(json.dumps({}))  # registry exists, wiki absent

    import synthadoc.cli._wiki as _wiki_mod

    with (
        patch.object(_wiki_mod, "_REGISTRY", reg_path),
        patch.object(_wiki_mod, "_fallback_wiki_root", return_value=None),
    ):
        hint = _wiki_mod._docker_wiki_hint("unknown-wiki")

    assert "unknown-wiki" in hint
    assert "/absolute/path/to/unknown-wiki" in hint
    assert "7070" in hint


def test_docker_wiki_hint_uses_placeholder_when_cwd_wiki_name_differs(tmp_path):
    """When the CWD wiki directory name does not match the requested wiki name,
    the hint must fall back to placeholders instead of showing the wrong wiki's path."""
    beta_root = tmp_path / "beta"
    beta_root.mkdir()
    sd = beta_root / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text("[server]\nport = 8099\n", encoding="utf-8")

    reg_path = tmp_path / "wikis.json"
    reg_path.write_text(json.dumps({}))

    import synthadoc.cli._wiki as _wiki_mod

    with (
        patch.object(_wiki_mod, "_REGISTRY", reg_path),
        patch.object(_wiki_mod, "_fallback_wiki_root", return_value=beta_root),
    ):
        # Request "alpha" but CWD wiki is "beta" — must not expose beta's config
        hint = _wiki_mod._docker_wiki_hint("alpha")

    assert "/absolute/path/to/alpha" in hint, "hint must use placeholder path for wrong-name wiki"
    assert "7070" in hint, "hint must use placeholder port for wrong-name wiki"
    assert "8099" not in hint, "hint must not leak beta's port when requesting alpha"
