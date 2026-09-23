// Copyright (C) 2026 William Johnason / axoviq.com

interface Props {
    enabled: boolean;
    onChange: (enabled: boolean) => void;
}

export function CrossWikiToggle({ enabled, onChange }: Props) {
    return (
        <button
            title={enabled ? "Cross-wiki search ON — click to search this wiki only" : "Search this wiki only — click to search all wikis"}
            aria-pressed={enabled}
            onClick={() => onChange(!enabled)}
            className={`cross-wiki-toggle${enabled ? " cross-wiki-toggle--on" : ""}`}
        >
            🌐
        </button>
    );
}
