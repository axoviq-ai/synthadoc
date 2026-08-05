// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useState } from "react";

interface Props {
    lines: string[];
    collapsed?: boolean;
}

export default function ToolProgressBlock({ lines, collapsed: collapsedProp }: Props) {
    const [open, setOpen] = useState(true);
    const isCollapsed = collapsedProp ?? !open;
    return (
        <div className="tool-progress-block" style={{ margin: "4px 0", fontSize: "0.85em", color: "var(--muted, #888)" }}>
            <button
                onClick={() => setOpen(!open)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "inherit" }}
                aria-expanded={!isCollapsed}
            >
                {isCollapsed ? "▶ Working..." : "▼ Working..."}
            </button>
            {!isCollapsed && (
                <ul style={{ margin: "2px 0 2px 16px", padding: 0, listStyle: "none" }}>
                    {lines.map((l, i) => <li key={i}>{l}</li>)}
                </ul>
            )}
        </div>
    );
}
