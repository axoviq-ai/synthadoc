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
    const latest = lines[lines.length - 1] ?? "";
    const history = lines.slice(0, -1);
    return (
        <div className="tool-progress-block" style={{ margin: "4px 0", fontSize: "0.85em", color: "var(--muted, #888)" }}>
            <button
                onClick={() => setOpen(!open)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "inherit" }}
                aria-expanded={!isCollapsed}
            >
                {isCollapsed ? "▶" : "▼"}
            </button>
            {" "}
            <span style={{ fontStyle: "italic" }}>{latest || "Working..."}</span>
            {!isCollapsed && history.length > 0 && (
                <ul style={{ margin: "2px 0 2px 16px", padding: 0, listStyle: "none", color: "var(--muted, #aaa)" }}>
                    {history.map((l, i) => <li key={i}>{l}</li>)}
                </ul>
            )}
        </div>
    );
}
