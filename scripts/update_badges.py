#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Count CLI commands, Obsidian plugin commands, and skills, then write docs/badges.json.

Run before committing when you add/remove commands or skills:
    python scripts/update_badges.py

CI runs this with --check to fail the build if badges.json is out of date:
    python scripts/update_badges.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


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

    total = 0
    for group in app.registered_groups:
        # Each registered group is a sub-Typer (e.g. audit, jobs, lint, schedule)
        sub_app = group.typer_instance
        total += len(sub_app.registered_commands)

    # Leaf commands registered directly on the top-level app
    total += len(app.registered_commands)

    return total


def count_obsidian_commands() -> int:
    """Count addCommand() calls in the Obsidian plugin source."""
    main_ts = ROOT / "obsidian-plugin" / "src" / "main.ts"
    if not main_ts.exists():
        return 0
    return main_ts.read_text(encoding="utf-8").count("this.addCommand(")


def count_skills() -> int:
    """Count skill directories that contain a scripts/main.py."""
    skills_dir = ROOT / "synthadoc" / "skills"
    return sum(
        1 for p in skills_dir.iterdir()
        if p.is_dir() and (p / "scripts" / "main.py").exists()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Update docs/badges.json")
    parser.add_argument("--check", action="store_true",
                        help="Exit with error if badges.json is out of date")
    args = parser.parse_args()

    data = {
        "cli_commands": count_cli_commands(),
        "obsidian_commands": count_obsidian_commands(),
        "skills": count_skills(),
    }

    badges_path = ROOT / "docs" / "badges.json"

    if args.check:
        if not badges_path.exists():
            print("ERROR: docs/badges.json missing. Run: python scripts/update_badges.py")
            sys.exit(1)
        current = json.loads(badges_path.read_text(encoding="utf-8"))
        if current != data:
            print("ERROR: docs/badges.json is out of date.")
            print(f"  Expected: {data}")
            print(f"  Found:    {current}")
            print("Run: python scripts/update_badges.py")
            sys.exit(1)
        print(f"OK: docs/badges.json is up to date — {data}")
        return

    badges_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs/badges.json: {data}")


if __name__ == "__main__":
    main()
