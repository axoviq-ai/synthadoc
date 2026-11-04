// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useQueryStream } from "./useQueryStream";
import type { CrossWikiCallbacks, StreamCallbacks } from "./api";

vi.mock("./api", () => ({
    streamQuery: vi.fn(),
    streamCrossWikiQuery: vi.fn(),
}));

import { streamCrossWikiQuery } from "./api";

describe("useQueryStream — cross-wiki operation-blocked response", () => {
    it("tells the caller to leave existing hints alone and pre-fills the question that was asked", async () => {
        const onHints = vi.fn();
        vi.mocked(streamCrossWikiQuery).mockImplementation(
            async (_question, _sessionId, cb: CrossWikiCallbacks) => {
                cb.onCrossWikiSkipped?.("operation detected");
                (cb as StreamCallbacks).onToken(
                    "Turn off cross-wiki search (deselect the globe icon) and ask again to run this."
                );
                cb.onDone([], undefined); // backend never sends next_hints/pre_prompt for this case
            },
        );
        const { result } = renderHook(() => useQueryStream("session-1", onHints));

        await act(async () => {
            await result.current.send("Run lint and report", false, undefined, true);
        });

        // undefined hints = "don't touch the chips that are already showing";
        // prePrompt falls back to the original question so the user can just
        // disable cross-wiki and hit Ask again without retyping it.
        expect(onHints).toHaveBeenCalledWith(undefined, "Run lint and report");
        // The message itself renders as an action-required box, not a plain
        // answer bubble, so it's easy to spot that something needs doing.
        const last = result.current.messages[result.current.messages.length - 1];
        expect(last.type).toBe("blocked");
    });

    it("still updates hints and prePrompt normally for an ordinary cross-wiki answer", async () => {
        const onHints = vi.fn();
        vi.mocked(streamCrossWikiQuery).mockImplementation(
            async (_question, _sessionId, cb: CrossWikiCallbacks) => {
                (cb as StreamCallbacks).onToken("Turing was born in 1912.");
                cb.onDone(["who else worked at Bletchley Park?"], undefined);
            },
        );
        const { result } = renderHook(() => useQueryStream("session-1", onHints));

        await act(async () => {
            await result.current.send("when was Turing born?", false, undefined, true);
        });

        expect(onHints).toHaveBeenCalledWith(["who else worked at Bletchley Park?"], undefined);
    });
});
