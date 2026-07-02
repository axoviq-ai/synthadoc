# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthadoc.cli.main import app  # noqa: F401 - prevents circular import
from synthadoc.cli.plugin import _set_reading_view_default


def test_set_reading_view_default_creates_app_json(tmp_path):
    """When app.json is absent, it is created with defaultViewMode=preview."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".obsidian").mkdir()

    result = _set_reading_view_default(wiki)
    assert result is True

    app_json = wiki / ".obsidian" / "app.json"
    assert app_json.exists()
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"


def test_set_reading_view_default_preserves_other_keys(tmp_path):
    """Existing keys in app.json are preserved; only defaultViewMode is updated."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    app_json.write_text(
        json.dumps({"theme": "obsidian", "fontSize": 14}), encoding="utf-8"
    )

    _set_reading_view_default(wiki)

    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"
    assert data["theme"] == "obsidian"
    assert data["fontSize"] == 14


def test_set_reading_view_default_idempotent(tmp_path):
    """If app.json already has defaultViewMode=preview, returns False (no-op) and does not rewrite."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    original = json.dumps({"defaultViewMode": "preview", "theme": "dark"})
    app_json.write_text(original, encoding="utf-8")

    result = _set_reading_view_default(wiki)
    assert result is False
    # File should be unchanged (or at minimum have the same content)
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"
    assert data["theme"] == "dark"


def test_set_reading_view_default_malformed_json(tmp_path):
    """Malformed app.json is healed: treated as empty dict, written with defaultViewMode=preview."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    app_json.write_text("{ not valid json }", encoding="utf-8")

    result = _set_reading_view_default(wiki)
    assert result is True  # file was written
    # Verify the file now contains valid JSON with the setting
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"


def test_set_reading_view_default_creates_obsidian_dir(tmp_path):
    """If .obsidian/ does not exist, it is created."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    # .obsidian does NOT exist

    result = _set_reading_view_default(wiki)
    assert result is True
    assert (wiki / ".obsidian" / "app.json").exists()
