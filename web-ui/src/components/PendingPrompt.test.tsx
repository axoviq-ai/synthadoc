// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

afterEach(cleanup);

function TextInput({ pendingPrompt, onConsumed }: { pendingPrompt?: string | null; onConsumed?: () => void }) {
    const [value, setValue] = React.useState("");
    React.useEffect(() => {
        if (pendingPrompt != null) setValue(pendingPrompt);
    }, [pendingPrompt]);
    return (
        <input
            value={value}
            onChange={(e) => {
                setValue(e.target.value);
                if (e.target.value === "" && onConsumed) onConsumed();
            }}
            data-testid="input"
        />
    );
}

describe("pendingPrompt behavior", () => {
    it("fills input without auto-submitting", () => {
        const onSubmit = vi.fn();
        render(<TextInput pendingPrompt="Re-ingest stale pages" />);
        const el = screen.getByTestId("input") as HTMLInputElement;
        expect(el.value).toContain("Re-ingest");
        expect(onSubmit).not.toHaveBeenCalled();
    });

    it("calls onConsumed when input is cleared", () => {
        const onConsumed = vi.fn();
        render(<TextInput pendingPrompt="Re-ingest stale pages" onConsumed={onConsumed} />);
        fireEvent.change(screen.getByTestId("input"), { target: { value: "" } });
        expect(onConsumed).toHaveBeenCalledOnce();
    });
});
