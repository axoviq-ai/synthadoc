// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

afterEach(cleanup);
import ConfirmCard from "./ConfirmCard";

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
});
