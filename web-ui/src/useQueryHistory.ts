// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useState, useCallback } from "react";

export interface HistoryEntry {
    id: string;
    question: string;
    timestamp: number;
}

const STORAGE_KEY = `synthadoc:query-history:${location.origin}`;
const MAX_ENTRIES = 50;

function loadHistory(): HistoryEntry[] {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
    } catch {
        return [];
    }
}

export function useQueryHistory() {
    const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);

    const addEntry = useCallback((question: string) => {
        setHistory((prev) => {
            // Deduplicate: move existing identical query to top
            const filtered = prev.filter((e) => e.question !== question);
            const entry: HistoryEntry = {
                id: crypto.randomUUID(),
                question,
                timestamp: Date.now(),
            };
            const next = [entry, ...filtered].slice(0, MAX_ENTRIES);
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* quota */ }
            return next;
        });
    }, []);

    return { history, addEntry };
}
