// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useRef, useEffect } from "react";

const STORAGE_KEY = "synthadoc.queryTimeoutSeconds";
export const DEFAULT_TIMEOUT = 60;

export function readTimeoutSetting(): number {
    const v = localStorage.getItem(STORAGE_KEY);
    const n = v ? parseInt(v, 10) : DEFAULT_TIMEOUT;
    return isNaN(n) || n < 10 ? DEFAULT_TIMEOUT : n;
}

interface Props {
    timeoutSeconds: number;
    onChangeTimeout: (v: number) => void;
    onClose: () => void;
}

export function SettingsPopover({ timeoutSeconds, onChangeTimeout, onClose }: Props) {
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        function handleClick(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) onClose();
        }
        function handleKey(e: KeyboardEvent) {
            if (e.key === "Escape") onClose();
        }
        document.addEventListener("mousedown", handleClick);
        document.addEventListener("keydown", handleKey);
        return () => {
            document.removeEventListener("mousedown", handleClick);
            document.removeEventListener("keydown", handleKey);
        };
    }, [onClose]);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = parseInt(e.target.value, 10);
        if (!isNaN(v) && v >= 10) {
            localStorage.setItem(STORAGE_KEY, String(v));
            onChangeTimeout(v);
        }
    };

    return (
        <div className="settings-popover" ref={ref} role="dialog" aria-label="Settings">
            <p className="settings-title">Settings</p>
            <label className="settings-row">
                <span className="settings-label">Query timeout</span>
                <div className="settings-input-wrap">
                    <input
                        type="number"
                        min={10}
                        max={600}
                        step={10}
                        value={timeoutSeconds}
                        onChange={handleChange}
                        className="settings-input"
                        aria-label="Query timeout in seconds"
                    />
                    <span className="settings-unit">s</span>
                </div>
            </label>
        </div>
    );
}
