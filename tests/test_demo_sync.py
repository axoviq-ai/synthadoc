# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for `synthadoc demo sync`."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synthadoc.cli.main import app

runner = CliRunner()


def _build_demo_template(tmp_path: Path, name: str) -> Path:
    """Create a minimal demo template directory with one raw_sources file."""
    template = tmp_path / "demo_templates" / name
    sources = template / "raw_sources" / "public-domain"
    sources.mkdir(parents=True)
    (sources / "sample-source.txt").write_text("demo content", encoding="utf-8")
    return template


def _build_installed_wiki(tmp_path: Path, name: str) -> Path:
    """Create a minimal installed wiki directory."""
    wiki = tmp_path / "wikis" / name
    (wiki / "raw_sources").mkdir(parents=True)
    (wiki / "wiki").mkdir(parents=True)
    return wiki


def _build_registry(wiki_path: Path, name: str) -> dict:
    return {
        name: {
            "path": str(wiki_path),
            "demo": name,
            "installed": "2026-05-24",
            "port": 7070,
        }
    }


def test_sync_copies_missing_files(tmp_path):
    """A file present in the demo template but absent in the installed wiki is copied."""
    name = "history-of-computing"
    template = _build_demo_template(tmp_path, name)
    installed = _build_installed_wiki(tmp_path, name)
    registry = _build_registry(installed, name)

    with patch("synthadoc.cli.demo._DEMOS", {name: template}), \
         patch("synthadoc.cli.demo._read_registry", return_value=registry):
        result = runner.invoke(app, ["demo", "sync", name])

    assert result.exit_code == 0, result.output
    dest_file = installed / "raw_sources" / "public-domain" / "sample-source.txt"
    assert dest_file.exists(), "Expected file to be copied into installed wiki"
    assert "sample-source.txt" in result.output


def test_sync_skips_existing_files(tmp_path):
    """A file already present in the installed wiki is not overwritten."""
    name = "history-of-computing"
    template = _build_demo_template(tmp_path, name)
    installed = _build_installed_wiki(tmp_path, name)

    # Pre-create the destination file with different content
    dest_dir = installed / "raw_sources" / "public-domain"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "sample-source.txt"
    original_content = "already here — must not be overwritten"
    dest_file.write_text(original_content, encoding="utf-8")

    registry = _build_registry(installed, name)

    with patch("synthadoc.cli.demo._DEMOS", {name: template}), \
         patch("synthadoc.cli.demo._read_registry", return_value=registry):
        result = runner.invoke(app, ["demo", "sync", name])

    assert result.exit_code == 0, result.output
    assert "already up to date" in result.output.lower()
    assert dest_file.read_text(encoding="utf-8") == original_content, (
        "Existing file must not be overwritten"
    )


def test_sync_unknown_wiki(tmp_path):
    """Syncing a wiki not in the registry exits with error message."""
    with patch("synthadoc.cli.demo._read_registry", return_value={}):
        result = runner.invoke(app, ["demo", "sync", "nonexistent-wiki"])

    assert result.exit_code != 0
    assert "not found in registry" in result.output


def test_sync_unknown_demo_template(tmp_path):
    """Syncing when no bundled demo template exists exits with error message."""
    name = "orphan-wiki"
    installed = _build_installed_wiki(tmp_path, name)
    registry = _build_registry(installed, name)

    with patch("synthadoc.cli.demo._DEMOS", {}), \
         patch("synthadoc.cli.demo._read_registry", return_value=registry):
        result = runner.invoke(app, ["demo", "sync", name])

    assert result.exit_code != 0
    assert "No bundled demo template" in result.output
