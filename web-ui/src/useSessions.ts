// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useState, useCallback, useEffect } from "react";
import { listSessions } from "./api";
import type { SessionSummary } from "./api";

export type { SessionSummary };

export function useSessions() {
    const [sessions, setSessions] = useState<SessionSummary[]>([]);

    const refresh = useCallback(async () => {
        try {
            const data = await listSessions();
            setSessions(data);
        } catch {
            // Server not reachable — keep existing list
        }
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    return { sessions, refresh };
}
