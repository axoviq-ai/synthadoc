// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter W. / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";
import { consumeSSE } from "./sse";

afterEach(() => { vi.unstubAllGlobals(); });

function stream(text: string): Response {
    const body = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(text)); c.close(); } });
    return new Response(body, { status: 200 });
}

describe("consumeSSE", () => {
    it("hands the final answer, with citation links resolved, to onAnswer", async () => {
        vi.stubGlobal("fetch", vi.fn(async () => stream(
            'event: token\ndata: {"text": "Zuse ([[konrad-zuse-z3-computer]])."}\n\n' +
            'event: answer\ndata: {"text": "Zuse ([[konrad-zuse]])."}\n\n' +
            'event: done\ndata: {"next_hints": []}\n\n')));
        const onToken = vi.fn(), onAnswer = vi.fn(), onDone = vi.fn();
        await consumeSSE("http://127.0.0.1:7070/query/stream?q=x",
                         { onToken, onAnswer, onCitations: vi.fn(), onDone });
        expect(onToken).toHaveBeenCalledWith("Zuse ([[konrad-zuse-z3-computer]]).");
        expect(onAnswer).toHaveBeenCalledWith("Zuse ([[konrad-zuse]]).");
        expect(onDone).toHaveBeenCalled();
    });
});
