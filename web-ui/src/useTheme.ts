// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useState, useEffect } from "react";

export type ThemeMode = "system" | "dark" | "light";

const STORAGE_KEY = "synthadoc-theme";

export function useTheme() {
    const [mode, setMode] = useState<ThemeMode>(() => {
        try {
            const s = localStorage.getItem(STORAGE_KEY);
            if (s === "dark" || s === "system" || s === "light") return s as ThemeMode;
        } catch { /* ignore */ }
        return "system";
    });

    useEffect(() => {
        const root = document.documentElement;
        if (mode === "system") {
            root.removeAttribute("data-theme");
        } else {
            root.setAttribute("data-theme", mode);
        }
        try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* ignore */ }
    }, [mode]);

    const cycle = () =>
        setMode(m => m === "system" ? "dark" : m === "dark" ? "light" : "system");

    return { mode, cycle };
}
