// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import ConfirmCard from "./ConfirmCard";

afterEach(cleanup);

describe("ConfirmCard", () => {
    it("renders yes and no buttons with correct labels", () => {
        render(
            <ConfirmCard
                message="Re-ingest 2 pages?"
                yesLabel="Yes, proceed"
                noLabel="Cancel"
                onConfirm={vi.fn()}
                onDecline={vi.fn()}
            />
        );
        expect(screen.getByText("Yes, proceed")).toBeDefined();
        expect(screen.getByText("Cancel")).toBeDefined();
        expect(screen.getByText("Re-ingest 2 pages?")).toBeDefined();
    });

    it("calls onConfirm when Yes is clicked", () => {
        const onConfirm = vi.fn();
        render(
            <ConfirmCard
                message="Proceed?"
                yesLabel="Yes"
                noLabel="No"
                onConfirm={onConfirm}
                onDecline={vi.fn()}
            />
        );
        fireEvent.click(screen.getByText("Yes"));
        expect(onConfirm).toHaveBeenCalledOnce();
    });

    it("calls onDecline when No is clicked", () => {
        const onDecline = vi.fn();
        render(
            <ConfirmCard
                message="Proceed?"
                yesLabel="Yes"
                noLabel="No"
                onConfirm={vi.fn()}
                onDecline={onDecline}
            />
        );
        fireEvent.click(screen.getByText("No"));
        expect(onDecline).toHaveBeenCalledOnce();
    });

    it("auto-dismisses via onDecline after timeoutSeconds", () => {
        vi.useFakeTimers();
        const onDecline = vi.fn();
        render(
            <ConfirmCard
                message="Proceed?"
                yesLabel="Yes"
                noLabel="No"
                onConfirm={vi.fn()}
                onDecline={onDecline}
                timeoutSeconds={1}
            />
        );
        expect(onDecline).not.toHaveBeenCalled();
        vi.advanceTimersByTime(1001);
        expect(onDecline).toHaveBeenCalledOnce();
        vi.useRealTimers();
    });

    it("renders diff viewer when diff prop is provided", () => {
        const diff = [
            "--- slug (current)",
            "+++ slug (proposed)",
            "@@ -1,3 +1,3 @@",
            " unchanged line",
            "-removed line",
            "+added line",
        ].join("\n");
        render(
            <ConfirmCard
                message="Apply changes to `slug`?"
                yesLabel="Apply"
                noLabel="Skip"
                diff={diff}
                onConfirm={vi.fn()}
                onDecline={vi.fn()}
            />
        );
        // Verify file headers, hunk marker, and changed lines are rendered.
        // Context lines have a leading space that getByText normalization strips —
        // testing the changed-line markers (+/-) is sufficient to verify the viewer.
        expect(screen.getByText("--- slug (current)")).toBeDefined();
        expect(screen.getByText("+++ slug (proposed)")).toBeDefined();
        expect(screen.getByText("@@ -1,3 +1,3 @@")).toBeDefined();
        expect(screen.getByText("-removed line")).toBeDefined();
        expect(screen.getByText("+added line")).toBeDefined();
    });

    it("does not render diff viewer when diff prop is absent", () => {
        render(
            <ConfirmCard
                message="Continue?"
                yesLabel="Yes"
                noLabel="No"
                onConfirm={vi.fn()}
                onDecline={vi.fn()}
            />
        );
        // No diff lines should be present
        expect(screen.queryByText(/^@@/)).toBeNull();
        expect(screen.queryByText(/^\+\+\+/)).toBeNull();
    });
});
