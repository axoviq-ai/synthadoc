// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useRef, useEffect } from "react";

const STORAGE_KEY_TIMEOUT = "synthadoc.queryTimeoutSeconds";
const STORAGE_KEY_MAX_RESULTS = "synthadoc.maxSearchResults";
export const DEFAULT_TIMEOUT = 60;
export const DEFAULT_MAX_RESULTS = 5;

export function readTimeoutSetting(): number {
    const v = localStorage.getItem(STORAGE_KEY_TIMEOUT);
    const n = v ? parseInt(v, 10) : DEFAULT_TIMEOUT;
    return isNaN(n) || n < 10 ? DEFAULT_TIMEOUT : n;
}

export function readMaxResultsSetting(): number {
    const v = localStorage.getItem(STORAGE_KEY_MAX_RESULTS);
    const n = v ? parseInt(v, 10) : DEFAULT_MAX_RESULTS;
    return isNaN(n) || n < 1 ? DEFAULT_MAX_RESULTS : n;
}

interface Props {
    timeoutSeconds: number;
    onChangeTimeout: (v: number) => void;
    maxResults: number;
    onChangeMaxResults: (v: number) => void;
    onClose: () => void;
}

export function SettingsPopover({ timeoutSeconds, onChangeTimeout, maxResults, onChangeMaxResults, onClose }: Props) {
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

    const handleTimeout = (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = parseInt(e.target.value, 10);
        if (!isNaN(v) && v >= 10) {
            localStorage.setItem(STORAGE_KEY_TIMEOUT, String(v));
            onChangeTimeout(v);
        }
    };

    const handleMaxResults = (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = parseInt(e.target.value, 10);
        if (!isNaN(v) && v >= 1) {
            localStorage.setItem(STORAGE_KEY_MAX_RESULTS, String(v));
            onChangeMaxResults(v);
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
                        onChange={handleTimeout}
                        className="settings-input"
                        aria-label="Query timeout in seconds"
                    />
                    <span className="settings-unit">s</span>
                </div>
            </label>
            <label className="settings-row">
                <span className="settings-label">Search results</span>
                <div className="settings-input-wrap">
                    <input
                        type="number"
                        min={1}
                        max={20}
                        step={1}
                        value={maxResults}
                        onChange={handleMaxResults}
                        className="settings-input"
                        aria-label="Max search results per enrich"
                        title="Max number of URLs to index per web search enrichment"
                    />
                    <span className="settings-unit">pages</span>
                </div>
            </label>
        </div>
    );
}
