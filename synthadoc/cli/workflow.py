# synthadoc/cli/workflow.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""'synthadoc workflow' subcommand group — launch agentic maintenance workflows.

Structure
---------
    synthadoc workflow run <workflow-name> [OPTIONS]

Each 'run' subcommand builds a natural-language query string and sends it to
the /query/stream endpoint.  The existing _stream_query function in query.py
handles all SSE events including confirm_request (user approval prompts), so
the full agentic loop works identically via CLI and web UI.

Adding a new workflow
---------------------
Register a new command under ``run_app``:

    @run_app.command("my-workflow")
    def my_workflow_cmd(...) -> None:
        ...
"""
from typing import Optional

import typer

from synthadoc.cli._wiki import resolve_wiki as _resolve_wiki
from synthadoc.cli.query import _stream_query

# ── top-level group: synthadoc workflow ───────────────────────────────────────

workflow_app = typer.Typer(
    name="workflow",
    help="Manage and run agentic maintenance workflows.",
    add_completion=False,
)

# ── sub-group: synthadoc workflow run ─────────────────────────────────────────

run_app = typer.Typer(
    name="run",
    help="Run an agentic workflow interactively.",
    add_completion=False,
)
workflow_app.add_typer(run_app)

# Map user-facing --type values to the internal scope token the agent expects.
_TYPE_TO_SCOPE: dict[str, str] = {
    "adversarial": "gate",
    "source-conflict": "conflict",
}


@run_app.command("contradiction-resolver")
def contradiction_resolver_cmd(
    slug: Optional[str] = typer.Option(
        None, "--slug", metavar="SLUG", help="Resolve only this page slug."
    ),
    type_: Optional[str] = typer.Option(
        None, "--type", metavar="TYPE",
        help=(
            "Scope by contradiction type: "
            "adversarial (pages demoted by the adversarial gate) | "
            "source-conflict (pages with source-level contradictions). "
            "Omit to resolve all contradicted pages."
        ),
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
      synthadoc workflow run contradiction-resolver
      synthadoc workflow run contradiction-resolver --slug alan-turing
      synthadoc workflow run contradiction-resolver --type adversarial
      synthadoc workflow run contradiction-resolver --type source-conflict -w my-wiki
    """
    resolved_wiki = _resolve_wiki(wiki)

    # Translate user-facing type name to the internal scope token.
    scope = _TYPE_TO_SCOPE.get(type_ or "", "all")

    parts = ["run contradiction resolver"]
    if slug:
        parts.append(f"--slug {slug}")
    if scope != "all":
        parts.append(f"--type {scope}")
    question = " ".join(parts)

    _stream_query(resolved_wiki, question, no_cache=True, timeout=timeout)
