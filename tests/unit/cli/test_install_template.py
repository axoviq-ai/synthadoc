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


# ---------------------------------------------------------------------------
# Domain resolution — helper unit tests
# ---------------------------------------------------------------------------

def test_domain_from_name_hyphens():
    from synthadoc.cli.install import _domain_from_name
    assert _domain_from_name("my-investment-wiki") == "My Investment Wiki"


def test_domain_from_name_underscores():
    from synthadoc.cli.install import _domain_from_name
    assert _domain_from_name("acme_corp_legal") == "Acme Corp Legal"


def test_domain_from_name_single_word():
    from synthadoc.cli.install import _domain_from_name
    assert _domain_from_name("research") == "Research"


def test_sanitize_domain_short_unchanged():
    from synthadoc.cli.install import _sanitize_domain
    assert _sanitize_domain("Investment Banking") == "Investment Banking"


def test_sanitize_domain_strips_whitespace():
    from synthadoc.cli.install import _sanitize_domain
    assert _sanitize_domain("  Investment Banking  ") == "Investment Banking"


def test_sanitize_domain_clean_word_boundary():
    """Cut falls exactly at a space — return domain[:48] with no trailing space."""
    from synthadoc.cli.install import _sanitize_domain
    # Construct a string where char[48] is a space
    # "A" * 48 + " B" — char[48] is ' '
    s = "word " * 9 + "extra words here"   # each "word " = 5 chars, 9 × 5 = 45; char[45]=' ', char[48]='r'
    # Build precisely: 47 non-space chars + space at position 47, so char[48] = next word
    prefix = "x" * 47 + " " + "overflow"  # char[47]=' ', len prefix = 57
    result = _sanitize_domain(prefix)
    assert len(result) <= 48
    assert not result.endswith(" ")


def test_sanitize_domain_mid_word_cut_finds_last_space():
    from synthadoc.cli.install import _sanitize_domain
    # 48 chars of text with the cut falling mid-word
    s = "Investment Banking Portfolio Management and Risk Analytics"
    result = _sanitize_domain(s)
    assert len(result) <= 48
    assert not result.endswith(" ")
    # Every char in result must come from the original string (no truncation invented words)
    assert s.startswith(result)


def test_sanitize_domain_no_space_hard_truncates():
    """A single word longer than 48 chars is hard-truncated."""
    from synthadoc.cli.install import _sanitize_domain
    long_word = "A" * 60
    result = _sanitize_domain(long_word)
    assert result == "A" * 48


def test_sanitize_domain_exactly_max_len_unchanged():
    from synthadoc.cli.install import _sanitize_domain, _DOMAIN_MAX_LEN
    s = "x" * _DOMAIN_MAX_LEN
    assert _sanitize_domain(s) == s


# ---------------------------------------------------------------------------
# Domain resolution — CLI integration tests
# ---------------------------------------------------------------------------

def test_install_no_domain_no_template_derives_from_wiki_name(tmp_path, mock_init_wiki):
    """No --domain, no --template: domain derived from wiki name, not 'General'."""
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki) as mock_iw, \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        result = runner.invoke(app, ["install", "my-investment-wiki", "--target", str(tmp_path)])
    assert result.exit_code == 0, result.output
    domain_arg = mock_iw.call_args[0][1]   # second positional arg to init_wiki
    assert domain_arg == "My Investment Wiki"
    assert domain_arg != "General"


def test_install_explicit_domain_short_used_verbatim(tmp_path, mock_init_wiki):
    """Short --domain value is passed through unchanged."""
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki) as mock_iw, \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path),
                                     "--domain", "Investment Banking"])
    assert result.exit_code == 0, result.output
    domain_arg = mock_iw.call_args[0][1]
    assert domain_arg == "Investment Banking"


def test_install_explicit_long_domain_truncated(tmp_path, mock_init_wiki):
    """--domain longer than 48 chars is truncated at a word boundary."""
    long_domain = "Investment Banking Portfolio Management and Risk Analytics for Global Markets"
    with patch("synthadoc.cli.install.init_wiki", side_effect=mock_init_wiki) as mock_iw, \
         patch("synthadoc.cli.install._assign_wiki_port", return_value=7070), \
         patch("synthadoc.cli.install._install_plugin_into", return_value=False):
        result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path),
                                     "--domain", long_domain])
    assert result.exit_code == 0, result.output
    domain_arg = mock_iw.call_args[0][1]
    assert len(domain_arg) <= 48
    assert not domain_arg.endswith(" ")
    assert long_domain.startswith(domain_arg)
