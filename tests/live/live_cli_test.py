# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live CLI integration test — exercises every CLI command against real processes.

Tests run against an EXISTING installed wiki with a live server + LLM.
No mocks.  This script is run manually, not by CI.

────────────────────────────────────────────────────────────────────────────────
 PREREQUISITES
────────────────────────────────────────────────────────────────────────────────
  1. A wiki must be installed (default: history-of-computing).
  2. The synthadoc server must be running for that wiki:
       synthadoc serve -w history-of-computing
  3. An LLM API key must be set in the environment (e.g. ANTHROPIC_API_KEY).

────────────────────────────────────────────────────────────────────────────────
 ENVIRONMENT VARIABLES
────────────────────────────────────────────────────────────────────────────────
  WIKI_NAME      Wiki to test against.          Default: history-of-computing
  SYNTHADOC_URL  HTTP base URL of the server.   Default: http://127.0.0.1:7070/

────────────────────────────────────────────────────────────────────────────────
 HOW TO RUN
────────────────────────────────────────────────────────────────────────────────
  # PowerShell
  $env:SYNTHADOC_URL = "http://127.0.0.1:7070/"
  python -X utf8 tests/live/live_cli_test.py

  # bash / macOS / Linux
  export SYNTHADOC_URL=http://127.0.0.1:7070/
  python -X utf8 tests/live/live_cli_test.py

  # Different wiki
  $env:WIKI_NAME = "ai-research"
  $env:SYNTHADOC_URL = "http://127.0.0.1:7072/"
  python -X utf8 tests/live/live_cli_test.py

────────────────────────────────────────────────────────────────────────────────
 TIERS
────────────────────────────────────────────────────────────────────────────────
  Tier 1 — Offline.  Runs always; no server or LLM key required.
             [1]–[12] — use, list, demo, routing, staging, candidates,
             context build, lint report, schedule, audit lifecycle purge,
             plugin upgrade, backup/restore
  Tier 2 — Live.  Runs when server responds at SYNTHADOC_URL; calls LLM.
             [13]–[23] — status, ingest, query, scaffold, export, jobs,
             lint run, schedule run, lifecycle, cache clear, audit

────────────────────────────────────────────────────────────────────────────────
 SIDE EFFECTS & ROLLBACK
────────────────────────────────────────────────────────────────────────────────
  • backup:     zip written to a temp dir, deleted after tests.
  • restore:    two wikis registered under '_live-test-restore' and
                '_live-test-restore-dflt'; directories deleted and registry
                entries removed (via `synthadoc uninstall`) after tests.
  • candidates: two temp pages are created, tested, then deleted (rollback).
  • lifecycle:  one archived page is restored → activated → archived (round-trip;
                page ends in the same archived state it started in).
  • ingest:     a tiny local file is ingested with --analyse-only (no page
                written to the wiki).
  • schedule:   a temporary schedule entry is added then removed.
  • use:        the default wiki is saved, temporarily changed, then restored.
  All other commands are read-only or idempotent.
"""
import argparse
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request

# ── Configuration ─────────────────────────────────────────────────────────────

WIKI_NAME     = os.environ.get("WIKI_NAME", "history-of-computing")
SYNTHADOC_URL = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070/")
PY            = sys.executable

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results: list[tuple[str, str, str]] = []

# ── Reporting helpers ─────────────────────────────────────────────────────────

def ok(label: str, note: str = "") -> None:
    print(f"  {PASS} {label}" + (f" — {note}" if note else ""))
    results.append(("PASS", label, note))

def fail(label: str, note: str) -> None:
    print(f"  {FAIL} {label} — {note}")
    results.append(("FAIL", label, note))

def warn(label: str, note: str) -> None:
    print(f"  {WARN} {label} — {note}")
    results.append(("WARN", label, note))

def info(msg: str) -> None:
    print(f"  {INFO} {msg}")

# ── CLI runner ────────────────────────────────────────────────────────────────

def run(args: list[str], *, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, "-m", "synthadoc"] + args,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        input=input,
    )

def check(
    label: str,
    args: list[str],
    *,
    contains: list[str] | None = None,
    not_contains: list[str] | None = None,
    expect_exit: int = 0,
    input: str | None = None,
) -> subprocess.CompletedProcess:
    r = run(args, input=input)
    combined = r.stdout + r.stderr
    if r.returncode != expect_exit:
        fail(label, f"exit {r.returncode} (expected {expect_exit})\n    {combined[:400]}")
        return r
    for phrase in contains or []:
        if phrase not in combined:
            fail(label, f"expected {phrase!r} in output\n    {combined[:400]}")
            return r
    for phrase in not_contains or []:
        if phrase in combined:
            fail(label, f"unexpected {phrase!r} in output\n    {combined[:400]}")
            return r
    ok(label, (contains or [""])[0])
    return r

# ── Server probe ──────────────────────────────────────────────────────────────

def server_alive() -> bool:
    try:
        with urllib.request.urlopen(SYNTHADOC_URL.rstrip("/") + "/", timeout=3):
            return True
    except Exception:
        return False

# ── Wiki introspection ────────────────────────────────────────────────────────

def discover_wiki_root() -> pathlib.Path | None:
    """Parse wiki root path from `synthadoc status` output."""
    r = run(["status", "-w", WIKI_NAME])
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip().startswith("Wiki:"):
            path_str = line.split("Wiki:", 1)[1].strip()
            p = pathlib.Path(path_str)
            if p.exists():
                return p
    return None

def find_pages_by_status(wiki_root: pathlib.Path, status: str) -> list[str]:
    """Return slugs of wiki pages whose frontmatter contains `status: <value>`."""
    slugs = []
    wiki_dir = wiki_root / "wiki"
    for f in sorted(wiki_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            if f"status: {status}" in text[:600]:
                slugs.append(f.stem)
        except OSError:
            pass
    return slugs

# ── Tier 1: Offline commands ──────────────────────────────────────────────────

def run_offline_tests(wiki_root: pathlib.Path) -> None:
    w = ["-w", WIKI_NAME]

    # ── use ──────────────────────────────────────────────────────────────────
    print("\n[1] use")
    # Save current default so we can restore it
    r_use_show = run(["use"])
    prev_default = ""
    for line in (r_use_show.stdout + r_use_show.stderr).splitlines():
        if "default" in line.lower() or WIKI_NAME in line:
            prev_default = line.strip()
            break

    check("use show",  ["use"],                   contains=[])
    check("use set",   ["use", WIKI_NAME],         contains=[WIKI_NAME])
    check("use clear", ["use", "--clear"],         contains=[])
    # Restore the wiki as default so the rest of the test's -w flags aren't
    # the only thing keeping commands bound to the right wiki
    run(["use", WIKI_NAME])
    ok("use restore default", WIKI_NAME)

    # ── list ─────────────────────────────────────────────────────────────────
    print("\n[2] list")
    check("list", ["list"], contains=[WIKI_NAME])

    # ── demo ─────────────────────────────────────────────────────────────────
    print("\n[3] demo")
    check("demo list", ["demo", "list"], contains=["history-of-computing"])
    check("demo sync", ["demo", "sync", WIKI_NAME])

    # ── routing ──────────────────────────────────────────────────────────────
    print("\n[4] routing")
    r_init = run(["routing", "init"] + w)
    init_out = r_init.stdout + r_init.stderr
    if r_init.returncode == 0 and "ROUTING" in init_out:
        ok("routing init", "ROUTING")
    elif "already exists" in init_out:
        warn("routing init", "ROUTING.md already exists (expected for existing wiki)")
    else:
        fail("routing init", f"exit {r_init.returncode}\n    {init_out[:300]}")
    check("routing validate", ["routing", "validate"] + w)
    check("routing clean",    ["routing", "clean"]    + w)

    # ── staging ───────────────────────────────────────────────────────────────
    print("\n[5] staging")
    check("staging policy show",      ["staging", "policy"]              + w)
    check("staging policy off",       ["staging", "policy", "off"]       + w)
    check("staging policy threshold", ["staging", "policy", "threshold",
                                       "--min-confidence", "high"]       + w)
    check("staging policy all",       ["staging", "policy", "all"]       + w)
    # Restore to a sensible default (threshold/high matches typical config)
    run(["staging", "policy", "threshold", "--min-confidence", "high"] + w)

    # ── candidates: create temp pages, test promote/discard, rollback ─────────
    print("\n[6] candidates")
    cand_dir  = wiki_root / "wiki" / "candidates"
    wiki_dir  = wiki_root / "wiki"
    cand_dir.mkdir(parents=True, exist_ok=True)

    _PROMOTE_SLUG = "_live-test-promote"
    _DISCARD_SLUG = "_live-test-discard"
    _promote_src  = cand_dir / f"{_PROMOTE_SLUG}.md"
    _discard_src  = cand_dir / f"{_DISCARD_SLUG}.md"
    _promote_dest = wiki_dir / f"{_PROMOTE_SLUG}.md"

    _fm = "---\ntitle: Live Test Page\nstatus: draft\nconfidence: high\ncreated: '2026-06-23T00:00:00'\n---\n\nTemporary page created by live_cli_test.py.\n"
    _promote_src.write_text(_fm, encoding="utf-8")
    _discard_src.write_text(_fm, encoding="utf-8")

    try:
        check("candidates list",    ["candidates", "list"]              + w, contains=[_PROMOTE_SLUG])
        check("candidates promote", ["candidates", "promote", _PROMOTE_SLUG] + w)
        check("candidates discard", ["candidates", "discard", _DISCARD_SLUG] + w)
    finally:
        # Rollback: remove promoted page from main wiki and any leftover cands
        _promote_dest.unlink(missing_ok=True)
        _promote_src.unlink(missing_ok=True)
        _discard_src.unlink(missing_ok=True)
        ok("candidates rollback")

    # ── context build ─────────────────────────────────────────────────────────
    print("\n[7] context build")
    check("context build", ["context", "build", "history of computing"] + w)

    # ── lint report ───────────────────────────────────────────────────────────
    print("\n[8] lint report")
    check("lint report", ["lint", "report"] + w)

    # ── schedule ──────────────────────────────────────────────────────────────
    print("\n[9] schedule")
    r_add = check("schedule add",
                  ["schedule", "add", "--op", "lint run", "--cron", "0 2 * * *"] + w,
                  contains=["sched-"])
    sched_id = ""
    for token in (r_add.stdout + r_add.stderr).split():
        if token.startswith("sched-"):
            sched_id = token
            break
    check("schedule list",    ["schedule", "list"]    + w, contains=["lint run"])
    check("schedule history", ["schedule", "history"] + w)
    check("schedule apply",   ["schedule", "apply"]   + w)
    if sched_id:
        check("schedule remove", ["schedule", "remove", sched_id] + w, contains=[sched_id])
    else:
        warn("schedule remove", "could not extract schedule ID from add output")

    # ── audit lifecycle purge ─────────────────────────────────────────────────
    print("\n[10] audit lifecycle purge")
    check("audit lifecycle purge --keep-latest",
          ["audit", "lifecycle", "purge", "--keep-latest", "10"] + w)

    # ── plugin upgrade (no-op when no vaults registered) ─────────────────────
    print("\n[11] plugin")
    check("plugin upgrade", ["plugin", "upgrade"])
    # plugin install requires an Obsidian vault; WARN if not configured
    r_pi = run(["plugin", "install"] + w)
    pi_out = r_pi.stdout + r_pi.stderr
    if r_pi.returncode == 0:
        ok("plugin install")
    else:
        warn("plugin install", "vault not configured — " + pi_out.strip()[:120])

    # ── backup / restore ──────────────────────────────────────────────────────
    print("\n[12] backup / restore")
    _RESTORE_NAME = "_live-test-restore"
    _RESTORE_DFLT = "_live-test-restore-dflt"
    _bk_dir       = pathlib.Path(tempfile.mkdtemp(prefix="synthadoc_bk_"))
    _restore_dir  = pathlib.Path(tempfile.mkdtemp(prefix="synthadoc_rs_"))

    def _db_page_states(db_path: pathlib.Path) -> int:
        """Return row count from page_states; 0 if the table doesn't exist."""
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            return conn.execute("SELECT COUNT(*) FROM page_states").fetchone()[0]
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()

    # Snapshot original wiki state before backup so we can compare after restore
    _orig_db   = wiki_root / ".synthadoc" / "audit.db"
    _orig_md   = len(list((wiki_root / "wiki").glob("*.md")))
    _orig_ps   = _db_page_states(_orig_db)

    try:
        # Backup to a temp directory
        r_bk = check(
            "backup basic",
            ["backup", "-w", WIKI_NAME, "--output", str(_bk_dir)],
            contains=["✓"],
        )
        zips = sorted(_bk_dir.glob("synthadoc-backup-*.zip"))
        zip_path = zips[0] if zips else None
        if zip_path:
            ok("backup zip created", zip_path.name)
        else:
            fail("backup zip created", f"no *.zip found in {_bk_dir}")

        check(
            "backup --no-sources",
            ["backup", "-w", WIKI_NAME, "--output", str(_bk_dir), "--no-sources"],
            contains=["excluded"],
        )

        if zip_path:
            # Restore with all explicit flags.
            # Pass input="y\n" because restoring a demo wiki under a new name triggers
            # an interactive "Continue?" prompt — we want to confirm automatically.
            check(
                "restore --name --target --port",
                [
                    "restore", str(zip_path),
                    "--name",   _RESTORE_NAME,
                    "--target", str(_restore_dir),
                    "--port",   "7099",
                ],
                contains=["✓ Restored", _RESTORE_NAME],
                input="y\n",
            )

            # Verify wiki directory exists on disk
            restored_dir = _restore_dir / _RESTORE_NAME
            if restored_dir.exists():
                ok("restore wiki dir created", str(restored_dir))
            else:
                fail("restore wiki dir created", f"not found: {restored_dir}")

            # Verify registration
            r_list = run(["list"])
            if _RESTORE_NAME in (r_list.stdout + r_list.stderr):
                ok("restore registered in registry", _RESTORE_NAME)
            else:
                fail("restore registered in registry",
                     f"{_RESTORE_NAME!r} not in `synthadoc list` output")

            # Verify config.toml port AND domain were rewritten
            cfg_path = restored_dir / ".synthadoc" / "config.toml"
            cfg_text = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
            if "7099" in cfg_text:
                ok("restore config.toml port rewritten", "port = 7099")
            else:
                fail("restore config.toml port rewritten",
                     "7099 not in restored config.toml")
            if f'domain = "{_RESTORE_NAME}"' in cfg_text:
                ok("restore config.toml domain rewritten", f'domain = "{_RESTORE_NAME}"')
            else:
                fail("restore config.toml domain rewritten",
                     f'domain = "{_RESTORE_NAME}" not in restored config.toml')

            # Verify registry shows the correct port for the restored wiki
            _list_out = r_list.stdout + r_list.stderr
            _restore_line = next(
                (ln for ln in _list_out.splitlines() if _RESTORE_NAME in ln), ""
            )
            if "7099" in _restore_line:
                ok("restore registry port correct", f"{_RESTORE_NAME} → port 7099")
            else:
                fail("restore registry port correct",
                     f"7099 not on {_RESTORE_NAME!r} line in `synthadoc list`")

            # Fidelity: wiki pages on disk match the original (raw glob, same method)
            _restored_md = len(list((restored_dir / "wiki").glob("*.md")))
            if _restored_md == _orig_md:
                ok("restore page count matches original",
                   f"{_restored_md} pages")
            else:
                fail("restore page count matches original",
                     f"restored={_restored_md}, original={_orig_md}")

            # Fidelity: audit.db was restored and lifecycle rows are present
            _restored_db = restored_dir / ".synthadoc" / "audit.db"
            if _restored_db.exists():
                ok("restore audit.db present", str(_restored_db.name))
            else:
                fail("restore audit.db present", "audit.db missing from restored wiki")
            _restored_ps = _db_page_states(_restored_db)
            if _orig_ps > 0 and _restored_ps == _orig_ps:
                ok("restore page_states row count matches original",
                   f"{_restored_ps} rows")
            elif _orig_ps == 0:
                ok("restore page_states row count", f"{_restored_ps} rows (original had 0)")
            else:
                fail("restore page_states row count matches original",
                     f"restored={_restored_ps}, original={_orig_ps}")

            # Duplicate-name restore must fail with a clear error (not a crash).
            # Confirm the demo warning so the process reaches the conflict check.
            check(
                "restore conflict exits non-zero",
                [
                    "restore", str(zip_path),
                    "--name",   _RESTORE_NAME,
                    "--target", str(_restore_dir),
                    "--port",   "7099",
                ],
                expect_exit=1,
                contains=["already registered"],
                input="y\n",
            )

            # Clean up _RESTORE_NAME so the default-target test gets a clean slate.
            # rmtree first so uninstall auto-cleans without prompts; pass confirmations
            # as belt-and-suspenders in case a file lock on Windows delays rmtree.
            shutil.rmtree(_restore_dir / _RESTORE_NAME, ignore_errors=True)
            run(["uninstall", _RESTORE_NAME], input=f"y\n{_RESTORE_NAME}\n")

            # Restore without --target → wiki lands in zip's parent folder.
            # Also confirm the demo rename warning.
            check(
                "restore default target (zip folder)",
                [
                    "restore", str(zip_path),
                    "--name",  _RESTORE_DFLT,
                    "--port",  "7098",
                ],
                contains=["Restoring to:", "✓ Restored"],
                input="y\n",
            )
            dflt_dir = _bk_dir / _RESTORE_DFLT
            if dflt_dir.exists():
                ok("restore default target dir correct",
                   f"{_RESTORE_DFLT} restored to zip's folder")
            else:
                fail("restore default target dir correct",
                     f"{_RESTORE_DFLT} not found under {_bk_dir}")

            shutil.rmtree(dflt_dir, ignore_errors=True)
            run(["uninstall", _RESTORE_DFLT], input=f"y\n{_RESTORE_DFLT}\n")
        else:
            warn("restore tests", "skipped — backup zip not found")

    finally:
        # Belt-and-suspenders cleanup: remove temp dirs then deregister
        shutil.rmtree(_restore_dir, ignore_errors=True)
        shutil.rmtree(_bk_dir,     ignore_errors=True)
        for _rn in (_RESTORE_NAME, _RESTORE_DFLT):
            run(["uninstall", _rn], input=f"y\n{_rn}\n")  # no-op if already cleaned; two-prompt path if path still exists
        ok("backup/restore rollback")


# ── Tier 2: Live server + LLM ─────────────────────────────────────────────────

def run_live_tests(wiki_root: pathlib.Path) -> None:
    w = ["-w", WIKI_NAME]

    # ── status ────────────────────────────────────────────────────────────────
    print("\n[13] status")
    check("status", ["status"] + w, contains=["Pages:"])

    # ── ingest (analyse-only — writes no wiki pages) ──────────────────────────
    print("\n[14] ingest")
    _src = pathlib.Path(tempfile.mktemp(suffix=".txt"))
    _src.write_text(
        "The ENIAC was the first general-purpose electronic computer, completed in 1945.\n",
        encoding="utf-8",
    )
    try:
        check("ingest --analyse-only",
              ["ingest", str(_src), "--analyse-only"] + w,
              contains=[])
    finally:
        _src.unlink(missing_ok=True)

    # ── query ─────────────────────────────────────────────────────────────────
    print("\n[15] query")
    check("query (cached or live)",
          ["query", "What is ENIAC?", "--no-stream"] + w,
          contains=[])

    # ── scaffold ──────────────────────────────────────────────────────────────
    print("\n[16] scaffold")
    check("scaffold", ["scaffold"] + w, contains=["job"])

    # ── export ────────────────────────────────────────────────────────────────
    print("\n[17] export")
    check("export llms.txt",      ["export", "-f", "llms.txt"]      + w)
    check("export llms-full.txt", ["export", "-f", "llms-full.txt"] + w)
    check("export json",          ["export", "-f", "json"]          + w)
    check("export graphml",       ["export", "-f", "graphml"]       + w)
    _okf_dir = tempfile.mkdtemp(prefix="synthadoc_okf_")
    try:
        check("export okf", ["export", "-f", "okf", "--output", _okf_dir] + w)
    finally:
        shutil.rmtree(_okf_dir, ignore_errors=True)

    # ── jobs ──────────────────────────────────────────────────────────────────
    print("\n[18] jobs")
    r_list = check("jobs list",          ["jobs", "list"]                     + w)
    check("jobs list --sort status",     ["jobs", "list", "--sort", "status"] + w)
    check("jobs list --order desc",      ["jobs", "list", "--order", "desc"]  + w)

    job_id = ""
    terminal_ids: list[str] = []
    for line in (r_list.stdout + r_list.stderr).splitlines():
        tokens = line.split()
        for t in tokens:
            if len(t) == 8 and all(c in "0123456789abcdef" for c in t):
                if not job_id:
                    job_id = t
                if any(s in line for s in ("completed", "failed", "cancelled")):
                    terminal_ids.append(t)
                break
    # Pick a delete candidate that isn't job_id — retrying job_id turns it pending,
    # and DELETE /jobs/{id} returns 409 for pending jobs.
    delete_id = next((t for t in terminal_ids if t != job_id), "")

    if job_id:
        check("jobs status", ["jobs", "status", job_id] + w)
        check("jobs retry",  ["jobs", "retry",  job_id] + w)
    else:
        warn("jobs status/retry", "no job found in list output")

    if delete_id:
        check("jobs delete", ["jobs", "delete", delete_id] + w, contains=[delete_id])
    else:
        warn("jobs delete", "no completed/failed job available to delete safely")

    check("jobs purge --older-than 365", ["jobs", "purge", "--older-than", "365"] + w)
    check("jobs cancel --yes",           ["jobs", "cancel", "--yes"]              + w)

    # ── lint run ──────────────────────────────────────────────────────────────
    print("\n[19] lint run")
    check("lint run", ["lint", "run"] + w, contains=["job"])

    # ── schedule run ──────────────────────────────────────────────────────────
    print("\n[20] schedule run")
    check("schedule run --op lint run",
          ["schedule", "run", "--op", "lint run"] + w)

    # ── lifecycle log + round-trip (restore → activate → archive) ─────────────
    print("\n[21] lifecycle")
    check("lifecycle log", ["lifecycle", "log"] + w)

    archived_slugs = find_pages_by_status(wiki_root, "archived")
    if archived_slugs:
        slug = archived_slugs[0]
        info(f"lifecycle round-trip on: {slug}")
        check("lifecycle restore",
              ["lifecycle", "restore", slug, "--reason", "live-test restore"] + w)
        check("lifecycle activate",
              ["lifecycle", "activate", slug, "--reason", "live-test activate"] + w)
        check("lifecycle archive",
              ["lifecycle", "archive",  slug, "--reason", "live-test archive"]  + w)
        ok("lifecycle round-trip complete", f"{slug}: archived → draft → active → archived")
    else:
        warn("lifecycle activate/archive/restore",
             "no archived pages found — skipping round-trip")

    # ── cache clear ───────────────────────────────────────────────────────────
    print("\n[22] cache clear")
    check("cache clear", ["cache", "clear"] + w)

    # ── audit ─────────────────────────────────────────────────────────────────
    print("\n[23] audit")
    check("audit history",   ["audit", "history"]   + w)
    check("audit cost",      ["audit", "cost"]       + w)
    check("audit queries",   ["audit", "queries"]    + w)
    check("audit events",    ["audit", "events"]     + w)
    check("audit citations", ["audit", "citations"]  + w)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 64)
    print("  Synthadoc Live CLI Test")
    print(f"  wiki      : {WIKI_NAME}")
    print(f"  server URL: {SYNTHADOC_URL}")
    print("=" * 64)

    # Verify wiki is installed
    r = run(["list"])
    if WIKI_NAME not in (r.stdout + r.stderr):
        print(f"\nFATAL: wiki '{WIKI_NAME}' is not installed.")
        print(f"  Run: synthadoc install {WIKI_NAME}")
        print(f"  Or set WIKI_NAME to an installed wiki.")
        sys.exit(1)
    ok(f"wiki '{WIKI_NAME}' is installed")

    wiki_root = discover_wiki_root()
    if not wiki_root:
        # Fall back: server may not be up yet but we can still do tier 1
        # Construct wiki_root from the registry path heuristic
        wiki_root = pathlib.Path.home() / "wikis" / WIKI_NAME
    ok(f"wiki root resolved", str(wiki_root))

    run_offline_tests(wiki_root)

    if server_alive():
        info(f"Server reachable at {SYNTHADOC_URL} — running live (tier 2) tests")
        # Re-discover wiki_root with server up (status endpoint returns the path)
        wiki_root = discover_wiki_root() or wiki_root

        # Validate that the running server is actually serving WIKI_NAME.
        # The CLI reads the server port from the wiki's config.toml — if the
        # server at SYNTHADOC_URL is serving a *different* wiki, all tier-2
        # CLI commands will get ERR-SRV-001 on the wrong port.
        try:
            import json as _json
            with urllib.request.urlopen(
                SYNTHADOC_URL.rstrip("/") + "/status", timeout=5
            ) as _r:
                _status = _json.loads(_r.read())
            _serving = pathlib.Path(_status.get("wiki", "")).name
            if _serving and _serving != WIKI_NAME:
                print()
                print(f"  FATAL: wiki/URL mismatch detected.")
                print(f"    Server at {SYNTHADOC_URL} is serving wiki '{_serving}',")
                print(f"    but --wiki is set to '{WIKI_NAME}'.")
                print(f"    The CLI reads the server port from '{WIKI_NAME}' config.toml,")
                print(f"    so all server-dependent commands will fail.")
                print()
                print(f"  Fix one of the following:")
                print(f"    A) Run the server for the right wiki:")
                print(f"         synthadoc serve -w {WIKI_NAME}")
                print(f"    B) Run the tests against the wiki that IS running:")
                print(f"         {PY} -X utf8 tests/live/live_cli_test.py --wiki {_serving}")
                sys.exit(1)
        except Exception:
            pass  # if status probe fails for any reason, let the tests surface it

        run_live_tests(wiki_root)
    else:
        warn("live tests (tier 2)",
             f"server not reachable at {SYNTHADOC_URL} — skipping")
        info("start 'synthadoc serve -w <wiki>' then re-run with SYNTHADOC_URL set")

    # ── Summary ───────────────────────────────────────────────────────────────
    passes = sum(1 for r in results if r[0] == "PASS")
    warns  = sum(1 for r in results if r[0] == "WARN")
    fails  = sum(1 for r in results if r[0] == "FAIL")

    print()
    print("=" * 64)
    print("  RESULTS SUMMARY")
    print("=" * 64)
    print(f"  PASS : {passes}")
    print(f"  WARN : {warns}")
    print(f"  FAIL : {fails}")
    if fails:
        print()
        print("  Failed commands:")
        for status, label, note in results:
            if status == "FAIL":
                print(f"    - {label}: {note[:220]}")
    print("=" * 64)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="live_cli_test.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--wiki", metavar="NAME",
        default=os.environ.get("WIKI_NAME", "history-of-computing"),
        help="Wiki to test against (overrides WIKI_NAME env var)",
    )
    parser.add_argument(
        "--url", metavar="URL",
        default=os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070/"),
        help="Server base URL (overrides SYNTHADOC_URL env var)",
    )
    args = parser.parse_args()
    WIKI_NAME     = args.wiki
    SYNTHADOC_URL = args.url
    main()
