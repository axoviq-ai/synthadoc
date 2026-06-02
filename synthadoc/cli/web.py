# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import re
import webbrowser
from typing import Optional

import httpx
import typer

from synthadoc.cli.main import app


@app.command("web")
def web_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    port: Optional[int] = typer.Option(None, "--port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Print URL without opening browser"),
):
    """Open the local web chat UI in your browser.

    Requires synthadoc serve to be running.
    """
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.cli._http import server_url, _no_server
    wiki = resolve_wiki(wiki)
    base = server_url(wiki)
    if port:
        base = re.sub(r":\d+$", f":{port}", base)
    try:
        httpx.get(f"{base}/", timeout=2)
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.RequestError:
        pass  # connected but transport issue — server is running, proceed
    url = f"{base}/app"
    typer.echo(f"Opening Synthadoc web UI at {url}")
    if not no_browser:
        webbrowser.open(url)
    else:
        typer.echo("(--no-browser: browser not opened)")
