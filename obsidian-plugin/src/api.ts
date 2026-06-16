// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { requestUrl } from "obsidian";

let BASE = "http://127.0.0.1:7070";

export function setBase(url: string): void {
    BASE = url.replace(/\/$/, "");
}

export function getBase(): string {
    return BASE;
}

async function _callInner(path: string, method = "GET", body?: object) {
    const res = await requestUrl({
        url: `${BASE}${path}`,
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
        throw: false,
    });
    if (res.status < 200 || res.status >= 300) {
        throw new Error(`synthadoc API ${res.status}`);
    }
    return res;
}

async function call(path: string, method = "GET", body?: object) {
    return (await _callInner(path, method, body)).json;
}

async function callRaw(path: string, method = "GET", body?: object): Promise<string> {
    return (await _callInner(path, method, body)).text;
}

export const api = {
    health:       ()                          => call("/health"),
    status:       ()                          => call("/status"),
    query:        (question: string, timeoutSeconds = 60) => call("/query", "POST", { question, timeout_seconds: timeoutSeconds }),
    ingest:       (source: string, maxResults?: number, force?: boolean) => call("/jobs/ingest", "POST", { source, ...(maxResults != null ? { max_results: maxResults } : {}), ...(force ? { force: true } : {}) }),
    config:       ()                          => call("/config"),
    lint:         (scope = "all", autoResolve = false, adversarial = true, checkUrls?: boolean | null) =>
        call("/jobs/lint", "POST", { scope, auto_resolve: autoResolve, adversarial, ...(checkUrls != null ? { check_url_availability: checkUrls } : {}) }),
    lintReport:   ()                          => call("/lint/report"),
    jobs:         (status?: string)           => call(status ? `/jobs?status=${encodeURIComponent(status)}` : "/jobs"),
    retryJob:     (jobId: string)             => call(`/jobs/${jobId}/retry`, "POST"),
    deleteJob:    (jobId: string)             => call(`/jobs/${jobId}`, "DELETE"),
    purgeJobs:    (olderThan: number)         => call(`/jobs?older_than=${olderThan}`, "DELETE"),
    scaffold:     (domain: string)            => call("/jobs/scaffold",   "POST", { domain }),
    job:           (jobId: string)             => call(`/jobs/${jobId}`),
    auditHistory:  (limit = 50)               => call(`/audit/history?limit=${limit}`),
    auditCosts:    (days = 30)                => call(`/audit/costs?days=${days}`),
    queryHistory:  (limit = 50)               => call(`/audit/queries?limit=${limit}`),
    auditEvents:   (limit = 100)              => call(`/audit/events?limit=${limit}`),
    routingStatus:   () => call("/routing/status"),
    routingInit:     () => call("/routing/init",     "POST"),
    routingValidate: () => call("/routing/validate", "POST"),
    routingClean:    () => call("/routing/clean",    "POST"),

    stagingPolicy:    () => call("/staging/policy"),
    stagingSetPolicy: (policy: string, confidenceMin?: string) =>
        call("/staging/policy", "POST", confidenceMin ? { policy, confidence_min: confidenceMin } : { policy }),

    candidates:          () => call("/candidates"),
    candidatesPromoteAll: () => call("/candidates/promote-all", "POST"),
    candidatesDiscardAll: () => call("/candidates/discard-all", "POST"),
    candidatePromote:    (slug: string) => call(`/candidates/${encodeURIComponent(slug)}/promote`, "POST"),
    candidateDiscard:    (slug: string) => call(`/candidates/${encodeURIComponent(slug)}/discard`, "POST"),

    contextBuild: (goal: string, tokenBudget: number) =>
        call("/context/build", "POST", { goal, token_budget: tokenBudget }),

    lifecycleStatus: () => call("/lifecycle/status"),
    lifecyclePages: () => call("/lifecycle/pages"),
    lifecycleEvents: (params: { slug?: string; to_state?: string; limit?: number; offset?: number }) => {
        const p = new URLSearchParams();
        if (params.slug) p.set("slug", params.slug);
        if (params.to_state) p.set("to_state", params.to_state);
        if (params.limit != null) p.set("limit", String(params.limit));
        if (params.offset != null) p.set("offset", String(params.offset));
        const qs = p.toString();
        return call(qs ? `/lifecycle/events?${qs}` : "/lifecycle/events");
    },
    lifecycleTransition: (slug: string, to_state: string, reason: string) =>
        call("/lifecycle/transition", "POST", { slug, to_state, reason }),

    exportWiki: (format: string, statusFilter = "all", contextPack?: string) =>
        callRaw("/export", "POST", {
            format,
            status_filter: statusFilter,
            ...(contextPack ? { context_pack: contextPack } : {}),
        }),

    exportWikiOkf: (statusFilter = "all"): Promise<Record<string, string>> =>
        call("/export", "POST", { format: "okf", status_filter: statusFilter }),

    queryStream: (question: string, sessionId: string | undefined, callbacks: import("./sse").SSECallbacks, noCache = false): Promise<void> => {
        const params = new URLSearchParams({ q: question });
        if (sessionId) params.set("session_id", sessionId);
        if (noCache) params.set("no_cache", "true");
        const url = `${BASE}/query/stream?${params.toString()}`;
        return import("./sse").then(({ consumeSSE }) => consumeSSE(url, callbacks));
    },
    createSession: (): Promise<{ session_id: string; mode: string; initial_hints: string[] }> => {
        return fetch(`${BASE}/sessions`, { method: "POST" }).then(r => r.json());
    },
};
