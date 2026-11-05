// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "../useQueryStream";

afterEach(cleanup);

describe("MessageBubble — blocked (action-required) messages", () => {
    it("renders in a distinct action-required box, not a plain assistant bubble", () => {
        const msg: Message = {
            id: "1",
            role: "assistant",
            text: "Turn off cross-wiki search (deselect the globe icon) and ask again to run this.",
            type: "blocked",
        };
        const { container } = render(<MessageBubble msg={msg} />);
        expect(container.querySelector(".blocked-bubble")).not.toBeNull();
        expect(container.querySelector(".bubble-assistant")).toBeNull();
    });

    it("renders markdown (bold/italic) instead of showing literal ** and * characters", () => {
        const msg: Message = {
            id: "2",
            role: "assistant",
            text: "**Actions and agentic workflows** need the full chat session.\n\n*Cross-wiki search skipped: operation detected*",
            type: "blocked",
        };
        const { container } = render(<MessageBubble msg={msg} />);
        expect(container.querySelector("strong")?.textContent).toBe("Actions and agentic workflows");
        expect(container.querySelector("em")?.textContent).toBe("Cross-wiki search skipped: operation detected");
        expect(container.textContent).not.toContain("**");
    });
});
