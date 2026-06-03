// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import sidebarBg from "../assets/sidebar-bg.png";
import type { HistoryEntry } from "../useQueryHistory";

function formatRelativeTime(ts: number): string {
    const diffMs = Date.now() - ts;
    const mins = Math.floor(diffMs / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return "Yesterday";
    return `${days}d ago`;
}

interface Props {
    wikiName: string;
    connected: boolean;
    history: HistoryEntry[];
    activeQuestion: string | null;
    onSelect: (question: string) => void;
    onNewRun: () => void;
}

export function Sidebar({ wikiName, connected, history, activeQuestion, onSelect, onNewRun }: Props) {
    return (
        <aside className="sidebar" style={{ backgroundImage: `url(${sidebarBg})` }}>
            <div className="sidebar-logo">
                <SynthadocLogo />
                <span className="sidebar-brand">Synthadoc</span>
            </div>

            <button className="new-run-btn" onClick={onNewRun}>
                <span className="new-run-plus">+</span>
                New Run
            </button>

            <section className="sidebar-history">
                {history.length > 0 && (
                    <p className="sidebar-section-label">Recent Runs</p>
                )}
                <ul className="history-list">
                    {history.map((entry) => (
                        <li
                            key={entry.id}
                            className={`history-item${activeQuestion === entry.question ? " history-item-active" : ""}`}
                            onClick={() => onSelect(entry.question)}
                            title={entry.question}
                        >
                            <span className="history-icon"><RunIcon /></span>
                            <span className="history-details">
                                <span className="history-question">{entry.question}</span>
                                <span className="history-time">{formatRelativeTime(entry.timestamp)}</span>
                            </span>
                        </li>
                    ))}
                </ul>
            </section>

            <div className="sidebar-footer">
                <a
                    className="sidebar-github"
                    href="https://github.com/axoviq/synthadoc"
                    target="_blank"
                    rel="noreferrer"
                >
                    <GithubIcon />
                    <span>Open Source</span>
                </a>
                <span className="sidebar-wiki-name">{wikiName || "—"}</span>
                <span
                    className={`sidebar-dot ${connected ? "sidebar-dot-ok" : "sidebar-dot-connecting"}`}
                    title={connected ? "Connected" : "Connecting…"}
                />
            </div>
        </aside>
    );
}

function SynthadocLogo() {
    return (
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="28" height="28" rx="7" fill="#7c3aed"/>
            <rect x="6" y="8" width="7" height="1.8" rx="0.9" fill="white"/>
            <rect x="6" y="11.6" width="7" height="1.8" rx="0.9" fill="white"/>
            <rect x="6" y="15.2" width="7" height="1.8" rx="0.9" fill="white"/>
            <rect x="6" y="18.8" width="5" height="1.8" rx="0.9" fill="white"/>
            <rect x="15" y="8" width="7" height="1.8" rx="0.9" fill="rgba(255,255,255,0.45)"/>
            <rect x="15" y="11.6" width="7" height="1.8" rx="0.9" fill="rgba(255,255,255,0.45)"/>
            <rect x="15" y="15.2" width="5" height="1.8" rx="0.9" fill="rgba(255,255,255,0.45)"/>
        </svg>
    );
}

function RunIcon() {
    return (
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1.5" y="1.5" width="11" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.2"/>
            <path d="M4 5.5h6M4 8h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
        </svg>
    );
}

function GithubIcon() {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
        </svg>
    );
}
