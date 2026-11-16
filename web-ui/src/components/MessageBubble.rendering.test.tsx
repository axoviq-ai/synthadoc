// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter White / axoviq.com
//
// Rendering regressions found while capturing the demos:
//   1. the grey "Sources:" line showed raw [[page]] links;
//   2. two citations with no space between them rendered as  a****b ;
//   3. **bold** next to full-width punctuation was not rendered.
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

describe("bold next to full-width (CJK) punctuation", () => {
    const cases: [string, string[]][] = [
        ["**重点（强调）**后续文字", ["重点（强调）"]],       // closing ** after （…） then CJK text
        ["文字**（加粗）**文字", ["（加粗）"]],               // opening ** before （ after CJK text
        ["**加粗**（说明）", ["加粗"]],                        // bold followed by （…）
        ["（**加粗**）", ["加粗"]],                            // bold inside （…）
        ["他说：**“你好”**然后离开了。", ["“你好”"]],           // curly quotes inside bold
        ["**注意：**请先备份。", ["注意："]],                   // full-width colon at the end of bold
    ];
    for (const [text, expected] of cases) {
        it(`renders ${JSON.stringify(text)}`, () => {
            const { container } = render(<MessageBubble msg={assistant(text)} />);
            expect(container.querySelector(".bubble-md")!.textContent).not.toContain("**");
            expect(strongTexts(container)).toEqual(expected);
        });
    }

    it("leaves ordinary English bold unchanged", () => {
        const { container } = render(<MessageBubble msg={assistant("A **bold** word and **another**.")} />);
        expect(strongTexts(container)).toEqual(["bold", "another"]);
    });

    it("does not touch ** inside code spans or fenced code", () => {
        const { container } = render(<MessageBubble msg={assistant("Use `**x**` or:\n\n```\n**y**\n```\n")} />);
        expect(strongTexts(container)).toEqual([]);
        expect(container.querySelector(".bubble-md")!.textContent).toContain("**x**");
        expect(container.querySelector(".bubble-md")!.textContent).toContain("**y**");
    });
});
