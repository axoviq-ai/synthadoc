# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""synthadoc — domain-agnostic LLM knowledge compilation engine."""
from pathlib import Path as _Path

# Single source of truth: repo root VERSION file.
# Shell scripts, CI, and docs all read VERSION directly.
# Python code imports __version__ from here.
# pyproject.toml delegates to this file via [tool.hatch.version] path.
__version__ = (_Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
