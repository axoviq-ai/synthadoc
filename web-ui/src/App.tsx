// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useCallback } from "react";
import { useSession } from "./useSession";
import { useQueryHistory } from "./useQueryHistory";
import { Sidebar } from "./components/Sidebar";
import { ChatWindow } from "./components/ChatWindow";
import heroBg from "./assets/hero-bg.png";

export default function App() {
    const { session, hints, updateHints, sessionError, resetSession } = useSession();
    const { history, addEntry } = useQueryHistory();
    const [resetKey, setResetKey] = useState(0);
    const [injectedQuery, setInjectedQuery] = useState<string | null>(null);
    const [lastQuestion, setLastQuestion] = useState<string | null>(null);

    const handleNewRun = useCallback(async () => {
        setResetKey((k) => k + 1);
        setInjectedQuery(null);
        setLastQuestion(null);
        await resetSession();
    }, [resetSession]);

    const handleSelect = useCallback((question: string) => {
        setInjectedQuery(question);
        setLastQuestion(question);
    }, []);

    const handleQuerySent = useCallback((question: string) => {
        addEntry(question);
        setLastQuestion(question);
    }, [addEntry]);

    const handleInjected = useCallback(() => {
        setInjectedQuery(null);
    }, []);

    return (
        <div className="app-layout">
            <Sidebar
                wikiName={session?.wiki_name ?? ""}
                connected={!!session}
                history={history}
                activeQuestion={lastQuestion}
                onSelect={handleSelect}
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
                    injectedQuery={injectedQuery}
                    onInjected={handleInjected}
                    onQuerySent={handleQuerySent}
                    showTip={history.length > 0}
                />
            </main>
        </div>
    );
}
