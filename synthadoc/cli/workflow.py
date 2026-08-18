# synthadoc/cli/workflow.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""'synthadoc workflow' subcommand group — launch agentic maintenance workflows.

Structure
---------
    synthadoc workflow list
    synthadoc workflow run --name <name> [WORKFLOW_ARGS...] [-w WIKI] [--timeout N]

``synthadoc workflow list`` prints all registered workflows with their
descriptions.

``synthadoc workflow run`` accepts the workflow name via ``--name`` and
forwards any remaining options (e.g. ``--slug``, ``--type``) verbatim to
the workflow's query string so each workflow can parse its own arguments.

The existing _stream_query function in query.py handles all SSE events
including confirm_request (user approval prompts), so the full agentic
loop works identically via CLI and web UI.

Adding a new workflow
---------------------
  1. Implement AgenticWorkflow in a new module under synthadoc/agents/workflows/.
  2. Set MATCH_RE, NAME, and DESCRIPTION on the class.
  3. Add one import line and one entry in ROUTED_WORKFLOWS in _registry.py.
  4. Add one entry to _WORKFLOW_QUERIES below that matches the class MATCH_RE.
  The workflow is then automatically available via ``synthadoc workflow run --name <name>``.
"""
from __future__ import annotations

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

# Query-string templates keyed by workflow NAME.
# Each value is a phrase that matches the workflow's MATCH_RE, triggering
# fast-path routing in ActionAgent without an LLM extraction call.
# Any extra CLI arguments passed by the user are appended verbatim so each
# workflow's build_initial_message can parse them from the query string.
_WORKFLOW_QUERIES: dict[str, str] = {
    "lint-report":             "run lint report",
    "broken-wikilinks":        "scan for broken wikilinks",
    "scaffold":                "run scaffold",
    "contradiction-resolver":  "run contradiction resolver",
    "ingest-lint":             "re-ingest stale pages",
}


@workflow_app.command("list")
def list_workflows() -> None:
    """List all registered agentic workflows available via 'workflow run'."""
    from synthadoc.agents.workflows._registry import CLI_REGISTRY

    if not CLI_REGISTRY:
        typer.echo("No workflows registered.")
        return

    rows = [
        (name, cls.DESCRIPTION or "", cls.CLI_ARGS or "")
        for name, cls in sorted(CLI_REGISTRY.items())
    ]
    name_w = max(len(name) for name in CLI_REGISTRY) + 2
    desc_w = max(len(desc) for _, desc, _ in rows) + 2
    typer.echo(f"{'NAME':<{name_w}}  {'DESCRIPTION':<{desc_w}}  EXTRA ARGS")
    typer.echo("-" * (name_w + 2 + desc_w + 2 + 45))
    for name, desc, args in rows:
        typer.echo(f"{name:<{name_w}}  {desc:<{desc_w}}  {args}")


@workflow_app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run_workflow(
    ctx: typer.Context,
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        metavar="NAME",
        help=(
            "Workflow to run.  Use 'synthadoc workflow list' to see all "
            "available workflows."
        ),
    ),
    wiki: Optional[str] = typer.Option(
        None,
        "--wiki",
        "-w",
        help="Wiki name (defaults to saved default or SYNTHADOC_WIKI env var).",
    ),
    timeout: int = typer.Option(
        3600,
        "--timeout",
        help="Max seconds to wait for the workflow to complete.",
    ),
) -> None:
    """Run an agentic maintenance workflow by name.

    \b
    Any options not listed above are forwarded to the workflow verbatim, so
    each workflow can define its own arguments.

    \b
    Examples:
      synthadoc workflow list
      synthadoc workflow run --name lint-report
      synthadoc workflow run --name broken-wikilinks
      synthadoc workflow run --name scaffold
      synthadoc workflow run --name contradiction-resolver
      synthadoc workflow run --name contradiction-resolver --slug alan-turing
      synthadoc workflow run --name contradiction-resolver --type adversarial
      synthadoc workflow run --name contradiction-resolver --type source-conflict
      synthadoc workflow run --name ingest-lint -w my-wiki
    """
    from synthadoc.agents.workflows._registry import CLI_REGISTRY

    if name not in CLI_REGISTRY:
        available = ", ".join(sorted(CLI_REGISTRY))
        typer.echo(
            f"Error: unknown workflow '{name}'.  "
            f"Available: {available}",
            err=True,
        )
        raise typer.Exit(code=1)

    resolved_wiki = _resolve_wiki(wiki)

    base_query = _WORKFLOW_QUERIES.get(name, f"run {name}")
    extra = " ".join(ctx.args)
    question = f"{base_query} {extra}".strip() if extra else base_query

    _stream_query(resolved_wiki, question, no_cache=True, timeout=timeout)
