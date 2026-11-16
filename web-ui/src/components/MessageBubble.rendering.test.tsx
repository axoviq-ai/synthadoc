// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter White / axoviq.com
//
// Rendering regressions found while capturing the demos:
//   1. the grey "Sources:" line showed raw [[page]] links;
//   2. two citations with no space between them rendered as  a****b .
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "../useQueryStream";

afterEach(cleanup);

function assistant(text: string, citations?: string[]): Message {
    return { id: "1", role: "assistant", text, citations } as Message;
}

function strongTexts(container: HTMLElement): string[] {
    return Array.from(container.querySelectorAll(".bubble-md strong")).map(e => e.textContent ?? "");
}

describe("Sources line", () => {
    it("shows same-wiki citations as page names, never as raw [[page]] links", () => {
        const { container } = render(
            <MessageBubble msg={assistant("Answer.", ["alan-turing", "eniac"])} />,
        );
        const sources = container.querySelector(".bubble-citations")!;
        expect(sources.textContent).not.toContain("[[");
        expect(sources.textContent).not.toContain("]]");
        expect(sources.textContent).toContain("alan-turing");
        expect(sources.textContent).toContain("eniac");
    });

    it("keeps the comma separation between citations", () => {
        const { container } = render(<MessageBubble msg={assistant("A.", ["a", "b", "c"])} />);
        expect(container.querySelector(".bubble-citations")!.textContent).toMatch(/a.*,.*b.*,.*c/);
    });

    it("still renders cross-wiki citations as a two-part pill", () => {
        const { container } = render(
            <MessageBubble msg={assistant("A.", ["finance-wiki::Leverage"])} />,
        );
        expect(container.querySelector(".citation-pill__wiki")!.textContent).toBe("finance-wiki");
        expect(container.querySelector(".citation-pill__page")!.textContent).toBe("Leverage");
    });
});

describe("adjacent citations", () => {
    it("renders two citations with no space between them as two separate bold titles", () => {
        const { container } = render(
            <MessageBubble msg={assistant("See [[Alan Turing]][[ENIAC]] for details.")} />,
        );
        expect(container.querySelector(".bubble-md")!.textContent).not.toContain("*");
        expect(strongTexts(container)).toEqual(["Alan Turing", "ENIAC"]);
    });

    it("handles three in a row and cross-wiki ones too", () => {
        const { container } = render(
            <MessageBubble msg={assistant("[[a]][[b]][[wiki-x::C]]")} />,
        );
        expect(container.querySelector(".bubble-md")!.textContent).not.toContain("*");
        expect(strongTexts(container)).toEqual(["a", "b", "[wiki-x]"]);
    });

    it("does not change the text of citations that are already separated", () => {
        const { container } = render(
            <MessageBubble msg={assistant("See [[a]], [[b]] and [[c]].")} />,
        );
        expect(container.querySelector(".bubble-md")!.textContent).toBe("See a, b and c.");
    });
});
