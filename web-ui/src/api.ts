// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

const BASE = "";  // same-origin; FastAPI serves at /query/stream etc.

export interface SessionInfo {
    session_id: string;
    mode: string;
    initial_hints: string[];
}

export interface StreamCallbacks {
    onToken: (text: string) => void;
    onCitations: (citations: string[]) => void;
    onGap: (suggestions: string[]) => void;
    onDone: (nextHints: string[]) => void;
    onError: (msg: string) => void;
}

export async function createSession(): Promise<SessionInfo> {
    const resp = await fetch(`${BASE}/sessions`, { method: "POST" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

export async function streamQuery(
    question: string,
    sessionId: string,
    callbacks: StreamCallbacks
): Promise<void> {
    const params = new URLSearchParams({ q: question, session_id: sessionId });
    const resp = await fetch(`${BASE}/query/stream?${params}`, {
        headers: { Accept: "text/event-stream" },
    });
    if (!resp.ok || !resp.body) {
        callbacks.onError(`HTTP ${resp.status}`);
        return;
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let evt = "message";
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split("\n");
            buf = lines.pop() ?? "";
            for (const line of lines) {
                if (line.startsWith("event:")) {
                    evt = line.slice(6).trim();
                } else if (line.startsWith("data:")) {
                    try {
                        const data = JSON.parse(line.slice(5).trim());
                        dispatch(evt, data, callbacks);
                    } catch { /* ignore */ }
                    evt = "message";
                }
            }
        }
    } finally {
        reader.cancel();
    }
}

function dispatch(event: string, data: Record<string, unknown>, cb: StreamCallbacks) {
    switch (event) {
        case "token": cb.onToken(data.text as string); break;
        case "citations": cb.onCitations((data.citations as string[]) ?? []); break;
        case "gap": cb.onGap((data.suggested_searches as string[]) ?? []); break;
        case "done": cb.onDone((data.next_hints as string[]) ?? []); break;
        case "error": cb.onError(data.message as string); break;
    }
}
