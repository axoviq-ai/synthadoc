// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useState, useCallback } from "react";
import { useSession } from "./useSession";
import { useSessions } from "./useSessions";
import { getSessionMessages, getHints } from "./api";
import { Sidebar } from "./components/Sidebar";
import { ChatWindow } from "./components/ChatWindow";
import type { Message } from "./useQueryStream";
import heroBg from "./assets/hero-bg.png";

export default function App() {
    const { session, hints, updateHints, sessionError, resetSession, resumeSession } = useSession();
    const { sessions, refresh: refreshSessions } = useSessions();
    const [resetKey, setResetKey] = useState(0);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [initialMessages, setInitialMessages] = useState<Message[]>([]);

    const handleNewRun = useCallback(async () => {
        setResetKey((k) => k + 1);
        setInitialMessages([]);
        setActiveSessionId(null);
        await resetSession();
    }, [resetSession]);

    const handleSelectSession = useCallback(async (sessionId: string, mode: string) => {
        resumeSession(sessionId, mode);
        const [msgs, hints] = await Promise.allSettled([
            getSessionMessages(sessionId),
            getHints(mode),
        ]);
        const mapped: Message[] = msgs.status === "fulfilled"
            ? msgs.value.map((m) => ({
                id: crypto.randomUUID(),
                role: m.role as "user" | "assistant",
                text: m.content,
                citations: m.citations.length > 0 ? m.citations : undefined,
                gapSuggestions: m.gap_suggestions.length > 0 ? m.gap_suggestions : undefined,
            }))
            : [];
        setInitialMessages(mapped);
        if (hints.status === "fulfilled") updateHints(hints.value);
        setActiveSessionId(sessionId);
        setResetKey((k) => k + 1);
    }, [resumeSession, updateHints]);

    const handleQuerySent = useCallback(() => {
        refreshSessions();
    }, [refreshSessions]);

    return (
        <div className="app-layout">
            <Sidebar
                wikiName={session?.wiki_name ?? ""}
                connected={!!session}
                sessions={sessions}
                activeSessionId={activeSessionId}
                onSelectSession={handleSelectSession}
                onNewRun={handleNewRun}
            />
            <main className="main-panel" style={{ backgroundImage: `url(${heroBg})` }}>
                {sessionError && (
                    <p className="error-banner error-banner-top" role="alert">{sessionError}</p>
                )}
                <ChatWindow
                    key={resetKey}
                    sessionId={session?.session_id ?? null}
                    mode={session?.mode ?? ""}
                    hints={hints}
                    onHints={updateHints}
                    wikiName={session?.wiki_name ?? ""}
                    injectedQuery={null}
                    onInjected={() => {}}
                    onQuerySent={handleQuerySent}
                    showTip={sessions.length > 0}
                    initialMessages={initialMessages}
                />
            </main>
        </div>
    );
}
