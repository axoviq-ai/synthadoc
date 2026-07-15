# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from pathlib import Path
from synthadoc.cli._init import init_wiki


def test_init_wiki_writes_custom_port(tmp_path):
    """config.toml must contain the port passed to init_wiki."""
    init_wiki(tmp_path, domain="Robotics", port=7071)
    config = (tmp_path / ".synthadoc" / "config.toml").read_text()
    assert "port = 7071" in config
    assert "port = 7070" not in config


def test_init_wiki_default_port_is_7070(tmp_path):
    """Default port when not specified must be 7070."""
    init_wiki(tmp_path, domain="General")
    config = (tmp_path / ".synthadoc" / "config.toml").read_text()
    assert "port = 7070" in config


def test_init_wiki_writes_domain_to_config(tmp_path):
    """config.toml must persist the domain under [wiki] domain."""
    init_wiki(tmp_path, domain="Machine Learning", port=7070)
    config = (tmp_path / ".synthadoc" / "config.toml").read_text()
    assert 'domain = "Machine Learning"' in config


def test_init_wiki_creates_expected_files(tmp_path):
    """All scaffold files must be created."""
    init_wiki(tmp_path, domain="General")
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "purpose.md").exists()
    assert (tmp_path / "wiki" / "dashboard.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "GEMINI.md").exists()
    assert (tmp_path / ".synthadoc" / "config.toml").exists()


def test_init_wiki_skill_files_contain_domain(tmp_path):
    """AGENTS.md, CLAUDE.md, GEMINI.md must all contain the domain name."""
    init_wiki(tmp_path, domain="Robotics", port=7072)
    for filename in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        content = (tmp_path / filename).read_text()
        assert "Robotics" in content, f"{filename} missing domain name"


def test_init_wiki_skill_files_contain_port(tmp_path):
    """All three skill files must embed the configured server port."""
    init_wiki(tmp_path, domain="Finance", port=7099)
    for filename in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        content = (tmp_path / filename).read_text()
        assert "7099" in content, f"{filename} missing port"


def test_init_wiki_skill_files_contain_cli_commands(tmp_path):
    """Skill files must contain key CLI commands for quick-reference."""
    init_wiki(tmp_path, domain="General")
    for filename in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        content = (tmp_path / filename).read_text()
        assert "synthadoc serve" in content, f"{filename} missing serve command"
        assert "synthadoc ingest" in content, f"{filename} missing ingest command"
        assert "synthadoc query" in content, f"{filename} missing query command"
        assert "synthadoc lint" in content, f"{filename} missing lint command"
        assert "synthadoc export" in content, f"{filename} missing export command"


def test_init_wiki_skill_files_differ_only_in_header(tmp_path):
    """AGENTS.md, CLAUDE.md, GEMINI.md must differ only in their H1 heading."""
    init_wiki(tmp_path, domain="General")
    agents = (tmp_path / "AGENTS.md").read_text().splitlines()
    claude = (tmp_path / "CLAUDE.md").read_text().splitlines()
    gemini = (tmp_path / "GEMINI.md").read_text().splitlines()
    assert agents[0].startswith("# AGENTS.md")
    assert claude[0].startswith("# CLAUDE.md")
    assert gemini[0].startswith("# GEMINI.md")
    # All lines after the first must be identical
    assert agents[1:] == claude[1:] == gemini[1:]


def test_init_wiki_agents_md_has_mcp_tools_table(tmp_path):
    """AGENTS.md must include the MCP tools reference table."""
    init_wiki(tmp_path, domain="General")
    content = (tmp_path / "AGENTS.md").read_text()
    assert "synthadoc_query" in content
    assert "synthadoc_ingest" in content
    assert "## MCP Tools" in content
