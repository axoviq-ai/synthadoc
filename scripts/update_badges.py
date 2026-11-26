#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Count CLI commands, Obsidian plugin commands, and skills, write docs/badges.json,
and bake the computed values into static shields.io badge URLs in README.md.

Badges are rendered as self-contained `img.shields.io/badge/<label>-<value>-<color>`
URLs (no secondary fetch) rather than `badge/dynamic/json?url=...` — the latter
requires GitHub's/PyPI's image proxy to do a live fetch of docs/badges.json on
every render, and a transient failure in that chain gets cached as a permanently
broken badge image.

Run before committing when you add/remove commands or skills:
    python scripts/update_badges.py

CI runs this with --check to fail the build if badges.json or README.md's
embedded badge values are out of date:
    python scripts/update_badges.py --check

To also update the coverage badge (CI only — requires a coverage.json from pytest-cov):
    python scripts/update_badges.py --coverage-json coverage.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent.parent
README_PATH = ROOT / "README.md"

# key in badges.json -> (alt text of the <img> tag in README.md, badge label,
# fixed color, or None to derive the color from the value via _coverage_color)
_BADGE_SPECS: dict[str, tuple[str, str, str | None, str]] = {
    "coverage": ("Coverage", "Coverage", None, "%"),
    "agents": ("AI agents", "AI agents", "crimson", ""),
    "skills": ("Skills", "Skills", "purple", ""),
    "mcp_tools": ("MCP tools", "MCP tools", "orange", ""),
    "hooks": ("Hook events", "Hook events", "teal", ""),
    "cli_commands": ("CLI commands", "CLI commands", "darkblue", ""),
    "obsidian_commands": ("Obsidian commands", "Obsidian commands", "blueviolet", ""),
    "maintenance_workflows": ("Maintenance workflows", "Maintenance workflows", "green", ""),
}


def count_cli_commands() -> int:
    """Count all executable CLI entry points by introspecting the Typer app directly.

    Counts leaf top-level commands (no subcommands) plus all subcommands of
    grouped commands. Avoids subprocess calls which can fail on CI due to
    terminal width or PATH differences.
    """
    # Ensure the package root is importable
    sys.path.insert(0, str(ROOT))

    # Import the fully-registered app (all sub-modules register on import)
    from synthadoc.cli.main import app  # noqa: PLC0415

    def _count(a: object) -> int:
        n = len(a.registered_commands)  # type: ignore[attr-defined]
        for g in a.registered_groups:   # type: ignore[attr-defined]
            n += _count(g.typer_instance)
        return n

    # Top-level leaf commands + all subcommands (recursive — handles nested
    # sub-apps such as `audit lifecycle purge`)
    return _count(app)


def count_obsidian_commands() -> int:
    """Count addCommand() calls in the Obsidian plugin source."""
    main_ts = ROOT / "obsidian-plugin" / "src" / "main.ts"
    if not main_ts.exists():
        return 0
    return main_ts.read_text(encoding="utf-8").count("this.addCommand(")


def count_mcp_tools() -> int:
    """Count MCP tools registered in mcp_server.py by counting @mcp.tool() decorators."""
    mcp_server_py = ROOT / "synthadoc" / "integration" / "mcp_server.py"
    if not mcp_server_py.exists():
        return 0
    return mcp_server_py.read_text(encoding="utf-8").count("@mcp.tool()")


def count_skills() -> int:
    """Count skill directories that contain a scripts/main.py."""
    skills_dir = ROOT / "synthadoc" / "skills"
    return sum(
        1 for p in skills_dir.iterdir()
        if p.is_dir() and (p / "scripts" / "main.py").exists()
    )


def count_agents() -> int:
    """Count Agent classes defined in synthadoc/agents/*.py.

    Excludes underscore-prefixed files (_base.py, _utils.py, …) which are
    internal modules, not agent implementations.
    """
    import re
    agents_dir = ROOT / "synthadoc" / "agents"
    pattern = re.compile(r"^class \w+Agent[:(]", re.MULTILINE)
    return sum(
        len(pattern.findall(p.read_text(encoding="utf-8")))
        for p in agents_dir.glob("*.py")
        if not p.name.startswith("_")
    )


def count_hooks() -> int:
    """Count hook scripts (.py files) in the hooks/ directory."""
    hooks_dir = ROOT / "hooks"
    return sum(1 for p in hooks_dir.glob("*.py"))


def count_maintenance_workflows() -> int:
    """Count user-facing agentic maintenance workflow entry points.

    Counts concrete AgenticWorkflow subclasses, then adds 1 for
    IngestLintWorkflow which exposes two distinct user-facing modes:
    bulk stale-page re-ingest and per-slug re-ingest.  That gives the
    user-facing count (9) that matches the table in
    docs/user-quick-start-guide.md § Step 26.
    """
    import re
    workflows_dir = ROOT / "synthadoc" / "agents" / "workflows"
    pattern = re.compile(r"^class \w+Workflow\(AgenticWorkflow\)", re.MULTILINE)
    class_count = sum(
        len(pattern.findall(p.read_text(encoding="utf-8")))
        for p in workflows_dir.glob("*.py")
    )
    # IngestLintWorkflow covers two user-facing entry points (bulk + per-slug).
    return class_count + 1


def read_coverage(coverage_json: Path) -> int:
    """Return total coverage as an integer (e.g. 87).

    Stored as a plain integer so shields.io can display it without
    misinterpreting the '%' character. The badge URL adds the suffix.

    Reads the JSON report produced by: pytest --cov=synthadoc --cov-report=json
    """
    data = json.loads(coverage_json.read_text(encoding="utf-8"))
    return round(data["totals"]["percent_covered"])


def _coverage_color(pct: int) -> str:
    if pct >= 80:
        return "brightgreen"
    if pct >= 60:
        return "yellow"
    return "red"


def _static_badge_url(label: str, value: object, color: str, suffix: str) -> str:
    """Build a self-contained shields.io static badge URL — no secondary fetch."""
    message = f"{value}{suffix}"
    return f"https://img.shields.io/badge/{quote(label)}-{quote(message)}-{color}"


def rewrite_readme_badges(readme_text: str, data: dict) -> str:
    """Replace each badge's <img src> with a freshly computed static shields.io URL.

    Matches on the <img>'s alt text (stable across rewrites) rather than the old
    URL, so this works both for the one-time dynamic->static conversion and for
    every later re-run once the badges are already static.
    """
    out = readme_text
    for key, (alt_text, label, fixed_color, suffix) in _BADGE_SPECS.items():
        if key not in data:
            continue  # e.g. coverage not yet known outside CI's --coverage-json run
        color = fixed_color if fixed_color is not None else _coverage_color(data[key])
        url = _static_badge_url(label, data[key], color, suffix)
        pattern = re.compile(rf'(<img src=")[^"]*(" alt="{re.escape(alt_text)}"/>)')
        out, n = pattern.subn(lambda m, u=url: f"{m.group(1)}{u}{m.group(2)}", out)
        if n == 0:
            print(f'WARNING: no <img alt="{alt_text}"/> found in README.md — badge not updated')
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Update docs/badges.json")
    parser.add_argument("--check", action="store_true",
                        help="Exit with error if the static counts in badges.json are out of date")
    parser.add_argument("--coverage-json", metavar="PATH",
                        help="Path to coverage.json produced by pytest --cov-report=json; "
                             "updates the coverage field in badges.json (CI use only)")
    args = parser.parse_args()

    # Static counts — checked by --check and updated locally before commits.
    static = {
        "cli_commands": count_cli_commands(),
        "obsidian_commands": count_obsidian_commands(),
        "skills": count_skills(),
        "mcp_tools": count_mcp_tools(),
        "agents": count_agents(),
        "hooks": count_hooks(),
        "maintenance_workflows": count_maintenance_workflows(),
    }

    badges_path = ROOT / "docs" / "badges.json"

    if args.check:
        if not badges_path.exists():
            print("ERROR: docs/badges.json missing. Run: python scripts/update_badges.py")
            sys.exit(1)
        current = json.loads(badges_path.read_text(encoding="utf-8"))
        # Only validate the static fields; coverage is updated by CI separately.
        stale = {k: v for k, v in static.items() if current.get(k) != v}
        if stale:
            print("ERROR: docs/badges.json is out of date.")
            print(f"  Stale fields: {stale}")
            print("Run: python scripts/update_badges.py")
            sys.exit(1)

        readme_text = README_PATH.read_text(encoding="utf-8")
        expected_readme = rewrite_readme_badges(readme_text, {**current, **static})
        if expected_readme != readme_text:
            print("ERROR: README.md's badge values are out of date.")
            print("Run: python scripts/update_badges.py")
            sys.exit(1)

        print(f"OK: docs/badges.json and README.md badges are up to date — {static}")
        return

    # Load existing badges.json to preserve fields we are not recomputing.
    existing: dict = {}
    if badges_path.exists():
        existing = json.loads(badges_path.read_text(encoding="utf-8"))

    data = {**existing, **static}

    if args.coverage_json:
        cov_path = Path(args.coverage_json)
        if not cov_path.exists():
            print(f"ERROR: coverage file not found: {cov_path}")
            sys.exit(1)
        pct = read_coverage(cov_path)
        data["coverage"] = pct                          # integer, e.g. 83
        data["coverage_color"] = _coverage_color(pct)
        print(f"Coverage: {pct}%")

    badges_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs/badges.json: {data}")

    readme_text = README_PATH.read_text(encoding="utf-8")
    new_readme = rewrite_readme_badges(readme_text, data)
    if new_readme != readme_text:
        README_PATH.write_text(new_readme, encoding="utf-8")
        print("Updated README.md badge URLs")


if __name__ == "__main__":
    main()
