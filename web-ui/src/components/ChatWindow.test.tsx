// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter W. / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

const send = vi.fn();
vi.mock("../useQueryStream", () => ({
    useQueryStream: () => ({
        messages: [], streaming: false, error: null, send,
        progressLines: [], pendingConfirm: null, setPendingConfirm: vi.fn(),
    }),
}));

import { ChatWindow } from "./ChatWindow";

afterEach(() => { cleanup(); send.mockClear(); });

function renderChat(onOwnQuestion: () => void) {
    render(<ChatWindow sessionId="s1" mode="POWER_USER" hints={["Who is Grace Hopper and what are they known for?"]}
                       onHints={vi.fn()} wikiName="demo" injectedQuery={null} onInjected={vi.fn()}
                       onQuerySent={vi.fn()} onOwnQuestion={onOwnQuestion} showTip={false}
                       initialMessages={[]} resolvedDark={false} />);
}

describe("ChatWindow", () => {
    it("reports a typed question, so pinned graph suggestions give way", () => {
        const onOwnQuestion = vi.fn();
        renderChat(onOwnQuestion);
        const box = screen.getByPlaceholderText("Ask your wiki...");
        fireEvent.change(box, { target: { value: "Plankalkul" } });
        fireEvent.keyDown(box, { key: "Enter" });
        expect(send).toHaveBeenCalledWith("Plankalkul", expect.anything(), expect.anything(), expect.anything());
        expect(onOwnQuestion).toHaveBeenCalledTimes(1);
    });

    it("does not report a suggestion sent as-is as the user's own question", () => {
        const onOwnQuestion = vi.fn();
        renderChat(onOwnQuestion);
        fireEvent.click(screen.getByText("Who is Grace Hopper and what are they known for?"));   // fills the box
        fireEvent.keyDown(screen.getByPlaceholderText("Ask your wiki..."), { key: "Enter" });
        expect(send).toHaveBeenCalledWith("Who is Grace Hopper and what are they known for?",
                                          expect.anything(), expect.anything(), expect.anything());
        expect(onOwnQuestion).not.toHaveBeenCalled();
    });

    it("reports an edited suggestion as the user's own question", () => {
        const onOwnQuestion = vi.fn();
        renderChat(onOwnQuestion);
        fireEvent.click(screen.getByText("Who is Grace Hopper and what are they known for?"));
        const box = screen.getByPlaceholderText("Ask your wiki...");
        fireEvent.change(box, { target: { value: "What did Grace Hopper build in 1952?" } });
        fireEvent.keyDown(box, { key: "Enter" });
        expect(onOwnQuestion).toHaveBeenCalledTimes(1);
    });
});
