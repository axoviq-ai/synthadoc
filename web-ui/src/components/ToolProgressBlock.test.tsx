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

    it("collapses when collapsed prop is true", () => {
        render(<ToolProgressBlock lines={["Working..."]} collapsed />);
        const content = screen.queryByText("Working...");
        expect(content).toBeNull();
    });
});
