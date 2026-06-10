// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useEffect, useCallback } from "react";
import { createSession } from "./api";
import type { SessionInfo } from "./api";

export function useSession() {
    const [session, setSession] = useState<SessionInfo | null>(null);
    const [hints, setHints] = useState<string[]>([]);
    const [sessionError, setSessionError] = useState<string | null>(null);

    const initSession = useCallback(async () => {
        try {
            const s = await createSession();
            setSession(s);
            setHints(s.initial_hints);
            setSessionError(null);
        } catch (err: unknown) {
            setSessionError(err instanceof Error ? err.message : "Failed to connect to server");
        }
    }, []);

    useEffect(() => { initSession(); }, [initSession]);

    const resetSession = useCallback(async () => {
        setSession(null);
        setHints([]);
        await initSession();
    }, [initSession]);

    const resumeSession = useCallback((sessionId: string, mode: string) => {
        setSession(prev => ({
            session_id: sessionId,
            mode,
            initial_hints: [],
            wiki_name: prev?.wiki_name ?? "",
        }));
        setHints([]);
    }, []);

    const updateHints = useCallback((next: string[]) => setHints(next), []);

    return { session, hints, updateHints, sessionError, resetSession, resumeSession };
}
