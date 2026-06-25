# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""synthadoc — domain-agnostic LLM knowledge compilation engine."""
from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
from importlib.metadata import version as _version
from pathlib import Path as _Path

try:
    __version__ = _version("synthadoc")
except _PackageNotFoundError:
    # Fallback for editable installs that haven't been registered yet.
    __version__ = (_Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
