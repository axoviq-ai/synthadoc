# synthadoc/cli/run.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""'synthadoc run' subcommand — launch agentic maintenance workflows from the CLI.

Each subcommand builds a natural-language query string and sends it to the
/query/stream endpoint. The existing _stream_query function in query.py handles
all SSE events including confirm_request (user approval prompts), so the full
agentic loop works identically via CLI and web UI.
"""
from typing import Optional

import typer

from synthadoc.cli._wiki import resolve_wiki as _resolve_wiki
from synthadoc.cli.query import _stream_query

run_app = typer.Typer(
    name="run",
    help="Run agentic maintenance workflows interactively.",
    add_completion=False,
)


@run_app.command("contradiction-resolver")
def contradiction_resolver_cmd(
    slug: Optional[str] = typer.Option(
        None, "--slug", metavar="SLUG", help="Resolve only this page slug."
    ),
    type_: Optional[str] = typer.Option(
        None, "--type", metavar="TYPE",
        help="Scope by contradiction type: gate | conflict | all (default: all).",
    ),
    wiki: Optional[str] = typer.Option(
        None, "--wiki", "-w",
        help="Wiki name (defaults to saved default or SYNTHADOC_WIKI env var)."
    ),
    timeout: int = typer.Option(
        3600, "--timeout", help="Max seconds to wait for the workflow to complete."
    ),
) -> None:
    """Interactively resolve pages in 'contradicted' state.

    \b
    The workflow lists contradicted pages, shows a cost estimate, then walks
    through each page with a diff-based approval step. Every change requires
    your approval before it is applied.

    \b
    Examples:
      synthadoc run contradiction-resolver
      synthadoc run contradiction-resolver --slug alan-turing
      synthadoc run contradiction-resolver --type gate
      synthadoc run contradiction-resolver --type conflict -w my-wiki
    """
    resolved_wiki = _resolve_wiki(wiki)

    parts = ["run contradiction resolver"]
    if slug:
        parts.append(f"--slug {slug}")
    if type_:
        parts.append(f"--type {type_}")
    question = " ".join(parts)

    _stream_query(resolved_wiki, question, no_cache=True, timeout=timeout)
