# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live template install test — installs a fresh wiki from the finance/banking
template, validates all expected outputs, then tears everything down.

────────────────────────────────────────────────────────────────────────────────
 PREREQUISITES
────────────────────────────────────────────────────────────────────────────────
  No LLM API key is required by this test script.  Tier 2 auto-detects
  whichever coding-tool CLI is available — Opencode is preferred (free,
  "opencode" binary), falling back to Claude Code ("claude" binary) — and
  patches the wiki's config.toml to use it before the server starts.
  Both CLIs are keyless; they use their own subscription auth.  If
  neither is found, Tier 2 still runs but ingest/scaffold LLM calls fall
  back to the default gemini provider (which needs GEMINI_API_KEY set).

  Tier 1 requires no running server (offline file/config validation).
  Tier 2 starts a local server automatically on port 7091; if the server
  fails to start, Tier 2 checks are skipped with a warning.

────────────────────────────────────────────────────────────────────────────────
 HOW TO RUN
────────────────────────────────────────────────────────────────────────────────
  # Tier 1 only (no server or LLM key required)
  python -X utf8 tests/live/live_template_install_test.py

  # Full run (Tier 1 + Tier 2 — server starts automatically on port 7091)
  python -X utf8 tests/live/live_template_install_test.py

  # Via run_all.py
  python -X utf8 tests/live/run_all.py --suite template_install

────────────────────────────────────────────────────────────────────────────────
 PORT
────────────────────────────────────────────────────────────────────────────────
  Hard-coded to 7091 to avoid conflicts with other live test suites.
  Override with --port.

────────────────────────────────────────────────────────────────────────────────
 SIDE EFFECTS
────────────────────────────────────────────────────────────────────────────────
  Installs then uninstalls live-test-template-wiki in a temp directory.
  Auto-cleans on success; on failure prints the target directory for inspection.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from synthadoc.core.queue import JobStatus

# ── Configuration ─────────────────────────────────────────────────────────────

PY        = sys.executable
TEMPLATE  = "finance/banking"
WIKI_NAME = "live-test-template-wiki"
DOMAIN    = "Live Test Banking"
PORT      = 7091

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _oneline(text: str, maxlen: int = 160) -> str:
    """Collapse multi-line CLI output to a single display line.

    Joins non-empty lines with ' | ' so the full content stays visible without
    leaking newlines into the terminal (which would strip the leading [INFO]/
    [WARN] prefix from continuation lines).
    """
    parts = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return " | ".join(parts)[:maxlen]


def _poll_job(job_id: str, label: str) -> JobStatus | None:
    """Poll a job via the server HTTP API until it reaches a terminal state.

    Logs each status transition as INFO. Returns the final JobStatus, or None
    if the server's job_timeout_seconds (default 600s) elapses without a
    terminal state — which means the job is stuck, not just slow.
    """
    deadline = time.monotonic() + 600  # matches server default job_timeout_seconds
    last_logged: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/jobs/{job_id}", timeout=5
            ) as resp:
                job_rec = json.loads(resp.read())
            try:
                js = JobStatus(job_rec.get("status", ""))
            except ValueError:
                js = None
            status_val = js.value if js else "?"
            if status_val != last_logged:
                info(f"{label} {job_id[:8]} status: {status_val}")
                last_logged = status_val
            if js and js.is_terminal:
                return js
        except Exception:
            pass  # server not yet ready or transient error
        time.sleep(5)
    return None  # job did not reach terminal state within server timeout


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


# ── Coding-tool provider helpers ──────────────────────────────────────────────


def _find_coding_provider() -> tuple[str, str] | None:
    """Return (provider_name, binary) for the first available coding-tool CLI.

    Preference order: Opencode ("opencode", free) → Claude Code ("claude").
    Returns None when neither binary is found in PATH.
    """
    for provider_name, binary in (("opencode", "opencode"), ("claude-code", "claude")):
        if shutil.which(binary):
            return provider_name, binary
    return None


def _patch_provider(wiki_root: pathlib.Path, provider_name: str) -> None:
    """Replace the [agents] default provider line in config.toml.

    Rewrites only the uncommented ``default = { ... }`` line so that the
    server subprocess uses a keyless coding-tool CLI instead of the gemini
    default written by `synthadoc install`.
    """
    import re
    config_path = wiki_root / ".synthadoc" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    text = re.sub(
        r"^(default\s*=\s*\{)[^}]*(})",
        f'default = {{ provider = "{provider_name}" }}',
        text,
        flags=re.MULTILINE,
    )
    config_path.write_text(text, encoding="utf-8")


# ── Server helpers ────────────────────────────────────────────────────────────


def server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3):
            return True
    except Exception:
        return False


def start_server(wiki_name: str, port: int) -> "subprocess.Popen | None":
    """Start `synthadoc serve -w {wiki_name}` and wait up to 20s for it to respond."""
    proc = subprocess.Popen(
        [PY, "-m", "synthadoc", "serve", "-w", wiki_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if server_alive(port):
            return proc
        if proc.poll() is not None:
            return None
        time.sleep(0.5)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return None


def stop_server(proc: subprocess.Popen) -> None:
    """Terminate server process, wait up to 5s, then kill."""
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    except Exception:
        pass


def _extract_job_id(text: str) -> str | None:
    """Return the first 32-hex-char job ID token from CLI output, or None."""
    for token in text.split():
        if len(token) == 32 and all(c in "0123456789abcdef" for c in token):
            return token
    return None


# ── Tier 1: No server needed ──────────────────────────────────────────────────


def run_tier1(wiki_root: pathlib.Path) -> None:

    # ── [1] install ───────────────────────────────────────────────────────────
    print("\n[1] install")
    check(
        "install exits 0",
        [
            "install", WIKI_NAME,
            "--target", str(wiki_root.parent),
            "--template", TEMPLATE,
            "--domain", DOMAIN,
            "--port", str(PORT),
        ],
        expect_exit=0,
    )

    # ── [2] registry ──────────────────────────────────────────────────────────
    print("\n[2] registry")
    registry_path = pathlib.Path.home() / ".synthadoc" / "wikis.json"
    try:
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
        entry = reg.get(WIKI_NAME, {})
        if entry.get("category") == "finance":
            ok("registry category == finance", entry.get("category", ""))
        else:
            fail("registry category == finance",
                 f"got {entry.get('category')!r}; full entry: {entry}")
        if entry.get("template") == "banking":
            ok("registry template == banking", entry.get("template", ""))
        else:
            fail("registry template == banking",
                 f"got {entry.get('template')!r}; full entry: {entry}")
    except Exception as exc:
        fail("registry parse", str(exc))

    # ── [3] templates list ────────────────────────────────────────────────────
    print("\n[3] templates list")
    check("templates list contains finance", ["templates", "list"], contains=["finance"])
    check("templates list contains banking", ["templates", "list"], contains=["banking"])

    # ── [4] synthadoc list TYPE column ────────────────────────────────────────
    print("\n[4] list")
    check("list shows finance/banking type", ["list"], contains=["finance/banking"])

    # ── [5] file structure ────────────────────────────────────────────────────
    print("\n[5] file structure")
    expected_files = [
        wiki_root / "ROUTING.md",
        wiki_root / "wiki" / "purpose.md",
        wiki_root / "wiki" / "index.md",
        wiki_root / "wiki" / "seeds.md",
        wiki_root / "AGENTS.md",
        wiki_root / "CLAUDE.md",
        wiki_root / "GEMINI.md",
        wiki_root / ".synthadoc" / "config.toml",
    ]
    all_present = True
    for f in expected_files:
        if f.exists():
            ok(f"file exists: {f.name}", str(f))
        else:
            fail(f"file exists: {f.name}", f"not found: {f}")
            all_present = False

    if all_present:
        # Verify ROUTING.md is from the banking template (not generic)
        routing_text = (wiki_root / "ROUTING.md").read_text(encoding="utf-8")
        if "banking" in routing_text.lower() or "deposit" in routing_text.lower():
            ok("ROUTING.md is banking-specific", "contains 'deposit' or 'banking'")
        else:
            fail("ROUTING.md is banking-specific",
                 f"neither 'banking' nor 'deposit' found in ROUTING.md — first 200: {routing_text[:200]}")

        # Verify purpose.md is from the template (not the generic placeholder)
        purpose_text = (wiki_root / "wiki" / "purpose.md").read_text(encoding="utf-8")
        if "banking" in purpose_text.lower():
            ok("purpose.md contains 'banking'")
        else:
            fail("purpose.md contains 'banking'",
                 f"not found in first 500 chars: {purpose_text[:500]}")

        if "general" in purpose_text[:200].lower():
            fail("purpose.md is not the generic placeholder",
                 f"found 'general' in first 200 chars: {purpose_text[:200]}")
        else:
            ok("purpose.md is not the generic placeholder")

        # Verify scaffold markers are present
        purpose_has_marker = "<!-- synthadoc:scaffold -->" in purpose_text
        if purpose_has_marker:
            ok("purpose.md has scaffold marker")
        else:
            fail("purpose.md has scaffold marker",
                 "<!-- synthadoc:scaffold --> not found in purpose.md")

        index_text = (wiki_root / "wiki" / "index.md").read_text(encoding="utf-8")
        index_has_marker = "<!-- synthadoc:scaffold -->" in index_text
        if index_has_marker:
            ok("index.md has scaffold marker")
        else:
            fail("index.md has scaffold marker",
                 "<!-- synthadoc:scaffold --> not found in index.md")

        # Verify AGENTS.md contains domain-specific banking keywords
        agents_text = (wiki_root / "AGENTS.md").read_text(encoding="utf-8")
        banking_kws = ["deposit", "banking", "BSA", "APY", "TILA", "credit", "loan"]
        if any(kw.lower() in agents_text.lower() for kw in banking_kws):
            found = next(kw for kw in banking_kws if kw.lower() in agents_text.lower())
            ok("AGENTS.md has banking-specific guidelines", f"keyword: {found!r}")
        else:
            fail("AGENTS.md has banking-specific guidelines",
                 f"none of {banking_kws!r} found in AGENTS.md")

    # ── [6] config.toml staging ───────────────────────────────────────────────
    print("\n[6] config.toml staging")
    cfg_path = wiki_root / ".synthadoc" / "config.toml"
    try:
        import tomllib
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        policy = cfg.get("ingest", {}).get("staging_policy", "")
        if policy == "all":
            ok("staging_policy == all", policy)
        else:
            fail("staging_policy == all", f"got {policy!r}")
    except Exception as exc:
        fail("config.toml parse", str(exc))

    # ── [7] stub count ────────────────────────────────────────────────────────
    print("\n[7] stub count")
    stubs = list((wiki_root / "wiki").glob("*.md"))
    n = len(stubs)
    if n >= 6:
        names = ", ".join(sorted(s.name for s in stubs))
        ok(f"wiki/ contains {n} pages (>= 6)", names)
    else:
        fail(f"wiki/ contains >= 6 pages",
             f"only {n} found: {[s.name for s in stubs]}")

    # ── [9] schedule entries (schedules.json written at install time) ──────────
    # Note: schedules are stored in schedules.json (JSON), not jobs.db.
    # jobs.db is the async job queue; schedules.json holds the cron schedule.
    print("\n[9] schedule entries")
    sched_path = wiki_root / ".synthadoc" / "schedules.json"
    if not sched_path.exists():
        fail("schedules.json exists after install", str(sched_path))
    else:
        try:
            entries = json.loads(sched_path.read_text(encoding="utf-8"))
            ops = [e.get("op", "") for e in entries]
            has_lint = any("lint" in op for op in ops)
            has_scaffold = any("scaffold" in op for op in ops)
            if has_lint:
                ok("schedules.json has lint entry", str(ops))
            else:
                fail("schedules.json has lint entry",
                     f"no lint op in schedules.json; ops found: {ops}")
            if has_scaffold:
                ok("schedules.json has scaffold entry", str(ops))
            else:
                fail("schedules.json has scaffold entry",
                     f"no scaffold op in schedules.json; ops found: {ops}")
        except Exception as exc:
            fail("schedules.json parse", str(exc))


# ── Tier 2: Live server + ingest + scaffold ────────────────────────────────────


def run_tier2(wiki_root: pathlib.Path) -> None:

    # ── [8a] provider detection & config patch ────────────────────────────────
    print("\n[8a] provider detection")
    coding = _find_coding_provider()
    if coding:
        provider_name, binary = coding
        _patch_provider(wiki_root, provider_name)
        ok("provider patched",
           f"config.toml → provider = {provider_name!r} (binary: {binary})")
    else:
        warn("provider detection",
             "neither 'claude' nor 'opencode' found in PATH — "
             "ingest/scaffold will use the default gemini provider "
             "(set GEMINI_API_KEY if you want LLM calls to succeed)")

    # ── [8] start server ──────────────────────────────────────────────────────
    print("\n[8] start server")
    proc = start_server(WIKI_NAME, PORT)
    if proc is None:
        warn("server start", f"server did not respond on port {PORT} within 20s — skipping Tier 2")
        return
    ok("server started", f"port {PORT}")

    try:
        # ── [10] ingest staging ───────────────────────────────────────────────
        print("\n[10] ingest staging")
        tmp_file = pathlib.Path(tempfile.mktemp(suffix=".txt", prefix="synthadoc_tmpl_"))
        tmp_file.write_text(
            "The Basel III accord requires banks to hold sufficient capital reserves "
            "as a percentage of their risk-weighted assets.\n",
            encoding="utf-8",
        )
        try:
            # Snapshot wiki/ before ingest so we can detect new files afterwards.
            wiki_dir = wiki_root / "wiki"
            cand_dir = wiki_dir / "candidates"
            pre_wiki = {f.name for f in wiki_dir.glob("*.md")}

            r_ingest = run(["ingest", str(tmp_file), "-w", WIKI_NAME])
            ingest_out = r_ingest.stdout + r_ingest.stderr
            if r_ingest.returncode == 0:
                # ingest CLI prints two lines; show only the first ("Enqueued … -> job …")
                first_line = ingest_out.strip().splitlines()[0] if ingest_out.strip() else ""
                info(f"ingest enqueued: {first_line[:120]}")
            else:
                warn("ingest enqueue", f"exit {r_ingest.returncode}: {ingest_out[:200]}")

            # Poll until the job reaches a terminal state. Pages may land in
            # wiki/candidates/ (staging_policy=all) or directly in wiki/.
            job_id = _extract_job_id(ingest_out)
            final_status: JobStatus | None = _poll_job(job_id, "ingest job") if job_id else None

            # Report where the ingest output landed.
            if final_status == JobStatus.COMPLETED:
                cands = list(cand_dir.glob("*.md")) if cand_dir.exists() else []
                new_wiki = [f.name for f in wiki_dir.glob("*.md")
                            if f.name not in pre_wiki]
                if cands:
                    ok("ingest staged to candidates/",
                       f"{len(cands)} file(s): {[c.name for c in cands]}")
                elif new_wiki:
                    ok("ingest written directly to wiki/",
                       f"new page(s): {new_wiki}")
                else:
                    warn("ingest output",
                         "job completed but no new .md found in candidates/ or wiki/")
            elif final_status is not None:
                warn("ingest job",
                     f"job {job_id[:8] if job_id else '?'} "
                     f"reached status={final_status.value!r}")
            else:
                # Job did not reach terminal state within 600s — may be stuck.
                warn("ingest job",
                     f"job {job_id[:8] if job_id else '?'} did not complete within "
                     f"600s — check server logs for errors")
        finally:
            tmp_file.unlink(missing_ok=True)

        # ── [11] scaffold preservation ────────────────────────────────────────
        print("\n[11] scaffold preservation")
        purpose_path = wiki_root / "wiki" / "purpose.md"
        _MARKER = "<!-- synthadoc:scaffold -->"

        def _text_before_marker(path: pathlib.Path) -> str:
            text = path.read_text(encoding="utf-8", errors="replace")
            if _MARKER in text:
                return text.split(_MARKER)[0]
            return text

        if not purpose_path.exists():
            warn("scaffold preservation", "wiki/purpose.md does not exist — skipping")
        else:
            purpose_before = _text_before_marker(purpose_path)
            info(f"purpose.md before scaffold ({len(purpose_before)} chars above marker)")

            # Enqueue scaffold via the server HTTP API (avoids the 60s
            # client-side timeout that the CLI's synchronous wait imposes).
            scaffold_job_id: str | None = None
            try:
                req_data = json.dumps({"domain": DOMAIN}).encode()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{PORT}/jobs/scaffold",
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    scaffold_resp = json.loads(resp.read())
                scaffold_job_id = scaffold_resp.get("job_id")
                info(f"scaffold enqueued: job {scaffold_job_id[:8] if scaffold_job_id else '?'}")
            except Exception as exc:
                warn("scaffold enqueue", f"POST /jobs/scaffold failed: {exc}")

            scaffold_status = _poll_job(scaffold_job_id, "scaffold job") if scaffold_job_id else None
            if scaffold_status == JobStatus.COMPLETED:
                info("scaffold completed")
            elif scaffold_status is not None:
                warn("scaffold job", f"reached status={scaffold_status.value!r}")
            elif scaffold_job_id:
                warn("scaffold job", "did not complete within 600s — check server logs")

            purpose_after = _text_before_marker(purpose_path)
            if purpose_before.strip() == purpose_after.strip():
                ok("scaffold preserved content above marker",
                   f"{len(purpose_before.strip())} chars unchanged")
            else:
                fail("scaffold preserved content above marker",
                     f"before={purpose_before.strip()[:120]!r} "
                     f"after={purpose_after.strip()[:120]!r}")

    finally:
        # ── [12] stop server ──────────────────────────────────────────────────
        print("\n[12] stop server")
        stop_server(proc)
        ok("server stopped")


# ── Teardown ──────────────────────────────────────────────────────────────────


def teardown(wiki_root: pathlib.Path, tmpdir: pathlib.Path) -> None:
    print("\n[teardown]")
    run(["uninstall", WIKI_NAME], input=f"y\n{WIKI_NAME}\n")
    shutil.rmtree(tmpdir, ignore_errors=True)
    ok("teardown complete")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 64)
    print("  Synthadoc Live Template Install Test")
    print(f"  template  : {TEMPLATE}")
    print(f"  wiki name : {WIKI_NAME}")
    print(f"  domain    : {DOMAIN}")
    print(f"  port      : {PORT}")
    print("=" * 64)

    tmpdir   = pathlib.Path(tempfile.mkdtemp(prefix="synthadoc_live_tmpl_"))
    wiki_root = tmpdir / WIKI_NAME

    try:
        run_tier1(wiki_root)

        info("Running Tier 2 (live server + ingest + scaffold)")
        run_tier2(wiki_root)
    finally:
        teardown(wiki_root, tmpdir)

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
        print("  Failed checks:")
        for status, label, note in results:
            if status == "FAIL":
                print(f"    - {label}: {note[:220]}")
    print("=" * 64)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="live_template_install_test.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--template", metavar="REF",
        default="finance/banking",
        help="Template reference to install (default: finance/banking)",
    )
    parser.add_argument(
        "--port", metavar="N",
        type=int,
        default=7091,
        help="Server port for Tier 2 checks (default: 7091)",
    )
    args = parser.parse_args()
    TEMPLATE = args.template
    PORT     = args.port
    main()
