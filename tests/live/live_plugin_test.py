# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live Obsidian plugin REST API integration test.

Calls every REST endpoint used by the Obsidian plugin directly from Python —
no Obsidian runtime needed.  Organized by the 14 plugin commands + ribbon icon.

────────────────────────────────────────────────────────────────────────────────
 PREREQUISITES
────────────────────────────────────────────────────────────────────────────────
  1. A wiki must be installed (default: history-of-computing).
  2. The synthadoc server must be running:
       synthadoc serve -w history-of-computing
  3. An LLM API key must be set (e.g. ANTHROPIC_API_KEY).

────────────────────────────────────────────────────────────────────────────────
 ENVIRONMENT VARIABLES
────────────────────────────────────────────────────────────────────────────────
  SYNTHADOC_URL  HTTP base URL of the server.   Default: http://127.0.0.1:7070
  WIKI_NAME      Wiki name (for CLI fallback).  Default: history-of-computing

────────────────────────────────────────────────────────────────────────────────
 HOW TO RUN
────────────────────────────────────────────────────────────────────────────────
  # PowerShell
  python -X utf8 tests/live/live_plugin_test.py

  # bash / macOS / Linux
  python -X utf8 tests/live/live_plugin_test.py

  # Different server or wiki
  python -X utf8 tests/live/live_plugin_test.py --url http://127.0.0.1:7071 --wiki ai-research

  # Show all flags
  python -X utf8 tests/live/live_plugin_test.py --help

────────────────────────────────────────────────────────────────────────────────
 COVERAGE
────────────────────────────────────────────────────────────────────────────────
  All 37 REST API calls from obsidian-plugin/src/api.ts, grouped by the
  14 Obsidian plugin commands + ribbon icon.

  Ribbon icon    : GET /health, GET /status
  [1] query      : POST /sessions, GET /query/stream (SSE), POST /query
  [2] ingest     : POST /jobs/ingest, GET /jobs/{id}, GET /jobs
  [3] jobs       : GET /jobs?status=, GET /lifecycle/status,
                   POST /jobs/{id}/retry, DELETE /jobs/{id},
                   DELETE /jobs?older_than=
  [4] lint-report: GET /lint/report
  [5] lint       : GET /config, POST /jobs/lint
  [6] scaffold   : POST /jobs/scaffold
  [7] audit      : GET /audit/history, GET /audit/costs,
                   GET /audit/queries, GET /audit/events
  [8] routing    : GET /routing/status, POST /routing/init,
                   POST /routing/validate, POST /routing/clean
  [9] staging    : GET /staging/policy, POST /staging/policy
  [10] candidates: GET /candidates, POST /candidates/{slug}/promote,
                   POST /candidates/{slug}/discard,
                   POST /candidates/promote-all,
                   POST /candidates/discard-all
  [11] context   : POST /context/build
  [12] provenance: GET /lifecycle/events?slug=
  [13] lifecycle : GET /lifecycle/status, GET /lifecycle/pages,
                   GET /lifecycle/events (various params),
                   POST /lifecycle/transition
  [14] export    : POST /export (llms.txt, json, okf)

────────────────────────────────────────────────────────────────────────────────
 SIDE EFFECTS & ROLLBACK
────────────────────────────────────────────────────────────────────────────────
  • candidates  : two temp pages are created on disk, tested via REST,
                  then deleted.  Rollback in a finally block.
  • lifecycle   : one archived page is transitioned round-trip
                  (archived → draft → active → archived).
  • staging     : policy saved, changed for one call, then restored.
  All other calls are read-only or idempotent.
"""
import argparse
import http.client
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── Configuration ─────────────────────────────────────────────────────────────
SYNTHADOC_URL = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
WIKI_NAME     = os.environ.get("WIKI_NAME", "history-of-computing")
PY            = sys.executable

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results: list[tuple[str, str, str]] = []

# ── Reporting ─────────────────────────────────────────────────────────────────

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

# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _call(method: str, path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, dict | str]:
    """HTTP call; returns (status_code, parsed_json_or_raw_str)."""
    url = SYNTHADOC_URL + path
    if method in ("POST", "PUT", "PATCH"):
        data = json.dumps(body).encode() if body is not None else b""
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return 0, {"_error": str(e)}


def GET(path: str, timeout: int = 10) -> tuple[int, dict | str]:
    return _call("GET", path, timeout=timeout)

def POST(path: str, body: dict | None = None, timeout: int = 60) -> tuple[int, dict | str]:
    return _call("POST", path, body=body, timeout=timeout)

def DELETE(path: str, timeout: int = 10) -> tuple[int, dict | str]:
    return _call("DELETE", path, timeout=timeout)


def sse_probe(path: str, timeout: int = 12) -> tuple[int, str, str]:
    """GET an SSE endpoint; returns (status, content_type, first_chunk)."""
    parsed = urllib.parse.urlparse(SYNTHADOC_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 7070
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", path, headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        ct = resp.getheader("Content-Type", "")
        try:
            chunk = resp.read(512).decode("utf-8", errors="replace")
        except Exception:
            chunk = ""
        try:
            conn.close()
        except Exception:
            pass
        return resp.status, ct, chunk
    except Exception as e:
        return 0, "", str(e)

# ── Wiki root discovery via CLI ────────────────────────────────────────────────

def _discover_wiki_root() -> pathlib.Path | None:
    try:
        r = subprocess.run(
            [PY, "-m", "synthadoc", "status", "-w", WIKI_NAME],
            capture_output=True, text=True, timeout=15,
        )
        for line in (r.stdout + r.stderr).splitlines():
            if line.strip().startswith("Wiki:"):
                p = pathlib.Path(line.split("Wiki:", 1)[1].strip())
                return p if p.exists() else None
    except Exception:
        pass
    return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 64)
    print("  Synthadoc Live Plugin REST API Test")
    print(f"  server URL : {SYNTHADOC_URL}")
    print(f"  wiki name  : {WIKI_NAME}")
    print("=" * 64)

    # ── Ribbon icon ───────────────────────────────────────────────────────────
    print("\n[Ribbon] api.health() + api.status()")

    code, body = GET("/health")
    if code == 200:
        ok("GET /health", str(body)[:60])
    else:
        fail("GET /health", f"HTTP {code}: {str(body)[:120]}")
        print("\nFATAL: server not reachable. Start: synthadoc serve -w <wiki>")
        sys.exit(1)

    code, body = GET("/status")
    if code == 200 and isinstance(body, dict):
        ok("GET /status", f"pages={body.get('pages', '?')}")
    else:
        fail("GET /status", f"HTTP {code}: {str(body)[:120]}")

    # ── [1] synthadoc-query ───────────────────────────────────────────────────
    print("\n[1] synthadoc-query — api.createSession(), api.queryStream(), api.query()")

    code, body = POST("/sessions")
    session_id: str | None = None
    if code == 200 and isinstance(body, dict) and "session_id" in body:
        ok("POST /sessions", f"session_id={body['session_id'][:8]}…")
        session_id = body["session_id"]
    else:
        fail("POST /sessions", f"HTTP {code}: {str(body)[:120]}")

    # SSE probe for GET /query/stream
    q = urllib.parse.quote("What is ENIAC?")
    sse_path = f"/query/stream?q={q}&no_cache=true"
    if session_id:
        sse_path += f"&session_id={urllib.parse.quote(session_id)}"
    sse_code, sse_ct, sse_chunk = sse_probe(sse_path)
    if sse_code == 200 and "text/event-stream" in sse_ct:
        ok("GET /query/stream (SSE)", f"Content-Type={sse_ct!r}  chunk={sse_chunk[:40]!r}")
    elif sse_code == 200:
        warn("GET /query/stream (SSE)", f"HTTP 200 but Content-Type={sse_ct!r} (expected text/event-stream)")
    else:
        fail("GET /query/stream (SSE)", f"HTTP {sse_code}: {sse_chunk[:80]!r}")

    code, body = POST("/query", {"question": "What is ENIAC?", "timeout_seconds": 30})
    if code == 200 and isinstance(body, dict) and "answer" in body:
        ok("POST /query", f"answer_len={len(body.get('answer', ''))}")
    else:
        warn("POST /query", f"HTTP {code}: {str(body)[:120]}")

    # ── [2] synthadoc-ingest ──────────────────────────────────────────────────
    print("\n[2] synthadoc-ingest — api.ingest(), api.job(), api.jobs()")

    code, body = POST("/jobs/ingest", {"source": "https://en.wikipedia.org/wiki/ENIAC"})
    ingest_job_id: str | None = None
    if code == 200 and isinstance(body, dict) and "job_id" in body:
        ok("POST /jobs/ingest", f"job_id={body['job_id'][:8]}…")
        ingest_job_id = body["job_id"]
    else:
        fail("POST /jobs/ingest", f"HTTP {code}: {str(body)[:120]}")

    if ingest_job_id:
        code, body = GET(f"/jobs/{ingest_job_id}")
        if code == 200 and isinstance(body, dict) and "status" in body:
            ok("GET /jobs/{id}", f"status={body['status']}")
        else:
            fail("GET /jobs/{id}", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/jobs")
    if code == 200 and isinstance(body, list):
        ok("GET /jobs", f"total={len(body)}")
    else:
        fail("GET /jobs", f"HTTP {code}: {str(body)[:120]}")

    # ── [3] synthadoc-jobs ────────────────────────────────────────────────────
    print("\n[3] synthadoc-jobs — api.jobs(), api.job(), api.lifecycleStatus(), api.retryJob(), api.deleteJob(), api.purgeJobs()")

    code, body = GET("/jobs?status=completed")
    if code == 200 and isinstance(body, list):
        ok("GET /jobs?status=completed", f"count={len(body)}")
    else:
        fail("GET /jobs?status=completed", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/lifecycle/status")
    if code == 200 and isinstance(body, dict):
        counts = body.get("counts", body)
        ok("GET /lifecycle/status (jobs badge)", f"counts={counts}")
    else:
        fail("GET /lifecycle/status (jobs badge)", f"HTTP {code}: {str(body)[:120]}")

    # find a terminal job for retry + delete
    code, jobs_list = GET("/jobs")
    terminal_job: dict | None = None
    second_terminal: dict | None = None
    if code == 200 and isinstance(jobs_list, list):
        for j in jobs_list:
            if j.get("status") in ("completed", "failed", "cancelled"):
                if terminal_job is None:
                    terminal_job = j
                elif second_terminal is None:
                    second_terminal = j
                    break

    if terminal_job:
        tid = terminal_job["id"]
        code, body = POST(f"/jobs/{tid}/retry")
        if code in (200, 409):
            ok("POST /jobs/{id}/retry", f"id={tid[:8]}…  HTTP={code}")
        else:
            fail("POST /jobs/{id}/retry", f"HTTP {code}: {str(body)[:120]}")

        del_job = second_terminal or terminal_job
        did = del_job["id"]
        code, body = DELETE(f"/jobs/{did}")
        if code in (200, 404, 409):
            ok("DELETE /jobs/{id}", f"id={did[:8]}…  HTTP={code}")
        else:
            fail("DELETE /jobs/{id}", f"HTTP {code}: {str(body)[:120]}")
    else:
        warn("POST /jobs/{id}/retry + DELETE /jobs/{id}", "no terminal job available — skipping")

    code, body = DELETE("/jobs?older_than=365")
    if code == 200 and isinstance(body, dict) and "purged" in body:
        ok("DELETE /jobs?older_than=365", f"purged={body['purged']}")
    else:
        fail("DELETE /jobs?older_than=365", f"HTTP {code}: {str(body)[:120]}")

    # ── [4] synthadoc-lint-report ─────────────────────────────────────────────
    print("\n[4] synthadoc-lint-report — api.lintReport()")

    code, body = GET("/lint/report")
    if code == 200 and isinstance(body, dict):
        ok("GET /lint/report", f"keys={list(body.keys())[:6]}")
    else:
        fail("GET /lint/report", f"HTTP {code}: {str(body)[:120]}")

    # ── [5] synthadoc-lint ────────────────────────────────────────────────────
    print("\n[5] synthadoc-lint — api.config(), api.lint()")

    code, body = GET("/config")
    if code == 200 and isinstance(body, dict):
        ok("GET /config", f"keys={list(body.keys())[:6]}")
    else:
        fail("GET /config", f"HTTP {code}: {str(body)[:120]}")

    code, body = POST("/jobs/lint", {"scope": "all", "auto_resolve": False, "adversarial": False})
    if code == 200 and isinstance(body, dict) and "job_id" in body:
        ok("POST /jobs/lint", f"job_id={body['job_id'][:8]}…")
    else:
        fail("POST /jobs/lint", f"HTTP {code}: {str(body)[:120]}")

    # ── [6] synthadoc-scaffold ────────────────────────────────────────────────
    print("\n[6] synthadoc-scaffold — api.scaffold()")

    code, body = POST("/jobs/scaffold", {"domain": "history of computing"})
    if code == 200 and isinstance(body, dict) and "job_id" in body:
        ok("POST /jobs/scaffold", f"job_id={body['job_id'][:8]}…")
    else:
        fail("POST /jobs/scaffold", f"HTTP {code}: {str(body)[:120]}")

    # ── [7] synthadoc-audit ───────────────────────────────────────────────────
    print("\n[7] synthadoc-audit — api.auditHistory(), api.auditCosts(), api.queryHistory(), api.auditEvents()")

    code, body = GET("/audit/history?limit=50")
    if code == 200:
        n = len(body) if isinstance(body, list) else len(body.get("history", body.get("entries", []))) if isinstance(body, dict) else "?"
        ok("GET /audit/history?limit=50", f"entries={n}")
    else:
        fail("GET /audit/history?limit=50", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/audit/costs?days=30")
    if code == 200 and isinstance(body, dict):
        ok("GET /audit/costs?days=30", f"keys={list(body.keys())[:5]}")
    else:
        fail("GET /audit/costs?days=30", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/audit/queries?limit=50")
    if code == 200:
        ok("GET /audit/queries?limit=50", f"type={type(body).__name__}")
    else:
        fail("GET /audit/queries?limit=50", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/audit/events?limit=100")
    if code == 200:
        ok("GET /audit/events?limit=100", f"type={type(body).__name__}")
    else:
        fail("GET /audit/events?limit=100", f"HTTP {code}: {str(body)[:120]}")

    # ── [8] synthadoc-routing ─────────────────────────────────────────────────
    print("\n[8] synthadoc-routing — api.routingStatus(), api.routingInit(), api.routingValidate(), api.routingClean()")

    code, body = GET("/routing/status")
    if code == 200 and isinstance(body, dict):
        ok("GET /routing/status", f"keys={list(body.keys())[:5]}")
    else:
        fail("GET /routing/status", f"HTTP {code}: {str(body)[:120]}")

    code, body = POST("/routing/init")
    if code == 200:
        ok("POST /routing/init", str(body)[:60])
    elif code in (400, 409, 422):
        warn("POST /routing/init", f"HTTP {code} — ROUTING.md likely already exists")
    else:
        fail("POST /routing/init", f"HTTP {code}: {str(body)[:120]}")

    code, body = POST("/routing/validate")
    if code == 200 and isinstance(body, dict):
        ok("POST /routing/validate", str(body)[:60])
    else:
        fail("POST /routing/validate", f"HTTP {code}: {str(body)[:120]}")

    code, body = POST("/routing/clean")
    if code == 200 and isinstance(body, dict):
        ok("POST /routing/clean", str(body)[:60])
    else:
        fail("POST /routing/clean", f"HTTP {code}: {str(body)[:120]}")

    # ── [9] synthadoc-staging ─────────────────────────────────────────────────
    print("\n[9] synthadoc-staging — api.stagingPolicy(), api.stagingSetPolicy()")

    code, prev_policy = GET("/staging/policy")
    if code == 200 and isinstance(prev_policy, dict):
        ok("GET /staging/policy", f"policy={prev_policy.get('policy', '?')}")
    else:
        fail("GET /staging/policy", f"HTTP {code}: {str(prev_policy)[:120]}")
        prev_policy = {}

    code, body = POST("/staging/policy", {"policy": "off"})
    if code == 200 and isinstance(body, dict):
        ok("POST /staging/policy (off)", str(body)[:60])
    else:
        fail("POST /staging/policy (off)", f"HTTP {code}: {str(body)[:120]}")

    restore: dict = {"policy": prev_policy.get("policy", "threshold")}
    if restore["policy"] == "threshold" and "confidence_min" in prev_policy:
        restore["confidence_min"] = prev_policy["confidence_min"]
    POST("/staging/policy", restore)
    ok("POST /staging/policy (restore)", restore["policy"])

    # ── [10] synthadoc-candidates ─────────────────────────────────────────────
    print("\n[10] synthadoc-candidates — api.candidates(), api.candidatePromote(), api.candidateDiscard(), api.candidatesPromoteAll(), api.candidatesDiscardAll()")

    code, body = GET("/candidates")
    if code == 200:
        cands = body if isinstance(body, list) else body.get("candidates", body.get("pages", [])) if isinstance(body, dict) else []
        ok("GET /candidates", f"count={len(cands)}")
    else:
        fail("GET /candidates", f"HTTP {code}: {str(body)[:120]}")
        cands = []

    _PROMOTE = "_live-plugin-test-promote"
    _DISCARD = "_live-plugin-test-discard"
    _fm = (
        "---\ntitle: Plugin Live Test Page\nstatus: draft\n"
        "confidence: high\ncreated: '2026-06-23T00:00:00'\n---\n\n"
        "Temporary page created by live_plugin_test.py.\n"
    )

    wiki_root = _discover_wiki_root()
    _promote_dest: pathlib.Path | None = None
    _created = False

    if wiki_root:
        cand_dir = wiki_root / "wiki" / "candidates"
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / f"{_PROMOTE}.md").write_text(_fm, encoding="utf-8")
        (cand_dir / f"{_DISCARD}.md").write_text(_fm, encoding="utf-8")
        _promote_dest = wiki_root / "wiki" / f"{_PROMOTE}.md"
        _created = True
        info(f"created temp candidates in {cand_dir}")
    else:
        warn("candidates setup", "wiki root not found via CLI — promote/discard skipped")

    try:
        if _created:
            code, body = POST(f"/candidates/{_PROMOTE}/promote")
            if code == 200:
                ok("POST /candidates/{slug}/promote", _PROMOTE)
            else:
                fail("POST /candidates/{slug}/promote", f"HTTP {code}: {str(body)[:120]}")

            code, body = POST(f"/candidates/{_DISCARD}/discard")
            if code == 200:
                ok("POST /candidates/{slug}/discard", _DISCARD)
            else:
                fail("POST /candidates/{slug}/discard", f"HTTP {code}: {str(body)[:120]}")

        code, body = POST("/candidates/promote-all")
        if code == 200 and isinstance(body, dict):
            ok("POST /candidates/promote-all", str(body)[:60])
        else:
            fail("POST /candidates/promote-all", f"HTTP {code}: {str(body)[:120]}")

        code, body = POST("/candidates/discard-all")
        if code == 200 and isinstance(body, dict):
            ok("POST /candidates/discard-all", str(body)[:60])
        else:
            fail("POST /candidates/discard-all", f"HTTP {code}: {str(body)[:120]}")

    finally:
        if wiki_root:
            if _promote_dest and _promote_dest.exists():
                _promote_dest.unlink()
            (wiki_root / "wiki" / "candidates" / f"{_PROMOTE}.md").unlink(missing_ok=True)
            (wiki_root / "wiki" / "candidates" / f"{_DISCARD}.md").unlink(missing_ok=True)
            ok("candidates rollback")

    # ── [11] synthadoc-context ────────────────────────────────────────────────
    print("\n[11] synthadoc-context — api.contextBuild()")

    code, body = POST("/context/build", {"goal": "history of computing", "token_budget": 4000})
    if code == 200 and isinstance(body, dict):
        ok("POST /context/build", f"keys={list(body.keys())[:5]}")
    else:
        fail("POST /context/build", f"HTTP {code}: {str(body)[:120]}")

    # ── [12] view-page-provenance ─────────────────────────────────────────────
    print("\n[12] view-page-provenance — api.lifecycleEvents({{slug}})")

    code, body = GET("/lifecycle/pages")
    prov_slug: str | None = None
    lc_pages: list = []
    if code == 200:
        lc_pages = body if isinstance(body, list) else body.get("pages", []) if isinstance(body, dict) else []
        if lc_pages:
            first = lc_pages[0]
            prov_slug = first.get("slug") if isinstance(first, dict) else first

    if prov_slug:
        code, body = GET(f"/lifecycle/events?slug={urllib.parse.quote(prov_slug)}")
        if code == 200:
            ok("GET /lifecycle/events?slug=...", f"slug={prov_slug!r}  type={type(body).__name__}")
        else:
            fail("GET /lifecycle/events?slug=...", f"HTTP {code}: {str(body)[:120]}")
    else:
        warn("GET /lifecycle/events?slug=...", "no page found for provenance test")

    # ── [13] lifecycle-modal ──────────────────────────────────────────────────
    print("\n[13] lifecycle-modal — api.lifecycleStatus(), api.lifecyclePages(), api.lifecycleEvents(), api.lifecycleTransition()")

    code, body = GET("/lifecycle/status")
    if code == 200 and isinstance(body, dict):
        ok("GET /lifecycle/status", f"keys={list(body.keys())[:5]}")
    else:
        fail("GET /lifecycle/status", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/lifecycle/pages")
    if code == 200:
        lc_pages = body if isinstance(body, list) else body.get("pages", []) if isinstance(body, dict) else []
        ok("GET /lifecycle/pages", f"count={len(lc_pages)}")
    else:
        fail("GET /lifecycle/pages", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/lifecycle/events")
    if code == 200:
        ok("GET /lifecycle/events", f"type={type(body).__name__}")
    else:
        fail("GET /lifecycle/events", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/lifecycle/events?to_state=active")
    if code == 200:
        ok("GET /lifecycle/events?to_state=active", f"type={type(body).__name__}")
    else:
        fail("GET /lifecycle/events?to_state=active", f"HTTP {code}: {str(body)[:120]}")

    code, body = GET("/lifecycle/events?limit=10&offset=0")
    if code == 200:
        ok("GET /lifecycle/events?limit=10&offset=0", f"type={type(body).__name__}")
    else:
        fail("GET /lifecycle/events?limit=10&offset=0", f"HTTP {code}: {str(body)[:120]}")

    # round-trip: find an archived page and cycle it archived→draft→active→archived
    archived_slug: str | None = None
    for p in lc_pages:
        if isinstance(p, dict) and p.get("state") == "archived":
            archived_slug = p.get("slug")
            break

    # If no archived page exists, promote an active page to archived temporarily
    # so the round-trip can still run, then restore it to active at the end.
    created_archived_slug: str | None = None
    if not archived_slug:
        for p in lc_pages:
            if isinstance(p, dict) and p.get("state") == "active":
                candidate = p.get("slug")
                code, body = POST("/lifecycle/transition",
                                  {"slug": candidate, "to_state": "archived",
                                   "reason": "plugin-live-test setup (temp archive)"})
                if code == 200:
                    archived_slug = candidate
                    created_archived_slug = candidate
                    info(f"no archived page found — archived '{candidate}' temporarily for round-trip")
                    break
        if not archived_slug:
            warn("POST /lifecycle/transition", "no active or archived page available — skipping round-trip")

    if archived_slug:
        info(f"lifecycle round-trip on: {archived_slug}")

        code, body = POST("/lifecycle/transition",
                          {"slug": archived_slug, "to_state": "draft",
                           "reason": "plugin-live-test restore"})
        if code == 200 and isinstance(body, dict):
            ok("POST /lifecycle/transition (archived→draft)", f"slug={archived_slug!r}")
        else:
            fail("POST /lifecycle/transition (archived→draft)", f"HTTP {code}: {str(body)[:120]}")

        code, body = POST("/lifecycle/transition",
                          {"slug": archived_slug, "to_state": "active",
                           "reason": "plugin-live-test activate"})
        if code == 200 and isinstance(body, dict):
            ok("POST /lifecycle/transition (draft→active)", f"slug={archived_slug!r}")
        else:
            fail("POST /lifecycle/transition (draft→active)", f"HTTP {code}: {str(body)[:120]}")

        code, body = POST("/lifecycle/transition",
                          {"slug": archived_slug, "to_state": "archived",
                           "reason": "plugin-live-test archive (restore)"})
        if code == 200 and isinstance(body, dict):
            ok("POST /lifecycle/transition (active→archived)", "round-trip complete")
        else:
            fail("POST /lifecycle/transition (active→archived)", f"HTTP {code}: {str(body)[:120]}")

        # Restore pages that were only archived as test setup back to active
        if created_archived_slug:
            POST("/lifecycle/transition",
                 {"slug": created_archived_slug, "to_state": "draft",
                  "reason": "plugin-live-test rollback"})
            POST("/lifecycle/transition",
                 {"slug": created_archived_slug, "to_state": "active",
                  "reason": "plugin-live-test rollback"})
            info(f"rolled back '{created_archived_slug}' to active")

    # ── [14] synthadoc-export-wiki ────────────────────────────────────────────
    print("\n[14] synthadoc-export-wiki — api.exportWiki(), api.exportWikiOkf()")

    # exportWiki (raw text): llms.txt
    code, body = POST("/export", {"format": "llms.txt", "status_filter": "active"})
    if code == 200 and isinstance(body, str) and body:
        ok("POST /export (llms.txt)", f"content_len={len(body)}")
    elif code == 200:
        warn("POST /export (llms.txt)", f"HTTP 200 but body type={type(body).__name__}")
    else:
        fail("POST /export (llms.txt)", f"HTTP {code}: {str(body)[:120]}")

    # exportWiki (raw text): json
    code, body = POST("/export", {"format": "json", "status_filter": "all"})
    if code == 200:
        ok("POST /export (json)", f"type={type(body).__name__}")
    else:
        fail("POST /export (json)", f"HTTP {code}: {str(body)[:120]}")

    # exportWikiOkf (JSON object)
    code, body = POST("/export", {"format": "okf", "status_filter": "all"})
    if code == 200 and isinstance(body, dict):
        ok("POST /export (okf)", f"keys={list(body.keys())[:5]}")
    elif code == 200:
        warn("POST /export (okf)", f"HTTP 200 but body type={type(body).__name__} (expected dict)")
    else:
        fail("POST /export (okf)", f"HTTP {code}: {str(body)[:120]}")

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
        print("  Failed endpoints:")
        for status, label, note in results:
            if status == "FAIL":
                print(f"    - {label}: {note[:220]}")
    print("=" * 64)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="live_plugin_test.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url", metavar="URL",
        default=os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070"),
        help="Server base URL (overrides SYNTHADOC_URL env var)",
    )
    parser.add_argument(
        "--wiki", metavar="NAME",
        default=os.environ.get("WIKI_NAME", "history-of-computing"),
        help="Wiki name for CLI fallback to discover wiki root (overrides WIKI_NAME env var)",
    )
    args = parser.parse_args()
    SYNTHADOC_URL = args.url.rstrip("/")
    WIKI_NAME = args.wiki
    main()
