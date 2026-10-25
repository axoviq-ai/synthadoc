# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter W. / axoviq.com
"""Shipped demo pages are installed into every demo wiki, so keep them clean."""
from __future__ import annotations

import re
from pathlib import Path

import synthadoc

_DEMOS = Path(synthadoc.__file__).parent / "demos"
_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def test_demo_pages_have_no_control_characters():
    pages = sorted(_DEMOS.glob("*/wiki/*.md"))
    assert pages
    bad = [str(p.relative_to(_DEMOS)) for p in pages if _CONTROL.search(p.read_bytes())]
    assert bad == []
