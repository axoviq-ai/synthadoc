# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(
    path: Path,
    text: str,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """Write *text* to *path* atomically via a .tmp sibling then os.replace().

    os.replace() is atomic on POSIX and on Windows (Vista+/Python 3.3+), so
    readers never see a partial file. The .tmp sibling lives in the same
    directory as the target, guaranteeing the rename stays on one filesystem.
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding=encoding, newline=newline)
    os.replace(tmp, path)
