// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

export interface SSECallbacks {
    onStatus?: (phase: string, sources?: number) => void;
    onToken: (text: string) => void;
    onCitations: (citations: string[]) => void;
    onGap?: (suggestions: string[]) => void;
    onDone: (nextHints: string[]) => void | Promise<void>;
    onError?: (message: string) => void;
}

/**
 * Consume an SSE stream from a URL, dispatching events to callbacks.
 * Uses fetch() with a ReadableStream reader — works in Obsidian's browser context.
 */
export async function consumeSSE(url: string, callbacks: SSECallbacks): Promise<void> {
    const resp = await fetch(url, { method: "GET", headers: { Accept: "text/event-stream" } });
    if (!resp.ok || !resp.body) {
        callbacks.onError?.(`HTTP ${resp.status}`);
        return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "message";

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
                if (line.startsWith("event:")) {
                    currentEvent = line.slice(6).trim();
                } else if (line.startsWith("data:")) {
                    const raw = line.slice(5).trim();
                    try {
                        const data = JSON.parse(raw);
                        await _dispatch(currentEvent, data, callbacks);
                    } catch { /* ignore malformed */ }
                    currentEvent = "message";
                }
            }
        }
    } finally {
        reader.cancel();
    }
}

async function _dispatch(event: string, data: Record<string, unknown>, cb: SSECallbacks): Promise<void> {
    switch (event) {
        case "status":
            cb.onStatus?.(data.phase as string, data.sources as number | undefined);
            break;
        case "token":
            cb.onToken(data.text as string);
            break;
        case "citations":
            cb.onCitations((data.citations as string[]) ?? []);
            break;
        case "gap":
            cb.onGap?.((data.suggested_searches as string[]) ?? []);
            break;
        case "done":
            await cb.onDone((data.next_hints as string[]) ?? []);
            break;
        case "error":
            cb.onError?.(data.message as string);
            break;
    }
}
