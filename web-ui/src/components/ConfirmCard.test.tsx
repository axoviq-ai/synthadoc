// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, vi, afterEach, test } from "vitest";
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import ConfirmCard from "./ConfirmCard";
import ScopedConfirmCard from "./ScopedConfirmCard";

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

    it("shows countdown when ≤ 60 s remain", () => {
        vi.useFakeTimers();
        render(
            <ConfirmCard
                message="Proceed?"
                yesLabel="Yes"
                noLabel="No"
                onConfirm={vi.fn()}
                onDecline={vi.fn()}
                timeoutSeconds={90}
            />
        );
        // At t=0, 90 s remaining — above threshold, countdown hidden
        expect(screen.queryByText(/Auto-declining/)).toBeNull();
        // Advance 31 s — 59 s remain, countdown should appear.
        // act() is required to flush the React state updates triggered by the
        // setInterval tick after fake timers are advanced.
        act(() => { vi.advanceTimersByTime(31_000); });
        expect(screen.getByText(/Auto-declining in 59 s/)).toBeDefined();
        vi.useRealTimers();
    });

    it("default timeoutSeconds is 300", () => {
        vi.useFakeTimers();
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
        // Should NOT have fired after 120 s (old default)
        act(() => { vi.advanceTimersByTime(120_000); });
        expect(onDecline).not.toHaveBeenCalled();
        // Should fire after 300 s
        act(() => { vi.advanceTimersByTime(180_001); });
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

// ── ScopedConfirmCard tests ───────────────────────────────────────────────────

const BLOCKS = [
    { id: "b0", old_text: "old0", new_text: "new0", status: "applied" as const, rejection_reason: null },
    { id: "b1", old_text: "bad1", new_text: "x1",   status: "rejected" as const, rejection_reason: "no_match" },
];

test("renders block view with applied and rejected blocks", () => {
    render(
        <ScopedConfirmCard
            sessionId="s1"
            pageSlug="pg"
            currentBody="old0 keep"
            accumulatedBody="new0 keep"
            blocks={BLOCKS}
            defaultTab="blocks"
            headerMessage="1 edit ready · 1 rejected"
            onDecide={() => {}}
        />
    );
    expect(screen.getByText("new0")).toBeDefined();
    expect(screen.getByText(/No match/)).toBeDefined();
});

test("renders page view tab with CodeMirror", () => {
    render(
        <ScopedConfirmCard
            sessionId="s1"
            pageSlug="pg"
            currentBody="old0 keep"
            accumulatedBody="new0 keep"
            blocks={BLOCKS}
            defaultTab="page"
            headerMessage="No safe edits found — you can edit the page manually below."
            onDecide={() => {}}
        />
    );
    // Zero-blocks case opens on page tab; header must be visible
    expect(screen.getByText(/No safe edits found/)).toBeDefined();
});

test("Approve calls onDecide with blocks mode", () => {
    const onDecide = vi.fn();
    render(
        <ScopedConfirmCard
            sessionId="s1" pageSlug="pg"
            currentBody="old0" accumulatedBody="new0"
            blocks={[BLOCKS[0]]} defaultTab="blocks"
            headerMessage="1 edit ready"
            onDecide={onDecide}
        />
    );
    fireEvent.click(screen.getByText("Approve"));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({
        confirmed: true, mode: "blocks",
    }));
});

test("Reject button calls onDecide with confirmed=false and correct payload shape", () => {
    const onDecide = vi.fn();
    render(
        <ScopedConfirmCard
            sessionId="s1" pageSlug="pg"
            currentBody="old0" accumulatedBody="new0"
            blocks={BLOCKS} defaultTab="blocks"
            headerMessage="1 edit ready · 1 rejected"
            onDecide={onDecide}
        />
    );
    fireEvent.click(screen.getByText("Reject"));
    expect(onDecide).toHaveBeenCalledOnce();
    const payload = onDecide.mock.calls[0][0];
    expect(payload.confirmed).toBe(false);
    expect(payload.mode).toBe("blocks");
    expect(Array.isArray(payload.includedBlockIds)).toBe(true);
    expect(payload.pageBody).toBeNull();
});

test("page-mode Approve calls onDecide with mode='page'", () => {
    // Open on the page tab by default (simulates zero-blocks case)
    const onDecide = vi.fn();
    render(
        <ScopedConfirmCard
            sessionId="s2" pageSlug="pg2"
            currentBody="original" accumulatedBody="original"
            blocks={[]} defaultTab="page"
            headerMessage="No safe edits found — you can edit the page manually below."
            onDecide={onDecide}
        />
    );
    fireEvent.click(screen.getByText("Approve"));
    expect(onDecide).toHaveBeenCalledOnce();
    const payload = onDecide.mock.calls[0][0];
    expect(payload.confirmed).toBe(true);
    expect(payload.mode).toBe("page");
    // pageBody should be a string (the editor content)
    expect(typeof payload.pageBody).toBe("string");
});
