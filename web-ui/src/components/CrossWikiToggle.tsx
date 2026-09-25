// Copyright (C) 2026 William Johnason / axoviq.com

interface Props {
    enabled: boolean;
    onChange: (enabled: boolean) => void;
}

export function CrossWikiToggle({ enabled, onChange }: Props) {
    return (
        <button
            title={enabled
                ? "Cross-wiki search is ON — deselect to search this wiki only"
                : "Cross-wiki search is OFF — select to search across all wikis"}
            aria-pressed={enabled}
            onClick={() => onChange(!enabled)}
            className={`cross-wiki-toggle${enabled ? " cross-wiki-toggle--on" : ""}`}
        >
            🌐
        </button>
    );
}
