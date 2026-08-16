# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def atomic_write_text(
    path: Path,
    text: str,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """Write *text* to *path* atomically via a .tmp sibling then os.replace().

    On POSIX, os.replace() swaps the directory entry atomically even when
    the target is open by another process — readers never see a partial file.

    On Windows, os.replace() raises PermissionError (WinError 5) when another
    process (e.g. Obsidian) holds the target open without FILE_SHARE_DELETE.
    _replace_windows() retries with exponential backoff so transient editor
    locks do not abort the write.
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding=encoding, newline=newline)
    if sys.platform == "win32":
        _replace_windows(tmp, path)
    else:
        os.replace(tmp, path)


def _replace_windows(
    src: Path,
    dst: Path,
    retries: int = 5,
    base_delay: float = 0.1,
) -> None:
    """os.replace() with exponential-backoff retry for Windows file-share locks.

    Attempts: 1 immediate + up to *retries* waits of base_delay * 2^attempt.
    Default schedule: 0.1 s, 0.2 s, 0.4 s, 0.8 s, 1.6 s — ~3.1 s total.
    Only retries on PermissionError; all other exceptions propagate immediately.
    """
    for attempt in range(retries + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == retries:
                raise
            time.sleep(base_delay * (2 ** attempt))
