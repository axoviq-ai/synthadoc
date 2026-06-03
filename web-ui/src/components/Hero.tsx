// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import heroBg from "../assets/hero-bg.png";

const MODE_LABELS: Record<string, string> = {
    NEW_WIKI: "New Wiki",
    EXPLORER: "Explorer",
    HEALTH_CHECK: "Health Check",
    POWER_USER: "Power User",
};

interface Props {
    mode: string;
}

export function Hero({ mode }: Props) {
    const modeLabel = MODE_LABELS[mode] ?? mode;
    return (
        <div className="hero">
            <div className="hero-bg" style={{ backgroundImage: `url(${heroBg})` }} />
            <div className="hero-content">
                {modeLabel && (
                    <span className="hero-mode-badge">{modeLabel.toUpperCase()}</span>
                )}
                <h2 className="hero-title">Synthadoc</h2>
                <p className="hero-subtitle">
                    An open-source LLM knowledge compilation engine that turns raw
                    documents into structured, local-first wikis.<br />
                    A transparent, human-readable alternative to traditional RAG,
                    which can be self-managed and self-improved.
                </p>
                <div className="hero-features">
                    <div className="hero-feature">
                        <span className="hero-feature-icon"><ShieldIcon /></span>
                        <div className="hero-feature-text">
                            <strong>Local-First</strong>
                            <p>Your data stays local. No third-party dependencies.</p>
                        </div>
                    </div>
                    <div className="hero-feature">
                        <span className="hero-feature-icon"><WikiIcon /></span>
                        <div className="hero-feature-text">
                            <strong>Structured Wikis</strong>
                            <p>Raw docs transformed into clean, interconnected knowledge.</p>
                        </div>
                    </div>
                    <div className="hero-feature">
                        <span className="hero-feature-icon"><CodeIcon /></span>
                        <div className="hero-feature-text">
                            <strong>Open & Transparent</strong>
                            <p>Fully open-source. Inspect, improve, and trust every step.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function ShieldIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
    );
}

function WikiIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
            <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
    );
}

function CodeIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 18 22 12 16 6"/>
            <polyline points="8 6 2 12 8 18"/>
        </svg>
    );
}
