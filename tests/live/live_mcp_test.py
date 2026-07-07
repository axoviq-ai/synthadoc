# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live MCP integration test — exercises all 12 MCP tools against a running server.

Prerequisites:
    synthadoc serve -w history-of-computing   # starts HTTP + MCP on port 7070

Run (default port 7070):
    python -X utf8 tests/live/live_mcp_test.py

Run against a different port (PowerShell):
    $env:MCP_URL = "http://127.0.0.1:8080/mcp/sse"
    python -X utf8 tests/live/live_mcp_test.py

Run against a different port (bash/macOS/Linux):
    export MCP_URL=http://127.0.0.1:8080/mcp/sse
    python -X utf8 tests/live/live_mcp_test.py

The -X utf8 flag is required on Windows to avoid encoding errors in terminal output.
MCP_URL defaults to http://127.0.0.1:7070/mcp/sse if the env var is not set.
"""
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:7070/mcp/sse")
_HTTP_BASE = MCP_URL.split("/mcp/sse")[0].rstrip("/")

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results = []


def ok(tool, note=""):
    tag = f"  {PASS} {tool}"
    if note:
        tag += f" — {note}"
    print(tag)
    results.append(("PASS", tool, note))


def fail(tool, note):
    print(f"  {FAIL} {tool} — {note}")
    results.append(("FAIL", tool, note))


def warn(tool, note):
    print(f"  {WARN} {tool} — {note}")
    results.append(("WARN", tool, note))


def info(msg):
    print(f"  {INFO} {msg}")


_TERMINAL = {"completed", "failed", "cancelled", "skipped"}


def _http_get_job(job_id: str) -> dict | None:
    """Poll a single job via the HTTP REST API."""
    try:
        with urllib.request.urlopen(f"{_HTTP_BASE}/jobs/{job_id}", timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


async def _wait_all_terminal(parent_job_id: str, max_wait: int = 180) -> bool:
    """Wait for parent job and its child jobs to reach terminal state."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        job = _http_get_job(parent_job_id)
        if job and job.get("status") in _TERMINAL:
            child_ids: list[str] = (job.get("result") or {}).get("child_job_ids", [])
            if not child_ids:
                return True
            child_deadline = time.monotonic() + max_wait
            while time.monotonic() < child_deadline:
                children = [_http_get_job(cid) for cid in child_ids]
                if all(c and c.get("status") in _TERMINAL for c in children):
                    return True
                await asyncio.sleep(4)
            return False
        await asyncio.sleep(4)
    return False


async def call(session, tool_name, args=None):
    from mcp import types as mct
    result = await session.call_tool(tool_name, args or {})
    # FastMCP returns content list; first item is text or dict
    if result.content and hasattr(result.content[0], "text"):
        try:
            return json.loads(result.content[0].text)
        except Exception:
            return {"_raw": result.content[0].text}
    return {"_empty": True}


async def run_tests():
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    print(f"\n{'='*60}")
    print(f"  Synthadoc MCP Live Test — {MCP_URL}")
    print(f"{'='*60}\n")

    async with sse_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            info("Session initialized")

            # ── 1. synthadoc_status ─────────────────────────────────────────
            print("\n[1] synthadoc_status")
            r = await call(session, "synthadoc_status")
            if "pages" in r and "wiki" in r:
                ok("synthadoc_status", f"wiki={r['wiki']!r}  pages={r['pages']}")
                wiki_pages = r["pages"]
            else:
                fail("synthadoc_status", f"unexpected response: {r}")
                wiki_pages = 0

            # ── 2. synthadoc_list_pages (all) ───────────────────────────────
            print("\n[2] synthadoc_list_pages — all")
            r = await call(session, "synthadoc_list_pages", {"status": "all"})
            if "pages" in r and isinstance(r["pages"], list):
                ok("synthadoc_list_pages(all)", f"total={r['total']}")
                all_pages = r["pages"]
                first_slug = all_pages[0]["slug"] if all_pages else None
                # check each page has expected fields
                missing = [k for k in ("slug","title","status","type","has_sources") if k not in (all_pages[0] if all_pages else {})]
                if missing:
                    warn("synthadoc_list_pages(all)", f"missing fields: {missing}")
            else:
                fail("synthadoc_list_pages(all)", f"unexpected: {r}")
                all_pages = []
                first_slug = None

            # ── 3. synthadoc_list_pages filtered by status ──────────────────
            print("\n[3] synthadoc_list_pages — filtered by 'active'")
            r = await call(session, "synthadoc_list_pages", {"status": "active"})
            if "pages" in r:
                active_pages = r["pages"]
                ok("synthadoc_list_pages(active)", f"active pages={len(active_pages)}")
                if active_pages:
                    active_slug = active_pages[0]["slug"]
                else:
                    active_slug = None
                    warn("synthadoc_list_pages(active)", "no active pages found — subsequent lifecycle test may be skipped")
            else:
                fail("synthadoc_list_pages(active)", str(r))
                active_pages = []
                active_slug = None

            # invalid status value
            print("\n[3b] synthadoc_list_pages — invalid status")
            r = await call(session, "synthadoc_list_pages", {"status": "nonexistent_state"})
            # should return pages filtered to nothing OR error
            # currently the code returns empty list (no match) rather than an error
            # This is a quality issue — no validation on status filter
            if "pages" in r and r["pages"] == []:
                warn("synthadoc_list_pages(invalid_status)",
                     "invalid status 'nonexistent_state' silently returns empty list — no error returned. "
                     "Should validate and return an error like synthadoc_jobs does.")
            elif "error" in r:
                ok("synthadoc_list_pages(invalid_status)", "correctly returns error for invalid status")
            else:
                info(f"response: {r}")

            # ── 4. synthadoc_search ─────────────────────────────────────────
            print("\n[4] synthadoc_search")
            for query in ["transistor", "alan turing", "ENIAC vacuum tube"]:
                r = await call(session, "synthadoc_search", {"terms": query})
                if "results" in r and isinstance(r["results"], list):
                    top = r["results"][0] if r["results"] else None
                    detail = f"hits={len(r['results'])}" + (f"  top={top['slug']!r}" if top else "  (no results)")
                    ok(f"synthadoc_search({query!r})", detail)
                    if r["results"]:
                        search_slug = r["results"][0]["slug"]
                else:
                    fail(f"synthadoc_search({query!r})", str(r))

            # empty query
            r = await call(session, "synthadoc_search", {"terms": ""})
            if "results" in r:
                ok("synthadoc_search(empty string)", f"returns {len(r['results'])} results (BM25 handles empty)")
            else:
                warn("synthadoc_search(empty string)", f"unexpected: {r}")

            # ── 5. synthadoc_read_page ──────────────────────────────────────
            print("\n[5] synthadoc_read_page")
            if first_slug:
                r = await call(session, "synthadoc_read_page", {"slug": first_slug})
                expected = {"slug", "title", "content", "status", "type", "tags", "lint_warnings", "sources"}
                missing = expected - set(r.keys())
                if not missing:
                    ok("synthadoc_read_page(valid)", f"slug={first_slug!r}  content_len={len(r.get('content',''))}")
                else:
                    fail("synthadoc_read_page(valid)", f"missing fields: {missing}")

            # non-existent slug
            r = await call(session, "synthadoc_read_page", {"slug": "this-page-does-not-exist"})
            if r.get("error") == "page not found":
                ok("synthadoc_read_page(missing)", "returns {error: 'page not found'}")
            else:
                fail("synthadoc_read_page(missing)", f"unexpected: {r}")

            # ── 6. synthadoc_context ────────────────────────────────────────
            print("\n[6] synthadoc_context")
            r = await call(session, "synthadoc_context",
                           {"goal": "Who invented the transistor and what was its impact?",
                            "token_budget": 5000})
            if "pages" in r or "items" in r or isinstance(r, dict):
                page_count = len(r.get("pages") or r.get("items") or [])
                omitted = len(r.get("omitted") or [])
                tokens = r.get("total_tokens") or r.get("tokens_used") or "?"
                ok("synthadoc_context", f"pages_included={page_count}  omitted={omitted}  tokens={tokens}")
                # check structure
                items = r.get("pages") or r.get("items") or []
                if items:
                    first = items[0]
                    missing_fields = [k for k in ("slug","excerpt","relevance") if k not in first]
                    if missing_fields:
                        warn("synthadoc_context", f"page item missing fields: {missing_fields}")
            else:
                fail("synthadoc_context", f"unexpected structure: {list(r.keys())}")

            # ── 7. synthadoc_lint_report ─────────────────────────────────────
            print("\n[7] synthadoc_lint_report")
            r = await call(session, "synthadoc_lint_report")
            expected_keys = {"contradicted", "orphans", "adversarial_warnings", "adversarial_pages"}
            missing = expected_keys - set(r.keys())
            if not missing:
                ok("synthadoc_lint_report",
                   f"contradicted={r['contradicted']}  orphans={len(r['orphans'])}  "
                   f"adversarial_warnings={r['adversarial_warnings']}")
                has_contradicted = bool(r["contradicted"])
                contradicted_slugs = r["contradicted"] if isinstance(r["contradicted"], list) else []
            else:
                fail("synthadoc_lint_report", f"missing keys: {missing}")
                has_contradicted = False
                contradicted_slugs = []

            # ── 8. synthadoc_lint (enqueue) ──────────────────────────────────
            print("\n[8] synthadoc_lint")
            if first_slug:
                r = await call(session, "synthadoc_lint", {"scope": first_slug})
                if "job_id" in r and "scope" in r:
                    ok("synthadoc_lint(single page)", f"job_id={r['job_id']}  scope={r['scope']!r}")
                    lint_job_id = r["job_id"]
                else:
                    fail("synthadoc_lint(single page)", str(r))
                    lint_job_id = None
            else:
                warn("synthadoc_lint", "skipped — no page slug available")
                lint_job_id = None

            # invalid scope (should it error or just enqueue?)
            r = await call(session, "synthadoc_lint", {"scope": "nonexistent-slug"})
            if "job_id" in r:
                warn("synthadoc_lint(nonexistent scope)",
                     "enqueues job for non-existent page — job will likely fail silently. "
                     "Consider validating slug before enqueuing.")
            elif "error" in r:
                ok("synthadoc_lint(nonexistent scope)", "correctly returns error")

            # ── 9. synthadoc_jobs ────────────────────────────────────────────
            print("\n[9] synthadoc_jobs")
            r = await call(session, "synthadoc_jobs", {"status": "all"})
            if "jobs" in r and isinstance(r["jobs"], list):
                ok("synthadoc_jobs(all)", f"total={len(r['jobs'])}")
                if r["jobs"]:
                    j = r["jobs"][0]
                    missing = [k for k in ("id","operation","status","created") if k not in j]
                    if missing:
                        warn("synthadoc_jobs", f"job entry missing fields: {missing}")
            else:
                fail("synthadoc_jobs(all)", str(r))

            # filter by completed
            r = await call(session, "synthadoc_jobs", {"status": "completed"})
            if "jobs" in r:
                ok("synthadoc_jobs(completed)", f"completed={len(r['jobs'])}")
            else:
                fail("synthadoc_jobs(completed)", str(r))

            # invalid status
            r = await call(session, "synthadoc_jobs", {"status": "bogus"})
            if "error" in r:
                ok("synthadoc_jobs(invalid status)", "returns error for invalid status")
            else:
                fail("synthadoc_jobs(invalid status)", f"should return error, got: {r}")

            # ── 10. synthadoc_write_page + restore ───────────────────────────
            print("\n[10] synthadoc_write_page")
            if first_slug:
                # read original
                original = await call(session, "synthadoc_read_page", {"slug": first_slug})
                original_content = original.get("content", "")
                original_title = original.get("title", "")

                # write modified content
                test_content = original_content + "\n\n<!-- MCP live test marker -->"
                r = await call(session, "synthadoc_write_page",
                               {"slug": first_slug, "content": test_content})
                if r.get("slug") == first_slug and "status" in r:
                    ok("synthadoc_write_page(update content)", f"slug={first_slug!r}  status={r['status']!r}")
                    # verify the write took effect
                    verify = await call(session, "synthadoc_read_page", {"slug": first_slug})
                    if "<!-- MCP live test marker -->" in verify.get("content", ""):
                        ok("synthadoc_write_page(verify read-back)", "content change confirmed by read_page")
                    else:
                        fail("synthadoc_write_page(verify read-back)", "content not updated in storage")
                    # restore original
                    await call(session, "synthadoc_write_page",
                               {"slug": first_slug, "content": original_content, "title": original_title})
                    info(f"Restored {first_slug!r} to original content")
                else:
                    fail("synthadoc_write_page(update content)", str(r))

                # non-existent page
                r = await call(session, "synthadoc_write_page",
                               {"slug": "does-not-exist-xyz", "content": "test"})
                if r.get("error") == "page not found":
                    ok("synthadoc_write_page(missing slug)", "returns {error: 'page not found'}")
                else:
                    fail("synthadoc_write_page(missing slug)", f"unexpected: {r}")
            else:
                warn("synthadoc_write_page", "skipped — no page slug available")

            # ── 11. synthadoc_lifecycle ──────────────────────────────────────
            print("\n[11] synthadoc_lifecycle")
            if active_slug:
                # active -> stale (valid transition)
                r = await call(session, "synthadoc_lifecycle",
                               {"slug": active_slug, "to_state": "stale",
                                "reason": "MCP live test — marking stale temporarily"})
                if "from_state" in r and r.get("to_state") == "stale":
                    ok("synthadoc_lifecycle(active->stale)", f"slug={active_slug!r}  timestamp={r.get('timestamp','?')!r}")
                    # restore: stale -> active
                    restore = await call(session, "synthadoc_lifecycle",
                                        {"slug": active_slug, "to_state": "active",
                                         "reason": "MCP live test — restore after stale test"})
                    if restore.get("to_state") == "active":
                        ok("synthadoc_lifecycle(stale->active restore)", "page restored to active")
                    else:
                        fail("synthadoc_lifecycle(stale->active restore)", str(restore))
                elif "error" in r:
                    fail("synthadoc_lifecycle(active->stale)", r["error"])
                else:
                    fail("synthadoc_lifecycle(active->stale)", str(r))

                # blocked transition: active -> contradicted -> stale (stale->contradicted is blocked)
                # First go active -> stale again, then try stale -> contradicted (must be blocked)
                await call(session, "synthadoc_lifecycle",
                           {"slug": active_slug, "to_state": "stale", "reason": "setup for blocked test"})
                r = await call(session, "synthadoc_lifecycle",
                               {"slug": active_slug, "to_state": "contradicted",
                                "reason": "should be blocked"})
                if "error" in r and "not permitted" in r["error"]:
                    ok("synthadoc_lifecycle(stale->contradicted blocked)", "correctly rejected with 'not permitted'")
                else:
                    fail("synthadoc_lifecycle(stale->contradicted blocked)",
                         f"expected error 'not permitted', got: {r}")
                # restore
                await call(session, "synthadoc_lifecycle",
                           {"slug": active_slug, "to_state": "active", "reason": "restore after blocked test"})

                # same-state transition (should error)
                r = await call(session, "synthadoc_lifecycle",
                               {"slug": active_slug, "to_state": "active", "reason": "same state test"})
                if "error" in r and "already in state" in r["error"]:
                    ok("synthadoc_lifecycle(same-state)", "correctly returns 'already in state' error")
                else:
                    fail("synthadoc_lifecycle(same-state)", f"expected 'already in state' error, got: {r}")

                # non-existent page
                r = await call(session, "synthadoc_lifecycle",
                               {"slug": "no-such-page-xyz", "to_state": "active", "reason": "test"})
                if r.get("error") == "page not found":
                    ok("synthadoc_lifecycle(missing slug)", "returns {error: 'page not found'}")
                else:
                    fail("synthadoc_lifecycle(missing slug)", str(r))

                # invalid to_state
                r = await call(session, "synthadoc_lifecycle",
                               {"slug": active_slug, "to_state": "published", "reason": "test"})
                if "error" in r and "invalid to_state" in r["error"]:
                    ok("synthadoc_lifecycle(invalid state)", "returns error for invalid to_state")
                else:
                    fail("synthadoc_lifecycle(invalid state)", f"expected invalid-state error, got: {r}")

            else:
                warn("synthadoc_lifecycle", "skipped — no active page available")

            # ── 12. synthadoc_export ─────────────────────────────────────────
            print("\n[12] synthadoc_export")

            # llms.txt — inline content (no output_path)
            r = await call(session, "synthadoc_export",
                           {"format": "llms.txt", "status_filter": "active"})
            if "content" in r and r.get("format") == "llms.txt":
                ok("synthadoc_export(llms.txt inline)", f"pages={r.get('pages')}  content_len={len(r['content'])}")
            elif "error" in r:
                fail("synthadoc_export(llms.txt inline)", r["error"])
            else:
                fail("synthadoc_export(llms.txt inline)", f"unexpected: {list(r.keys())}")

            # json — inline
            r = await call(session, "synthadoc_export",
                           {"format": "json", "status_filter": "all"})
            if "content" in r and r.get("format") == "json":
                ok("synthadoc_export(json inline)", f"pages={r.get('pages')}  content_len={len(str(r['content']))}")
            else:
                fail("synthadoc_export(json inline)", f"unexpected: {r}")

            # okf — writes to disk (default path)
            r = await call(session, "synthadoc_export",
                           {"format": "okf", "status_filter": "active"})
            if r.get("format") == "okf" and "output_path" in r and "files_written" in r:
                ok("synthadoc_export(okf to disk)", f"files_written={r['files_written']}  path={r['output_path']!r}")
            elif "error" in r:
                fail("synthadoc_export(okf to disk)", r["error"])
            else:
                fail("synthadoc_export(okf to disk)", f"unexpected: {r}")

            # invalid format
            r = await call(session, "synthadoc_export", {"format": "pdf"})
            if "error" in r and "unknown format" in r["error"]:
                ok("synthadoc_export(invalid format)", "returns error for unknown format")
            else:
                fail("synthadoc_export(invalid format)", f"expected 'unknown format' error, got: {r}")

            # ── 13. synthadoc_ingest ─────────────────────────────────────────
            print("\n[13] synthadoc_ingest")
            # ingest a direct, stable Wikipedia URL — avoids third-party timeouts
            # that plagued the old "search for: Harvard Mark I" search-intent form
            # (search results returned unreliable domains like devx.com that timed out)
            _INGEST_URL = "https://en.wikipedia.org/wiki/Harvard_Mark_I"
            r = await call(session, "synthadoc_ingest", {"source": _INGEST_URL})
            if "job_id" in r and "source" in r:
                ok("synthadoc_ingest(url)", f"job_id={r['job_id']!r}  source={r['source']!r}")
                info("Waiting for ingest job to reach terminal state (max 3 min)…")
                _done = await _wait_all_terminal(r["job_id"])
                if _done:
                    info("Ingest job reached terminal state")
                else:
                    warn("synthadoc_ingest(url)",
                         "Job still running after 3 min — check the Jobs panel")
            elif "error" in r:
                fail("synthadoc_ingest(url)", r["error"])
            else:
                fail("synthadoc_ingest(url)", f"unexpected: {r}")

            # empty source — quality check
            r = await call(session, "synthadoc_ingest", {"source": ""})
            if "error" in r:
                ok("synthadoc_ingest(empty source)", "returns error for empty source")
            elif "job_id" in r:
                warn("synthadoc_ingest(empty source)",
                     "empty source enqueues a job — likely fails silently later. "
                     "Consider validating before enqueuing.")
            else:
                info(f"empty ingest response: {r}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  RESULTS SUMMARY")
    print(f"{'='*60}")
    passes = [r for r in results if r[0] == "PASS"]
    fails  = [r for r in results if r[0] == "FAIL"]
    warns  = [r for r in results if r[0] == "WARN"]
    print(f"  PASS : {len(passes)}")
    print(f"  WARN : {len(warns)}")
    print(f"  FAIL : {len(fails)}")
    if warns:
        print(f"\n  Quality issues (WARN):")
        for _, tool, note in warns:
            print(f"    • {tool}: {note}")
    if fails:
        print(f"\n  Failures (FAIL):")
        for _, tool, note in fails:
            print(f"    • {tool}: {note}")
    print()
    return len(fails)


if __name__ == "__main__":
    n_fails = asyncio.run(run_tests())
    sys.exit(1 if n_fails else 0)
