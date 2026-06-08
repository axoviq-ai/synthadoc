# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get, get_stream


def _format_gap_callout(suggested_searches: list[str], wiki: str) -> str:
    """Build the Obsidian [!tip] callout for a knowledge gap."""
    terminal_cmds = "\n".join(
        f'synthadoc ingest "search for: {s}" -w {wiki}'
        for s in suggested_searches
    )
    return (
        "\n---\n\n"
        "> [!tip] Knowledge Gap Detected\n"
        "> Your wiki doesn't have enough on this topic yet. Enrich it with a web search:\n"
        ">\n"
        "> **From Obsidian:** Open Command Palette (`Cmd+P` / `Ctrl+P`) "
        "→ **Synthadoc: Ingest...** → Web search tab\n"
        ">\n"
        "> **From the terminal:**\n"
        "> ```bash\n"
        + "\n".join(f"> {cmd}" for cmd in terminal_cmds.splitlines()) + "\n"
        "> ```\n"
        ">\n"
        "> After ingesting, re-run your query to get a richer answer."
    )


def _stream_query(wiki: str, question: str, no_cache: bool, timeout: int) -> None:
    """Stream the query response via SSE and print tokens as they arrive."""
    citations = []
    suggested = []
    knowledge_gap = False
    params: dict = {"q": question}
    if no_cache:
        params["no_cache"] = "true"
    try:
        for event_name, data in get_stream(wiki, "/query/stream", timeout=timeout, **params):
            if event_name == "token":
                typer.echo(data.get("text", ""), nl=False)
            elif event_name == "citations":
                citations = data.get("citations", [])
            elif event_name == "gap":
                knowledge_gap = True
                suggested = data.get("suggested_searches", [])
            elif event_name == "error":
                typer.echo(f"\nError: {data.get('message', 'unknown error')}", err=True)
                return
    except Exception as _exc:
        typer.echo(f"\nError: stream interrupted ({type(_exc).__name__}: {_exc})", err=True)
    typer.echo("")  # newline after streamed tokens
    if citations:
        typer.echo("\nSources: " + ", ".join(f"[[{c}]]" for c in citations))
    if knowledge_gap and suggested:
        typer.echo(_format_gap_callout(suggested, wiki))


@app.command("query")
def query_cmd(
    question: str = typer.Argument(..., help="Question to ask the wiki"),
    save: bool = typer.Option(False, "--save", help="Save answer as wiki page"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    timeout: int = typer.Option(60, "--timeout", help="Seconds to wait for the LLM (default 60; increase for slow providers)"),
    no_stream: bool = typer.Option(False, "--no-stream", help="Use blocking endpoint (for scripts/pipes)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache, always call LLM"),
):
    """Query the wiki. Requires synthadoc serve to be running."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    if no_stream:
        params = {"q": question}
        if no_cache:
            params["no_cache"] = "true"
        result = get(wiki, "/query", timeout=timeout, **params)
        typer.echo(result["answer"])
        if result.get("citations"):
            typer.echo("\nSources: " + ", ".join(f"[[{c}]]" for c in result["citations"]))
        if result.get("knowledge_gap") and result.get("suggested_searches"):
            typer.echo(_format_gap_callout(result["suggested_searches"], wiki))
    else:
        _stream_query(wiki, question, no_cache=no_cache, timeout=timeout)
