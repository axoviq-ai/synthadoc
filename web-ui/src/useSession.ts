// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useEffect } from "react";
import { createSession } from "./api";
import type { SessionInfo } from "./api";

export function useSession() {
    const [session, setSession] = useState<SessionInfo | null>(null);
    const [hints, setHints] = useState<string[]>([]);

    useEffect(() => {
        createSession()
            .then((s) => {
                setSession(s);
                setHints(s.initial_hints);
            })
            .catch(() => {
                // server not ready; session will be null
            });
    }, []);

    const updateHints = (next: string[]) => setHints(next);

    return { session, hints, updateHints };
}
