# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
import pytest

from synthadoc.config import AuthConfig, load_config

_BASE = '[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n'


def _load(tmp_path, extra=""):
    f = tmp_path / "config.toml"
    f.write_text(_BASE + extra)
    return load_config(project_config=f)


def test_enforce_is_off_by_default(tmp_path):
    assert _load(tmp_path).auth == AuthConfig(enforce=False)


def test_enforce_can_be_turned_on(tmp_path):
    assert _load(tmp_path, "[auth]\nenforce = true\n").auth.enforce is True


@pytest.mark.parametrize("value", ['"false"', '"true"', "1", "0"])
def test_enforce_must_be_a_toml_boolean(tmp_path, value):
    """A string "false" is truthy in Python, which would silently turn enforcement on."""
    with pytest.raises(ValueError, match="enforce"):
        _load(tmp_path, f"[auth]\nenforce = {value}\n")
