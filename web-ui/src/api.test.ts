// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter W. / axoviq.com
import { describe, it, expect, vi } from "vitest";
import { dispatch, type StreamCallbacks } from "./api";

function callbacks(): StreamCallbacks {
    return { onToken: vi.fn(), onAnswer: vi.fn(), onCitations: vi.fn(), onGap: vi.fn(),
             onDone: vi.fn(), onError: vi.fn() } as unknown as StreamCallbacks;
}

describe("dispatch", () => {
    it("passes the final answer text, with citation links resolved, to onAnswer", () => {
        const cb = callbacks();
        dispatch("answer", { text: "Zuse designed Plankalkül ([[konrad-zuse]])." }, cb);
        expect(cb.onAnswer).toHaveBeenCalledWith("Zuse designed Plankalkül ([[konrad-zuse]]).");
        expect(cb.onToken).not.toHaveBeenCalled();
    });

    it("ignores an answer event without text", () => {
        const cb = callbacks();
        dispatch("answer", {}, cb);
        expect(cb.onAnswer).not.toHaveBeenCalled();
    });
});
