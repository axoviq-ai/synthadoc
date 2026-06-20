// src/api.integration.test.ts
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
//
// Integration tests for the Synthadoc HTTP API contract consumed by api.ts.
// These tests hit a live server — run with: npm run test:integration
// The server URL defaults to http://127.0.0.1:7070; override with SYNTHADOC_BASE_URL.
//
// Each test validates the response SHAPE (field names and types), not content,
// so they pass regardless of which wiki is loaded.

import { describe, it, expect, beforeAll } from "vitest";

const BASE = (process.env.SYNTHADOC_BASE_URL ?? "http://127.0.0.1:7070").replace(/\/$/, "");

async function get(path: string) {
    const r = await fetch(`${BASE}${path}`, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
    return r.json();
}

async function post(path: string, body: object) {
    const r = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const text = await r.text();
    let parsed: unknown;
    try { parsed = JSON.parse(text); } catch { parsed = text; }
    return { status: r.status, body: parsed };
}

// Skip all tests if the server is not reachable.
let serverUp = false;
beforeAll(async () => {
    try {
        await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(3000) });
        serverUp = true;
    } catch {
        console.warn(`\n⚠  Synthadoc server not reachable at ${BASE} — skipping integration tests`);
    }
});

function skipIfDown() {
    if (!serverUp) return true;
    return false;
}

// ── Core ──────────────────────────────────────────────────────────────────────

describe("GET /health", () => {
    it("returns status:ok", async () => {
        if (skipIfDown()) return;
        const d = await get("/health");
        expect(d.status).toBe("ok");
    });
});

describe("GET /status", () => {
    it("returns wiki name, page count, and job counts", async () => {
        if (skipIfDown()) return;
        const d = await get("/status");
        expect(typeof d.wiki).toBe("string");
        expect(typeof d.pages).toBe("number");
        expect(typeof d.jobs_pending).toBe("number");
        expect(typeof d.jobs_total).toBe("number");
    });
});

// ── Lifecycle/status — Bug 1 ──────────────────────────────────────────────────

describe("GET /lifecycle/status", () => {
    it("returns a flat dict with all 5 lifecycle states (no counts wrapper)", async () => {
        if (skipIfDown()) return;
        const d = await get("/lifecycle/status");
        // Must be a flat dict — no nested 'counts' key
        expect(d).not.toHaveProperty("counts");
        for (const state of ["draft", "active", "contradicted", "stale", "archived"]) {
            expect(d).toHaveProperty(state);
            expect(typeof d[state]).toBe("number");
        }
    });

    it("all state counts are non-negative integers", async () => {
        if (skipIfDown()) return;
        const d = await get("/lifecycle/status");
        for (const state of ["draft", "active", "contradicted", "stale", "archived"]) {
            expect(d[state]).toBeGreaterThanOrEqual(0);
        }
    });
});

// ── Lifecycle/events — Bug 2 ──────────────────────────────────────────────────

describe("GET /lifecycle/events", () => {
    it("total reflects the full DB count, not just the page size", async () => {
        if (skipIfDown()) return;
        // Request a small page — total should be the real DB count
        const d = await get("/lifecycle/events?limit=5&offset=0");
        expect(d).toHaveProperty("events");
        expect(d).toHaveProperty("total");
        expect(Array.isArray(d.events)).toBe(true);
        expect(d.events.length).toBeLessThanOrEqual(5);
        // If there are more than 5 events in the DB, total must exceed page size
        if (d.total > 5) {
            expect(d.total).toBeGreaterThan(d.events.length);
        }
    });

    it("event objects have the expected fields", async () => {
        if (skipIfDown()) return;
        const d = await get("/lifecycle/events?limit=1");
        if (d.events.length === 0) return; // empty wiki — skip shape check
        const ev = d.events[0];
        expect(typeof ev.id).toBe("number");
        expect(typeof ev.slug).toBe("string");
        expect(typeof ev.to_state).toBe("string");
        expect(typeof ev.timestamp).toBe("string");
    });

    it("pagination offset returns different events", async () => {
        if (skipIfDown()) return;
        const page1 = await get("/lifecycle/events?limit=3&offset=0");
        const page2 = await get("/lifecycle/events?limit=3&offset=3");
        if (page1.total <= 3) return; // not enough events to paginate
        const ids1 = new Set(page1.events.map((e: any) => e.id));
        const ids2 = new Set(page2.events.map((e: any) => e.id));
        const overlap = [...ids1].filter(id => ids2.has(id));
        expect(overlap).toHaveLength(0);
    });
});

// ── Lifecycle/transition — Bugs 3 & 4 ────────────────────────────────────────

describe("POST /lifecycle/transition", () => {
    it("returns {slug, from_state, to_state, timestamp} — no ok field", async () => {
        if (skipIfDown()) return;
        // Find an active page to test with
        const pages = await get("/lifecycle/pages");
        const active = pages.pages?.find((p: any) => p.state === "active");
        if (!active) return; // no active pages — skip

        const { status, body } = await post("/lifecycle/transition", {
            slug: active.slug,
            to_state: "stale",
            reason: "integration test",
        });
        expect(status).toBe(200);
        expect(body).toHaveProperty("slug", active.slug);
        expect(body).toHaveProperty("from_state", "active");
        expect(body).toHaveProperty("to_state", "stale");
        expect(body).toHaveProperty("timestamp");
        expect(body).not.toHaveProperty("ok");

        // Revert — stale → active must succeed (no graph enforcement)
        const revert = await post("/lifecycle/transition", {
            slug: active.slug,
            to_state: "active",
            reason: "integration test revert",
        });
        expect(revert.status).toBe(200);
    });

    it("allows active → contradicted (manual contradiction flag)", async () => {
        if (skipIfDown()) return;
        const pages = await get("/lifecycle/pages");
        const active = pages.pages?.find((p: any) => p.state === "active");
        if (!active) return;

        // active → contradicted is a valid user-driven transition
        const { status } = await post("/lifecycle/transition", {
            slug: active.slug,
            to_state: "contradicted",
            reason: "integration test cross-state",
        });
        expect(status).toBe(200);

        // Revert: contradicted → active is also permitted
        await post("/lifecycle/transition", {
            slug: active.slug,
            to_state: "active",
            reason: "integration test revert",
        });
    });

    it("returns 422 for a blocked transition (graph enforcement)", async () => {
        if (skipIfDown()) return;
        const pages = await get("/lifecycle/pages");
        const active = pages.pages?.find((p: any) => p.state === "active");
        if (!active) return;

        // active → stale → contradicted is blocked: stale and contradicted are
        // different issue types and cannot be crossed directly
        await post("/lifecycle/transition", {
            slug: active.slug, to_state: "stale", reason: "mark outdated",
        });
        const { status, body } = await post("/lifecycle/transition", {
            slug: active.slug,
            to_state: "contradicted",
            reason: "should be blocked",
        });
        expect(status).toBe(422);
        expect((body as any).detail).toMatch(/not permitted/);

        // Restore
        await post("/lifecycle/transition", { slug: active.slug, to_state: "active", reason: "revert" });
    });

    it("returns 422 when transitioning to the same state", async () => {
        if (skipIfDown()) return;
        const pages = await get("/lifecycle/pages");
        const active = pages.pages?.find((p: any) => p.state === "active");
        if (!active) return;

        const { status, body } = await post("/lifecycle/transition", {
            slug: active.slug,
            to_state: "active",
            reason: "same-state test",
        });
        expect(status).toBe(422);
        expect(body.detail).toMatch(/already in state/);
    });

    it("returns 404 for a non-existent page", async () => {
        if (skipIfDown()) return;
        const { status } = await post("/lifecycle/transition", {
            slug: "this-page-does-not-exist-integration-test",
            to_state: "active",
            reason: "test",
        });
        expect(status).toBe(404);
    });
});

// ── Sessions — Bug 5 ──────────────────────────────────────────────────────────

describe("GET /sessions", () => {
    it("returns sessions with correct field names", async () => {
        if (skipIfDown()) return;
        const sessions = await get("/sessions?limit=5");
        expect(Array.isArray(sessions)).toBe(true);
        if (sessions.length === 0) return; // no sessions yet — skip shape check

        const s = sessions[0];
        expect(s).toHaveProperty("session_id");
        expect(s).toHaveProperty("first_q");
        expect(s).toHaveProperty("last_active");
        expect(s).toHaveProperty("turn_count");
        expect(s).toHaveProperty("questions");
        expect(Array.isArray(s.questions)).toBe(true);
        // Old field names must not be present
        expect(s).not.toHaveProperty("turns");
        expect(s).not.toHaveProperty("mode");
        expect(s).not.toHaveProperty("created_at");
    });

    it("first_q matches the first element of questions", async () => {
        if (skipIfDown()) return;
        const sessions = await get("/sessions?limit=5");
        if (sessions.length === 0) return;
        const s = sessions[0];
        if (!s.questions.length) return;
        expect(s.first_q).toBe(s.questions[0]);
    });

    it("turn_count matches questions array length", async () => {
        if (skipIfDown()) return;
        const sessions = await get("/sessions?limit=5");
        if (sessions.length === 0) return;
        for (const s of sessions) {
            expect(s.turn_count).toBe(s.questions.length);
        }
    });
});

// ── Jobs — Bug 6 (payload missing from single-job endpoint) ──────────────────

describe("GET /jobs and GET /jobs/:id", () => {
    it("/jobs list includes payload field", async () => {
        if (skipIfDown()) return;
        const jobs = await get("/jobs");
        expect(Array.isArray(jobs)).toBe(true);
        if (jobs.length === 0) return;
        expect(jobs[0]).toHaveProperty("payload");
    });

    it("/jobs/:id includes payload field matching the list", async () => {
        if (skipIfDown()) return;
        const jobs = await get("/jobs");
        if (jobs.length === 0) return;
        const job = jobs[0];
        const single = await get(`/jobs/${job.id}`);
        expect(single).toHaveProperty("payload");
        expect(single.payload).toEqual(job.payload);
    });
});

// ── Analyse — Bug 7 (plain text returned 500 instead of 422) ─────────────────

describe("POST /analyse", () => {
    it("returns 422 (not 500) when source is plain text with no matching skill", async () => {
        if (skipIfDown()) return;
        const { status } = await post("/analyse", { source: "Geoffrey Hinton is a deep learning pioneer." });
        // Must be a client error, not a server crash
        expect(status).toBe(422);
    });
});

// ── Lint report ───────────────────────────────────────────────────────────────

describe("GET /lint/report", () => {
    it("returns orphans and contradictions arrays; adversarial_warnings is array or null", async () => {
        if (skipIfDown()) return;
        const d = await get("/lint/report");
        expect(Array.isArray(d.orphans)).toBe(true);
        expect(Array.isArray(d.contradictions)).toBe(true);
        expect(d.adversarial_warnings === null || Array.isArray(d.adversarial_warnings)).toBe(true);
    });
});

// ── Provenance/citations ──────────────────────────────────────────────────────

describe("GET /provenance/citations", () => {
    it("returns total as full DB count and a citations array", async () => {
        if (skipIfDown()) return;
        const d = await get("/provenance/citations?limit=3");
        expect(typeof d.total).toBe("number");
        expect(Array.isArray(d.citations)).toBe(true);
        expect(d.citations.length).toBeLessThanOrEqual(3);
        if (d.total > 3) {
            expect(d.total).toBeGreaterThan(d.citations.length);
        }
    });
});
