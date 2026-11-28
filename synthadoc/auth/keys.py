# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""API-key format, hashing, names, scopes and expiry. Pure functions, no I/O.

A key is ``sd_<key_id>_<secret>``: ``key_id`` is 12 lowercase hex characters (not secret,
used to look the key up and to name it in lists and audit lines) and ``secret`` is 64 hex
characters (256 bits). Only ``sha256(secret)`` is ever stored.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional

KEY_PREFIX = "sd"
_KEY_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_SECRET_RE = re.compile(r"^[0-9a-f]{64}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")

SCOPES = ("read", "write", "operate", "admin")
ROLE_SCOPES: dict[str, tuple[str, ...]] = {
    "viewer": ("read",),
    "contributor": ("read", "write"),
    "operator": ("read", "write", "operate"),
    "admin": ("read", "write", "operate", "admin"),
}

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class NewKey:
    key_id: str
    secret: str
    secret_hash: str

    @property
    def key(self) -> str:
        return f"{KEY_PREFIX}_{self.key_id}_{self.secret}"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def generate_key() -> NewKey:
    key_id = secrets.token_hex(6)
    secret = secrets.token_hex(32)
    return NewKey(key_id, secret, hash_secret(secret))


def parse_key(text: object) -> Optional[tuple[str, str]]:
    """``(key_id, secret)`` for a well-formed key, else ``None``. Never raises."""
    if not isinstance(text, str):
        return None
    parts = text.strip().split("_")
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        return None
    key_id, secret = parts[1], parts[2]
    if not (_KEY_ID_RE.match(key_id) and _SECRET_RE.match(secret)):
        return None
    return key_id, secret


def looks_like_key_id(text: str) -> bool:
    return bool(_KEY_ID_RE.match(text.lower()))


def validate_name(name: str) -> str:
    """Return *name* when it is a safe label, else raise ``ValueError``.

    ``key list`` prints names to a terminal, so the alphabet is small (no control or
    escape characters). A name shaped like a key id is refused so that
    ``revoke KEY_ID|NAME`` is never ambiguous.
    """
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError("A key name uses only letters, digits and . _ @ - (1 to 64 characters).")
    if looks_like_key_id(name):
        raise ValueError("A key name must not look like a key id (12 hex characters).")
    return name


def parse_scopes(text: str) -> tuple[str, ...]:
    """``"write,read"`` -> ``("read", "write")``: canonical order, no duplicates."""
    wanted = {part.strip().lower() for part in text.split(",") if part.strip()}
    if not wanted:
        raise ValueError("Give at least one scope.")
    unknown = sorted(wanted - set(SCOPES))
    if unknown:
        raise ValueError(f"Unknown scope: {', '.join(unknown)}. Choose from {', '.join(SCOPES)}.")
    return tuple(s for s in SCOPES if s in wanted)


def scopes_for_role(role: str) -> tuple[str, ...]:
    try:
        return ROLE_SCOPES[role.lower()]
    except KeyError:
        raise ValueError(f"Unknown role: {role}. Choose from {', '.join(ROLE_SCOPES)}.") from None


def format_utc(moment: datetime) -> str:
    """Store timestamps in one fixed UTC format."""
    return moment.astimezone(timezone.utc).strftime(UTC_FORMAT)


def parse_utc(text: str) -> datetime:
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=timezone.utc)


_RELATIVE_RE = re.compile(r"^(\d+)([dh])$")


def parse_expiry(text: str, *, now: Optional[datetime] = None,
                 local_tz: Optional[timezone] = None) -> datetime:
    """When a key expires, as an aware UTC datetime.

    ``30d`` and ``12h`` are relative to *now*. A date (``2027-03-01``) means the end of that
    day in the local time zone, so "expires 2027-03-01" reads as "valid through that day".
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    text = text.strip()
    relative = _RELATIVE_RE.match(text)
    if relative:
        amount = int(relative.group(1))
        if amount < 1:
            raise ValueError("An expiry must be in the future.")
        delta = timedelta(days=amount) if relative.group(2) == "d" else timedelta(hours=amount)
        return now + delta
    try:
        day = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Give an expiry as 30d, 12h or a date such as 2027-03-01.") from None
    tz = local_tz or datetime.now().astimezone().tzinfo
    end_of_day = datetime.combine(day, time(23, 59, 59), tzinfo=tz).astimezone(timezone.utc)
    if end_of_day <= now:
        raise ValueError("An expiry must be in the future.")
    return end_of_day
