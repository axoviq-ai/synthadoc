// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useEffect, useCallback } from "react";
import { createSession } from "./api";
import type { SessionInfo } from "./api";

export function useSession() {
    const [session, setSession] = useState<SessionInfo | null>(null);
    const [hints, setHints] = useState<string[]>([]);
    const [sessionError, setSessionError] = useState<string | null>(null);

    useEffect(() => {
        createSession()
            .then((s) => {
                setSession(s);
                setHints(s.initial_hints);
            })
            .catch((err: unknown) => {
                setSessionError(err instanceof Error ? err.message : "Failed to connect to server");
            });
    }, []);

    const updateHints = useCallback((next: string[]) => setHints(next), []);

    return { session, hints, updateHints, sessionError };
}
