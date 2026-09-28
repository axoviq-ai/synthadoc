# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def fmt_ts(ts: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Convert a stored UTC timestamp to local time for display.

    Handles both ISO 8601 strings (``+00:00`` or ``Z`` suffix, as produced by
    ``datetime.now(timezone.utc).isoformat()``) and bare SQLite
    ``datetime('now')`` strings (``YYYY-MM-DD HH:MM:SS``, no tz marker,
    assumed UTC).

    Returns a string in the local system timezone formatted with *fmt*, or
    ``"—"`` when *ts* is ``None`` or empty.
    """
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime(fmt)
    except (ValueError, TypeError):
        return ts[:16] if ts else "—"


def normalise_ts(ts: str) -> str:
    """Normalise *ts* to a full ISO 8601 datetime with an explicit UTC offset.

    Accepts the same inputs as :func:`fmt_ts` plus date-only strings:

    * ``"2026-07-12"``                    → ``"2026-07-12T00:00:00Z"``
    * ``"2026-09-19T00:20:23"``           → ``"2026-09-19T00:20:23Z"``
    * ``"2026-09-19T00:20:23+00:00"``     → ``"2026-09-19T00:20:23Z"``
    * ``"2026-09-19T00:20:23Z"``          → ``"2026-09-19T00:20:23Z"``

    Returns *ts* unchanged when it cannot be parsed.
    """
    if not ts:
        return ts
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        # Last chance: bare date YYYY-MM-DD (fromisoformat won't accept it on
        # Python <3.11 as a datetime; try it as a date and promote to midnight UTC)
        from datetime import date as _date
        try:
            d = _date.fromisoformat(ts[:10])
            dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return ts  # unparseable; pass through unchanged
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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
