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

export interface ToolProgressData {
    tool: string;
    job_id?: string;
    message: string;
}

export interface ConfirmRequestData {
    session_id: string;
    message: string;
    yes_label: string;
    no_label: string;
    /** Unified diff string — present only for diff-review confirms (e.g. contradiction resolver). */
    diff?: string;
}

export interface StreamCallbacks {
    onToken: (text: string) => void;
    onCitations: (citations: string[]) => void;
    onGap: (suggestions: string[]) => void;
    onDone: (nextHints: string[], prePrompt?: string) => void;
    onError: (msg: string) => void;
    onClarify?: (data: ClarifyData) => void;
    onNotice?: (text: string) => void;
    onToolProgress?: (data: ToolProgressData) => void;
    onConfirmRequest?: (data: ConfirmRequestData) => void;
}

export interface SessionSummary {
    session_id: string;
    mode: string;
    first_q: string;
    last_active: string;
    turn_count: number;
    questions: string[];
}

export interface SessionMessage {
    role: string;
    content: string;
    citations: string[];
    gap_suggestions: string[];
}

export async function createSession(): Promise<SessionInfo> {
    const resp = await fetch(`${BASE}/sessions`, { method: "POST" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

export async function listSessions(limit = 20): Promise<SessionSummary[]> {
    const resp = await fetch(`${BASE}/sessions?limit=${limit}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

export async function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
    const resp = await fetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}/messages`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

export async function getHints(mode: string): Promise<string[]> {
    const resp = await fetch(`${BASE}/hints?mode=${encodeURIComponent(mode)}`);
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.hints ?? [];
}

export async function streamQuery(
    question: string,
    sessionId: string,
    callbacks: StreamCallbacks,
    signal?: AbortSignal,
    noCache?: boolean,
    timeoutSeconds?: number,
): Promise<void> {
    const params = new URLSearchParams({ q: question, session_id: sessionId });
    if (noCache) params.set("no_cache", "true");
    if (timeoutSeconds != null) params.set("timeout_seconds", String(timeoutSeconds));
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
            const prePrompt = typeof data.pre_prompt === "string" ? data.pre_prompt : undefined;
            cb.onDone(hints, prePrompt);
            break;
        }
        case "tool_progress": {
            if (cb.onToolProgress) {
                cb.onToolProgress({
                    tool: typeof data.tool === "string" ? data.tool : "",
                    job_id: typeof data.job_id === "string" ? data.job_id : undefined,
                    message: typeof data.message === "string" ? data.message : "",
                });
            }
            break;
        }
        case "confirm_request": {
            if (cb.onConfirmRequest) {
                cb.onConfirmRequest({
                    session_id: typeof data.session_id === "string" ? data.session_id : "",
                    message: typeof data.message === "string" ? data.message : "",
                    yes_label: typeof data.yes_label === "string" ? data.yes_label : "Yes",
                    no_label: typeof data.no_label === "string" ? data.no_label : "No",
                    diff: typeof data.diff === "string" ? data.diff : undefined,
                });
            }
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
