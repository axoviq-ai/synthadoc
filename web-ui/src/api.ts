// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

const BASE = "";  // same-origin; FastAPI serves at /query/stream etc.

export interface SessionInfo {
    session_id: string;
    mode: string;
    initial_hints: string[];
    wiki_name?: string;
}

export interface ClarifyData {
    prompt: string;
    candidates: string[];
    action: string;
}

export interface StreamCallbacks {
    onToken: (text: string) => void;
    onCitations: (citations: string[]) => void;
    onGap: (suggestions: string[]) => void;
    onDone: (nextHints: string[]) => void;
    onError: (msg: string) => void;
    onClarify?: (data: ClarifyData) => void;
    onNotice?: (text: string) => void;
}

export async function createSession(): Promise<SessionInfo> {
    const resp = await fetch(`${BASE}/sessions`, { method: "POST" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

export async function streamQuery(
    question: string,
    sessionId: string,
    callbacks: StreamCallbacks,
    signal?: AbortSignal,
    noCache?: boolean,
): Promise<void> {
    const params = new URLSearchParams({ q: question, session_id: sessionId });
    if (noCache) params.set("no_cache", "true");
    const resp = await fetch(`${BASE}/query/stream?${params}`, {
        headers: { Accept: "text/event-stream" },
        signal,
    });
    if (!resp.ok || !resp.body) {
        callbacks.onError(`HTTP ${resp.status}`);
        return;
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let evt = "message";
    let terminated = false;
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split(/\r?\n/);
            buf = lines.pop() ?? "";
            for (const line of lines) {
                if (line.startsWith("event:")) {
                    evt = line.slice(6).trim();
                } else if (line.startsWith("data:")) {
                    try {
                        const data = JSON.parse(line.slice(5).trim());
                        if (evt === "done" || evt === "error") terminated = true;
                        dispatch(evt, data, callbacks);
                    } catch { /* ignore */ }
                } else if (line === "") {
                    // Blank line signals end of one SSE event record; reset event name for next record.
                    evt = "message";
                }
            }
        }
    } finally {
        if (!terminated) callbacks.onError("Stream ended unexpectedly");
        reader.cancel();
    }
}

function dispatch(event: string, data: Record<string, unknown>, cb: StreamCallbacks) {
    switch (event) {
        case "token": {
            const text = typeof data.text === "string" ? data.text : "";
            cb.onToken(text);
            break;
        }
        case "citations": {
            const citations = Array.isArray(data.citations)
                ? (data.citations as unknown[]).filter((c): c is string => typeof c === "string")
                : [];
            cb.onCitations(citations);
            break;
        }
        case "gap": {
            const suggestions = Array.isArray(data.suggested_searches)
                ? (data.suggested_searches as unknown[]).filter((s): s is string => typeof s === "string")
                : [];
            cb.onGap(suggestions);
            break;
        }
        case "done": {
            const hints = Array.isArray(data.next_hints)
                ? (data.next_hints as unknown[]).filter((h): h is string => typeof h === "string")
                : [];
            cb.onDone(hints);
            break;
        }
        case "error": {
            const msg = typeof data.message === "string" ? data.message : "unknown error";
            cb.onError(msg);
            break;
        }
        case "clarify": {
            if (cb.onClarify) {
                const prompt = typeof data.prompt === "string" ? data.prompt : "";
                const candidates = Array.isArray(data.candidates)
                    ? (data.candidates as unknown[]).filter((c): c is string => typeof c === "string")
                    : [];
                const action = typeof data.action === "string" ? data.action : "";
                cb.onClarify({ prompt, candidates, action });
            }
            break;
        }
        case "notice": {
            if (cb.onNotice) {
                const text = typeof data.text === "string" ? data.text : "";
                cb.onNotice(text);
            }
            break;
        }
    }
}
