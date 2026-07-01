// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { memo, useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../useQueryStream";
import { JOB, ENRICH, ENRICH_LABEL, type EnrichState } from "../jobStatus";

interface Props { msg: Message; wikiName?: string; maxResults?: number; onChipClick?: (value: string) => void; }

const _IS_URL = /^https?:\/\//i;
const POLL_INTERVAL_MS = 3000;


// Patterns that indicate a permanent skip — force re-index won't help
const _PERM_BLOCK = /auto-blocked|err-skill-003|blocked automated|future urls.*skipped|\b40[34]\b/i;
const isPermBlocked = (reason: string | null) => !!reason && _PERM_BLOCK.test(reason);

function shortUrl(url: string): string {
    try { return new URL(url).hostname.replace(/^www\./, "") + new URL(url).pathname; }
    catch { return url; }
}

type ChildProgress = { done: number; total: number };

function GapCallout({ suggestions, wikiName, maxResults }: { suggestions: string[]; wikiName?: string; maxResults?: number }) {
    const [copied, setCopied] = useState(false);
    const [enrichStates, setEnrichStates] = useState<EnrichState[]>(() => suggestions.map(() => ENRICH.IDLE));
    const [jobIds, setJobIds] = useState<(string | null)[]>(() => suggestions.map(() => null));
    const [jobReasons, setJobReasons] = useState<(string | null)[]>(() => suggestions.map(() => null));
    const [jobResults, setJobResults] = useState<(Record<string, string[]> | null)[]>(() => suggestions.map(() => null));
    const [childProgress, setChildProgress] = useState<(ChildProgress | null)[]>(() => suggestions.map(() => null));
    const [jobIdCopied, setJobIdCopied] = useState<number | null>(null);
    const pollsRef = useRef<Map<number, ReturnType<typeof setInterval>>>(new Map());
    const wikiFlag = wikiName ? ` -w ${wikiName}` : "";
    const commands = suggestions
        .map((s) => _IS_URL.test(s)
            ? `synthadoc ingest "${s}"${wikiFlag}`
            : `synthadoc ingest "search for: ${s}"${wikiFlag}`)
        .join("\n");

    // Clear all polls on unmount
    useEffect(() => () => { pollsRef.current.forEach(id => clearInterval(id)); }, []);

    const handleCopy = () => {
        navigator.clipboard.writeText(commands).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => {});
    };

    const setTerminal = (idx: number, state: EnrichState, reason: string | null) => {
        setEnrichStates(prev => { const next = [...prev]; next[idx] = state; return next; });
        if (reason) setJobReasons(prev => { const next = [...prev]; next[idx] = reason; return next; });
    };

    const _JOB_TERMINAL = new Set<string>([JOB.COMPLETED, JOB.SKIPPED, JOB.FAILED, JOB.DEAD, JOB.CANCELLED]);

    const startChildMonitoring = (childIds: string[], idx: number) => {
        const childSet = new Set(childIds);
        setChildProgress(prev => { const next = [...prev]; next[idx] = { done: 0, total: childIds.length }; return next; });
        const id = setInterval(async () => {
            try {
                const r = await fetch("/jobs", { cache: "no-store" });
                if (!r.ok) return;
                const allJobs: Array<{ id: string; status: string; error?: string | null; result?: Record<string, string[]> }> = await r.json();
                const children = allJobs.filter(j => childSet.has(j.id));
                const done = children.filter(j => _JOB_TERMINAL.has(j.status)).length;
                setChildProgress(prev => { const next = [...prev]; next[idx] = { done, total: childIds.length }; return next; });
                if (done >= childIds.length) {
                    clearInterval(id); pollsRef.current.delete(idx);
                    const allCreated = children.flatMap(j => j.result?.pages_created ?? []);
                    const allUpdated = children.flatMap(j => j.result?.pages_updated ?? []);
                    setJobResults(prev => { const next = [...prev]; next[idx] = { pages_created: allCreated, pages_updated: allUpdated }; return next; });
                    setChildProgress(prev => { const next = [...prev]; next[idx] = null; return next; });
                    const pageCount = allCreated.length + allUpdated.length;
                    const failCount = children.filter(j => j.status === JOB.FAILED || j.status === JOB.DEAD).length;
                    const skipCount = children.filter(j => j.status === JOB.SKIPPED).length;
                    if (pageCount > 0) {
                        // Partial or full success — note any non-indexed children in the reason row
                        const parts: string[] = [];
                        if (failCount > 0) parts.push(`${failCount} failed`);
                        if (skipCount > 0) parts.push(`${skipCount} skipped`);
                        setTerminal(idx, ENRICH.DONE, parts.length > 0 ? parts.join(", ") : null);
                    } else if (failCount > 0) {
                        setTerminal(idx, ENRICH.ERROR, ENRICH_LABEL.REASON_INGEST_ERR);
                    } else {
                        // All skipped — pass concatenated error reasons so isPermBlocked can classify
                        const combinedReason = children.map(j => j.error ?? "").join(" ") || ENRICH_LABEL.REASON_HASH_SKIP;
                        setTerminal(idx, ENRICH.SKIPPED, combinedReason);
                    }
                }
            } catch { /* network hiccup — keep polling */ }
        }, POLL_INTERVAL_MS);
        pollsRef.current.set(idx, id);
    };

    const startPolling = (jobId: string, idx: number) => {
        const id = setInterval(async () => {
            try {
                const r = await fetch(`/jobs/${jobId}`, { cache: "no-store" });
                if (!r.ok) return;
                const job = await r.json();
                if (job.status === JOB.COMPLETED) {
                    clearInterval(id); pollsRef.current.delete(idx);
                    const childIds: string[] = job.result?.child_job_ids ?? [];
                    if (childIds.length > 0) {
                        // Parent spawned child jobs — monitor them before marking Done
                        startChildMonitoring(childIds, idx);
                        return;
                    }
                    setJobResults(prev => { const next = [...prev]; next[idx] = job.result || null; return next; });
                    setTerminal(idx, ENRICH.DONE, null);
                } else if (job.status === JOB.SKIPPED) {
                    clearInterval(id); pollsRef.current.delete(idx);
                    setTerminal(idx, ENRICH.SKIPPED, job.error || ENRICH_LABEL.REASON_HASH_SKIP);
                } else if (job.status === JOB.FAILED || job.status === JOB.DEAD) {
                    clearInterval(id); pollsRef.current.delete(idx);
                    setTerminal(idx, ENRICH.ERROR, job.error || ENRICH_LABEL.REASON_INGEST_ERR);
                } else if (job.status === JOB.CANCELLED) {
                    clearInterval(id); pollsRef.current.delete(idx);
                    setTerminal(idx, ENRICH.ERROR, job.error || ENRICH_LABEL.REASON_CANCELLED);
                }
                // pending / in_progress — keep polling
            } catch { /* network hiccup — keep polling */ }
        }, POLL_INTERVAL_MS);
        pollsRef.current.set(idx, id);
    };

    const handleEnrich = async (s: string, idx: number, force = false) => {
        const source = _IS_URL.test(s) ? s : `search for: ${s}`;
        // Clear any existing poll for this slot (e.g. force re-index after skipped)
        if (pollsRef.current.has(idx)) {
            clearInterval(pollsRef.current.get(idx)!);
            pollsRef.current.delete(idx);
        }
        setEnrichStates(prev => { const next = [...prev]; next[idx] = ENRICH.LOADING; return next; });
        setJobIds(prev => { const next = [...prev]; next[idx] = null; return next; });
        setJobReasons(prev => { const next = [...prev]; next[idx] = null; return next; });
        setJobResults(prev => { const next = [...prev]; next[idx] = null; return next; });
        setChildProgress(prev => { const next = [...prev]; next[idx] = null; return next; });
        try {
            const body: Record<string, unknown> = { source, force };
            if (!_IS_URL.test(s) && maxResults !== undefined) body.max_results = maxResults;
            const resp = await fetch("/jobs/ingest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!resp.ok) {
                setTerminal(idx, ENRICH.ERROR, `HTTP ${resp.status}`);
                return;
            }
            const { job_id } = await resp.json();
            setJobIds(prev => { const next = [...prev]; next[idx] = job_id; return next; });
            startPolling(job_id, idx);
        } catch {
            setTerminal(idx, ENRICH.ERROR, ENRICH_LABEL.REASON_NETWORK);
        }
    };

    return (
        <div className="bubble-gap-callout">
            <p className="gap-title">💡 Knowledge Gap Detected</p>
            <p className="gap-text">
                Your wiki doesn't have enough on this topic yet. Click to ingest:
            </p>
            <ul className="gap-suggestions">
                {suggestions.map((s, i) => {
                    const state = enrichStates[i] ?? ENRICH.IDLE;
                    const isUrl = _IS_URL.test(s);
                    const reason = jobReasons[i];
                    const result = jobResults[i];
                    const prog = childProgress[i];
                    const doneCount = result
                        ? (result.pages_created?.length ?? 0) + (result.pages_updated?.length ?? 0)
                        : 0;
                    const doneLabel = doneCount > 0
                        ? `${ENRICH_LABEL.BTN_DONE} ${doneCount} page${doneCount > 1 ? "s" : ""}`
                        : ENRICH_LABEL.BTN_DONE;
                    const loadingLabel = prog
                        ? `Indexing ${prog.done}/${prog.total}…`
                        : ENRICH_LABEL.BTN_LOADING;
                    const loadingTip = prog ? ENRICH_LABEL.TIP_INDEXING : ENRICH_LABEL.TIP_LOADING;
                    return (
                        <li key={i} className="gap-suggestion-item">
                            <div className="gap-suggestion-row">
                                {isUrl
                                    ? <span className="gap-suggestion-type gap-type-url">URL</span>
                                    : <span className="gap-suggestion-type gap-type-search">search</span>}
                                <code className="gap-suggestion-cmd" title={s}>
                                    {isUrl ? shortUrl(s) : s}
                                </code>
                                <button
                                    className={`gap-enrich-btn gap-enrich-${state}`}
                                    onClick={() => handleEnrich(s, i)}
                                    disabled={state !== ENRICH.IDLE}
                                    title={state === ENRICH.LOADING ? loadingTip : undefined}
                                >
                                    {state === ENRICH.IDLE    ? (isUrl ? ENRICH_LABEL.BTN_IDLE_URL : ENRICH_LABEL.BTN_IDLE_SEARCH) :
                                     state === ENRICH.LOADING ? loadingLabel :
                                     state === ENRICH.DONE    ? doneLabel :
                                     state === ENRICH.SKIPPED ? (isPermBlocked(reason) ? ENRICH_LABEL.BTN_BLOCKED : ENRICH_LABEL.BTN_SKIPPED)
                                                              : ENRICH_LABEL.BTN_ERROR}
                                </button>
                            </div>
                            {jobIds[i] && (
                                <div className="gap-job-id-row">
                                    <span className="gap-job-id-label">Job</span>
                                    <code className="gap-job-id-code">{jobIds[i]}</code>
                                    <button
                                        className={`gap-job-id-copy${jobIdCopied === i ? " copied" : ""}`}
                                        onClick={() => {
                                            navigator.clipboard.writeText(jobIds[i]!).then(() => {
                                                setJobIdCopied(i);
                                                setTimeout(() => setJobIdCopied(null), 2000);
                                            }).catch(() => {});
                                        }}
                                        title="Copy job ID"
                                    >
                                        {jobIdCopied === i ? "✓" : "⎘"}
                                    </button>
                                </div>
                            )}
                            {reason && (
                                <p className="gap-job-reason">{reason}</p>
                            )}
                            {state === ENRICH.SKIPPED && !isPermBlocked(reason) && (
                                <button
                                    className="gap-force-btn"
                                    onClick={() => handleEnrich(s, i, true)}
                                >
                                    ↻ Re-index with --force
                                </button>
                            )}
                        </li>
                    );
                })}
            </ul>
            <details className="gap-cli-details">
                <summary className="gap-section">Run from terminal instead</summary>
                <div className="gap-pre-wrap">
                    <pre className="gap-pre"><code>{commands}</code></pre>
                    <button className="gap-copy-btn" onClick={handleCopy}>
                        {copied ? "Copied!" : "Copy"}
                    </button>
                </div>
            </details>
            <p className="gap-footer">After ingesting, re-run your query to get a richer answer.</p>
        </div>
    );
}

// Fenced code block wrapper with a one-click copy button
function PreBlock({ children }: { children?: React.ReactNode }) {
    const [copied, setCopied] = useState(false);
    const preRef = useRef<HTMLPreElement>(null);
    const copy = () => {
        const text = preRef.current?.textContent ?? "";
        navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => {});
    };
    return (
        <div className="code-block-wrap">
            <pre ref={preRef}>{children}</pre>
            <button className="code-copy-btn" onClick={copy} title="Copy to clipboard">
                {copied ? "✓" : "Copy"}
            </button>
        </div>
    );
}

// Escape CLI-style placeholders like <schedule-id> or <wiki-name> that appear
// outside code spans. ReactMarkdown v10 drops unknown HTML tags silently, making
// these placeholders invisible. We only target hyphenated names (not <br>, <em>, etc).
// Content inside fenced code blocks (```...```) or inline code (`...`) is left
// verbatim — the <code> element renders angle brackets correctly without escaping.
function escapePlaceholders(text: string): string {
    const PLACEHOLDER = /<([a-z][a-z0-9]*(?:-[a-z0-9]+)+)>/g;
    const CODE_RE = /```[\s\S]*?```|`[^`]*`/g;
    const parts: string[] = [];
    let cursor = 0;
    let m: RegExpExecArray | null;
    while ((m = CODE_RE.exec(text)) !== null) {
        parts.push(text.slice(cursor, m.index).replace(PLACEHOLDER, "&lt;$1&gt;"));
        parts.push(m[0]);
        cursor = m.index + m[0].length;
    }
    parts.push(text.slice(cursor).replace(PLACEHOLDER, "&lt;$1&gt;"));
    return parts.join("");
}

function ClarifyBubble({
    content,
    candidates,
    onChipClick,
}: {
    content: string;
    candidates: string[];
    onChipClick?: (value: string) => void;
}) {
    return (
        <div className="clarify-bubble">
            <p className="clarify-header">{content}</p>
            {candidates.length > 0 && (
                <div className="chip-list">
                    {candidates.map((c, i) => (
                        <button key={c} className="chip" onClick={() => onChipClick?.(c)}>
                            {i + 1}. {c}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

function NoticeBubble({ content }: { content: string }) {
    return <div className="notice-bubble">{content}</div>;
}

const CLARIFY_ACTION_VERB: Record<string, string> = {
    lifecycle_activate: "Activate",
    lifecycle_archive:  "Archive",
    lifecycle_restore:  "Restore",
};

export const MessageBubble = memo(function MessageBubble({ msg, wikiName, maxResults, onChipClick }: Props) {
    const isUser = msg.role === "user";

    if (msg.type === "clarify") {
        const verb = CLARIFY_ACTION_VERB[msg.action ?? ""];
        const handleClarifyChip = (slug: string) =>
            onChipClick?.(verb ? `${verb} ${slug}` : slug);
        return <ClarifyBubble content={msg.text} candidates={msg.candidates ?? []} onChipClick={handleClarifyChip} />;
    }
    if (msg.type === "notice") {
        return <NoticeBubble content={msg.text} />;
    }

    return (
        <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
            {isUser
                ? <p className="bubble-text">{msg.text}</p>
                : !msg.text
                    ? (
                        <div className="bubble-thinking" aria-label="Synthadoc is thinking">
                            <span /><span /><span />
                        </div>
                    )
                    : <div className="bubble-md">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: PreBlock }}>
                            {escapePlaceholders(msg.text)}
                        </ReactMarkdown>
                      </div>
            }
            {msg.citations && msg.citations.length > 0 && (
                <p className="bubble-citations">
                    Sources: {msg.citations.map((c) => `[[${c}]]`).join(", ")}
                </p>
            )}
            {msg.gapSuggestions && msg.gapSuggestions.length > 0 && (
                <GapCallout suggestions={msg.gapSuggestions} wikiName={wikiName} maxResults={maxResults} />
            )}
        </div>
    );
});
