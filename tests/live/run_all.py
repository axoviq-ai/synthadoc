# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Run all Synthadoc live tests in sequence: CLI, MCP, and Obsidian plugin REST API.

Usage:
    python -X utf8 tests/live/run_all.py [options]

Options:
    --url URL      Server HTTP base URL (default: http://127.0.0.1:7070)
    --wiki NAME    Wiki name to test against (default: history-of-computing)
    --mcp-url URL  MCP SSE endpoint URL (default: <url>/mcp/sse)
    --suite NAME   Run only this suite; repeatable: --suite cli --suite mcp
                   Choices: cli  mcp  plugin  (default: all three)

Examples:
    # Run all suites against default wiki + port
    python -X utf8 tests/live/run_all.py

    # Run against a different wiki and port
    python -X utf8 tests/live/run_all.py --wiki ai-research --url http://127.0.0.1:7071

    # Run only the plugin suite
    python -X utf8 tests/live/run_all.py --suite plugin

    # Run CLI and MCP only, skip plugin
    python -X utf8 tests/live/run_all.py --suite cli --suite mcp
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

SUITES = {
    "cli":    "live_cli_test.py",
    "mcp":    "live_mcp_test.py",
    "plugin": "live_plugin_test.py",
}

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def run_suite(name: str, script: Path, extra_args: list[str], env: dict) -> int:
    print(f"\n{'='*64}")
    print(f"  Running suite: {name.upper()} — {script.name}")
    print(f"{'='*64}")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(script)] + extra_args,
        env=env,
    )
    return r.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="run_all.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url", metavar="URL",
        default="http://127.0.0.1:7070",
        help="Server HTTP base URL (default: http://127.0.0.1:7070)",
    )
    parser.add_argument(
        "--wiki", metavar="NAME",
        default="history-of-computing",
        help="Wiki name (default: history-of-computing)",
    )
    parser.add_argument(
        "--mcp-url", metavar="URL",
        default=None,
        help="MCP SSE endpoint URL (default: <url>/mcp/sse)",
    )
    parser.add_argument(
        "--suite", metavar="NAME",
        action="append",
        choices=list(SUITES),
        help="Run only this suite; repeatable (default: all)",
    )
    args = parser.parse_args()

    base    = args.url.rstrip("/")
    mcp_url = args.mcp_url or f"{base}/mcp/sse"
    to_run  = args.suite or list(SUITES)

    # Per-suite CLI args (override env vars for explicit invocation)
    suite_args = {
        "cli":    ["--wiki", args.wiki, "--url", base + "/"],
        "mcp":    [],
        "plugin": ["--wiki", args.wiki, "--url", base],
    }
    # Per-suite environment
    suite_env = {
        "cli":    {**os.environ, "WIKI_NAME": args.wiki, "SYNTHADOC_URL": base + "/"},
        "mcp":    {**os.environ, "MCP_URL": mcp_url},
        "plugin": {**os.environ, "WIKI_NAME": args.wiki, "SYNTHADOC_URL": base},
    }

    codes: dict[str, int] = {}
    for name in to_run:
        codes[name] = run_suite(
            name,
            HERE / SUITES[name],
            suite_args[name],
            suite_env[name],
        )

    print(f"\n{'='*64}")
    print("  ALL SUITES SUMMARY")
    print(f"{'='*64}")
    for name, code in codes.items():
        mark = PASS if code == 0 else FAIL
        print(f"  [{mark}] {name}")
    print(f"{'='*64}")

    sys.exit(0 if all(c == 0 for c in codes.values()) else 1)


if __name__ == "__main__":
    main()
