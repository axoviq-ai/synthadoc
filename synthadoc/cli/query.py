# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re as _re
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get, get_stream, post

# Queries that route to the agentic workflow (orchestrate action).
# These need a much longer server timeout and interactive confirm handling.
_WORKFLOW_RE = _re.compile(
    r"\bre.?ingest\b|\bstale\s+pages?\b|\borchestrat|\bagentic\s+workflow"
    r"|\bcontradiction.{0,30}\bresolv|\bresolv.{0,30}\bcontradict"
    r"|\bfix\s+contradicted\b|\bcontradiction\s+resolver\b",
    _re.IGNORECASE,
)
_WORKFLOW_TIMEOUT = 3600  # seconds — contradiction resolver can run for up to 1 hour


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
    params: dict = {"q": question, "timeout_seconds": timeout}
    if no_cache:
        params["no_cache"] = "true"
    try:
        for event_name, data in get_stream(wiki, "/query/stream", timeout=timeout, **params):
            if event_name == "token":
                typer.echo(data.get("text", ""), nl=False)
            elif event_name == "tool_progress":
                msg = data.get("message", "")
                if msg:
                    typer.echo(f"  {msg}", err=True)
            elif event_name == "confirm_request":
                _handle_confirm(wiki, data)
            elif event_name == "citations":
                citations = data.get("citations", [])
            elif event_name == "gap":
                knowledge_gap = True
                suggested = data.get("suggested_searches", [])
            elif event_name == "error":
                msg = data.get("message", "unknown error")
                typer.echo(f"\nError: {msg}", err=True)
                if "timed out" in msg.lower() and not _WORKFLOW_RE.search(question):
                    typer.echo(
                        f"Tip: local models on CPU-only machines are significantly slower than GPU-accelerated "
                        f"or cloud inference. Pass --timeout {timeout * 2} to allow more time, or switch to a "
                        f"cloud provider (e.g. gemini-2.5-flash-lite is free).",
                        err=True,
                    )
                return
    except (typer.Exit, SystemExit):
        raise
    except Exception as _exc:
        typer.echo(f"\nError: stream interrupted ({type(_exc).__name__}: {_exc})", err=True)
    typer.echo("")  # newline after streamed tokens
    if citations:
        typer.echo("\nSources: " + ", ".join(f"[[{c}]]" for c in citations))
    if knowledge_gap and suggested:
        typer.echo(_format_gap_callout(suggested, wiki))


def _handle_confirm(wiki: str, data: dict) -> None:
    """Print a confirmation prompt and POST the user's response to /action/confirm.

    The ``diff`` field (unified diff string) is included in the SSE payload by
    tool_propose_and_apply so the web UI can render a diff viewer.  The CLI
    prints it before the prompt so users see what changed before approving.
    """
    message = data.get("message", "Proceed?")
    session_id = data.get("session_id", "")
    yes_label = data.get("yes_label", "Yes")
    no_label = data.get("no_label", "No")
    diff = data.get("diff", "")
    typer.echo(f"\n{message}")
    if diff:
        typer.echo("\n  Changes:\n")
        for line in diff.splitlines():
            typer.echo(f"  {line}")
        typer.echo("")
    response = typer.prompt(f"  [{yes_label}/{no_label}]", default="y", prompt_suffix=" > ")
    confirmed = response.strip().lower() in ("y", "yes", yes_label.lower())
    if session_id:
        try:
            post(wiki, "/action/confirm", {"session_id": session_id, "confirmed": confirmed})
        except Exception:
            pass  # Confirm gate will time out on the server if the POST fails


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
    if _WORKFLOW_RE.search(question) and timeout < _WORKFLOW_TIMEOUT:
        timeout = _WORKFLOW_TIMEOUT
    if no_stream:
        params = {"q": question, "timeout_seconds": timeout}
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
