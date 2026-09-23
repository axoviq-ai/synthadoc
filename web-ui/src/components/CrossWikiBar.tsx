// Copyright (C) 2026 William Johnason / axoviq.com

interface Props {
    state: "searching" | "done" | "idle";
    wikis?: string[];       // querying
    responded?: string[];   // done
    offline?: string[];     // done
}

export function CrossWikiBar({ state, wikis, responded, offline }: Props) {
    if (state === "idle") return null;
    const offlineMsg = offline && offline.length > 0 ? ` · ⚠ ${offline.join(", ")} offline` : "";
    const text = state === "searching"
        ? `🌐 Searching: ${wikis?.join(" · ") ?? "…"}`
        : `🌐 Searched: ${responded?.join(" · ") ?? "—"}${offlineMsg}`;
    return (
        <div className={`cross-wiki-bar${state === "done" && offlineMsg ? " cross-wiki-bar--warn" : ""}`}>
            {text}
        </div>
    );
}
