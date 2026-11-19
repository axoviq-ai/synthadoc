# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from synthadoc.config import load_config


def test_wiki_display_name_parsed(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[wiki]\ndomain = "x"\ndisplay_name = "Personal Learning"\n', encoding="utf-8")
    cfg = load_config(project_config=cfg_file)
    assert cfg.wiki.display_name == "Personal Learning"


def test_wiki_display_name_defaults_empty(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[wiki]\ndomain = "x"\n', encoding="utf-8")
    assert load_config(project_config=cfg_file).wiki.display_name == ""
