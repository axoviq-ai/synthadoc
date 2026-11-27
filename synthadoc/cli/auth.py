# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""``synthadoc key create | list | revoke`` and ``synthadoc wiki rebind``.

These commands open the API-key store directly. What authorises them is the operating
system: the secret directory is private to the current user, so whoever can run the CLI as
the wiki's owner can create the first admin key (and replace a lost one) with no existing
credential.
"""
from __future__ import annotations

import logging
from typing import Optional

import typer

from synthadoc.auth import keys
from synthadoc.auth.store import AuthStore, AuthStoreError, KeyRecord
from synthadoc.cli._wiki import resolve_wiki, resolve_wiki_path
from synthadoc.security import paths
from synthadoc.utils import fmt_ts

logger = logging.getLogger(__name__)

key_app = typer.Typer(name="key", help="Manage API keys for this wiki.")
wiki_app = typer.Typer(name="wiki", help="Wiki identity and secret-storage maintenance.")

_WHEN = "%Y-%m-%d %H:%M %Z"


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code)


def _secret_error(exc: paths.SecretPathError) -> None:
    """Public message and hint to the operator; the raw detail (paths) only to the log."""
    if exc.detail:
        logger.warning("secret storage: %s", exc.detail)
    _fail(f"{exc.public_message} {exc.hint}".strip())


def _open(wiki: Optional[str], *, create: bool) -> tuple[Optional[AuthStore], object]:
    root = resolve_wiki_path(resolve_wiki(wiki))
    try:
        return AuthStore.open(root, create=create), root
    except paths.SecretPathError as exc:
        _secret_error(exc)
    except AuthStoreError as exc:
        _fail(str(exc))
    raise AssertionError("unreachable")


@key_app.command("create")
def key_create(
    name: str = typer.Option(..., "--name", help="A label, e.g. ci-ingest or alice"),
    role: Optional[str] = typer.Option(None, "--role", help="viewer, contributor, operator or admin"),
    scopes: Optional[str] = typer.Option(None, "--scopes", help="Comma list of read,write,operate,admin"),
    expires: Optional[str] = typer.Option(None, "--expires", help="30d, 12h or a date such as 2027-03-01"),
    quiet: bool = typer.Option(False, "--quiet", help="Print only the key (for scripts)"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """Create an API key. The key is shown once and cannot be shown again."""
    if (role is None) == (scopes is None):
        _fail("Give exactly one of --role or --scopes.", 2)
    try:
        keys.validate_name(name)
        granted = keys.scopes_for_role(role) if role is not None else keys.parse_scopes(scopes)
        expires_at = keys.parse_expiry(expires) if expires else None
    except ValueError as exc:
        _fail(str(exc), 2)
    store, _root = _open(wiki, create=True)
    try:
        made = store.create_key(name, granted, role=role.lower() if role else None,
                                expires_at=expires_at)
    except AuthStoreError as exc:
        _fail(str(exc))
    if quiet:
        typer.echo(made.key)
        return
    rec = made.record
    typer.echo(f"Created key '{rec.name}' ({rec.key_id}) with scopes: {', '.join(rec.scopes)}")
    typer.echo(f"Expires: {fmt_ts(keys.format_utc(rec.expires_at), _WHEN) if rec.expires_at else 'never'}")
    typer.echo("")
    typer.echo(f"  {made.key}")
    typer.echo("")
    typer.echo("Store it now. It cannot be shown again; to replace it, create a new key and revoke this one.")


def _grant(rec: KeyRecord) -> str:
    return rec.role or ",".join(rec.scopes)


@key_app.command("list")
def key_list(
    all_: bool = typer.Option(False, "--all", help="Include revoked and expired keys"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """List API keys (never their secrets)."""
    store, _root = _open(wiki, create=False)
    records = store.list_keys(include_inactive=all_) if store else []
    if not records:
        typer.echo("No keys.")
        return
    now = store._clock()
    typer.echo(f"{'KEY ID':<13}{'NAME':<22}{'GRANTS':<26}{'STATUS':<9}{'EXPIRES':<24}LAST USED")
    for r in records:
        expires = fmt_ts(keys.format_utc(r.expires_at), _WHEN) if r.expires_at else "never"
        used = fmt_ts(keys.format_utc(r.last_used_at), _WHEN) if r.last_used_at else "never"
        typer.echo(f"{r.key_id:<13}{r.name:<22}{_grant(r):<26}{r.status(now):<9}{expires:<24}{used}")


@key_app.command("revoke")
def key_revoke(
    ident: str = typer.Argument(..., metavar="KEY_ID|NAME", help="A key id or a key name"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """Revoke a key. It stops working on the next request."""
    store, _root = _open(wiki, create=False)
    if store is None:
        typer.echo("No keys.")
        raise typer.Exit(1)
    outcome = store.revoke_key(ident)
    if outcome is None:
        _fail(f"No active key matches '{ident}'.")
    rec, changed = outcome
    typer.echo(f"{'Revoked' if changed else 'Already revoked'}: '{rec.name}' ({rec.key_id})")
    if changed and "admin" in rec.scopes and not any(
            "admin" in r.scopes for r in store.list_keys()):
        typer.echo("Note: no active admin key is left. Run `synthadoc key create --role admin` to make one.")


@wiki_app.command("rebind")
def wiki_rebind(
    wiki_id: Optional[str] = typer.Option(
        None, "--wiki-id", help="The wiki id, for a folder restored without its .synthadoc/wiki_id"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """Point this wiki's secrets at its current folder after a move, rename or restore."""
    root = resolve_wiki_path(resolve_wiki(wiki))
    known = paths.read_wiki_id(root)
    chosen = wiki_id or known
    if chosen is None:
        _fail("This folder has no wiki id. Pass --wiki-id with the id of the wiki it belongs to "
              "(the folder name under <SYNTHADOC_HOME>/auth/).", 2)
    try:
        paths.rebind(chosen, root)
    except paths.SecretPathError as exc:
        _secret_error(exc)
    typer.echo(f"Rebound the secrets of wiki {chosen} to {root}")
