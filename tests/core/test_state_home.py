# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""Per-user state follows SYNTHADOC_HOME, so one mounted volume holds all of it."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from synthadoc.core.state_home import state_path


def test_state_path_defaults_to_the_dot_synthadoc_folder(monkeypatch):
    monkeypatch.delenv("SYNTHADOC_HOME", raising=False)
    assert state_path("wikis.json") == Path.home() / ".synthadoc" / "wikis.json"


def test_state_path_follows_synthadoc_home(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNTHADOC_HOME", str(tmp_path))
    assert state_path("skills") == tmp_path / "skills"


def test_a_relative_home_ends_with_a_one_line_message(monkeypatch):
    monkeypatch.setenv("SYNTHADOC_HOME", "relative/dir")
    with pytest.raises(SystemExit) as exc:
        state_path("wikis.json")
    assert "SYNTHADOC_HOME" in str(exc.value) and "\n" not in str(exc.value)


@pytest.mark.parametrize("module, attr, parts", [
    ("synthadoc.cli._wiki", "_REGISTRY", ("wikis.json",)),
    ("synthadoc.cli._wiki", "DEFAULT_WIKI_FILE", ("default_wiki",)),
    ("synthadoc.cli._wiki", "CROSS_WIKI_ROUTING_PATH", ("CROSS_WIKI_ROUTING.md",)),
    ("synthadoc.cli.install", "_REGISTRY", ("wikis.json",)),
    ("synthadoc.agents.skill_agent", "_GLOBAL_SKILLS_DIR", ("skills",)),
])
def test_module_state_locations_follow_synthadoc_home(monkeypatch, tmp_path, module, attr, parts):
    """Evaluated at import, i.e. at process start, which is when Docker sets the variable."""
    mod = importlib.import_module(module)
    monkeypatch.setenv("SYNTHADOC_HOME", str(tmp_path))
    try:
        mod = importlib.reload(mod)
        assert getattr(mod, attr) == tmp_path.joinpath(*parts)
    finally:
        monkeypatch.delenv("SYNTHADOC_HOME", raising=False)
        importlib.reload(mod)


def test_the_embedding_model_cache_defaults_under_synthadoc_home(monkeypatch, tmp_path):
    from synthadoc.storage.search import embed_model_cache_dir
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    monkeypatch.setenv("SYNTHADOC_HOME", str(tmp_path))
    assert embed_model_cache_dir() == tmp_path / "models"
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "elsewhere"))
    assert embed_model_cache_dir() == tmp_path / "elsewhere"
