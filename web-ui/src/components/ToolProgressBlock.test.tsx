// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import ToolProgressBlock from "./ToolProgressBlock";

afterEach(cleanup);

describe("ToolProgressBlock", () => {
    it("renders progress message", () => {
        render(<ToolProgressBlock lines={["Re-ingesting page 1/2..."]} />);
        expect(screen.getByText(/re-ingesting/i)).toBeDefined();
    });

    it("always shows latest line; hides history when collapsed", () => {
        // ToolProgressBlock always renders the latest progress message.
        // When collapsed, history entries (all but the last line) are hidden.
        render(<ToolProgressBlock lines={["older step", "Working..."]} collapsed />);
        // Latest line is always visible.
        expect(screen.getByText("Working...")).toBeDefined();
        // History (older entries) is hidden when collapsed.
        expect(screen.queryByText("older step")).toBeNull();
    });
});
