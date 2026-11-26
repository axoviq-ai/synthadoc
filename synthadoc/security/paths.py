# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Where Synthadoc keeps secrets, and the wiki identity that keys them.

Secrets live under ``<home>/<area>/<wiki_id>/`` and never inside the wiki folder.
``<home>`` is ``$SYNTHADOC_HOME`` or ``~/.synthadoc``; ``wiki_id`` is a random UUID
stored in ``<wiki>/.synthadoc/wiki_id``. Because that file travels with the folder
(copy, sync, git, restore), every secret directory also records which wiki folder
it was created for (``binding.json``) and refuses a different one until an explicit
:func:`rebind`. A restore onto another machine finds no directory for the id, which
is the intended "needs re-authentication" outcome.

Leaf module: stdlib only (interface spec section 0). Fail closed: any doubt about
the location, ownership or permissions raises :class:`SecretPathError`.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

HOME_ENV = "SYNTHADOC_HOME"
AREAS = frozenset({"auth", "live", "peers"})

_WINDOWS = sys.platform == "win32"
_WIKI_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_REPARSE_POINT = 0x400          # Windows symlinks and junctions
_HOME_HINT = (
    f"Set {HOME_ENV} to a directory outside any git repository and outside the wiki "
    f"(for example {HOME_ENV}=/var/lib/synthadoc, or a path on a mounted volume in Docker)."
)
_REBIND_HINT = ("If this wiki folder was legitimately moved or restored, run "
                "`synthadoc wiki rebind`.")


class SecretPathError(Exception):
    """A secret location or wiki identity is missing, unsafe or does not match.

    ``str(e)`` and ``public_message`` are generic and safe for API clients. ``detail``
    is for the server log only (may contain paths). ``hint`` tells the operator how to
    fix it and is meant for CLI output, not API responses.
    """

    public_message = "Secret storage location is not permitted."

    def __init__(self, detail: str = "", hint: str = "") -> None:
        super().__init__(self.public_message)
        self.detail = detail
        self.hint = hint


# ------------------------------------------------------------------------- home

def synthadoc_home() -> Path:
    """``$SYNTHADOC_HOME`` if set (must be absolute), else ``~/.synthadoc``."""
    raw = os.environ.get(HOME_ENV, "").strip()
    if not raw:
        return Path.home() / ".synthadoc"
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise SecretPathError(f"{HOME_ENV} must be an absolute path, got {raw!r}",
                              f"Set {HOME_ENV} to an absolute path.")
    return p


# --------------------------------------------------------------------- wiki id

def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_WIKI_ID_RE.match(value))


def _create_exclusive(path: Path, text: str) -> None:
    """Create *path* with *text*; FileExistsError if it already exists."""
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_text_settled(path: Path) -> Optional[str]:
    """File text, or None if absent. Waits briefly for a concurrent creator's first write."""
    for _ in range(25):
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        if text.strip():
            return text
        time.sleep(0.01)
    return ""


def _read_id(path: Path) -> Optional[str]:
    text = _read_text_settled(path)
    if text is None:
        return None
    value = text.strip()
    if not _valid_id(value):
        raise SecretPathError(f"{path} does not contain a valid wiki id",
                              "Fix or remove the file; it is never overwritten automatically.")
    return value


def ensure_wiki_id(wiki_root: Path, *, on_created: Optional[Callable[[str], None]] = None) -> str:
    """The wiki's stable id, created lazily on first need.

    Existing wikis have no id, so it is created when first required. ``on_created`` is
    called once, with the new id, only by the caller that created it (the server uses it
    to record the event in the audit trail; this module cannot import the audit code).
    Fails closed if the folder is missing or read-only, or the id file is corrupt.
    """
    root = Path(wiki_root)
    if not root.is_dir():
        raise SecretPathError(f"wiki folder {root} does not exist")
    meta = root / ".synthadoc"
    try:
        meta.mkdir(exist_ok=True)
        if not meta.is_dir():
            raise NotADirectoryError(str(meta))
    except OSError as exc:
        raise SecretPathError(f"cannot use {meta}: {exc}") from exc
    id_file = meta / "wiki_id"
    existing = _read_id(id_file)
    if existing:
        return existing
    new_id = str(uuid.uuid4())
    try:
        _create_exclusive(id_file, new_id + "\n")
    except FileExistsError:                      # another process won the race
        winner = _read_id(id_file)
        if winner:
            return winner
        raise SecretPathError(f"{id_file} appeared but is empty") from None
    except OSError as exc:
        raise SecretPathError(f"cannot write {id_file}: {exc}") from exc
    if on_created is not None:
        on_created(new_id)
    return new_id


# ------------------------------------------------------------- location checks

def _real(path: Path) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def _is_inside(child: str, parent: str) -> bool:
    child, parent = child.rstrip("\\/"), parent.rstrip("\\/")
    return child == parent or child.startswith(parent + os.sep)


def _check_home_location(home: Path, wiki_root: Path) -> None:
    home_real = _real(home)
    if _is_inside(home_real, _real(wiki_root)):
        raise SecretPathError("the secret home is inside the wiki folder", _HOME_HINT)
    probe = Path(home_real)
    for candidate in (probe, *probe.parents):
        if (candidate / ".git").exists():
            raise SecretPathError(f"the secret home is inside a git work tree ({candidate})",
                                  _HOME_HINT)


def _check_area(area: str) -> None:
    if not isinstance(area, str) or area not in AREAS:
        raise SecretPathError(f"unknown secret area {area!r}")


def _check_id(wiki_id: str) -> None:
    if not _valid_id(wiki_id):
        raise SecretPathError("malformed wiki id")


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    if _WINDOWS:
        try:
            return bool(path.lstat().st_file_attributes & _REPARSE_POINT)
        except (OSError, AttributeError):
            return False
    return False


# ---------------------------------------------------------- private directories

def _private_ok_posix(path: Path) -> bool:
    st = path.lstat()
    return (stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode)
            and st.st_uid == os.getuid() and (st.st_mode & 0o077) == 0)


def _private_ok_windows(path: Path) -> bool:
    from synthadoc.security import _winacl
    try:
        _winacl.verify_current_user_only(str(path))
        return True
    except _winacl.AclError:
        return False


def _ensure_private_dir(path: Path) -> Path:
    """Create *path* if needed and make sure only the current user can use it."""
    if _is_link(path):
        raise SecretPathError(f"{path} is a symbolic link or junction")
    try:
        path.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise SecretPathError(f"cannot create {path}: {exc}") from exc
    if not path.is_dir() or _is_link(path):
        raise SecretPathError(f"{path} is not a plain directory")
    if _WINDOWS:
        if not _private_ok_windows(path):
            from synthadoc.security import _winacl
            try:
                _winacl.restrict_to_current_user(str(path))
            except _winacl.AclError as exc:
                raise SecretPathError(f"cannot restrict {path}: {exc}") from exc
            if not _private_ok_windows(path):
                raise SecretPathError(f"cannot verify the ACL of {path}")
    else:
        if path.lstat().st_uid != os.getuid():
            raise SecretPathError(f"{path} is owned by another user")
        if not _private_ok_posix(path):
            try:
                os.chmod(path, 0o700)
            except OSError as exc:
                raise SecretPathError(f"cannot restrict {path}: {exc}") from exc
            if not _private_ok_posix(path):
                raise SecretPathError(f"cannot verify the mode of {path}")
    return path


def _ensure_home(home: Path) -> None:
    try:
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise SecretPathError(f"cannot create {home}: {exc}") from exc


# ---------------------------------------------------------------------- binding

def _write_private_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _binding_text(wiki_id: str, root_real: str) -> str:
    return json.dumps({"wiki_id": wiki_id, "last_path": root_real})


def _check_binding(directory: Path, wiki_id: str, wiki_root: Path) -> None:
    binding = directory / "binding.json"
    root_real = os.path.realpath(str(wiki_root))
    try:
        fd = os.open(str(binding), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    except OSError as exc:
        raise SecretPathError(f"cannot create {binding}: {exc}") from exc
    else:
        try:
            os.write(fd, _binding_text(wiki_id, root_real).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    text = _read_text_settled(binding)
    try:
        data = json.loads(text or "")
        same = (data["wiki_id"] == wiki_id
                and os.path.normcase(os.path.realpath(data["last_path"])) == os.path.normcase(root_real))
    except (ValueError, KeyError, TypeError) as exc:
        raise SecretPathError(f"{binding} is unreadable: {exc}", _REBIND_HINT) from exc
    if not same:
        raise SecretPathError(
            f"{binding} is bound to a different wiki folder than {root_real}", _REBIND_HINT)


# ------------------------------------------------------------------- public API

def secret_dir(area: str, wiki_id: str, *, wiki_root: Path) -> Path:
    """The private directory for ``(area, wiki_id)``, created and verified on every call.

    Refuses: an unknown area or malformed id; a home inside the wiki folder or a git work
    tree; a symlink; a directory another user owns or others can read; and a directory
    bound to a different wiki folder (a copied or moved folder carrying the same id).
    """
    _check_area(area)
    _check_id(wiki_id)
    root = Path(wiki_root)
    home = synthadoc_home()
    _check_home_location(home, root)
    _ensure_home(home)
    directory = _ensure_private_dir(_ensure_private_dir(home / area) / wiki_id)
    _check_binding(directory, wiki_id, root)
    return directory


def rebind(wiki_id: str, wiki_root: Path) -> None:
    """Point every secret directory of *wiki_id* at *wiki_root*. Explicit, admin CLI only.

    For a legitimate move, rename or restore. The id file in *wiki_root* is created if
    missing and must match if present, so a wrong folder cannot take over another
    wiki's secrets by accident.
    """
    _check_id(wiki_id)
    root = Path(wiki_root)
    if not root.is_dir():
        raise SecretPathError(f"wiki folder {root} does not exist")
    meta = root / ".synthadoc"
    try:
        meta.mkdir(exist_ok=True)
        id_file = meta / "wiki_id"
        present = _read_id(id_file)
        if present is None:
            _create_exclusive(id_file, wiki_id + "\n")
        elif present != wiki_id:
            raise SecretPathError("the wiki folder has a different wiki id",
                                  "Rebind with the id stored in that folder, or fix the folder.")
    except OSError as exc:
        raise SecretPathError(f"cannot prepare {meta}: {exc}") from exc
    home = synthadoc_home()
    _check_home_location(home, root)
    updated = 0
    for area in sorted(AREAS):
        directory = home / area / wiki_id
        if not directory.is_dir():
            continue
        _ensure_private_dir(directory)
        _write_private_atomic(directory / "binding.json",
                              _binding_text(wiki_id, os.path.realpath(str(root))))
        updated += 1
    if not updated:
        raise SecretPathError("no secrets are bound to that wiki id",
                              "Check the id; nothing was changed in the secret store.")
