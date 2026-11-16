// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter White / axoviq.com
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import ConfirmCard from "./components/ConfirmCard";
import { markdownPlugins } from "./markdownPlugins";

afterEach(cleanup);

const CJK = "**重点（强调）**后续文字";

describe("shared markdown plugins", () => {
    it("render CJK bold next to full-width punctuation", () => {
        const { container } = render(<ReactMarkdown remarkPlugins={markdownPlugins}>{CJK}</ReactMarkdown>);
        expect(container.querySelector("strong")?.textContent).toBe("重点（强调）");
        expect(container.textContent).not.toContain("**");
    });

    it("still render GitHub-flavoured markdown (tables, strikethrough, task lists)", () => {
        const md = "| a | b |\n|---|---|\n| 1 | 2 |\n\n~~gone~~\n\n- [x] done\n";
        const { container } = render(<ReactMarkdown remarkPlugins={markdownPlugins}>{md}</ReactMarkdown>);
        expect(container.querySelector("table")).not.toBeNull();
        expect(container.querySelector("del")?.textContent).toBe("gone");
        expect(container.querySelector("input[type=checkbox]")).not.toBeNull();
    });

    it("are used by the confirm card too (every ReactMarkdown site shares one list)", () => {
        const { container } = render(
            <ConfirmCard message={CJK} yesLabel="Yes" noLabel="No" onConfirm={vi.fn()} onDecline={vi.fn()} />,
        );
        expect(container.querySelector("strong")?.textContent).toBe("重点（强调）");
    });
});
