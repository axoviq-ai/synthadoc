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
                   Choices: cli  mcp  plugin  snapshots  (default: all four)

Examples:
    # Run all suites against the default wiki (history-of-computing, port 7070)
    python -X utf8 tests/live/run_all.py

    # Server on a non-default port (wiki name must match what the server serves)
    python -X utf8 tests/live/run_all.py --url http://127.0.0.1:7071

    # Different wiki — server must be running for that wiki
    python -X utf8 tests/live/run_all.py --wiki my-wiki --url http://127.0.0.1:7072

    # Run only the plugin suite
    python -X utf8 tests/live/run_all.py --suite plugin

    # Run CLI and MCP only, skip plugin
    python -X utf8 tests/live/run_all.py --suite cli --suite mcp

    # Run agentic workflow tests only (requires v1.2.0 feature to be shipped)
    python -X utf8 tests/live/run_all.py --suite agentic

    # Run lint report workflow tests only (requires v1.2.1 feature to be shipped)
    python -X utf8 tests/live/run_all.py --suite lint_report

    # Run scaffold workflow tests only (requires v1.2.1 feature to be shipped)
    # Note: the accept-path tests re-scaffold the wiki (index.md etc. overwritten)
    python -X utf8 tests/live/run_all.py --suite scaffold
"""
import argparse
import atexit
import os
import subprocess
import sys
from pathlib import Path

from live_helpers import backup_wiki as _backup_wiki
from live_helpers import register_sigterm_handler as _register_sigterm_handler
from live_helpers import restore_wiki as _restore_wiki

_DEFAULT_WIKI_FILE = Path.home() / ".synthadoc" / "default_wiki"


def _configured_wiki() -> str:
    """Return the wiki set by `synthadoc use`, falling back to history-of-computing."""
    try:
        name = _DEFAULT_WIKI_FILE.read_text(encoding="utf-8").strip()
        return name or "history-of-computing"
    except FileNotFoundError:
        return "history-of-computing"

HERE = Path(__file__).parent

SUITES = {
    "cli":              "live_cli_test.py",
    "mcp":              "live_mcp_test.py",
    "plugin":           "live_plugin_test.py",
    "snapshots":        "test_lifecycle_snapshots_live.py",
    "agentic":          "test_agentic_ingest_lint_live.py",
    "broken_wikilinks": "test_broken_wikilinks_live.py",
    "lint_report":      "test_lint_report_workflow_live.py",
    "scaffold":         "test_scaffold_workflow_live.py",
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
        "--wiki", "-w", metavar="NAME",
        default=_configured_wiki(),
        help="Wiki name (default: wiki set by `synthadoc use`, or history-of-computing)",
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

    # Pre-flight: verify the server is serving the expected wiki before
    # spending time on any suite.  Mismatch causes the CLI suite to fail
    # every server-dependent command with ERR-SRV-001.
    import json as _json
    import urllib.request as _urlreq
    _snap: Path | None = None
    _wiki_root: Path | None = None
    try:
        with _urlreq.urlopen(f"{base}/status", timeout=5) as _r:
            _status = _json.loads(_r.read())
        _serving = Path(_status.get("wiki", "")).name
        _wiki_root_str = _status.get("wiki", "")
        if _wiki_root_str:
            _wiki_root = Path(_wiki_root_str)
        if _serving and _serving != args.wiki:
            print(f"\nERROR: wiki/URL mismatch.")
            print(f"  Server at {base} is serving wiki '{_serving}',")
            print(f"  but --wiki is '{args.wiki}'.")
            print(f"  The CLI reads the server port from '{args.wiki}' config.toml,")
            print(f"  so all server-dependent CLI commands will fail with ERR-SRV-001.")
            print()
            print(f"  Fix one of the following:")
            print(f"    A) Run the server for the right wiki:")
            print(f"         synthadoc serve -w {args.wiki}")
            print(f"    B) Pass the wiki that IS running:")
            print(f"         {sys.executable} -X utf8 tests/live/run_all.py --wiki {_serving}")
            print(f"         {sys.executable} -X utf8 tests/live/run_all.py")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        pass  # server not yet up — individual suites will handle this gracefully

    # Take a snapshot of the wiki before any suite can mutate it so we can
    # restore it automatically when all suites complete (or on Ctrl-C / error).
    if _wiki_root is not None:
        _snap = _backup_wiki(_wiki_root)
        if _snap:
            atexit.register(_restore_wiki, _snap, _wiki_root, args.wiki)
            _register_sigterm_handler()

    # Per-suite CLI args (override env vars for explicit invocation)
    suite_args = {
        "cli":              ["--wiki", args.wiki, "--url", base + "/"],
        "mcp":              [],
        "plugin":           ["--wiki", args.wiki, "--url", base, "--no-restore"],
        "snapshots":        [],
        "agentic":          [],
        "broken_wikilinks": [],
        "lint_report":      [],
        "scaffold":         [],
    }
    # Per-suite environment
    suite_env = {
        "cli":              {**os.environ, "WIKI_NAME": args.wiki, "SYNTHADOC_URL": base + "/"},
        "mcp":              {**os.environ, "MCP_URL": mcp_url},
        "plugin":           {**os.environ, "WIKI_NAME": args.wiki, "SYNTHADOC_URL": base},
        "snapshots":        {**os.environ, "SYNTHADOC_URL": base},
        "agentic":          {**os.environ, "SYNTHADOC_URL": base},
        "broken_wikilinks": {**os.environ, "SYNTHADOC_URL": base},
        "lint_report":      {**os.environ, "SYNTHADOC_URL": base},
        "scaffold":         {**os.environ, "SYNTHADOC_URL": base},
    }

    print(f"\n{'='*64}")
    print("  SYNTHADOC LIVE TESTS")
    print(f"{'='*64}")
    print(f"  url        : {base}")
    print(f"  wiki       : {args.wiki}")
    print(f"  suites     : {', '.join(to_run)}")
    if _snap:
        print(f"  snapshot   : {_snap}  (restored on exit)")
    elif _wiki_root:
        print("  snapshot   : failed — wiki will not be auto-restored")
    else:
        print("  snapshot   : skipped (server not reachable yet)")
    print(f"{'='*64}")

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
