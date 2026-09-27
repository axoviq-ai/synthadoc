# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Standalone diagnostic script for the stale-page re-ingest workflow.

Borrows an existing active/draft page (exactly like the live test does),
makes it stale, runs the agentic "re-ingest+stale+pages" workflow, and
dumps detailed diagnostic output showing exactly where the STALE→DRAFT
transition succeeds or fails.

Usage (server must be running):
    python -X utf8 tests/live/diagnose_stale_reingest.py

Set SYNTHADOC_URL to override the default http://127.0.0.1:7070.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")

# ── helpers ────────────────────────────────────────────────────────────────────

def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            r = client.delete(f"{BASE}{path}")
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


def _raw(path: str, method: str = "GET", body: dict | None = None) -> httpx.Response:
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            return client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            return client.delete(f"{BASE}{path}")
        return client.get(f"{BASE}{path}")


def _wait_job(job_id: str, max_wait: int = 240) -> str:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            body = _api(f"/jobs/{job_id}")
            status = body.get("status", "")
            if status in {"completed", "failed", "cancelled"}:
                return status
        except Exception:
            pass
        time.sleep(3)
    return "timeout"


def _wait_for_queue_idle(max_wait: int = 120) -> None:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            r = _raw("/jobs")
            if r.status_code == 200:
                active = [j for j in r.json()
                          if isinstance(j, dict)
                          and j.get("status") not in {"completed", "failed", "cancelled"}]
                if not active:
                    return
        except Exception:
            pass
        time.sleep(3)


def _page_frontmatter_state(wiki_dir: Path, slug: str) -> str | None:
    page_file = wiki_dir / f"{slug}.md"
    try:
        text = page_file.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    fm = text[3:end]
    for line in fm.splitlines():
        if line.strip().startswith("status:"):
            return line.split(":", 1)[1].strip().strip('"\'')
    return None


def _audit_db_state(slug: str) -> str | None:
    try:
        pages = _api("/lifecycle/pages").get("pages", [])
        for p in pages:
            if p["slug"] == slug:
                return p.get("state")
    except Exception:
        pass
    return None


def _get_source_path_from_page(wiki_dir: Path, slug: str) -> Path | None:
    page_file = wiki_dir / f"{slug}.md"
    try:
        text = page_file.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    fm_text = text[3:end]
    for m in re.finditer(r'file:\s*(?P<file>[^\n]+)', fm_text):
        val = m.group("file").strip().strip('"\'')
        if val.startswith("http://") or val.startswith("https://"):
            continue
        p = Path(val)
        if not p.is_absolute():
            wiki_root = wiki_dir.parent
            candidate = wiki_root / p
            if not candidate.exists():
                candidate = wiki_root / "raw_sources" / p
            p = candidate
        if not (p.exists() and p.is_file()):
            continue
        if p.suffix.lower() not in {".txt", ".md"}:
            continue
        return p
    return None


def sep(label: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")


# ── main diagnostic ────────────────────────────────────────────────────────────

def main() -> None:
    sep("1. Server health check")
    try:
        status = _api("/status")
        wiki_root = Path(status["wiki"])
        wiki_dir = wiki_root / "wiki"
        print(f"  Server OK. Wiki root: {wiki_root}")
    except Exception as e:
        print(f"  FAIL: Cannot reach server at {BASE}: {e}")
        sys.exit(1)

    # Find a suitable page to borrow (active or draft with a local text source)
    sep("2. Find borrowable page with local text source")
    _wait_for_queue_idle()
    pages = _api("/lifecycle/pages").get("pages", [])

    borrowed: tuple[str, Path, str, str] | None = None  # (slug, source_path, orig_content, orig_state)
    for target_state in ("active", "draft"):
        for page_info in pages:
            if page_info.get("state") != target_state:
                continue
            slug = page_info["slug"]
            sp = _get_source_path_from_page(wiki_dir, slug)
            if sp is None:
                continue
            try:
                orig = sp.read_text(encoding="utf-8")
            except Exception:
                continue
            borrowed = (slug, sp, orig, target_state)
            break
        if borrowed:
            break

    if not borrowed:
        print("  FAIL: no suitable page found (need active/draft page with local txt/md source)")
        sys.exit(1)

    slug, source_path, orig_content, orig_state = borrowed
    print(f"  Borrowing page: {slug!r}  (state={orig_state!r})")
    print(f"  Source file:    {source_path}")

    # Isolate any pre-existing stale pages so the workflow only sees our page
    sep("3. Isolate pre-existing stale pages")
    isolated: list[str] = []
    for page_info in pages:
        if page_info.get("state") != "stale" or page_info["slug"] == slug:
            continue
        r = _raw("/lifecycle/transition", "POST", {
            "slug": page_info["slug"],
            "to_state": "active",
            "reason": "diag: isolate pre-existing stale page",
        })
        if r.status_code == 200:
            isolated.append(page_info["slug"])
    print(f"  Isolated {len(isolated)} pre-existing stale page(s): {isolated}")

    try:
        # Transition borrowed page to STALE
        sep("4. Transition borrowed page to STALE")
        if orig_state == "draft":
            r = _raw("/lifecycle/transition", "POST", {
                "slug": slug, "to_state": "active",
                "reason": "diag: promote draft before staling",
            })
            print(f"  DRAFT→ACTIVE: {r.status_code}")
        r = _raw("/lifecycle/transition", "POST", {
            "slug": slug, "to_state": "stale",
            "reason": "diag: manufacturing stale page for re-ingest diagnostic",
        })
        print(f"  →STALE: {r.status_code}")

        fm_state = _page_frontmatter_state(wiki_dir, slug)
        db_state = _audit_db_state(slug)
        print(f"  Frontmatter: {fm_state!r}   Audit DB: {db_state!r}")
        if fm_state != "stale" or db_state != "stale":
            print("  FAIL: page not stale in both stores")
            return

        # Run the agentic workflow
        sep("5. Run agentic re-ingest workflow")
        _wait_for_queue_idle()
        print("  Queue idle. Streaming workflow…")

        session_id = str(uuid.uuid4())
        # Same endpoint and parameters as _stream_with_autoconfirm in the test file
        stream_path = (
            f"/query/stream?q=re-ingest+stale+pages"
            f"&session_id={session_id}&no_cache=true&timeout_seconds=600"
        )
        events: list[tuple[str, dict]] = []
        lock = threading.Lock()
        t0 = time.monotonic()

        def _auto_confirm():
            # Background thread: poll collected events and confirm any confirm_request
            while True:
                time.sleep(0.3)
                with lock:
                    snapshot = list(events)
                for evt_type, data in snapshot:
                    if evt_type == "confirm_request":
                        sid = data.get("session_id", session_id)
                        try:
                            _raw("/action/confirm", "POST", {
                                "session_id": sid,
                                "confirmed": True,
                            })
                        except Exception:
                            pass
                    if evt_type == "done":
                        return

        monitor = threading.Thread(target=_auto_confirm, daemon=True)
        monitor.start()

        current_type = "message"
        current_data: list[str] = []
        buf = ""

        with httpx.Client(timeout=httpx.Timeout(630)) as client:
            with client.stream("GET", f"{BASE}{stream_path}") as resp:
                resp.raise_for_status()
                for chunk in resp.iter_text():
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.rstrip("\r")
                        if not line:
                            if current_data:
                                raw = "\n".join(current_data)
                                try:
                                    data = json.loads(raw)
                                except json.JSONDecodeError:
                                    data = {"raw": raw}
                                with lock:
                                    events.append((current_type, data))
                            current_type = "message"
                            current_data = []
                        elif line.startswith("event:"):
                            current_type = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data.append(line[5:].lstrip())

        monitor.join(timeout=5)

        elapsed = time.monotonic() - t0
        print(f"  Workflow finished in {elapsed:.1f}s, {len(events)} events total")

        # Analyse events
        sep("6. SSE event analysis")
        print(f"  Event types: {[t for t, _ in events]}")

        progress = [(t, d) for t, d in events if t == "tool_progress"]
        print(f"\n  tool_progress events ({len(progress)}):")
        for i, (_, d) in enumerate(progress, 1):
            tool = d.get("tool", "?")
            msg = d.get("message", "")
            status_val = d.get("status", "")
            print(f"    [{i}] tool={tool!r:<20} status={status_val!r:<12} message={msg!r}")

        errors = [(t, d) for t, d in events if t == "error"]
        if errors:
            print(f"\n  ERROR events: {errors}")
        else:
            print("\n  No error events.")

        full_text = "".join(d.get("text", "") for t, d in events if t == "token")
        if full_text:
            print(f"\n  LLM narrative ({len(full_text)} chars):")
            # Print first 800 chars, trimmed at word boundary
            preview = full_text[:800]
            print(f"    {preview!r}")

        # Check page state after workflow
        sep("7. Page state immediately after workflow")
        fm_now = _page_frontmatter_state(wiki_dir, slug)
        db_now = _audit_db_state(slug)
        print(f"  Frontmatter (wiki file): {fm_now!r}")
        print(f"  Audit DB:                {db_now!r}")

        sep("8. Page state after 30s wait")
        time.sleep(30)
        fm_later = _page_frontmatter_state(wiki_dir, slug)
        db_later = _audit_db_state(slug)
        print(f"  Frontmatter (wiki file): {fm_later!r}")
        print(f"  Audit DB:                {db_later!r}")

        print()
        if fm_later == "stale":
            print("  RESULT: FAIL — wiki file still STALE → ingest never ran the update path")
            print("          Check whether ingest job returned 'skip' (look for skip in progress events above)")
        elif db_later == "stale":
            print("  RESULT: FAIL — wiki file is NOT stale but audit DB still is")
            print("          Either: (a) ingest wrote the file but audit DB set_page_state failed,")
            print("          or: (b) lint's Check 4 re-staled the audit DB after seeing wiki≠DB")
        else:
            print(f"  RESULT: PASS — page is now wiki={fm_later!r} / auditDB={db_later!r}")

    finally:
        sep("9. Restore borrowed page")
        try:
            source_path.write_text(orig_content, encoding="utf-8")
            r = _api("/jobs/ingest", "POST", {"source": str(source_path), "force": True})
            final = _wait_job(r["job_id"], max_wait=180)
            print(f"  Restore ingest: {final}")
        except Exception as ex:
            print(f"  Restore ingest FAILED: {ex}")
        if orig_state == "active":
            try:
                _raw("/lifecycle/transition", "POST", {
                    "slug": slug, "to_state": "active",
                    "reason": "diag: restore to original active state",
                })
                print(f"  Restored {slug!r} → active")
            except Exception as ex:
                print(f"  Restore transition failed: {ex}")

        for iso_slug in isolated:
            try:
                _raw("/lifecycle/transition", "POST", {
                    "slug": iso_slug, "to_state": "stale",
                    "reason": "diag: restore isolated stale page",
                })
            except Exception:
                pass
        if isolated:
            print(f"  Restored {len(isolated)} isolated page(s)")
        print()


if __name__ == "__main__":
    main()
