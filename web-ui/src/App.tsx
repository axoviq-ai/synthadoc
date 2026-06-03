// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useSession } from "./useSession";
import { ChatWindow } from "./components/ChatWindow";

const MODE_LABELS: Record<string, string> = {
    NEW_WIKI: "New Wiki",
    EXPLORER: "Explorer",
    HEALTH_CHECK: "Health Check",
    POWER_USER: "Power User",
};

export default function App() {
    const { session, hints, updateHints, sessionError } = useSession();

    return (
        <div className="app">
            <header className="app-header">
                <h1>Synthadoc</h1>
                {session && (
                    <span className="session-mode">
                        {MODE_LABELS[session.mode] ?? session.mode}
                    </span>
                )}
            </header>
            {!session && !sessionError && <p className="connecting">Connecting to server…</p>}
            {sessionError && <p className="error-banner" role="alert">{sessionError}</p>}
            <ChatWindow
                sessionId={session?.session_id ?? null}
                hints={hints}
                onHints={updateHints}
                wikiName={session?.wiki_name ?? ""}
            />
        </div>
    );
}
