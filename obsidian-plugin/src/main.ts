// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { App, FileSystemAdapter, MarkdownRenderer, Modal, Notice, Plugin, PluginSettingTab, Setting, TFile } from "obsidian";
import { api, setBase, getBase } from "./api";

const SUPPORTED_EXTENSIONS = new Set([
    "md", "txt", "pdf", "docx", "xlsx", "csv",
    "png", "jpg", "jpeg", "webp", "gif", "tiff",
]);

// Filenames excluded from Pick-files scan: generated wiki output and known system/config files.
const PICK_FILES_EXCLUDED_NAMES = new Set([
    "log.md", "routing.md", "agents.md", "readme.md",
    "dashboard.md", "index.md", "overview.md", "claude.md", "gemini.md",
]);

interface SynthadocSettings {
    serverUrl: string;
    rawSourcesFolder: string;
}

const DEFAULT_SETTINGS: SynthadocSettings = {
    serverUrl: "http://127.0.0.1:7070",
    rawSourcesFolder: "raw_sources",
};

export default class SynthadocPlugin extends Plugin {
    settings: SynthadocSettings = DEFAULT_SETTINGS;
    private _citationScanTimer: ReturnType<typeof setTimeout> | null = null;

    async onload() {
        await this.loadSettings();
        setBase(this.settings.serverUrl);
        // Register export file extensions so Obsidian indexes and shows them in the
        // file explorer without the user needing to enable "Detect all file extensions".
        this.registerExtensions(["json", "txt", "graphml"], "markdown");
        this.addSettingTab(new SynthadocSettingTab(this.app, this));

        this.addCommand({
            id: "synthadoc-query",
            name: "Query: ask the wiki...",
            callback: () => new QueryModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-ingest",
            name: "Ingest...",
            callback: () => new IngestModal(this.app, this.settings.rawSourcesFolder).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs",
            name: "Jobs...",
            callback: () => new JobsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint-report",
            name: "Lint: report",
            callback: () => new LintReportModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint",
            name: "Lint: run...",
            callback: () => new LintRunModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-scaffold",
            name: "Wiki: regenerate scaffold...",
            callback: () => new ScaffoldModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-audit",
            name: "Audit...",
            callback: () => new AuditModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-routing",
            name: "Routing: manage ROUTING.md...",
            callback: () => new RoutingModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-staging",
            name: "Staging: manage staging policy...",
            callback: () => new StagingModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-candidates",
            name: "Candidates: review candidate pages...",
            callback: () => new CandidatesModal(this.app).open(),
        });
        this.addCommand({
            id: "synthadoc-context",
            name: "Context: build context pack...",
            callback: () => new ContextModal(this.app).open(),
        });

        this.addCommand({
            id: "view-page-provenance",
            name: "View Page Provenance",
            callback: () => {
                const activeFile = this.app.workspace.getActiveFile();
                const slug = activeFile ? activeFile.basename : "";
                const wikiRoot = this.app.vault.adapter instanceof FileSystemAdapter
                    ? this.app.vault.adapter.getBasePath() : "";
                new ProvenanceModal(this.app, this.settings.serverUrl, wikiRoot, slug).open();
            },
        });

        this.addCommand({
            id: "lifecycle-modal",
            name: "Manage Page Lifecycle",
            callback: () => {
                const wikiRoot = this.app.vault.adapter instanceof FileSystemAdapter
                    ? this.app.vault.adapter.getBasePath() : "";
                new LifecycleModal(this.app, wikiRoot, this.settings.serverUrl).open();
            },
        });

        this.addCommand({
            id: "synthadoc-export-wiki",
            name: "Export Wiki",
            callback: () => new ExportModal(this.app).open(),
        });

        this.addRibbonIcon("book-open", "Synthadoc status", async () => {
            const [healthRes, statusRes] = await Promise.allSettled([
                api.health(),
                api.status(),
            ]);
            const online = healthRes.status === "fulfilled";
            const engineLabel = online ? "✅ online" : "❌ offline — run 'synthadoc serve'";
            const pages = statusRes.status === "fulfilled"
                ? ` · ${(statusRes.value as any).pages} pages`
                : "";
            new Notice(`Synthadoc: ${engineLabel}${pages}`);
        });

        // Citation chip renderer: ^[file.txt:12-24] → clickable chip.
        //
        // Obsidian converts ^[...] inline footnotes into numbered [N] superscripts and
        // appends section.footnotes to the container AFTER all post-processor el blocks
        // fire. So Path 1 (footnotes → body refs) must run deferred via setTimeout so
        // section.footnotes is in the DOM when we query it.
        //
        // Paths 2 and 3 handle the rare case where Obsidian leaves ^[...] as a raw
        // <sup> or text node instead of converting it to a footnote.
        this.registerMarkdownPostProcessor((el, _ctx) => {
            const wikiRoot: string = this.app.vault.adapter instanceof FileSystemAdapter
                ? this.app.vault.adapter.getBasePath()
                : "";

            const CITE_RE = /\^\[([^\]:]+):(\d+)-(\d+)\]/g;
            const BRACKET_RE = /^\^?\[([^\]:]+):(\d+)-(\d+)\]$/;

            // Path 2: <sup> whose full text is [file:L-L] or ^[file:L-L].
            for (const sup of Array.from(el.querySelectorAll("sup"))) {
                const text = (sup as HTMLElement).textContent?.trim() ?? "";
                const m = BRACKET_RE.exec(text);
                if (m) (sup as HTMLElement).replaceWith(
                    this._makeChip(wikiRoot, m[1], parseInt(m[2], 10), parseInt(m[3], 10))
                );
            }

            // Path 3: raw text nodes containing ^[file:L-L].
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            const textNodes: Text[] = [];
            let node: Node | null;
            while ((node = walker.nextNode())) textNodes.push(node as Text);

            for (const textNode of textNodes) {
                const text = textNode.textContent || "";
                if (!text.includes("^[")) continue;
                CITE_RE.lastIndex = 0;
                const frag = document.createDocumentFragment();
                let last = 0;
                let m: RegExpExecArray | null;
                while ((m = CITE_RE.exec(text)) !== null) {
                    if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
                    frag.appendChild(this._makeChip(wikiRoot, m[1], parseInt(m[2], 10), parseInt(m[3], 10)));
                    last = m.index + m[0].length;
                }
                if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
                if (last > 0) {
                    const parent = textNode.parentNode;
                    if (parent?.nodeName === "SUP" && parent.textContent === text) {
                        parent.replaceWith(frag);
                    } else {
                        parent?.replaceChild(frag, textNode);
                    }
                }
            }

            // Path 1 (deferred): Obsidian converted ^[...] to numbered footnotes.
            // section.footnotes is appended after all el blocks fire, so we defer
            // the whole-document scan 100 ms (debounced) to let the DOM settle.
            if (this._citationScanTimer !== null) clearTimeout(this._citationScanTimer);
            this._citationScanTimer = setTimeout(() => {
                this._citationScanTimer = null;
                this._replaceFootnoteCitations(wikiRoot);
            }, 100);
        });
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }

    private _makeChip(wikiRoot: string, filename: string, lineStart: number, lineEnd: number): HTMLSpanElement {
        const chip = document.createElement("span");
        chip.className = "synthadoc-citation-chip";
        chip.textContent = `${filename}:${lineStart}-${lineEnd}`;
        chip.style.cssText = [
            "display:inline-block",
            "background:#4f46e5",
            "color:#ffffff",
            "border-radius:4px",
            "padding:1px 6px",
            "font-size:10px",
            "font-weight:500",
            "cursor:pointer",
            "margin:0 3px",
            "vertical-align:middle",
            "-webkit-user-select:text",
            "user-select:text",
        ].join(";");
        chip.addEventListener("click", () => {
            new SourceViewerModal(this.app, filename, lineStart, lineEnd, wikiRoot).open();
        });
        return chip;
    }

    // Whole-document scan run after Obsidian finishes rendering section.footnotes.
    // Derives body reference IDs from footnote li ids (fn-N → fnref-N) rather than
    // from the backref anchor's class, which varies across Obsidian versions.
    private _replaceFootnoteCitations(wikiRoot: string): void {
        for (const section of Array.from(document.querySelectorAll("section.footnotes"))) {
            for (const li of Array.from(section.querySelectorAll("li[id]"))) {
                const liEl = li as HTMLElement;
                const raw = liEl.textContent?.trim() ?? "";
                const m = /^([^\]:]+):(\d+)-(\d+)/.exec(raw);
                if (!m) continue;
                const [, filename, ls, le] = m;
                // li.id: "fn-1", "fn-1-abc", "user-content-fn-1" → "fnref-1", "fnref-1-abc", "user-content-fnref-1"
                const refId = liEl.id.replace(/\bfn-/, "fnref-");
                const target = document.getElementById(refId);
                if (target) {
                    // id may be on the <a> inside <sup>; replace the <sup> ancestor
                    (target.closest("sup") ?? target).replaceWith(
                        this._makeChip(wikiRoot, filename, parseInt(ls, 10), parseInt(le, 10))
                    );
                }
                liEl.remove();
            }
            if (!(section as HTMLElement).querySelector("li"))
                (section as HTMLElement).remove();
        }
    }

    async ingestFile(file: TFile) {
        try {
            const absPath = (this.app.vault.adapter as any).getFullPath(file.path);
            const r = await api.ingest(absPath) as any;
            new Notice(`Synthadoc: ingest queued (job ${r.job_id})`);
        } catch { new Notice("Synthadoc: ingest failed — is the server running?"); }
    }

}

class IngestModal extends Modal {
    private _rawSourcesFolder: string;
    private _pollTimer: number | null = null;
    private _wsPollTimer: number | null = null;

    constructor(app: App, rawSourcesFolder?: string) {
        super(app);
        this._rawSourcesFolder = (rawSourcesFolder ?? "raw_sources").replace(/\/$/, "") || "raw_sources";
    }

    onOpen() {
        this.modalEl.style.width = "clamp(480px, 60vw, 820px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Ingest" });
        makeDraggable(this.modalEl, titleEl);

        // Tab bar
        const tabBar = contentEl.createEl("div");
        tabBar.style.cssText = "display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid var(--background-modifier-border)";

        type TabName = "Web search" | "URL" | "All raw_sources" | "Pick files";
        const tabNames: TabName[] = ["Web search", "URL", "All raw_sources", "Pick files"];
        const panels: Record<TabName, HTMLElement> = {} as any;
        const tabBtns: Record<TabName, HTMLElement> = {} as any;

        tabNames.forEach(name => {
            const btn = tabBar.createEl("div", { text: name });
            btn.style.cssText = "padding:6px 14px;cursor:pointer;font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px;color:var(--text-muted)";
            tabBtns[name] = btn;
            const panel = contentEl.createEl("div");
            panel.style.display = "none";
            panels[name] = panel;
        });

        const switchTab = (name: TabName) => {
            tabNames.forEach(t => {
                panels[t].style.display = "none";
                tabBtns[t].style.borderBottomColor = "transparent";
                tabBtns[t].style.color = "var(--text-muted)";
            });
            panels[name].style.display = "";
            tabBtns[name].style.borderBottomColor = "var(--interactive-accent)";
            tabBtns[name].style.color = "var(--text-normal)";
        };

        tabNames.forEach(name => { tabBtns[name].onclick = () => switchTab(name); });

        this._buildWebSearchTab(panels["Web search"]);
        this._buildUrlTab(panels["URL"]);
        this._buildAllSourcesTab(panels["All raw_sources"]);
        this._buildPickFilesTab(panels["Pick files"]);
        switchTab("Web search");
    }

    private _makeJobsLink(container: HTMLElement): void {
        const link = container.createEl("a", { text: "View jobs →" });
        link.style.cssText = "font-size:12px;cursor:pointer;color:var(--link-color);margin-right:auto";
        link.onclick = () => {
            this.close();
            setTimeout(() => new JobsModal(
                this.app,
                new Set(["pending", "in_progress", "failed", "skipped"]),
            ).open(), 150);
        };
    }

    private _forceRow(panel: HTMLElement): () => boolean {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:6px;margin-bottom:10px;font-size:12px;color:var(--text-muted)";
        const cb = row.createEl("input", { type: "checkbox" }) as HTMLInputElement;
        const lbl = row.createEl("label", { text: "Force re-ingest (skip duplicate check)" });
        lbl.style.cssText = "cursor:pointer";
        lbl.onclick = () => { cb.checked = !cb.checked; };
        return () => !!cb.checked;
    }

    private _buildWebSearchTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Type a topic — Synthadoc will search the web and compile results into your wiki.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const textarea = panel.createEl("textarea", { placeholder: "e.g. Bank of Canada rate outlook 2025\nOntario housing market trends" }) as HTMLTextAreaElement;
        textarea.style.cssText = "width:100%;min-height:72px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const settingsRow = panel.createEl("div");
        settingsRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:12px";
        settingsRow.createEl("label", { text: "Max results:" });
        const maxResultsInput = settingsRow.createEl("input", { type: "number" }) as HTMLInputElement;
        maxResultsInput.value = "20";
        maxResultsInput.min = "1";
        maxResultsInput.max = "50";
        maxResultsInput.step = "1";
        maxResultsInput.style.cssText = "width:60px;padding:4px 6px";
        settingsRow.createEl("span", { text: "URLs" }).style.marginRight = "16px";
        settingsRow.createEl("label", { text: "Poll interval:" });
        const intervalInput = settingsRow.createEl("input", { type: "number" }) as HTMLInputElement;
        intervalInput.value = "2000";
        intervalInput.min = "500";
        intervalInput.max = "10000";
        intervalInput.step = "500";
        intervalInput.style.cssText = "width:70px;padding:4px 6px";
        settingsRow.createEl("span", { text: "ms" });

        const isForced = this._forceRow(panel);

        const btnRow = panel.createEl("div");
        btnRow.style.cssText = "display:flex;align-items:center;gap:8px;justify-content:flex-end;margin-bottom:10px";
        this._makeJobsLink(btnRow);
        const btn = btnRow.createEl("button", { text: "Search" }) as HTMLButtonElement;

        const statusEl = panel.createEl("p");
        statusEl.style.cssText = "font-size:12px;min-height:20px;margin-bottom:4px;-webkit-user-select:text;user-select:text";
        const pagesEl = panel.createEl("div");
        pagesEl.style.cssText = "-webkit-user-select:text;user-select:text";
        const errorsEl = panel.createEl("div");
        errorsEl.style.cssText = "-webkit-user-select:text;user-select:text";

        const stopPolling = () => {
            if (this._wsPollTimer !== null) { window.clearTimeout(this._wsPollTimer); this._wsPollTimer = null; }
        };

        const startPolling = (jobId: string, pollInterval: number) => {
            const pages = new Set<string>();
            const errors: string[] = [];
            let childJobIds: string[] = [];
            const settledChildren = new Set<string>();
            const TERMINAL = ["completed", "failed", "dead", "skipped", "cancelled"];

            const poll = async () => {
                try {
                    const job = await api.job(jobId) as any;
                    const phase = job.progress?.phase;
                    const isDone = ["completed", "failed", "dead", "skipped"].includes(job.status);
                    if (job.result?.child_job_ids?.length && childJobIds.length === 0) childJobIds = job.result.child_job_ids;
                    if (!isDone) {
                        if (phase === "searching") statusEl.setText("Searching the web…");
                        else if (phase === "found_urls") {
                            const total = job.progress?.total ?? 0;
                            statusEl.setText(`Found ${total} URL${total !== 1 ? "s" : ""} — ingesting…`);
                        } else if (job.status === "pending") {
                            statusEl.setText("⏳ Queued — waiting for worker (other jobs are running)…");
                        } else if (job.status === "in_progress") {
                            statusEl.setText("⏳ Starting web search…");
                        }
                    }
                    if (childJobIds.length > 0) {
                        const allJobs = await api.jobs() as any[];
                        for (const cj of allJobs) {
                            if (!childJobIds.includes(cj.id) || !TERMINAL.includes(cj.status) || settledChildren.has(cj.id)) continue;
                            settledChildren.add(cj.id);
                            if (cj.status === "completed") {
                                for (const s of (cj.result?.pages_created ?? [])) pages.add(s);
                                for (const s of (cj.result?.pages_updated ?? [])) pages.add(s);
                            } else if (cj.error) {
                                const msg = `${cj.payload?.source ?? cj.id}: ${cj.error}`;
                                if (!errors.includes(msg)) errors.push(msg);
                            }
                        }
                        const remaining = childJobIds.length - settledChildren.size;
                        if (remaining > 0) statusEl.setText(isDone ? `Wrapping up — ${remaining} ingest${remaining !== 1 ? "s" : ""} still running…` : `Ingesting ${childJobIds.length} URL${childJobIds.length !== 1 ? "s" : ""}… (${settledChildren.size} done)`);
                    }
                    if (pages.size > 0) {
                        pagesEl.empty();
                        pagesEl.createEl("p", { text: `Pages (${pages.size}):` }).style.cssText = "font-size:12px;font-weight:bold;margin-bottom:2px";
                        const ul = pagesEl.createEl("ul");
                        ul.style.cssText = "font-size:12px;margin:0;padding-left:18px";
                        for (const s of pages) ul.createEl("li", { text: s });
                    }
                    if (errors.length > 0) {
                        errorsEl.empty();
                        errorsEl.createEl("p", { text: `Errors (${errors.length}):` }).style.cssText = "font-size:12px;font-weight:bold;margin-bottom:2px;color:var(--text-error)";
                        const ul = errorsEl.createEl("ul");
                        ul.style.cssText = "font-size:12px;margin:0;padding-left:18px;color:var(--text-error)";
                        for (const e of errors) ul.createEl("li", { text: e });
                    }
                    const allChildrenSettled = childJobIds.length > 0 && settledChildren.size >= childJobIds.length;
                    if (isDone && (childJobIds.length === 0 || allChildrenSettled)) {
                        stopPolling();
                        btn.disabled = false;
                        textarea.disabled = false;
                        if (job.status === "completed" || allChildrenSettled) {
                            statusEl.style.cssText += ";font-weight:bold;color:var(--text-success)";
                            statusEl.setText(`Done — ${pages.size} page(s) written.`);
                            new Notice(`Synthadoc: web search complete — ${pages.size} page(s)`);
                        } else {
                            statusEl.setText(`Search ${job.status}${job.error ? `: ${job.error}` : ""}`);
                        }
                        return;
                    }
                } catch { /* server unreachable — keep polling */ }
                this._wsPollTimer = window.setTimeout(poll, pollInterval);
            };
            this._wsPollTimer = window.setTimeout(poll, pollInterval);
        };

        const submit = async () => {
            const topic = textarea.value.trim();
            if (!topic) return;
            btn.disabled = true;
            textarea.disabled = true;
            const pollInterval = Math.min(10000, Math.max(500, parseInt(intervalInput.value) || 2000));
            const maxResults = Math.min(50, Math.max(1, parseInt(maxResultsInput.value) || 20));
            statusEl.setText("Queuing web search…");
            pagesEl.empty();
            errorsEl.empty();
            try {
                const r = await api.ingest(`search for: ${topic}`, maxResults, isForced()) as any;
                new Notice(`Synthadoc: web search queued (job ${r.job_id})`);
                startPolling(r.job_id, pollInterval);
            } catch {
                statusEl.setText("Error: is synthadoc serve running?");
                btn.disabled = false;
                textarea.disabled = false;
            }
        };

        btn.onclick = submit;
        textarea.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
    }

    private _buildUrlTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Paste a URL — Synthadoc will fetch, parse, and convert it into a wiki article. Supports web pages, PDFs, and YouTube videos.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const row = panel.createEl("div");
        row.style.cssText = "display:flex;gap:8px;margin-bottom:10px";
        const input = row.createEl("input", { type: "url", placeholder: "https://..." }) as HTMLInputElement;
        input.style.cssText = "flex:1;padding:4px 8px";
        const btn = row.createEl("button", { text: "Ingest" }) as HTMLButtonElement;

        const isForced = this._forceRow(panel);

        const linkRow = panel.createEl("div");
        linkRow.style.cssText = "display:flex;margin-bottom:6px";
        this._makeJobsLink(linkRow);

        const out = panel.createEl("div");
        out.style.cssText = "margin-top:4px;-webkit-user-select:text;user-select:text";

        const setStatus = (text: string, color?: string) => {
            out.empty();
            const p = out.createEl("p", { text });
            if (color) p.style.cssText = `color:${color}`;
        };

        const startPolling = (jobId: string) => {
            this._pollTimer = window.setInterval(async () => {
                try {
                    const job = await api.job(jobId) as any;
                    const status: string = job.status;
                    if (status === "pending") { setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`); return; }
                    if (status === "in_progress") { setStatus(`⏳ Ingesting… (job ${jobId.slice(0, 8)})`); return; }
                    window.clearInterval(this._pollTimer!);
                    this._pollTimer = null;
                    btn.disabled = false;
                    input.disabled = false;
                    if (status === "completed") {
                        const parts = jobResultSummary(job.result ?? {});
                        out.empty();
                        out.createEl("p", { text: "✅ Done." }).style.cssText = "font-weight:bold;margin-bottom:4px";
                        if (parts.length) out.createEl("p", { text: parts.join(" · ") }).style.cssText = "font-size:12px;color:var(--text-muted)";
                        new Notice(`Synthadoc: ingest done (job ${jobId.slice(0, 8)})`);
                    } else if (status === "skipped") {
                        setStatus("⏭️ Skipped — already ingested.", "var(--text-muted)");
                    } else {
                        setStatus(`❌ ${status}${job.error ? `: ${job.error}` : ""}`, "var(--text-error)");
                    }
                } catch { /* server unreachable — keep polling silently */ }
            }, 2000);
        };

        const submit = async () => {
            const url = input.value.trim();
            if (!url) return;
            btn.disabled = true;
            input.disabled = true;
            setStatus("⏳ Queuing…");
            try {
                const r = await api.ingest(url, undefined, isForced()) as any;
                const jobId: string = r.job_id;
                setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`);
                startPolling(jobId);
            } catch {
                setStatus("❌ Error: is synthadoc serve running?", "var(--text-error)");
                btn.disabled = false;
                input.disabled = false;
            }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    }

    private _buildAllSourcesTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Ingest every supported file in your configured raw sources folder in one click. Files already ingested are skipped unless Force re-ingest is checked.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const folderRow = panel.createEl("div");
        folderRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        folderRow.createEl("label", { text: "Folder" }).style.cssText = "white-space:nowrap;font-size:13px;color:var(--text-muted)";
        const folderDisplay = folderRow.createEl("span");
        folderDisplay.style.cssText = "flex:1;padding:4px 8px;font-size:13px;color:var(--text-muted);background:var(--background-secondary);border-radius:4px;-webkit-user-select:text;user-select:text";
        folderDisplay.textContent = this._rawSourcesFolder;

        const statusEl = panel.createEl("div");
        statusEl.style.cssText = "min-height:40px;margin-bottom:12px;font-size:13px;-webkit-user-select:text;user-select:text";

        const isForced = this._forceRow(panel);

        const btnRow = panel.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;align-items:center";
        this._makeJobsLink(btnRow);
        const ingestBtn = btnRow.createEl("button", { text: "Ingest all" }) as HTMLButtonElement;
        ingestBtn.style.cssText = "font-weight:bold";

        const setStatus = (html: string) => { statusEl.innerHTML = html; };

        ingestBtn.onclick = async () => {
            const folder = this._rawSourcesFolder;

            const files = (this.app.vault.getFiles() as any[]).filter((f: any) => {
                if (!f.path.startsWith(folder + "/")) return false;
                return SUPPORTED_EXTENSIONS.has((f.extension ?? "").toLowerCase());
            });

            if (!files.length) {
                setStatus(`<span style="color:var(--text-muted)">No supported files found in <em>${folder}</em>.</span>`);
                return;
            }

            ingestBtn.disabled = true;
            setStatus(`⏳ Queuing ${files.length} file(s)…`);

            const force = isForced();
            const jobIds: string[] = [];
            let queueFailed = 0;
            for (const file of files) {
                try {
                    const absPath = (this.app.vault.adapter as any).getFullPath(file.path);
                    const r = await api.ingest(absPath, undefined, force) as any;
                    if (r?.job_id) jobIds.push(r.job_id);
                } catch { queueFailed++; }
            }

            if (!jobIds.length) {
                setStatus(`<span style="color:var(--text-error)">❌ All ${files.length} file(s) failed to queue — is synthadoc serve running?</span>`);
                ingestBtn.disabled = false;
                return;
            }

            setStatus(`⏳ Queued ${jobIds.length} job(s)${queueFailed ? ` (${queueFailed} failed to queue)` : ""}. Monitoring progress…`);

            const pending = new Set(jobIds);
            let done = 0;

            this._pollTimer = window.setInterval(async () => {
                try {
                    const allJobs = await api.jobs() as any[];
                    for (const jobId of [...pending]) {
                        const job = allJobs.find((j: any) => j.id === jobId);
                        if (!job) { pending.delete(jobId); done++; continue; }
                        if (["completed", "failed", "dead", "skipped"].includes(job.status)) {
                            pending.delete(jobId);
                            done++;
                        }
                    }
                    setStatus(`⏳ ${jobIds.length - done} running, ${done} of ${jobIds.length} settled…`);

                    if (pending.size === 0) {
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        setStatus(`✅ All ${jobIds.length} job(s) complete.${queueFailed ? ` (${queueFailed} file(s) failed to queue.)` : ""}`);
                        ingestBtn.disabled = false;
                    }
                } catch { /* server unreachable — keep polling */ }
            }, 2000);
        };
    }

    private _buildPickFilesTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Browse to any folder, scan for supported files, then select which ones to ingest. Great for one-off ingestion from a custom location.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const folderRow = panel.createEl("div");
        folderRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px";
        folderRow.createEl("label", { text: "Folder" }).style.cssText = "white-space:nowrap;font-size:13px";
        let selectedFolder = "";   // vault-relative (or "" for vault root)
        let selectedAbsPath = "";  // full OS path — shown in display and used as guard
        const folderDisplay = folderRow.createEl("input") as HTMLInputElement;
        folderDisplay.type = "text";
        folderDisplay.readOnly = true;
        folderDisplay.placeholder = "Click Browse… to select a folder";
        folderDisplay.style.cssText = "flex:1;min-width:0;padding:4px 8px;font-size:13px;color:var(--text-muted);background:var(--background-secondary);border:1px solid transparent;border-radius:4px;cursor:default;outline:none";

        const browseBtn = folderRow.createEl("button", { text: "Browse…" }) as HTMLButtonElement;
        browseBtn.onclick = async () => {
            try {
                const remote = (window as any).require?.("@electron/remote")
                    ?? (window as any).require?.("electron")?.remote;
                if (!remote?.dialog) { new Notice("Folder picker unavailable in this environment"); return; }
                const result = await remote.dialog.showOpenDialog({ properties: ["openDirectory"], title: "Select source folder" });
                if (!result.canceled && result.filePaths?.[0]) {
                    const absPath: string = result.filePaths[0];
                    const basePath: string = (this.app.vault.adapter as any).getBasePath?.() ?? "";
                    const rel = (basePath && absPath.toLowerCase().startsWith(basePath.toLowerCase()))
                        ? absPath.slice(basePath.length).replace(/^[/\\]+/, "").replace(/\\/g, "/")
                        : absPath.replace(/\\/g, "/");
                    selectedAbsPath = absPath;
                    selectedFolder = rel;          // may be "" when vault root is selected
                    folderDisplay.value = absPath; // always show the full OS path
                    folderDisplay.style.color = "var(--text-normal)";
                    scanBtn.disabled = false;
                }
            } catch { new Notice("Could not open folder picker"); }
        };

        const scanBtn = folderRow.createEl("button", { text: "Scan" }) as HTMLButtonElement;
        scanBtn.disabled = true;

        const selectRow = panel.createEl("div");
        selectRow.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:4px;font-size:12px";
        const selAllBtn = selectRow.createEl("button", { text: "Select all" }) as HTMLButtonElement;
        const deselAllBtn = selectRow.createEl("button", { text: "Deselect all" }) as HTMLButtonElement;
        const countLabel = selectRow.createEl("span");
        countLabel.style.cssText = "font-size:12px;color:var(--text-muted);margin-left:auto";

        const listEl = panel.createEl("div");
        listEl.style.cssText = "overflow-y:auto;max-height:180px;border:1px solid var(--background-modifier-border);border-radius:4px;padding:4px;margin-bottom:8px;font-size:12px";
        listEl.createEl("span", { text: "Click Browse… to select a folder, then click Scan." }).style.cssText = "color:var(--text-muted);padding:4px;display:block";

        const statusEl = panel.createEl("div");
        statusEl.style.cssText = "min-height:28px;margin-bottom:8px;font-size:13px;-webkit-user-select:text;user-select:text";

        const isForced = this._forceRow(panel);

        const btnRow = panel.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;align-items:center";
        this._makeJobsLink(btnRow);
        const ingestBtn = btnRow.createEl("button", { text: "Ingest selected" }) as HTMLButtonElement;
        ingestBtn.style.cssText = "font-weight:bold";
        ingestBtn.disabled = true;

        let scannedFiles: any[] = [];
        let checkboxRefs: HTMLInputElement[] = [];

        const updateCount = () => {
            countLabel.textContent = checkboxRefs.length ? `${checkboxRefs.filter(c => c.checked).length} / ${checkboxRefs.length} selected` : "";
            ingestBtn.disabled = checkboxRefs.filter(c => c.checked).length === 0;
        };

        const renderFiles = (files: any[]) => {
            scannedFiles = files;
            checkboxRefs = [];
            listEl.empty();
            if (!files.length) {
                listEl.createEl("span", { text: "No supported files found." }).style.cssText = "color:var(--text-muted);padding:4px;display:block";
                updateCount();
                return;
            }
            files.forEach(f => {
                const row = listEl.createEl("div");
                row.style.cssText = "display:flex;align-items:center;gap:6px;padding:2px 4px;border-radius:3px";
                const cb = row.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                checkboxRefs.push(cb);
                cb.checked = true;
                cb.addEventListener("change", updateCount);
                const lbl = row.createEl("label");
                lbl.style.cssText = "cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
                lbl.createEl("span", { text: f.name }).style.fontWeight = "500";
                lbl.createEl("span", { text: "  " + f.path }).style.cssText = "color:var(--text-muted);font-size:11px";
                lbl.onclick = () => { cb.checked = !cb.checked; updateCount(); };
            });
            updateCount();
        };

        const scan = () => {
            if (!selectedAbsPath) return;  // Browse has not been used yet
            const folder = selectedFolder.trim().replace(/\/$/, "");
            // folder is "" when the vault root itself was selected — matches all vault files
            let wikiExcluded = 0;
            let systemExcluded = 0;
            const files = (this.app.vault.getFiles() as any[]).filter((f: any) => {
                if (folder && !f.path.startsWith(folder + "/")) return false;
                if (!SUPPORTED_EXTENSIONS.has((f.extension ?? "").toLowerCase())) return false;
                // Exclude files inside any wiki/ subfolder (those are generated wiki pages)
                const relative = folder ? f.path.slice(folder.length + 1) : f.path;
                if (relative.startsWith("wiki/") || relative.includes("/wiki/")) {
                    wikiExcluded++;
                    return false;
                }
                // Exclude known system / config filenames
                if (PICK_FILES_EXCLUDED_NAMES.has((f.name ?? "").toLowerCase())) {
                    systemExcluded++;
                    return false;
                }
                return true;
            });
            renderFiles(files);
            const parts: string[] = [];
            if (wikiExcluded > 0) parts.push(`${wikiExcluded} wiki page${wikiExcluded !== 1 ? "s" : ""}`);
            if (systemExcluded > 0) parts.push(`${systemExcluded} system file${systemExcluded !== 1 ? "s" : ""}`);
            if (parts.length > 0) {
                statusEl.innerHTML = `<span style="color:var(--text-muted);font-size:12px">ℹ Excluded ${parts.join(" and ")} — not source files</span>`;
            } else {
                statusEl.innerHTML = "";
            }
        };

        scanBtn.onclick = scan;
        selAllBtn.onclick = () => { checkboxRefs.forEach(c => { c.checked = true; }); updateCount(); };
        deselAllBtn.onclick = () => { checkboxRefs.forEach(c => { c.checked = false; }); updateCount(); };

        const setStatus = (html: string) => { statusEl.innerHTML = html; };

        ingestBtn.onclick = async () => {
            const selectedFiles = scannedFiles.filter((_, i) => checkboxRefs[i]?.checked);
            if (!selectedFiles.length) return;

            ingestBtn.disabled = true;
            scanBtn.disabled = true;
            browseBtn.disabled = true;
            setStatus(`⏳ Queuing ${selectedFiles.length} file(s)…`);

            const force = isForced();
            const jobIds: string[] = [];
            let queueFailed = 0;
            for (const file of selectedFiles) {
                try {
                    const absPath = (this.app.vault.adapter as any).getFullPath(file.path);
                    const r = await api.ingest(absPath, undefined, force) as any;
                    if (r?.job_id) jobIds.push(r.job_id);
                } catch { queueFailed++; }
            }

            if (!jobIds.length) {
                setStatus(`<span style="color:var(--text-error)">❌ All ${selectedFiles.length} file(s) failed to queue — is synthadoc serve running?</span>`);
                ingestBtn.disabled = false;
                scanBtn.disabled = false;
                browseBtn.disabled = false;
                updateCount();
                return;
            }

            setStatus(`⏳ Queued ${jobIds.length} job(s)${queueFailed ? ` (${queueFailed} failed to queue)` : ""}. Monitoring…`);

            const pending = new Set(jobIds);
            let done = 0;

            this._pollTimer = window.setInterval(async () => {
                try {
                    const allJobs = await api.jobs() as any[];
                    for (const jobId of [...pending]) {
                        const job = allJobs.find((j: any) => j.id === jobId);
                        if (!job) { pending.delete(jobId); done++; continue; }
                        if (["completed", "failed", "dead", "skipped"].includes(job.status)) {
                            pending.delete(jobId);
                            done++;
                        }
                    }
                    setStatus(`⏳ ${jobIds.length - done} running, ${done} of ${jobIds.length} settled…`);

                    if (pending.size === 0) {
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        setStatus(`✅ All ${jobIds.length} job(s) complete.${queueFailed ? ` (${queueFailed} file(s) failed to queue.)` : ""}`);
                        ingestBtn.disabled = false;
                        scanBtn.disabled = false;
                        browseBtn.disabled = false;
                        updateCount();
                    }
                } catch { /* server unreachable — keep polling */ }
            }, 2000);
        };
    }

    onClose() {
        if (this._pollTimer !== null) { window.clearInterval(this._pollTimer); this._pollTimer = null; }
        if (this._wsPollTimer !== null) { window.clearTimeout(this._wsPollTimer); this._wsPollTimer = null; }
        this.contentEl.empty();
    }
}

class SynthadocSettingTab extends PluginSettingTab {
    plugin: SynthadocPlugin;

    constructor(app: App, plugin: SynthadocPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();
        containerEl.createEl("h2", { text: "Synthadoc settings" });

        new Setting(containerEl)
            .setName("Server URL")
            .setDesc("URL of the synthadoc HTTP server for this vault (e.g. http://127.0.0.1:7070)")
            .addText(text => text
                .setPlaceholder("http://127.0.0.1:7070")
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    setBase(value);
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName("Raw sources folder")
            .setDesc("Vault-relative folder scanned by 'Ingest all sources' (default: raw_sources)")
            .addText(text => text
                .setPlaceholder("raw_sources")
                .setValue(this.plugin.settings.rawSourcesFolder)
                .onChange(async (value) => {
                    this.plugin.settings.rawSourcesFolder = value;
                    await this.plugin.saveSettings();
                }));
    }
}

const STATUS_EMOJI: Record<string, string> = {
    pending:     "🕐",
    in_progress: "⏳",
    completed:   "✅",
    failed:      "❌",
    skipped:     "⏭️",
    dead:        "💀",
    cancelled:   "🚫",
};

const STATUS_FILTER_OPTIONS = ["pending", "in_progress", "completed", "failed", "skipped", "dead", "cancelled"] as const;

function jobResultSummary(r: Record<string, any>): string[] {
    const parts: string[] = [];
    if (r.pages_created?.length) parts.push(`created: ${r.pages_created.join(", ")}`);
    if (r.pages_updated?.length) parts.push(`updated: ${r.pages_updated.join(", ")}`);
    if (r.pages_flagged?.length) parts.push(`flagged: ${r.pages_flagged.join(", ")}`);
    if (r.skip_reason) parts.push(`skipped: ${r.skip_reason}`);
    return parts;
}

function makeDraggable(modalEl: HTMLElement, handle: HTMLElement): void {
    if (typeof document === "undefined" || typeof handle.addEventListener !== "function") return;
    modalEl.style.position = "fixed";
    handle.style.cursor = "grab";
    let dragging = false;
    let startX = 0, startY = 0, origLeft = 0, origTop = 0;

    const startDrag = (e: MouseEvent) => {
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = modalEl.getBoundingClientRect();
        origLeft = rect.left;
        origTop = rect.top;
        modalEl.style.transform = "none";
        modalEl.style.left = origLeft + "px";
        modalEl.style.top = origTop + "px";
        modalEl.style.margin = "0";
        handle.style.cursor = "grabbing";
        e.preventDefault();
    };

    // Drag from the title bar
    handle.addEventListener("mousedown", startDrag);

    // Also drag from the modal frame/padding — but not from inside the content area
    modalEl.addEventListener("mousedown", (e: MouseEvent) => {
        if (handle.contains(e.target as Node)) return; // already handled above
        if (handle.parentElement && handle.parentElement.contains(e.target as Node)) return; // inside content
        startDrag(e);
    });

    document.addEventListener("mousemove", (e: MouseEvent) => {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        modalEl.style.left = (origLeft + dx) + "px";
        modalEl.style.top  = (origTop  + dy) + "px";
    });

    document.addEventListener("mouseup", () => {
        if (dragging) {
            dragging = false;
            handle.style.cursor = "grab";
        }
    });
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "skipped", "dead", "cancelled"]);
const JOBS_PAGE_SIZE = 25;

class JobsModal extends Modal {
    private _selected: Set<string> = new Set(["pending", "in_progress"]);

    constructor(app: App, initialFilters?: Set<string>) {
        super(app);
        if (initialFilters) this._selected = new Set(initialFilters);
    }
    private _intervalSecs = 10;
    private _countdown = 10;
    private _countdownTimer: number | null = null;
    private _tableEl: HTMLElement | null = null;
    private _countdownEl: HTMLElement | null = null;
    private _retryBtn: HTMLButtonElement | null = null;
    private _deleteBtn: HTMLButtonElement | null = null;
    private _checkedIds: Set<string> = new Set();
    private _page = 0;
    private _filteredJobs: any[] = [];
    private _prevBtn: HTMLButtonElement | null = null;
    private _nextBtn: HTMLButtonElement | null = null;
    private _pageLabel: HTMLElement | null = null;
    private _pageRow: HTMLElement | null = null;
    private _sortBy: "created_at" | "status" | "operation" = "created_at";
    private _sortOrder: "asc" | "desc" = "desc";

    onOpen() {
        this.modalEl.style.width = "clamp(760px, 80vw, 1100px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Jobs" });
        makeDraggable(this.modalEl, titleEl);

        // Draft/stale badge — fetch lifecycle status and show badge if any pages need attention
        (async () => {
            try {
                const lcStatus = await api.lifecycleStatus() as any;
                const counts = lcStatus.counts || lcStatus;
                if ((counts.draft || 0) + (counts.stale || 0) > 0) {
                    const badge = contentEl.createDiv();
                    badge.style.cssText = "display:flex;gap:12px;font-size:12px;margin-top:4px";
                    if (counts.draft) {
                        const d = badge.createSpan({ text: `${counts.draft} draft` });
                        d.style.color = "var(--color-orange)";
                        d.style.cursor = "pointer";
                        d.addEventListener("click", () => {
                            this.close();
                            const wr = this.app.vault.adapter instanceof FileSystemAdapter
                                ? this.app.vault.adapter.getBasePath() : "";
                            new LifecycleModal(this.app, wr, getBase(), LifecycleState.DRAFT).open();
                        });
                    }
                    if (counts.stale) {
                        const s = badge.createSpan({ text: `${counts.stale} stale` });
                        s.style.color = "var(--color-yellow)";
                        s.style.cursor = "pointer";
                        s.addEventListener("click", () => {
                            this.close();
                            const wr = this.app.vault.adapter instanceof FileSystemAdapter
                                ? this.app.vault.adapter.getBasePath() : "";
                            new LifecycleModal(this.app, wr, getBase(), LifecycleState.STALE).open();
                        });
                    }
                }
            } catch { /* server may not be running */ }
        })();

        // Status checkboxes
        const filterRow = contentEl.createEl("div");
        filterRow.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px";
        const filterLabel = filterRow.createEl("span", { text: "Show:" });
        filterLabel.style.cssText = "font-size:12px;font-weight:600;margin-right:2px";

        for (const status of STATUS_FILTER_OPTIONS) {
            const label = filterRow.createEl("label");
            label.style.cssText = "display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer;user-select:none";
            const cb = label.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            cb.checked = this._selected.has(status);
            label.appendText(status.replace("_", " "));
            cb.onchange = () => {
                if (cb.checked) this._selected.add(status);
                else this._selected.delete(status);
                this._page = 0;
                this._resetAndLoad();
            };
        }

        // Quick-launch links
        const quickRow = contentEl.createEl("div");
        quickRow.style.cssText = "display:flex;align-items:center;gap:12px;margin-bottom:8px;font-size:12px";
        quickRow.createEl("span", { text: "Launch:" }).style.cssText = "color:var(--text-muted);font-weight:600";
        const _makeQuickLink = (label: string, open: () => void) => {
            const a = quickRow.createEl("a", { text: label });
            a.style.cssText = "cursor:pointer;color:var(--link-color)";
            a.onclick = () => { this.close(); setTimeout(open, 150); };
        };
        _makeQuickLink("Ingest",      () => new IngestModal(this.app).open());
        _makeQuickLink("Lint",        () => new LintRunModal(this.app).open());
        _makeQuickLink("Lint report", () => new LintReportModal(this.app).open());

        // Interval + countdown row
        const intervalRow = contentEl.createEl("div");
        intervalRow.style.cssText = "display:flex;align-items:center;gap:6px;margin-bottom:10px;font-size:12px;color:var(--text-muted)";
        intervalRow.createEl("span", { text: "Auto-refresh every" });
        const intervalInput = intervalRow.createEl("input", { type: "number" }) as HTMLInputElement;
        intervalInput.value = String(this._intervalSecs);
        intervalInput.min = "5";
        intervalInput.max = "30";
        intervalInput.style.cssText = "width:46px;padding:2px 5px;font-size:12px";
        intervalRow.createEl("span", { text: "s  ·" });
        this._countdownEl = intervalRow.createEl("span");

        intervalInput.onchange = () => {
            const v = Math.min(30, Math.max(5, parseInt(intervalInput.value) || 10));
            intervalInput.value = String(v);
            this._intervalSecs = v;
            this._resetAndLoad();
        };

        // Action buttons — right-aligned on the interval row
        this._retryBtn = intervalRow.createEl("button", { text: "Retry selected" }) as HTMLButtonElement;
        this._retryBtn.disabled = true;
        this._retryBtn.style.cssText = "font-size:12px;margin-left:auto";
        this._retryBtn.onclick = () => this._retrySelected();
        this._deleteBtn = intervalRow.createEl("button", { text: "Delete selected" }) as HTMLButtonElement;
        this._deleteBtn.disabled = true;
        this._deleteBtn.style.cssText = "font-size:12px";
        this._deleteBtn.onclick = () => this._deleteSelected();

        // Table
        this._tableEl = contentEl.createEl("div");
        this._tableEl.style.cssText = "overflow-y:auto;max-height:50vh;-webkit-user-select:text;user-select:text";

        // Pagination row — hidden when all results fit on one page
        this._pageRow = contentEl.createEl("div");
        this._pageRow.style.cssText = "display:none;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--text-muted);";
        this._prevBtn = this._pageRow.createEl("button", { text: "← Prev" }) as HTMLButtonElement;
        this._pageLabel = this._pageRow.createEl("span");
        this._nextBtn = this._pageRow.createEl("button", { text: "Next →" }) as HTMLButtonElement;
        this._prevBtn.onclick = () => { this._page--; this._renderTable(); };
        this._nextBtn.onclick = () => { this._page++; this._renderTable(); };

        // Purge footer
        const purgeRow = contentEl.createEl("div");
        purgeRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-top:12px;padding-top:10px;border-top:1px solid var(--background-modifier-border);font-size:12px;color:var(--text-muted)";
        purgeRow.createEl("span", { text: "Older than" });
        const purgeDaysInput = purgeRow.createEl("input", { type: "number" }) as HTMLInputElement;
        purgeDaysInput.value = "7";
        purgeDaysInput.style.cssText = "width:50px;padding:2px 5px;font-size:12px";
        purgeRow.createEl("span", { text: "days" });
        const purgeBtn = purgeRow.createEl("button", { text: "Purge old jobs" });
        purgeBtn.style.cssText = "font-size:12px";
        const purgeStatusEl = purgeRow.createEl("span");
        purgeStatusEl.style.cssText = "font-size:12px";
        purgeBtn.onclick = async () => {
            const days = parseInt(purgeDaysInput.value) || 7;
            purgeBtn.disabled = true;
            purgeStatusEl.setText("Purging…");
            try {
                const r = await api.purgeJobs(days) as any;
                purgeStatusEl.setText(`Purged ${r.purged} job(s)`);
                new Notice(`Synthadoc: purged ${r.purged} job(s)`);
                this._load();
            } catch {
                purgeStatusEl.setText("Error: is synthadoc serve running?");
            } finally { purgeBtn.disabled = false; }
        };

        this._resetAndLoad();
    }

    private _resetAndLoad() {
        this._stopTimer();
        this._countdown = this._intervalSecs;
        this._tickCountdown();
        this._load();
        this._countdownTimer = window.setInterval(() => {
            this._countdown--;
            this._tickCountdown();
            if (this._countdown <= 0) {
                this._countdown = this._intervalSecs;
                this._load();
            }
        }, 1000);
    }

    private _tickCountdown() {
        if (this._countdownEl) {
            this._countdownEl.setText(`refreshing in ${this._countdown}s`);
        }
    }

    private _stopTimer() {
        if (this._countdownTimer !== null) {
            window.clearInterval(this._countdownTimer);
            this._countdownTimer = null;
        }
    }

    private async _load() {
        if (!this._tableEl) return;
        try {
            const allJobs = await api.jobs() as any[];
            this._filteredJobs = this._selected.size === 0
                ? allJobs
                : allJobs.filter((j: any) => this._selected.has(j.status));
            this._renderTable();
        } catch {
            if (this._tableEl) this._tableEl.setText("Error: is synthadoc serve running?");
        }
    }

    private _hasRetryableChecked(): boolean {
        const RETRYABLE = new Set(["failed", "dead", "cancelled"]);
        return [...this._checkedIds].some(id => {
            const job = this._filteredJobs.find((j: any) => j.id === id);
            return job && RETRYABLE.has(job.status);
        });
    }

    private _updateActionBtns() {
        if (this._deleteBtn) this._deleteBtn.disabled = this._checkedIds.size === 0;
        if (this._retryBtn) this._retryBtn.disabled = !this._hasRetryableChecked();
    }

    private async _retrySelected() {
        if (!this._retryBtn || !this._hasRetryableChecked()) return;
        this._retryBtn.disabled = true;
        if (this._deleteBtn) this._deleteBtn.disabled = true;
        const RETRYABLE = new Set(["failed", "dead", "cancelled"]);
        const ids = [...this._checkedIds].filter(id => {
            const job = this._filteredJobs.find((j: any) => j.id === id);
            return job && RETRYABLE.has(job.status);
        });
        await Promise.allSettled(ids.map(id => api.retryJob(id)));
        this._checkedIds.clear();
        this._load();
    }

    private async _deleteSelected() {
        if (!this._deleteBtn || this._checkedIds.size === 0) return;
        this._deleteBtn.disabled = true;
        const ids = [...this._checkedIds];
        await Promise.allSettled(ids.map(id => api.deleteJob(id)));
        this._checkedIds.clear();
        this._load();
    }

    private _sortedJobs(): any[] {
        const col = this._sortBy;
        const dir = this._sortOrder === "asc" ? 1 : -1;
        return [...this._filteredJobs].sort((a, b) => {
            const av: string = a[col] ?? "";
            const bv: string = b[col] ?? "";
            return av < bv ? -dir : av > bv ? dir : 0;
        });
    }

    private _renderTable() {
        if (!this._tableEl) return;
        this._tableEl.empty();

        const sorted = this._sortedJobs();
        const total = sorted.length;
        const totalPages = Math.max(1, Math.ceil(total / JOBS_PAGE_SIZE));
        this._page = Math.min(this._page, totalPages - 1);
        const jobs = sorted.slice(this._page * JOBS_PAGE_SIZE, (this._page + 1) * JOBS_PAGE_SIZE);

        // Update pagination controls
        if (this._prevBtn) this._prevBtn.disabled = this._page === 0;
        if (this._nextBtn) this._nextBtn.disabled = this._page >= totalPages - 1;
        if (this._pageRow) this._pageRow.style.display = totalPages > 1 ? "flex" : "none";
        if (this._pageLabel) this._pageLabel.textContent = `Page ${this._page + 1} of ${totalPages} (${total} total)`;

        // Remove stale checked IDs no longer in the filtered list (handles deletions / filter changes)
        const allFilteredIds = new Set(this._filteredJobs.map((j: any) => j.id));
        for (const id of this._checkedIds) {
            if (!allFilteredIds.has(id)) this._checkedIds.delete(id);
        }
        this._updateActionBtns();

        if (total === 0) {
            this._tableEl.createEl("p", { text: "No jobs match the selected filters.", cls: "synthadoc-muted" });
            return;
        }

        const terminalJobs = jobs.filter((j: any) => TERMINAL_STATUSES.has(j.status));
        const hasTerminal = terminalJobs.length > 0;

        const table = this._tableEl.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";

        const hrow = table.createEl("thead").createEl("tr");

        // Select-all checkbox header cell
        const selectAllTh = hrow.createEl("th");
        selectAllTh.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border);width:28px";
        let selectAllCb: HTMLInputElement | null = null;
        if (hasTerminal) {
            selectAllCb = selectAllTh.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            selectAllCb.title = "Select all";
            selectAllCb.checked = terminalJobs.every((j: any) => this._checkedIds.has(j.id));
            selectAllCb.indeterminate = !selectAllCb.checked && terminalJobs.some((j: any) => this._checkedIds.has(j.id));
        }

        const SORT_HEADERS: { label: string; col: "status" | "operation" | "created_at" | null }[] = [
            { label: "Job ID", col: null },
            { label: "Status", col: "status" },
            { label: "Operation", col: "operation" },
            { label: "Source", col: null },
            { label: "Created", col: "created_at" },
        ];
        for (const { label, col } of SORT_HEADERS) {
            const th = hrow.createEl("th");
            th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
            if (col) {
                const indicator = this._sortBy === col ? (this._sortOrder === "asc" ? " ▲" : " ▼") : " ⇅";
                th.setText(label + indicator);
                th.style.cursor = "pointer";
                th.title = `Sort by ${label}`;
                th.onclick = () => {
                    if (this._sortBy === col) {
                        this._sortOrder = this._sortOrder === "asc" ? "desc" : "asc";
                    } else {
                        this._sortBy = col;
                        this._sortOrder = "asc";
                    }
                    this._page = 0;
                    this._renderTable();
                };
            } else {
                th.setText(label);
            }
        }

        const rowCheckboxes: HTMLInputElement[] = [];

        const tbody = table.createEl("tbody");
        for (const job of jobs) {
            const tr = tbody.createEl("tr");
            const isTerminal = TERMINAL_STATUSES.has(job.status);
            const source = job.payload?.source
                ? job.payload.source.split(/[\\/]/).pop()
                : job.operation === "lint" ? "(lint)" : "—";
            // SQLite stores UTC without tz marker; append +00:00 so JS parses as UTC
            const created = job.created_at
                ? new Date(job.created_at.replace(" ", "T") + "+00:00").toLocaleString()
                : "—";
            const icon = STATUS_EMOJI[job.status] ?? "";

            // Checkbox cell
            const cbTd = tr.createEl("td");
            cbTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);width:28px";
            if (isTerminal) {
                const cb = cbTd.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                cb.checked = this._checkedIds.has(job.id);
                cb.onchange = () => {
                    if (cb.checked) this._checkedIds.add(job.id);
                    else this._checkedIds.delete(job.id);
                    if (selectAllCb) {
                        selectAllCb.checked = terminalJobs.every((j: any) => this._checkedIds.has(j.id));
                        selectAllCb.indeterminate = !selectAllCb.checked && terminalJobs.some((j: any) => this._checkedIds.has(j.id));
                    }
                    this._updateActionBtns();
                };
                rowCheckboxes.push(cb);
            }

            // Job ID cell — monospace, full ID visible and selectable for copy
            const idTd = tr.createEl("td");
            idTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);font-family:monospace;font-size:11px;color:var(--text-muted)";
            idTd.setText(job.id ?? "—");

            for (const text of [`${icon} ${job.status}`, job.operation, source, created]) {
                const td = tr.createEl("td", { text });
                td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
            }
            if (job.status === "completed" && job.result) {
                const detail = jobResultSummary(job.result);
                if (detail.length) {
                    const dtd = tbody.createEl("tr").createEl("td", { text: detail.join(" · ") });
                    dtd.colSpan = 6;
                    dtd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-muted)";
                }
            }
            if ((job.status === "failed" || job.status === "dead") && job.error) {
                const etd = tbody.createEl("tr").createEl("td", { text: `Error: ${job.error}` });
                etd.colSpan = 6;
                etd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-error)";
            }
            if (job.status === "skipped" && job.error) {
                const wtd = tbody.createEl("tr").createEl("td", { text: `Skipped: ${job.error}` });
                wtd.colSpan = 6;
                wtd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-warning)";
            }
        }

        if (selectAllCb) {
            selectAllCb.onchange = () => {
                for (const job of terminalJobs) {
                    if (selectAllCb!.checked) this._checkedIds.add(job.id);
                    else this._checkedIds.delete(job.id);
                }
                for (const cb of rowCheckboxes) cb.checked = selectAllCb!.checked;
                this._updateActionBtns();
            };
        }
    }

    onClose() {
        this._stopTimer();
        this.contentEl.empty();
    }
}

class LintRunModal extends Modal {
    private _pollTimer: number | null = null;

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Run lint" });
        makeDraggable(this.modalEl, titleEl);
        this.modalEl.style.width = "clamp(480px, 55vw, 680px)";

        const intro = contentEl.createEl("p", {
            text: "Lint checks every wiki page for contradictions, orphaned links, and adversarial claims. Configure the options below then click Run lint to enqueue the job.",
        });
        intro.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:16px;-webkit-user-select:text;user-select:text";

        function addLintOption(
            id: string,
            title: string,
            hint: string,
            defaultChecked = false
        ): HTMLInputElement {
            const row = contentEl.createEl("div");
            row.style.cssText = "display:flex;align-items:flex-start;gap:10px;margin-bottom:14px";
            const input = row.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            input.id = id;
            input.checked = defaultChecked;
            input.style.cssText = "margin-top:3px;flex-shrink:0;cursor:pointer";
            const textBlock = row.createEl("div");
            const lbl = textBlock.createEl("label", { text: title });
            lbl.htmlFor = id;
            lbl.style.cssText = "display:block;font-size:13px;font-weight:600;margin-bottom:3px;cursor:pointer";
            const desc = textBlock.createEl("p", { text: hint });
            desc.style.cssText = "font-size:11px;color:var(--text-muted);margin:0;-webkit-user-select:text;user-select:text";
            return input;
        }

        const cb = addLintOption(
            "lint-auto-resolve",
            "Auto-resolve contradictions",
            "Auto-resolve rewrites contradicted pages to reconcile conflicts automatically. Leave unchecked to review the report first."
        );
        const skipAdvCb = addLintOption(
            "lint-skip-adversarial",
            "Skip adversarial review",
            "Adversarial review uses a second LLM pass to flag unsupported claims. Check this to skip that pass and finish faster."
        );
        const checkUrlCb = addLintOption(
            "lint-check-urls",
            "Check URL availability",
            "Issue an HTTP HEAD request for each URL-sourced page. A 404 or 410 response (or a removed YouTube video) transitions the page to archived. Network timeouts leave the page unchanged."
        );

        // Pre-check based on server config (async — defaults to unchecked on failure)
        api.config().then((cfg: any) => {
            if (cfg?.check_url_availability) checkUrlCb.checked = true;
        }).catch(() => {});

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;align-items:center;gap:8px;justify-content:flex-end";
        const reportLink = btnRow.createEl("a", { text: "Lint report →" });
        reportLink.style.cssText = "display:none;font-size:12px;cursor:pointer;color:var(--link-color)";
        reportLink.onclick = () => {
            this.close();
            setTimeout(() => new LintReportModal(this.app).open(), 150);
        };
        const btn = btnRow.createEl("button", { text: "Run lint" });

        const out = contentEl.createEl("div");
        out.style.cssText = "margin-top:12px;-webkit-user-select:text;user-select:text";

        btn.onclick = async () => {
            const autoResolve = cb.checked;
            const adversarial = !skipAdvCb.checked;
            const checkUrls = checkUrlCb.checked ? true : null;
            btn.disabled = true;
            cb.disabled = true;
            skipAdvCb.disabled = true;
            checkUrlCb.disabled = true;
            reportLink.style.display = "none";
            out.empty();
            out.createEl("p", { text: autoResolve ? "⏳ Enqueueing lint with auto-resolve…" : "⏳ Enqueueing lint…" });
            try {
                const r = await api.lint("all", autoResolve, adversarial, checkUrls) as any;
                const jobId: string = r.job_id;
                out.empty();
                out.createEl("p", { text: `⏳ Lint running… (job ${jobId.slice(0, 8)})` });

                this._pollTimer = window.setInterval(async () => {
                    try {
                        const job = await api.job(jobId) as any;
                        const status: string = job.status;

                        if (status === "in_progress" || status === "pending") {
                            out.empty();
                            out.createEl("p", { text: `⏳ Lint ${status === "pending" ? "queued" : "running"}… (job ${jobId.slice(0, 8)})` });
                            return;
                        }

                        // Job settled — stop polling
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;

                        if (status === "completed") {
                            try {
                                const report = await api.lintReport() as any;
                                const details: any[] = report.contradiction_details ?? [];
                                const contradictions: string[] = report.contradictions ?? [];
                                const orphans: string[] = report.orphans ?? [];
                                const adversarialWarnings: any[] = report.adversarial_warnings ?? [];
                                const truncatedSources: any[] = report.truncated_sources ?? [];
                                out.empty();
                                const summary = out.createEl("p");
                                summary.style.cssText = "font-weight:bold;margin-bottom:6px";
                                summary.setText(`✅ Done — ${contradictions.length} contradiction(s), ${orphans.length} orphan(s), ${adversarialWarnings.length} adversarial warning(s), ${truncatedSources.length} truncated source(s).`);
                                if (adversarialWarnings.length > 0 || truncatedSources.length > 0) {
                                    const advHint = out.createEl("p", { text: "Open Lint report → to see full details." });
                                    advHint.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:4px";
                                }
                                for (const d of details) {
                                    const block = out.createEl("div");
                                    block.style.cssText = "margin-bottom:6px";
                                    block.createEl("span", { text: `❌ ${d.slug}` }).style.cssText = "font-size:12px;color:var(--text-error);font-weight:600";
                                    if (d.contradiction_note) {
                                        block.createEl("div", { text: `Why flagged: ${d.contradiction_note}` }).style.cssText = "font-size:11px;color:var(--text-muted);margin-top:2px";
                                    }
                                    if (d.unresolved_note) {
                                        block.createEl("div", { text: `⚠ Auto-resolve failed: ${d.unresolved_note}` }).style.cssText = "font-size:11px;color:var(--text-warning);margin-top:2px";
                                    }
                                }
                                if (orphans.length > 0) {
                                    out.createEl("p", { text: `Orphans: ${orphans.join(", ")}` }).style.cssText = "font-size:12px;color:var(--text-muted)";
                                }
                                new Notice(`Synthadoc: lint done — ${contradictions.length} contradictions, ${orphans.length} orphans, ${adversarialWarnings.length} adversarial warnings, ${truncatedSources.length} truncated sources`);
                            } catch {
                                out.empty();
                                out.createEl("p", { text: "✅ Lint complete. Could not load report." });
                            }
                        } else {
                            out.empty();
                            out.createEl("p", { text: `❌ Lint ${status}${job.error ? `: ${job.error}` : ""}` }).style.cssText = "color:var(--text-error)";
                        }
                        btn.disabled = false;
                        cb.disabled = false;
                        skipAdvCb.disabled = false;
                        checkUrlCb.disabled = false;
                        reportLink.style.display = "";
                    } catch {
                        // server unreachable — keep polling silently
                    }
                }, 2000);
            } catch {
                out.empty();
                out.createEl("p", { text: "❌ Error: is synthadoc serve running?" });
                btn.disabled = false;
                cb.disabled = false;
                skipAdvCb.disabled = false;
                checkUrlCb.disabled = false;
            }
        };
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
}

class LintReportModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const header = contentEl.createEl("div");
        header.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:4px";
        const titleEl = header.createEl("h3", { text: "Synthadoc: Lint report" });
        titleEl.style.cssText = "margin:0";
        const runBtn = header.createEl("button", { text: "▶ Run lint" });
        runBtn.style.cssText = "font-size:12px;padding:3px 10px;cursor:pointer";
        runBtn.onclick = () => { this.close(); new LintRunModal(this.app).open(); };
        this.modalEl.style.width = "clamp(680px, 75vw, 1060px)";
        makeDraggable(this.modalEl, header);

        // Draft/stale badge — fetch lifecycle status and show badge if any pages need attention
        (async () => {
            try {
                const lcStatus = await api.lifecycleStatus() as any;
                const counts = lcStatus.counts || lcStatus;
                if ((counts.draft || 0) + (counts.stale || 0) > 0) {
                    const badge = header.createDiv();
                    badge.style.cssText = "display:flex;gap:12px;font-size:12px;margin-top:4px";
                    if (counts.draft) {
                        const d = badge.createSpan({ text: `${counts.draft} draft` });
                        d.style.color = "var(--color-orange)";
                        d.style.cursor = "pointer";
                        d.addEventListener("click", () => {
                            this.close();
                            const wr = this.app.vault.adapter instanceof FileSystemAdapter
                                ? this.app.vault.adapter.getBasePath() : "";
                            new LifecycleModal(this.app, wr, getBase(), LifecycleState.DRAFT).open();
                        });
                    }
                    if (counts.stale) {
                        const s = badge.createSpan({ text: `${counts.stale} stale` });
                        s.style.color = "var(--color-yellow)";
                        s.style.cursor = "pointer";
                        s.addEventListener("click", () => {
                            this.close();
                            const wr = this.app.vault.adapter instanceof FileSystemAdapter
                                ? this.app.vault.adapter.getBasePath() : "";
                            new LifecycleModal(this.app, wr, getBase(), LifecycleState.STALE).open();
                        });
                    }
                }
            } catch { /* server may not be running */ }
        })();

        const out = contentEl.createEl("div");
        out.style.cssText = "-webkit-user-select:text;user-select:text";
        out.createEl("p", { text: "Loading…", cls: "synthadoc-muted" });

        api.lintReport().then((r: any) => {
            out.empty();
            const details: any[] = r.contradiction_details ??
                (r.contradictions ?? []).map((s: string) => ({ slug: s }));
            const orphanDetails: any[] = r.orphan_details ??
                (r.orphans ?? []).map((s: string) => ({ slug: s, index_suggestion: `- [[${s}]]` }));
            const adversarialWarnings: any[] = r.adversarial_warnings ?? [];
            const truncatedSources: any[] = r.truncated_sources ?? [];
            const citationIssuesBySlug: Record<string, any[]> = r.citation_issues_by_slug ?? {};
            const citationSlugs = Object.keys(citationIssuesBySlug);
            const totalCitationIssues = Object.values(citationIssuesBySlug).reduce(
                (sum: number, issues: any[]) => sum + issues.length, 0);
            const totalAdvWarnings = adversarialWarnings.reduce(
                (sum: number, p: any) => sum + ((p.warnings as any[])?.length ?? 0), 0);

            // Tab bar
            const tabBar = out.createEl("div");
            tabBar.style.cssText = "display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid var(--background-modifier-border)";

            type TabName = "Contradictions" | "Orphans" | "Adversarial" | "Truncated" | "Citations";
            const tabNames: TabName[] = ["Contradictions", "Orphans", "Adversarial", "Truncated", "Citations"];
            const tabLabels: Record<TabName, string> = {
                "Contradictions": `❗ Contradictions (${details.length})`,
                "Orphans": `🔗 Orphans (${orphanDetails.length})`,
                "Adversarial": `🔍 Adversarial (${totalAdvWarnings})`,
                "Truncated": `✂ Truncated (${truncatedSources.length})`,
                "Citations": `📎 Citations (${totalCitationIssues})`,
            };
            const panels: Record<TabName, HTMLElement> = {} as any;
            const tabBtns: Record<TabName, HTMLElement> = {} as any;

            tabNames.forEach(name => {
                const btn = tabBar.createEl("div", { text: tabLabels[name] });
                btn.style.cssText = "padding:6px 14px;cursor:pointer;font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px;color:var(--text-muted)";
                tabBtns[name] = btn;
                const panel = out.createEl("div");
                panel.style.display = "none";
                panels[name] = panel;
            });

            const switchTab = (name: TabName) => {
                tabNames.forEach(t => {
                    panels[t].style.display = "none";
                    tabBtns[t].style.borderBottomColor = "transparent";
                    tabBtns[t].style.color = "var(--text-muted)";
                });
                panels[name].style.display = "";
                tabBtns[name].style.borderBottomColor = "var(--interactive-accent)";
                tabBtns[name].style.color = "var(--text-normal)";
            };

            tabNames.forEach(name => { tabBtns[name].onclick = () => switchTab(name); });

            // Contradictions panel
            if (details.length === 0) {
                panels["Contradictions"].createEl("p", { text: "✅ No contradictions found." });
            } else {
                const ul = panels["Contradictions"].createEl("ul");
                details.forEach(({ slug, contradiction_note, unresolved_note }) => {
                    const li = ul.createEl("li");
                    li.createEl("code", { text: slug });
                    li.appendText(" — open the page, resolve the conflict, set status: active");
                    if (contradiction_note) {
                        const n = li.createEl("div");
                        n.style.cssText = "font-size:11px;margin-top:2px";
                        const wfl = n.createEl("span", { text: "Why flagged: " });
                        wfl.style.cssText = "color:var(--color-orange,#f59e0b);font-weight:600";
                        n.createEl("span", { text: contradiction_note })
                            .style.cssText = "color:var(--text-muted)";
                    }
                    if (unresolved_note) {
                        const n = li.createEl("div", { text: `⚠ Auto-resolve failed: ${unresolved_note}` });
                        n.style.cssText = "font-size:11px;color:var(--text-warning);margin-top:2px";
                    }
                });
            }

            // Orphans panel
            if (orphanDetails.length === 0) {
                panels["Orphans"].createEl("p", { text: "✅ No orphan pages found." });
            } else {
                const ul = panels["Orphans"].createEl("ul");
                orphanDetails.forEach(({ slug, index_suggestion }) => {
                    const li = ul.createEl("li");
                    const slugLink = li.createEl("a", { text: slug });
                    slugLink.style.cssText = "cursor:pointer;font-family:var(--font-monospace);font-size:var(--font-smaller);font-weight:600";
                    slugLink.onclick = () => this.app.workspace.openLinkText(slug, "", false);
                    li.appendText(" — no inbound links");
                    const sug = li.createEl("div");
                    sug.style.cssText = "font-size:11px;margin-top:2px";
                    const sugLbl = sug.createEl("span", { text: "Suggested index entry: " });
                    sugLbl.style.cssText = "color:var(--interactive-accent);font-weight:600";
                    sug.createEl("code", { text: index_suggestion });
                });
            }

            // Adversarial panel
            if (adversarialWarnings.length === 0) {
                panels["Adversarial"].createEl("p", { text: "✅ No adversarial warnings found." });
            } else {
                adversarialWarnings.forEach(({ slug, warnings, suggested_reingests }) => {
                    const block = panels["Adversarial"].createEl("div");
                    block.style.cssText = "margin-bottom:12px;border-bottom:1px solid var(--background-modifier-border);padding-bottom:8px";
                    block.createEl("strong", { text: slug });
                    const warnList = block.createEl("ul");
                    (warnings as any[]).forEach(({ claim, concern }) => {
                        const li = warnList.createEl("li");
                        if (claim) {
                            const claimEl = li.createEl("div", { text: `⚠ "${claim}"` });
                            claimEl.style.cssText = "font-size:12px;font-style:italic;color:var(--color-orange,#f59e0b)";
                        }
                        const concernEl = li.createEl("div");
                        concernEl.style.cssText = "font-size:11px;margin-top:2px";
                        const lbl = concernEl.createEl("span", { text: "Concern: " });
                        lbl.style.cssText = "color:var(--color-orange,#f59e0b);font-weight:600";
                        concernEl.createEl("span", { text: concern ?? "(no concern text)" })
                            .style.cssText = "color:var(--text-muted)";
                    });
                    if ((suggested_reingests as string[])?.length > 0) {
                        const reingestDiv = block.createEl("div");
                        reingestDiv.style.cssText = "margin-top:6px";
                        reingestDiv.createEl("div", { text: "💡 If the source has updated content, re-ingest with --force to refresh this page:" })
                            .style.cssText = "font-size:11px;color:var(--text-muted)";
                        (suggested_reingests as string[]).forEach(cmd => {
                            const p = reingestDiv.createEl("div");
                            p.createEl("code", { text: cmd + " --force" })
                                .style.cssText = "font-size:11px;-webkit-user-select:text;user-select:text";
                        });
                    }
                });
            }

            // Truncated sources panel
            if (truncatedSources.length === 0) {
                panels["Truncated"].createEl("p", { text: "✅ No truncated sources." });
            } else {
                const ul = panels["Truncated"].createEl("ul");
                truncatedSources.forEach(({ slug, file, size, suggested_reingest }) => {
                    const li = ul.createEl("li");
                    const slugLink = li.createEl("a", { text: slug });
                    slugLink.style.cssText = "cursor:pointer;font-family:var(--font-monospace);font-size:var(--font-smaller);font-weight:600";
                    slugLink.onclick = () => this.app.workspace.openLinkText(slug, "", false);
                    li.appendText(` — source exceeded limit (${(size as number).toLocaleString()} chars)`);
                    const srcDiv = li.createEl("div");
                    srcDiv.style.cssText = "font-size:11px;margin-top:2px";
                    const srcLbl = srcDiv.createEl("span", { text: "Source: " });
                    srcLbl.style.cssText = "color:var(--text-muted);font-weight:600";
                    srcDiv.createEl("code", { text: file });
                    if (suggested_reingest) {
                        const reingestDiv = li.createEl("div");
                        reingestDiv.style.cssText = "margin-top:4px";
                        reingestDiv.createEl("div", { text: "💡 Re-ingest with a higher limit:" })
                            .style.cssText = "font-size:11px;color:var(--text-muted)";
                        reingestDiv.createEl("code", { text: suggested_reingest })
                            .style.cssText = "font-size:11px;-webkit-user-select:text;user-select:text";
                    }
                });
            }

            // Citations panel
            if (citationSlugs.length === 0) {
                panels["Citations"].createEl("p", { text: "✅ No citation issues found." });
            } else {
                const ul = panels["Citations"].createEl("ul");
                ul.style.cssText = "list-style:none;padding:0;margin:0;max-height:400px;overflow-y:auto";
                citationSlugs.forEach(slug => {
                    const issues: any[] = citationIssuesBySlug[slug] ?? [];
                    const li = ul.createEl("li");
                    li.style.cssText = "margin-bottom:10px";
                    const slugLink = li.createEl("a", { text: slug });
                    slugLink.style.cssText = "cursor:pointer;font-family:var(--font-monospace);font-size:var(--font-smaller);font-weight:600";
                    slugLink.onclick = () => this.app.workspace.openLinkText(slug, "", false);
                    li.appendText(` (${issues.length})`);
                    const issueList = li.createEl("ul");
                    issueList.style.cssText = "margin:4px 0 0 16px;padding:0";
                    issues.forEach(({ citation, reason }: any) => {
                        const issueLi = issueList.createEl("li");
                        issueLi.style.cssText = "font-size:11px;color:var(--text-muted);margin-bottom:2px";
                        issueLi.createEl("code", { text: citation })
                            .style.cssText = "-webkit-user-select:text;user-select:text";
                        issueLi.appendText(` — ${reason}`);
                    });
                });
            }

            // Default to first tab with data, or Contradictions
            const defaultTab: TabName =
                details.length > 0 ? "Contradictions" :
                truncatedSources.length > 0 ? "Truncated" :
                citationSlugs.length > 0 ? "Citations" :
                orphanDetails.length > 0 ? "Orphans" : "Adversarial";
            switchTab(defaultTab);

        }).catch(() => {
            out.empty();
            out.createEl("p", { text: "Error: is synthadoc serve running?" });
        });
    }
    onClose() { this.contentEl.empty(); }
}

class ScaffoldModal extends Modal {
    private _pollTimer: number | null = null;

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Regenerate scaffold" });
        makeDraggable(this.modalEl, titleEl);
        contentEl.createEl("p", {
            text: "Rewrites index.md, AGENTS.md, and purpose.md for your wiki domain using the LLM. Existing wiki pages are preserved.",
            cls: "synthadoc-muted",
        }).style.cssText = "font-size:12px;margin-bottom:12px";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;gap:8px;margin-bottom:12px";
        const input = row.createEl("input", { type: "text", placeholder: "e.g. Canadian tax law" });
        input.style.cssText = "flex:1;padding:4px 8px";
        const btn = row.createEl("button", { text: "Scaffold" });

        const out = contentEl.createEl("p");
        out.style.cssText = "font-size:12px;min-height:18px;-webkit-user-select:text;user-select:text";

        // Pre-fill domain from status if available
        api.status().then((s: any) => {
            if (s?.wiki) {
                const parts = s.wiki.replace(/\\/g, "/").split("/");
                input.value = parts[parts.length - 1].replace(/-/g, " ");
            }
        }).catch(() => {/* ignore */});

        const submit = async () => {
            const domain = input.value.trim();
            if (!domain) return;
            btn.disabled = true;
            input.disabled = true;
            out.setText("⏳ Queuing scaffold job…");
            try {
                const r = await api.scaffold(domain) as any;
                const jobId: string = r.job_id;
                out.setText(`⏳ Queued — job ${jobId.slice(0, 8)}…`);
                new Notice(`Synthadoc: scaffold queued (job ${jobId})`);

                this._pollTimer = window.setInterval(async () => {
                    try {
                        const job = await api.job(jobId) as any;
                        const status: string = job.status;

                        if (status === "pending") { out.setText(`⏳ Queued — job ${jobId.slice(0, 8)}…`); return; }
                        if (status === "in_progress") { out.setText(`⏳ Generating scaffold… (job ${jobId.slice(0, 8)})`); return; }

                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        btn.disabled = false;
                        input.disabled = false;

                        if (status === "completed") {
                            const routingMsg = job.result?.routing_regenerated ? " ROUTING.md regenerated." : "";
                            out.setText(`✅ Done — index.md, AGENTS.md, and purpose.md updated.${routingMsg}`);
                            new Notice("Synthadoc: scaffold complete");
                        } else if (status === "skipped") {
                            out.setText("⏭️ Skipped — already up to date.");
                        } else {
                            out.setText(`❌ ${status}${job.error ? `: ${job.error}` : ""}`);
                        }
                    } catch { /* server unreachable — keep polling */ }
                }, 2000);
            } catch {
                out.setText("❌ Error: is synthadoc serve running?");
                btn.disabled = false;
                input.disabled = false;
            }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
        setTimeout(() => input.focus(), 50);
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
}

class AuditModal extends Modal {
    onOpen() {
        this.modalEl.style.width = "clamp(560px, 70vw, 960px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Audit" });
        makeDraggable(this.modalEl, titleEl);

        const tabBar = contentEl.createEl("div");
        tabBar.style.cssText = "display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid var(--background-modifier-border)";

        type TabName = "Query history" | "Ingest history" | "Events" | "Cost summary";
        const tabNames: TabName[] = ["Query history", "Ingest history", "Events", "Cost summary"];
        const panels: Record<TabName, HTMLElement> = {} as any;
        const tabBtns: Record<TabName, HTMLElement> = {} as any;

        tabNames.forEach(name => {
            const btn = tabBar.createEl("div", { text: name });
            btn.style.cssText = "padding:6px 14px;cursor:pointer;font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px;color:var(--text-muted)";
            tabBtns[name] = btn;
            const panel = contentEl.createEl("div");
            panel.style.display = "none";
            panels[name] = panel;
        });

        const switchTab = (name: TabName) => {
            tabNames.forEach(t => {
                panels[t].style.display = "none";
                tabBtns[t].style.borderBottomColor = "transparent";
                tabBtns[t].style.color = "var(--text-muted)";
            });
            panels[name].style.display = "";
            tabBtns[name].style.borderBottomColor = "var(--interactive-accent)";
            tabBtns[name].style.color = "var(--text-normal)";
        };

        tabNames.forEach(name => { tabBtns[name].onclick = () => switchTab(name); });

        this._buildQueryHistoryTab(panels["Query history"]);
        this._buildIngestHistoryTab(panels["Ingest history"]);
        this._buildEventsTab(panels["Events"]);
        this._buildCostSummaryTab(panels["Cost summary"]);
        switchTab("Query history");
    }

    private _buildQueryHistoryTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "50";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "records" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = panel.createEl("div");

        const load = async () => {
            const limit = parseInt(input.value) || 50;
            tableEl.setText("Loading…");
            try {
                const r = await api.queryHistory(limit) as any;
                tableEl.empty();
                if (!r.records.length) {
                    tableEl.createEl("p", { text: "No queries recorded yet." });
                    return;
                }
                const table = tableEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;-webkit-user-select:text;user-select:text";
                const hrow = table.createEl("thead").createEl("tr");
                for (const h of ["Question", "Sub-Qs", "Tokens", "Cost (USD)", "Asked at"]) {
                    const th = hrow.createEl("th", { text: h });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
                }
                const tbody = table.createEl("tbody");
                for (const rec of r.records) {
                    const tr = tbody.createEl("tr");
                    const ts = rec.queried_at ? new Date(rec.queried_at).toLocaleString() : "—";
                    for (const text of [
                        rec.question.length > 80 ? rec.question.slice(0, 77) + "…" : rec.question,
                        String(rec.sub_questions_count ?? 1),
                        (rec.tokens ?? 0).toLocaleString(),
                        `$${(rec.cost_usd ?? 0).toFixed(4)}`,
                        ts,
                    ]) {
                        const td = tr.createEl("td", { text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                    }
                }
            } catch {
                tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        load();
    }

    private _buildIngestHistoryTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "50";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "records" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = panel.createEl("div");

        const load = async () => {
            const limit = parseInt(input.value) || 50;
            tableEl.setText("Loading…");
            try {
                const r = await api.auditHistory(limit) as any;
                tableEl.empty();
                if (!r.records.length) {
                    tableEl.createEl("p", { text: "No ingest records yet." });
                    return;
                }
                const table = tableEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;-webkit-user-select:text;user-select:text;table-layout:fixed";
                // colgroup — fixes column widths so the table doesn't reflow per row
                const cg = table.createEl("colgroup");
                for (const w of ["20%", "26%", "8%", "10%", "36%"]) {
                    const col = cg.createEl("col") as HTMLElement;
                    col.style.width = w;
                }
                const COLS = [
                    { label: "Source",     wrap: false },
                    { label: "Wiki page",  wrap: false },
                    { label: "Tokens",     wrap: true  },
                    { label: "Cost (USD)", wrap: true  },
                    { label: "Ingested at", wrap: true },
                ];
                const hrow = table.createEl("thead").createEl("tr");
                for (const col of COLS) {
                    const th = hrow.createEl("th", { text: col.label });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border);white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
                }
                const tbody = table.createEl("tbody");
                for (const rec of r.records) {
                    const tr = tbody.createEl("tr");
                    const _parts = rec.source_path.split(/[\\/]/);
                    const src = _parts.filter(Boolean).pop() ?? rec.source_path;
                    const ts = rec.ingested_at ? new Date(rec.ingested_at).toLocaleString() : "—";
                    const cells = [
                        { text: src,                                    nowrap: true  },
                        { text: rec.wiki_page,                          nowrap: true  },
                        { text: (rec.tokens ?? 0).toLocaleString(),     nowrap: true  },
                        { text: `$${(rec.cost_usd ?? 0).toFixed(4)}`,   nowrap: true  },
                        { text: ts,                                      nowrap: true  },
                    ];
                    for (const cell of cells) {
                        const td = tr.createEl("td", { text: cell.text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);overflow:hidden;text-overflow:ellipsis"
                            + (cell.nowrap ? ";white-space:nowrap" : "");
                    }
                }
            } catch {
                tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        load();
    }

    private _buildEventsTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "100";
        input.min = "1";
        input.max = "1000";
        input.style.cssText = "width:70px;padding:4px 8px";
        row.createEl("span", { text: "events (max 1000)" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = panel.createEl("div");
        tableEl.style.cssText = "max-height:60vh;overflow-y:auto";

        const load = async () => {
            let limit = parseInt(input.value) || 100;
            if (limit < 1) limit = 1;
            if (limit > 1000) limit = 1000;
            input.value = String(limit);
            tableEl.setText("Loading…");
            try {
                const r = await api.auditEvents(limit) as any;
                tableEl.empty();
                if (!r.records.length) {
                    tableEl.createEl("p", { text: "No audit events found." });
                    return;
                }
                const table = tableEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;-webkit-user-select:text;user-select:text";
                const hrow = table.createEl("thead").createEl("tr");
                for (const h of ["Timestamp", "Job ID", "Event", "Metadata"]) {
                    const th = hrow.createEl("th", { text: h });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border);white-space:nowrap";
                }
                const tbody = table.createEl("tbody");
                for (const rec of r.records) {
                    const tr = tbody.createEl("tr");
                    const ts = rec.timestamp ? rec.timestamp.slice(0, 16).replace("T", " ") : "—";
                    const jobId = rec.job_id ? rec.job_id.slice(0, 8) : "—";
                    for (const text of [ts, jobId, rec.event ?? "—", rec.metadata ?? "—"]) {
                        const td = tr.createEl("td", { text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);font-size:11px";
                    }
                }
            } catch {
                tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
        load();
    }

    private _buildCostSummaryTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "30";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "days" });
        const btn = row.createEl("button", { text: "Load" });

        const out = panel.createEl("div");

        const load = async () => {
            const days = parseInt(input.value) || 30;
            out.setText("Loading…");
            try {
                const r = await api.auditCosts(days) as any;
                out.empty();

                const summary = out.createEl("div");
                summary.style.cssText = "margin-bottom:16px";
                summary.createEl("p", {
                    text: `Total: ${(r.total_tokens ?? 0).toLocaleString()} tokens · $${(r.total_cost_usd ?? 0).toFixed(4)} USD`,
                }).style.cssText = "font-weight:bold;-webkit-user-select:text;user-select:text";

                if (r.daily?.length) {
                    const table = out.createEl("table");
                    table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";
                    const hrow = table.createEl("thead").createEl("tr");
                    for (const h of ["Day", "Cost (USD)"]) {
                        const th = hrow.createEl("th", { text: h });
                        th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
                    }
                    const tbody = table.createEl("tbody");
                    for (const d of r.daily) {
                        const tr = tbody.createEl("tr");
                        for (const text of [d.day, `$${(d.cost_usd ?? 0).toFixed(4)}`]) {
                            const td = tr.createEl("td", { text });
                            td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                        }
                    }
                } else {
                    out.createEl("p", { text: "No cost data for this period.", cls: "synthadoc-muted" });
                }
            } catch {
                out.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        load();
    }

    onClose() { this.contentEl.empty(); }
}

class QueryModal extends Modal {
    onOpen() {
        // Scale with viewport: min 520px, 60% of screen width, max 860px
        this.modalEl.style.width = "clamp(520px, 60vw, 860px)";

        // Block the backdrop's built-in click-to-close so the user must close explicitly
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Query your wiki" });
        makeDraggable(this.modalEl, titleEl);

        const input = contentEl.createEl("textarea", { placeholder: "Ask a question…\n(Ctrl+Enter or Cmd+Enter to submit)" });
        input.style.cssText = "width:100%;min-height:72px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:12px";

        const settingsGroup = row.createEl("div");
        settingsGroup.style.cssText = "display:flex;align-items:center;gap:16px";

        const noCacheLabel = settingsGroup.createEl("label");
        noCacheLabel.style.cssText = "display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text-muted);white-space:nowrap;cursor:pointer";
        const noCacheCheckbox = noCacheLabel.createEl("input", { type: "checkbox" }) as HTMLInputElement;
        noCacheCheckbox.checked = false;
        noCacheLabel.appendText("Bypass cache");

        const timeoutGroup = settingsGroup.createEl("div");
        timeoutGroup.style.cssText = "display:flex;align-items:center;gap:6px";
        const timeoutLabel = timeoutGroup.createEl("label", { text: "Timeout (s):" });
        timeoutLabel.style.cssText = "font-size:12px;color:var(--text-muted);white-space:nowrap";
        const timeoutInput = timeoutGroup.createEl("input", { type: "number" }) as HTMLInputElement;
        timeoutInput.value = "60";
        timeoutInput.min = "10";
        timeoutInput.max = "300";
        timeoutInput.step = "10";
        timeoutInput.style.cssText = "width:60px;padding:4px 6px;font-size:12px";

        const btn = row.createEl("button", { text: "Ask" });

        const out = contentEl.createEl("div");
        out.style.cssText = "max-height:60vh;overflow-y:auto;padding:4px 0;-webkit-user-select:text;user-select:text";

        // Handle internal [[wikilinks]] rendered by MarkdownRenderer inside the modal.
        // Obsidian's normal link handler doesn't fire inside modals, so we intercept
        // clicks here, open the file via the workspace API, then close the modal.
        out.addEventListener("click", (e) => {
            const link = (e.target as HTMLElement).closest("a");
            if (!link) return;
            const href = link.getAttribute("data-href") || link.getAttribute("href") || "";
            if (!href || href.startsWith("http://") || href.startsWith("https://")) return;
            e.preventDefault();
            e.stopPropagation();
            this.app.workspace.openLinkText(href, "", false);
            this.close();
        });

        const submit = async () => {
            if (!input.value.trim()) return;
            btn.disabled = true;
            out.empty();
            const statusEl = out.createEl("p", { text: "Streaming…", cls: "synthadoc-muted" });
            const streamEl = out.createEl("span");
            let fullAnswer = "";
            let citations: string[] = [];
            let knowledgeGap = false;
            let suggestedSearches: string[] = [];

            const renderFinal = async () => {
                out.empty();
                if (fullAnswer) {
                    await MarkdownRenderer.render(this.app, fullAnswer, out, "", this);
                }
                if (citations.length) {
                    const cite = out.createEl("p");
                    cite.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:8px";
                    cite.setText("Sources: " + citations.join(", "));
                }
                if (knowledgeGap && suggestedSearches.length) {
                    await this._renderGapSection(out, suggestedSearches);
                }
                btn.disabled = false;
            };

            try {
                await api.queryStream(input.value.trim(), undefined, {
                    onStatus: (phase) => { statusEl.setText(phase === "retrieving" ? "Searching…" : "Generating…"); },
                    onToken: (text) => {
                        fullAnswer += text;
                        streamEl.textContent = (streamEl.textContent ?? "") + text;
                    },
                    onCitations: (c) => { citations = c; },
                    onGap: (s) => { knowledgeGap = true; suggestedSearches = s; },
                    onDone: async () => { await renderFinal(); },
                    onError: (msg) => {
                        out.empty();
                        out.createEl("p", { text: `Error: ${msg}` });
                        btn.disabled = false;
                    },
                }, noCacheCheckbox.checked);
            } catch {
                // Fallback to blocking query if streaming fails
                try {
                    const timeoutSecs = Math.min(300, Math.max(10, parseInt(timeoutInput.value) || 60));
                    const r = await api.query(input.value, timeoutSecs) as any;
                    out.empty();
                    await MarkdownRenderer.render(this.app, r.answer, out, "", this);
                    if (r.citations?.length) {
                        const cite = out.createEl("p");
                        cite.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:8px";
                        cite.setText("Sources: " + r.citations.join(", "));
                    }
                    if (r.knowledge_gap && r.suggested_searches?.length) {
                        await this._renderGapSection(out, r.suggested_searches as string[]);
                    }
                } catch {
                    out.empty();
                    out.createEl("p", { text: "Error: is synthadoc serve running?" });
                } finally { btn.disabled = false; }
            }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
    }
    private async _renderGapSection(container: HTMLElement, suggestions: string[]): Promise<void> {
        const commands = suggestions
            .map((s) => `synthadoc ingest "search for: ${s}"`)
            .join("\n");
        const callout = [
            "> [!tip] Knowledge Gap Detected",
            "> Your wiki doesn't have enough on this topic yet. Enrich it with a web search:",
            ">",
            "> **From Obsidian:** Open Command Palette (`Cmd+P` / `Ctrl+P`) → **Synthadoc: Ingest...** → Web search tab",
            ">",
            "> **From the terminal:**",
        ].join("\n");
        const gapEl = container.createEl("div");
        gapEl.style.cssText = "margin-top:16px";
        await MarkdownRenderer.render(this.app, callout, gapEl, "", this);

        const calloutContent = gapEl.querySelector(".callout-content") as HTMLElement | null;
        const target = calloutContent ?? gapEl;

        const row = target.createEl("div");
        row.style.cssText = "display:flex;align-items:flex-start;gap:8px;margin:6px 0";

        const pre = row.createEl("pre");
        pre.style.cssText = "flex:1;margin:0;padding:6px 10px;background:var(--background-secondary);border-radius:4px;font-family:var(--font-monospace);font-size:12px;white-space:pre;overflow-x:auto;color:var(--text-normal)";
        pre.setText(commands);

        const copyBtn = row.createEl("button");
        copyBtn.style.cssText = "flex-shrink:0;align-self:flex-start;padding:3px 10px;font-size:11px;cursor:pointer";
        copyBtn.setText("Copy");
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(commands).then(() => {
                copyBtn.setText("Copied!");
                setTimeout(() => copyBtn.setText("Copy"), 2000);
            }).catch(() => {});
        };

        const footer = target.createEl("p");
        footer.style.cssText = "font-size:12px;color:var(--text-muted);margin-top:6px";
        footer.setText("After ingesting, re-run your query to get a richer answer.");
    }
    onClose() { this.contentEl.empty(); }
}

class RoutingModal extends Modal {
    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(560px, 65vw, 900px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Routing" });
        makeDraggable(modalEl, titleEl);

        const contentBox = contentEl.createEl("pre");
        contentBox.style.cssText = "display:none;border:1px solid var(--background-modifier-border);"
            + "border-radius:4px;padding:8px;margin-bottom:12px;font-size:12px;"
            + "white-space:pre-wrap;overflow-y:auto;max-height:45vh;";

        const statusMsg = contentEl.createEl("p");
        statusMsg.style.cssText = "margin-bottom:12px;font-size:13px;";

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;margin-bottom:10px;";
        const initBtn     = btnRow.createEl("button", { text: "Init" });
        const validateBtn = btnRow.createEl("button", { text: "Validate" });
        const cleanBtn    = btnRow.createEl("button", { text: "Clean" });

        const descEl = contentEl.createEl("div");
        descEl.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:12px;";
        descEl.innerHTML =
            `<div style="display:grid;grid-template-columns:68px 1fr;gap:3px 10px;">` +
            `<strong>Init</strong><span>Bootstrap ROUTING.md from current index.md branch structure (run once)</span>` +
            `<strong>Validate</strong><span>Report dangling slugs (pages listed in ROUTING.md that no longer exist)</span>` +
            `<strong>Clean</strong><span>Auto-remove dangling slugs from ROUTING.md</span>` +
            `</div>`;

        const resultEl = contentEl.createEl("div");
        resultEl.style.cssText = "font-size:13px;min-height:24px;";
        const setResult = (html: string) => { resultEl.innerHTML = html; };

        const applyInitialized = (content: string) => {
            contentBox.style.display = "block";
            contentBox.textContent = content;
            statusMsg.style.display = "none";
            initBtn.disabled = true;
            validateBtn.disabled = false;
            cleanBtn.disabled = false;
        };

        const applyUninitialized = () => {
            contentBox.style.display = "none";
            statusMsg.style.display = "block";
            statusMsg.textContent = "ROUTING.md not found. Run Init to generate it from your current index.md.";
            initBtn.disabled = false;
            validateBtn.disabled = true;
            cleanBtn.disabled = true;
        };

        api.routingStatus().then((r: any) => {
            r.exists ? applyInitialized(r.content) : applyUninitialized();
        }).catch(() => {
            initBtn.disabled = true;
            validateBtn.disabled = true;
            cleanBtn.disabled = true;
            setResult("❌ Cannot reach Synthadoc server. Is it running?");
        });

        initBtn.onclick = async () => {
            initBtn.disabled = true;
            setResult("⏳ Initializing…");
            try {
                const r = await api.routingInit() as any;
                applyInitialized(r.content);
                setResult(`✅ ROUTING.md created — ${r.branches} branches, ${r.slugs} slugs.`);
            } catch (e: any) {
                initBtn.disabled = false;
                const msg = /409/.test(e.message) ? "ROUTING.md already exists. Delete it first to re-init."
                          : /400/.test(e.message) ? "index.md not found — run scaffold first."
                          : e.message ?? "Unexpected error.";
                setResult(`❌ ${msg}`);
            }
        };

        validateBtn.onclick = async () => {
            setResult("⏳ Validating…");
            try {
                const r = await api.routingValidate() as any;
                if (r.clean) {
                    setResult("✅ ROUTING.md is clean — no dangling slugs.");
                } else {
                    const n = r.dangling.length;
                    const rows = r.dangling
                        .map((d: any) => `&nbsp;&nbsp;[${d.branch}]&nbsp;&nbsp;[[${d.slug}]]`)
                        .join("<br>");
                    setResult(`⚠️ ${n} dangling slug${n === 1 ? "" : "s"} found:<br>`
                        + `<code style="font-size:12px;">${rows}</code>`);
                }
            } catch (e: any) {
                const msg = /404/.test(e.message) ? "ROUTING.md not found — run Init first."
                          : e.message ?? "Unexpected error.";
                setResult(`❌ ${msg}`);
            }
        };

        cleanBtn.onclick = async () => {
            setResult("⏳ Cleaning…");
            try {
                const r = await api.routingClean() as any;
                if (r.removed.length === 0) {
                    setResult("✅ ROUTING.md is clean — nothing to remove.");
                } else {
                    const n = r.removed.length;
                    const rows = r.removed
                        .map((d: any) => `&nbsp;&nbsp;[${d.branch}]&nbsp;&nbsp;[[${d.slug}]]`)
                        .join("<br>");
                    contentBox.textContent = r.content;
                    setResult(`✅ Removed ${n} dangling entr${n === 1 ? "y" : "ies"} from ROUTING.md:<br>`
                        + `<code style="font-size:12px;">${rows}</code><br>ROUTING.md updated.`);
                }
            } catch (e: any) {
                const msg = /404/.test(e.message) ? "ROUTING.md not found — run Init first."
                          : e.message ?? "Unexpected error.";
                setResult(`❌ ${msg}`);
            }
        };
    }

    onClose(): void {
        this.contentEl.empty();
    }
}

// ── Shared UI helper ─────────────────────────────────────────────────────────

function makeSegmented(
    parent: HTMLElement,
    options: { value: string; label: string }[],
    initial: string,
    onChange: (value: string) => void,
): { getValue: () => string; setValue: (v: string) => void } {
    const wrap = parent.createEl("div");
    wrap.style.cssText = "display:inline-flex;border:1px solid var(--background-modifier-border);"
        + "border-radius:6px;overflow:hidden;";

    let current = initial;
    const btns: Record<string, HTMLButtonElement> = {};

    const activate = (val: string) => {
        current = val;
        for (const [v, btn] of Object.entries(btns)) {
            const active = v === val;
            btn.style.background = active ? "var(--interactive-accent)" : "var(--background-primary)";
            btn.style.color = active ? "var(--text-on-accent)" : "var(--text-normal)";
            btn.style.fontWeight = active ? "600" : "400";
        }
    };

    for (const opt of options) {
        const btn = wrap.createEl("button", { text: opt.label }) as HTMLButtonElement;
        btn.style.cssText = "border:none;border-radius:0;padding:5px 14px;font-size:13px;cursor:pointer;transition:background 0.1s;";
        btns[opt.value] = btn;
        btn.onclick = () => {
            activate(opt.value);
            onChange(opt.value);
        };
    }

    activate(initial);
    return {
        getValue: () => current,
        setValue: (v: string) => activate(v),
    };
}

// ── StagingModal ─────────────────────────────────────────────────────────────

class StagingModal extends Modal {
    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(480px, 55vw, 760px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Staging Policy" });
        makeDraggable(modalEl, titleEl);

        const stateEl = contentEl.createEl("div");
        stateEl.style.cssText = "margin-bottom:16px;padding:10px 12px;border-radius:6px;"
            + "background:var(--background-secondary);font-size:13px;min-height:36px;";

        // Policy row
        const policyRow = contentEl.createEl("div");
        policyRow.style.cssText = "display:flex;align-items:center;gap:12px;margin-bottom:14px;";
        policyRow.createEl("span", { text: "Policy" }).style.cssText
            = "font-size:13px;font-weight:600;min-width:90px;";
        const policySeg = makeSegmented(
            policyRow,
            [
                { value: "off", label: "Off" },
                { value: "all", label: "All" },
                { value: "threshold", label: "Threshold" },
            ],
            "off",
            (val) => {
                confidenceRow.style.display = val === "threshold" ? "flex" : "none";
            },
        );

        // Confidence row (visible only when threshold)
        const confidenceRow = contentEl.createEl("div");
        confidenceRow.style.cssText = "display:none;align-items:center;gap:12px;margin-bottom:14px;";
        confidenceRow.createEl("span", { text: "Min confidence" }).style.cssText
            = "font-size:13px;font-weight:600;min-width:90px;";
        const confidenceSeg = makeSegmented(
            confidenceRow,
            [
                { value: "high", label: "High" },
                { value: "medium", label: "Medium" },
                { value: "low", label: "Low" },
            ],
            "high",
            () => {},
        );

        // Description
        const descEl = contentEl.createEl("div");
        descEl.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:14px;"
            + "display:grid;grid-template-columns:80px 1fr;gap:3px 10px;";
        descEl.innerHTML =
            `<strong>Off</strong><span>All new pages go directly to the wiki (default).</span>` +
            `<strong>All</strong><span>Every new page goes to staging — you review and promote manually.</span>` +
            `<strong>Threshold</strong><span>Pages whose confidence is below the minimum are staged for review.</span>`;

        // Action row
        const actionRow = contentEl.createEl("div");
        actionRow.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:12px;";
        const saveBtn = actionRow.createEl("button", { text: "Save" }) as HTMLButtonElement;
        saveBtn.style.cssText = "font-weight:bold;";

        const resultEl = contentEl.createEl("div");
        resultEl.style.cssText = "font-size:13px;min-height:22px;margin-bottom:12px;";
        const setResult = (html: string) => { resultEl.innerHTML = html; };

        // Footer link
        const footer = contentEl.createEl("div");
        footer.style.cssText = "border-top:1px solid var(--background-modifier-border);padding-top:10px;font-size:12px;";
        const candLink = footer.createEl("a", { text: "Candidate pages →" });
        candLink.style.cssText = "cursor:pointer;color:var(--link-color);";
        candLink.onclick = () => {
            this.close();
            setTimeout(() => (this.app as any).commands?.executeCommandById("synthadoc:synthadoc-candidates"), 150);
        };

        // Load current state
        const applyState = (policy: string, confMin: string) => {
            policySeg.setValue(policy);
            confidenceSeg.setValue(confMin || "high");
            confidenceRow.style.display = policy === "threshold" ? "flex" : "none";
            const labels: Record<string, string> = {
                off: "Staging is <strong>disabled</strong>. All new pages publish directly.",
                all: "Staging is <strong>enabled (all)</strong>. Every new page goes to staging.",
                threshold: `Staging is <strong>enabled (threshold)</strong>. Pages below <em>${confMin || "high"}</em> confidence are staged.`,
            };
            stateEl.innerHTML = labels[policy] ?? policy;
        };

        api.stagingPolicy().then((r: any) => {
            applyState(r.policy, r.confidence_min);
        }).catch(() => {
            setResult("❌ Cannot reach Synthadoc server. Is it running?");
            saveBtn.disabled = true;
        });

        saveBtn.onclick = async () => {
            saveBtn.disabled = true;
            setResult("⏳ Saving…");
            const policy = policySeg.getValue();
            const confMin = policy === "threshold" ? confidenceSeg.getValue() : undefined;
            try {
                const r = await api.stagingSetPolicy(policy, confMin) as any;
                applyState(r.policy, r.confidence_min);
                setResult(`✅ Policy updated to <strong>${r.policy}</strong>${r.policy === "threshold" ? ` (min confidence: ${r.confidence_min})` : ""}.`);
            } catch (e: any) {
                setResult(`❌ ${e.message ?? "Failed to save."}`);
            } finally {
                saveBtn.disabled = false;
            }
        };
    }

    onClose(): void {
        this.contentEl.empty();
    }
}

// ── CandidatesModal ───────────────────────────────────────────────────────────

const CAND_PAGE_SIZE = 30;

const CONF_BADGE: Record<string, string> = {
    high:   "background:#2d6a2d;color:#b6ffb6;",
    medium: "background:#7a6000;color:#fff3b0;",
    low:    "background:#7a2020;color:#ffb6b6;",
};

class CandidatesModal extends Modal {
    private _candidates: any[] = [];
    private _page = 0;
    private _selected: Set<string> = new Set();
    private _sortCol: "slug" | "title" | "confidence" | "created" = "confidence";
    private _sortAsc = true;

    private _sortedCandidates(): any[] {
        const CONF_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
        const col = this._sortCol;
        const dir = this._sortAsc ? 1 : -1;
        return [...this._candidates].sort((a, b) => {
            let av: any, bv: any;
            if (col === "confidence") {
                av = CONF_ORDER[a.confidence] ?? 3;
                bv = CONF_ORDER[b.confidence] ?? 3;
            } else {
                av = (a[col] ?? "").toString().toLowerCase();
                bv = (b[col] ?? "").toString().toLowerCase();
            }
            if (av < bv) return -dir;
            if (av > bv) return dir;
            // secondary: newest ingested first
            const ca = a.created ?? "";
            const cb = b.created ?? "";
            return ca < cb ? 1 : ca > cb ? -1 : 0;
        });
    }

    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(760px, 85vw, 1200px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Candidate Pages" });
        makeDraggable(modalEl, titleEl);

        const resultEl = contentEl.createEl("div");
        resultEl.style.cssText = "font-size:13px;min-height:22px;margin-bottom:8px;";
        const setResult = (html: string) => { resultEl.innerHTML = html; };

        // Top action bar
        const actionBar = contentEl.createEl("div");
        actionBar.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center;";

        const promoteSelBtn = actionBar.createEl("button", { text: "Promote Selected" }) as HTMLButtonElement;
        const discardSelBtn = actionBar.createEl("button", { text: "Discard Selected" }) as HTMLButtonElement;
        discardSelBtn.style.color = "var(--text-error)";

        // Table container
        const tableWrap = contentEl.createEl("div");
        tableWrap.style.cssText = "overflow-y:auto;max-height:50vh;margin-bottom:10px;"
            + "border:1px solid var(--background-modifier-border);border-radius:4px;";

        // Pagination row
        const pageRow = contentEl.createEl("div");
        pageRow.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:12px;font-size:12px;color:var(--text-muted);";
        const prevBtn = pageRow.createEl("button", { text: "← Prev" }) as HTMLButtonElement;
        const pageLabel = pageRow.createEl("span");
        const nextBtn = pageRow.createEl("button", { text: "Next →" }) as HTMLButtonElement;

        // Footer
        const footer = contentEl.createEl("div");
        footer.style.cssText = "border-top:1px solid var(--background-modifier-border);padding-top:10px;font-size:12px;";
        const stagingLink = footer.createEl("a", { text: "← Staging policy" });
        stagingLink.style.cssText = "cursor:pointer;color:var(--link-color);";
        stagingLink.onclick = () => {
            this.close();
            setTimeout(() => (this.app as any).commands?.executeCommandById("synthadoc:synthadoc-staging"), 150);
        };

        const CAND_COLS: { key: "slug" | "title" | "confidence" | "created"; label: string; align: string }[] = [
            { key: "slug",       label: "Slug",       align: "left" },
            { key: "title",      label: "Title",      align: "left" },
            { key: "confidence", label: "Confidence", align: "center" },
            { key: "created",    label: "Ingested",   align: "left" },
        ];

        const render = () => {
            tableWrap.empty();
            const sorted = this._sortedCandidates();
            const total = sorted.length;
            const totalPages = Math.max(1, Math.ceil(total / CAND_PAGE_SIZE));
            this._page = Math.min(this._page, totalPages - 1);
            const slice = sorted.slice(this._page * CAND_PAGE_SIZE, (this._page + 1) * CAND_PAGE_SIZE);

            prevBtn.disabled = this._page === 0;
            nextBtn.disabled = this._page >= totalPages - 1;
            pageRow.style.display = totalPages > 1 ? "flex" : "none";
            pageLabel.textContent = `Page ${this._page + 1} of ${totalPages} (${total} total)`;

            if (total === 0) {
                tableWrap.createEl("div", { text: "No candidates. All new pages are publishing directly." })
                    .style.cssText = "padding:20px;text-align:center;color:var(--text-muted);font-size:13px;";
                promoteSelBtn.disabled = true;
                discardSelBtn.disabled = true;
                return;
            }

            const table = tableWrap.createEl("table");
            table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;";

            const thead = table.createEl("thead");
            const hrow = thead.createEl("tr");
            hrow.style.cssText = "background:var(--background-secondary);";
            const thCheck = hrow.createEl("th");
            thCheck.style.cssText = "padding:6px 8px;width:32px;";
            const allCheckbox = thCheck.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            allCheckbox.title = "Select all on this page";

            for (const col of CAND_COLS) {
                const th = hrow.createEl("th");
                th.style.cssText = `padding:6px 8px;text-align:${col.align};cursor:pointer;user-select:none;white-space:nowrap;`;
                const isCurrent = this._sortCol === col.key;
                th.textContent = col.label + (isCurrent ? (this._sortAsc ? " ▲" : " ▼") : " ⇅");
                th.onclick = () => {
                    if (this._sortCol === col.key) {
                        this._sortAsc = !this._sortAsc;
                    } else {
                        this._sortCol = col.key;
                        // confidence: high first (asc in CONF_ORDER); ingested: newest first (desc); others: a-z
                        this._sortAsc = col.key !== "created";
                    }
                    this._page = 0;
                    render();
                };
            }

            const tbody = table.createEl("tbody");
            const rowCheckboxes: HTMLInputElement[] = [];

            for (const c of slice) {
                const tr = tbody.createEl("tr");
                tr.style.cssText = "border-top:1px solid var(--background-modifier-border);";
                tr.onmouseenter = () => { tr.style.background = "var(--background-modifier-hover)"; };
                tr.onmouseleave = () => { tr.style.background = ""; };

                const tdCheck = tr.createEl("td");
                tdCheck.style.cssText = "padding:6px 8px;text-align:center;";
                const cb = tdCheck.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                cb.checked = this._selected.has(c.slug);
                cb.onchange = () => {
                    cb.checked ? this._selected.add(c.slug) : this._selected.delete(c.slug);
                    updateSelBtns();
                    allCheckbox.indeterminate = rowCheckboxes.some(x => x.checked) && !rowCheckboxes.every(x => x.checked);
                    allCheckbox.checked = rowCheckboxes.every(x => x.checked);
                };
                rowCheckboxes.push(cb);

                tr.createEl("td", { text: c.slug }).style.cssText
                    = "padding:6px 8px;font-family:var(--font-monospace);font-size:12px;";
                tr.createEl("td", { text: c.title }).style.cssText = "padding:6px 8px;";

                const tdConf = tr.createEl("td");
                tdConf.style.cssText = "padding:6px 8px;text-align:center;";
                if (c.confidence) {
                    const badge = tdConf.createEl("span", { text: c.confidence });
                    badge.style.cssText = `border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;`
                        + (CONF_BADGE[c.confidence] ?? "background:var(--background-modifier-border);color:var(--text-normal);");
                }

                tr.createEl("td", { text: c.created ? c.created.slice(0, 10) : "—" })
                    .style.cssText = "padding:6px 8px;color:var(--text-muted);";
            }

            allCheckbox.checked = slice.length > 0 && slice.every(c => this._selected.has(c.slug));
            allCheckbox.onchange = () => {
                for (const c of slice) {
                    allCheckbox.checked ? this._selected.add(c.slug) : this._selected.delete(c.slug);
                }
                for (const cb of rowCheckboxes) cb.checked = allCheckbox.checked;
                updateSelBtns();
            };

            updateSelBtns();
        };

        const updateSelBtns = () => {
            const hasSel = this._selected.size > 0;
            promoteSelBtn.disabled = !hasSel;
            discardSelBtn.disabled = !hasSel;
        };

        const reload = async () => {
            setResult("⏳ Loading…");
            try {
                this._candidates = await api.candidates() as any[];
                this._selected.clear();
                setResult(`${this._candidates.length} candidate${this._candidates.length === 1 ? "" : "s"} awaiting review.`);
                render();
            } catch {
                setResult("❌ Cannot reach Synthadoc server. Is it running?");
                promoteSelBtn.disabled = true;
                discardSelBtn.disabled = true;
            }
        };

        prevBtn.onclick = () => { this._page--; render(); };
        nextBtn.onclick = () => { this._page++; render(); };

        promoteSelBtn.onclick = async () => {
            const slugs = [...this._selected];
            promoteSelBtn.disabled = true;
            setResult(`⏳ Promoting ${slugs.length} page${slugs.length === 1 ? "" : "s"}…`);
            const failed: string[] = [];
            for (const slug of slugs) {
                try { await api.candidatePromote(slug); }
                catch { failed.push(slug); }
            }
            const ok = slugs.length - failed.length;
            setResult(`✅ Promoted ${ok}${failed.length ? `; ❌ ${failed.length} failed: ${failed.join(", ")}` : ""}.`);
            await reload();
        };

        discardSelBtn.onclick = async () => {
            const slugs = [...this._selected];
            discardSelBtn.disabled = true;
            setResult(`⏳ Discarding ${slugs.length} page${slugs.length === 1 ? "" : "s"}…`);
            const failed: string[] = [];
            for (const slug of slugs) {
                try { await api.candidateDiscard(slug); }
                catch { failed.push(slug); }
            }
            const ok = slugs.length - failed.length;
            setResult(`✅ Discarded ${ok}${failed.length ? `; ❌ ${failed.length} failed: ${failed.join(", ")}` : ""}.`);
            await reload();
        };

        reload();
    }

    onClose(): void {
        this._candidates = [];
        this._selected.clear();
        this.contentEl.empty();
    }
}

// ── ContextModal ──────────────────────────────────────────────────────────────

const DEFAULT_TOKEN_BUDGET = 4000;

function renderContextPackMarkdown(pack: any): string {
    const now = new Date().toISOString().slice(0, 19);
    const omittedNote = pack.omitted?.length
        ? ` | Omitted: ${pack.omitted.length} page(s) (budget exceeded)`
        : "";
    const lines: string[] = [
        `# Context Pack: ${pack.goal}`,
        `Generated: ${now}`,
        `Token budget: ${pack.token_budget} | Used: ${pack.tokens_used}${omittedNote}`,
        "",
        "---",
        "",
    ];
    for (const p of pack.pages ?? []) {
        lines.push(`## [[${p.slug}]] — relevance: ${Number(p.relevance).toFixed(2)}`);
        lines.push(`> ${p.excerpt}`);
        lines.push(
            `Source: \`${p.source}\` | Confidence: ${p.confidence}` +
            (p.tags?.length ? ` | Tags: ${(p.tags as string[]).join(", ")}` : ""),
        );
        lines.push("");
    }
    if (pack.omitted?.length) {
        lines.push("---", "", "## Omitted — token budget exceeded");
        for (const p of pack.omitted) {
            lines.push(`- [[${p.slug}]] — ~${p.estimated_tokens} tokens`);
        }
    }
    return lines.join("\n");
}

class ContextModal extends Modal {
    private _result = "";

    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(560px, 65vw, 900px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Context Pack" });
        makeDraggable(modalEl, titleEl);

        // Description
        const desc = contentEl.createEl("p");
        desc.style.cssText = "font-size:13px;color:var(--text-muted);margin-bottom:14px;line-height:1.5;";
        desc.textContent =
            "A context pack assembles the most relevant wiki pages into a single cited Markdown " +
            "document within a token budget. Use it to ground an external LLM prompt, save evidence " +
            "alongside a draft you are writing, or pipe it into another tool.";

        // Goal input
        const goalLabel = contentEl.createEl("div", { text: "Goal / question" });
        goalLabel.style.cssText = "font-size:12px;font-weight:600;margin-bottom:4px;";
        const goalInput = contentEl.createEl("textarea") as HTMLTextAreaElement;
        goalInput.placeholder = "e.g. early computing pioneers";
        goalInput.rows = 3;
        goalInput.style.cssText = "width:100%;box-sizing:border-box;resize:vertical;font-size:13px;"
            + "margin-bottom:12px;padding:6px 8px;border-radius:4px;"
            + "border:1px solid var(--background-modifier-border);background:var(--background-primary);";

        // Token budget row
        const budgetRow = contentEl.createEl("div");
        budgetRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:14px;";
        budgetRow.createEl("span", { text: "Token budget" }).style.cssText
            = "font-size:12px;font-weight:600;white-space:nowrap;";
        const budgetInput = budgetRow.createEl("input") as HTMLInputElement;
        budgetInput.type = "number";
        budgetInput.min = "100";
        budgetInput.max = "32000";
        budgetInput.step = "100";
        budgetInput.value = String(DEFAULT_TOKEN_BUDGET);
        budgetInput.style.cssText = "width:90px;padding:4px 6px;font-size:13px;border-radius:4px;"
            + "border:1px solid var(--background-modifier-border);background:var(--background-primary);";
        budgetRow.createEl("span", { text: "tokens" }).style.cssText
            = "font-size:12px;color:var(--text-muted);";

        // Build button + status
        const buildRow = contentEl.createEl("div");
        buildRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:14px;";
        const buildBtn = buildRow.createEl("button", { text: "Build Context Pack" }) as HTMLButtonElement;
        buildBtn.style.cssText = "font-weight:bold;";
        const statusEl = buildRow.createEl("span");
        statusEl.style.cssText = "font-size:12px;color:var(--text-muted);";

        // Result section (hidden until first build)
        const resultSection = contentEl.createEl("div");
        resultSection.style.display = "none";

        const divider = resultSection.createEl("hr");
        divider.style.cssText = "margin:0 0 10px;border:none;border-top:1px solid var(--background-modifier-border);";

        const resultMeta = resultSection.createEl("div");
        resultMeta.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:6px;";

        const resultArea = resultSection.createEl("textarea") as HTMLTextAreaElement;
        resultArea.readOnly = true;
        resultArea.rows = 22;
        resultArea.style.cssText = "width:100%;box-sizing:border-box;resize:vertical;font-size:12px;"
            + "font-family:var(--font-monospace);padding:8px;border-radius:4px;"
            + "border:1px solid var(--background-modifier-border);background:var(--background-secondary);"
            + "margin-bottom:10px;";

        // Action buttons row
        const actionRow = resultSection.createEl("div");
        actionRow.style.cssText = "display:flex;gap:8px;align-items:center;";

        const copyBtn = actionRow.createEl("button", { text: "Copy to Clipboard" }) as HTMLButtonElement;
        const saveBtn = actionRow.createEl("button", { text: "Save as .md" }) as HTMLButtonElement;
        const copyNote = actionRow.createEl("span");
        copyNote.style.cssText = "font-size:12px;color:var(--text-muted);";

        // Copy handler
        copyBtn.onclick = async () => {
            try {
                await navigator.clipboard.writeText(this._result);
                copyNote.textContent = "✅ Copied!";
                setTimeout(() => { copyNote.textContent = ""; }, 2500);
            } catch {
                copyNote.textContent = "❌ Copy failed — select and copy manually.";
            }
        };

        // Save as handler — uses Electron native dialog so status shows only after user confirms
        saveBtn.onclick = async () => {
            const slug = goalInput.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40) || "context-pack";
            const filename = `${slug}.md`;
            saveBtn.disabled = true;
            copyNote.textContent = "💾 Saving…";
            try {
                const electron = (window as any).require("electron");
                const nodefs = (window as any).require("fs");
                const nodepath = (window as any).require("path");
                const result = await electron.remote.dialog.showSaveDialog({
                    defaultPath: filename,
                    filters: [{ name: "Markdown", extensions: ["md"] }],
                });
                if (!result.canceled && result.filePath) {
                    await nodefs.promises.writeFile(result.filePath, this._result, "utf-8");
                    copyNote.textContent = `✅ Saved as ${nodepath.basename(result.filePath)}`;
                    setTimeout(() => { copyNote.textContent = ""; }, 3000);
                } else {
                    copyNote.textContent = "";
                }
            } catch {
                // Fallback for non-Electron environments
                const blob = new Blob([this._result], { type: "text/markdown;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                copyNote.textContent = `✅ Saved as ${filename}`;
                setTimeout(() => { copyNote.textContent = ""; }, 3000);
            } finally {
                saveBtn.disabled = false;
            }
        };

        // Build handler
        const runBuild = async () => {
            const goal = goalInput.value.trim();
            if (!goal) {
                statusEl.textContent = "⚠ Enter a goal or question first.";
                return;
            }
            const budget = Math.max(100, parseInt(budgetInput.value, 10) || DEFAULT_TOKEN_BUDGET);
            budgetInput.value = String(budget);

            buildBtn.disabled = true;
            statusEl.textContent = "⏳ Building…";
            resultSection.style.display = "none";

            try {
                const pack = await api.contextBuild(goal, budget) as any;
                this._result = renderContextPackMarkdown(pack);
                resultArea.value = this._result;
                resultMeta.textContent =
                    `${pack.pages?.length ?? 0} page(s) included · ${pack.tokens_used} / ${pack.token_budget} tokens used`
                    + (pack.omitted?.length ? ` · ${pack.omitted.length} omitted` : "");
                resultSection.style.display = "block";
                statusEl.textContent = "";
                copyNote.textContent = "";
            } catch (e: any) {
                statusEl.textContent = `❌ ${e.message ?? "Failed to build context pack."}`;
            } finally {
                buildBtn.disabled = false;
            }
        };

        buildBtn.onclick = runBuild;

        // Ctrl/Cmd+Enter submits
        goalInput.addEventListener("keydown", (e: KeyboardEvent) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                runBuild();
            }
        });

        goalInput.focus();
    }

    onClose(): void {
        this._result = "";
        this.contentEl.empty();
    }
}

const RAW_SOURCES_DIR = "raw_sources";

class SourceViewerModal extends Modal {
    constructor(
        app: App,
        private filename: string,
        private lineStart: number,
        private lineEnd: number,
        private wikiRoot: string,
    ) { super(app); }

    onOpen() {
        this.modalEl.style.width = "clamp(700px, 75vw, 1060px)";

        // Draggable title bar (same pattern as ProvenanceModal).
        const container = this.modalEl;
        const bar = document.createElement("div");
        bar.style.cssText = [
            "display:flex", "align-items:center", "justify-content:space-between",
            "padding:10px 16px", "border-bottom:1px solid var(--background-modifier-border)",
            "cursor:grab", "user-select:none", "-webkit-user-select:none", "flex-shrink:0",
        ].join(";");
        const titleSpan = document.createElement("span");
        titleSpan.textContent = `${this.filename} — lines ${this.lineStart}–${this.lineEnd}`;
        titleSpan.style.cssText = "font-weight:600;font-size:14px";
        bar.appendChild(titleSpan);
        const hint = document.createElement("span");
        hint.textContent = "drag to move";
        hint.style.cssText = "font-size:10px;color:var(--text-faint)";
        bar.appendChild(hint);
        container.insertBefore(bar, this.contentEl);
        this.contentEl.style.cssText += ";user-select:text;-webkit-user-select:text";
        bar.addEventListener("mousedown", (e: MouseEvent) => {
            e.preventDefault();
            const rect = container.getBoundingClientRect();
            container.style.position = "fixed";
            container.style.left = rect.left + "px";
            container.style.top = rect.top + "px";
            container.style.transform = "none";
            container.style.margin = "0";
            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;
            bar.style.cursor = "grabbing";
            const onMove = (ev: MouseEvent) => {
                container.style.left = (ev.clientX - offsetX) + "px";
                container.style.top = (ev.clientY - offsetY) + "px";
            };
            const onUp = () => {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
                bar.style.cursor = "grab";
            };
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
        });

        const fs = (window as any).require("fs") as typeof import("fs");
        const { contentEl } = this;
        contentEl.empty();

        const CONTEXT_LINES = 5;
        const extractedFilename = this.filename.includes(".")
            ? this.filename.replace(/\.[^.]+$/, ".txt")
            : this.filename + ".txt";
        const extractedPath = `${this.wikiRoot}/.synthadoc/extracted/${extractedFilename}`;
        const rawSourcePath = `${this.wikiRoot}/${RAW_SOURCES_DIR}/${this.filename}`;
        const stem = this.filename.replace(/\.[^.]+$/, "");
        const pagemapPath = `${this.wikiRoot}/.synthadoc/extracted/${stem}.pdf.pagemap`;

        // Plain-text source types can be read directly from raw_sources/ as a fallback.
        // Binary types (xlsx, docx, png, …) cannot — they need a sidecar that the
        // ingest pipeline only writes for PDFs today.
        const TEXT_EXTENSIONS = new Set(["md", "txt", "csv"]);
        const dotIdx = this.filename.lastIndexOf(".");
        // Files with no extension (bare slugs) are treated as plain text.
        const ext = dotIdx >= 0 ? this.filename.slice(dotIdx + 1).toLowerCase() : "";
        const isText = TEXT_EXTENSIONS.has(ext) || ext === "";
        const findInSubdirs = (dir: string, name: string): string | null => {
            if (!fs.existsSync(dir)) return null;
            for (const entry of fs.readdirSync(dir, { withFileTypes: true }) as import("fs").Dirent[]) {
                const child = `${dir}/${entry.name}`;
                if (entry.isDirectory()) {
                    const found = findInSubdirs(child, name);
                    if (found) return found;
                } else if (entry.name === name) {
                    return child;
                }
            }
            return null;
        };
        const resolvePath = (): string => {
            if (fs.existsSync(extractedPath)) return extractedPath;
            if (isText && fs.existsSync(rawSourcePath)) return rawSourcePath;
            if (isText) {
                const found = findInSubdirs(`${this.wikiRoot}/${RAW_SOURCES_DIR}`, this.filename);
                if (found) return found;
            }
            throw new Error("no-sidecar");
        };

        try {
            const text: string = fs.readFileSync(resolvePath(), "utf-8");
            const lines = text.split("\n");
            const start = Math.max(0, this.lineStart - 1 - CONTEXT_LINES);
            const end = Math.min(lines.length, this.lineEnd + CONTEXT_LINES);
            const pre = contentEl.createEl("pre");
            pre.style.cssText = "overflow:auto;max-height:60vh;font-size:12px;line-height:1.5";
            for (let i = start; i < end; i++) {
                const lineNum = i + 1;
                const span = pre.createEl("div");
                span.textContent = `${String(lineNum).padStart(4)} ${lines[i]}`;
                const inRange = lineNum >= this.lineStart && lineNum <= this.lineEnd;
                span.style.cssText = inRange
                    ? "background:var(--background-modifier-hover);font-weight:600"
                    : "color:var(--text-muted)";
            }

            // PDF jump button — only shown when content is past page 1 (page 1 is the default).
            try {
                const pagemap: Record<string, number> = JSON.parse(fs.readFileSync(pagemapPath, "utf-8"));
                const pdfPage = this.resolvePagemap(pagemap, this.lineStart);
                if (pdfPage > 1) {
                    const pdfName = this.filename.endsWith(".txt")
                        ? this.filename.replace(/\.txt$/, ".pdf")
                        : this.filename;
                    const btn = contentEl.createEl("button", { text: `Open PDF at page ${pdfPage} →` });
                    btn.style.cssText = "margin-top:12px;cursor:pointer";
                    btn.addEventListener("click", () => {
                        this.close();
                        this.app.workspace.openLinkText(`${RAW_SOURCES_DIR}/${pdfName}#page=${pdfPage}`, "", true);
                    });
                    contentEl.createEl("p", {
                        text: "Line numbers refer to extracted text. The PDF page shown is the closest match.",
                    }).style.cssText = "font-size:11px;color:var(--text-muted);margin-top:4px";
                }
            } catch { /* no pagemap — PDF jump not available */ }
        } catch {
            const msg = isText
                ? `Could not read source file for ${this.filename}.`
                : `Preview not available for .${ext} files. Open the original in raw_sources/ to view its content.`;
            contentEl.createEl("p", { text: msg })
                .style.cssText = "color:var(--text-error)";
        }
    }

    private resolvePagemap(pagemap: Record<string, number>, lineStart: number): number {
        const keys = Object.keys(pagemap).map(Number).sort((a, b) => a - b);
        let page = 1;
        for (const k of keys) {
            if (k <= lineStart) page = pagemap[String(k)];
            else break;
        }
        return page;
    }

    onClose() { this.contentEl.empty(); }
}

const PROVENANCE_PAGE_SIZE = 50;

class ProvenanceModal extends Modal {
    private filter = "";
    private sortCol = "ingested_at";
    private sortAsc = false;
    private page = 0;
    private allRows: Record<string, unknown>[] = [];
    private total = 0;
    private tableWrap: HTMLElement | null = null;
    private pagerWrap: HTMLElement | null = null;

    constructor(app: App, private serverUrl: string, private wikiRoot: string, private initialSlug: string = "") {
        super(app);
    }

    async onOpen() {
        this.modalEl.style.width = "clamp(900px, 82vw, 1200px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        this.filter = this.initialSlug;
        this.setupTitleBar();
        await this.load();
        this.renderAll();
    }

    // Inserts a draggable title bar above contentEl and enables text selection.
    private setupTitleBar() {
        const container = this.modalEl;

        const bar = document.createElement("div");
        bar.style.cssText = [
            "display:flex",
            "align-items:center",
            "justify-content:space-between",
            "padding:10px 16px",
            "border-bottom:1px solid var(--background-modifier-border)",
            "cursor:grab",
            "user-select:none",
            "-webkit-user-select:none",
            "flex-shrink:0",
        ].join(";");

        const title = document.createElement("span");
        title.textContent = "Page Provenance";
        title.style.cssText = "font-weight:600;font-size:14px";
        bar.appendChild(title);

        const hint = document.createElement("span");
        hint.textContent = "drag to move";
        hint.style.cssText = "font-size:10px;color:var(--text-faint)";
        bar.appendChild(hint);

        container.insertBefore(bar, this.contentEl);

        // Allow all text inside the modal body to be selected and copied.
        this.contentEl.style.cssText += ";user-select:text;-webkit-user-select:text";

        // Drag-to-move: capture current position on mousedown, then track movement.
        bar.addEventListener("mousedown", (e: MouseEvent) => {
            e.preventDefault();
            const rect = container.getBoundingClientRect();
            // Switch from Obsidian's centered transform to explicit fixed positioning.
            container.style.position = "fixed";
            container.style.left = rect.left + "px";
            container.style.top = rect.top + "px";
            container.style.transform = "none";
            container.style.margin = "0";

            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;
            bar.style.cursor = "grabbing";

            const onMove = (ev: MouseEvent) => {
                container.style.left = (ev.clientX - offsetX) + "px";
                container.style.top = (ev.clientY - offsetY) + "px";
            };
            const onUp = () => {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
                bar.style.cursor = "grab";
            };
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
        });
    }

    private async load() {
        const params = new URLSearchParams({
            limit: String(PROVENANCE_PAGE_SIZE),
            offset: String(this.page * PROVENANCE_PAGE_SIZE),
            sort: this.sortCol,
            order: this.sortAsc ? "asc" : "desc",
        });
        if (this.filter) params.set("page", this.filter);
        try {
            const resp = await fetch(`${this.serverUrl}/provenance/citations?${params}`);
            const data = await resp.json() as { citations: Record<string, unknown>[]; total: number };
            this.allRows = data.citations || [];
            this.total = data.total || 0;
        } catch {
            this.allRows = [];
            this.total = 0;
        }
    }

    private renderAll() {
        const { contentEl } = this;
        contentEl.empty();
        contentEl.style.cssText = "display:flex;flex-direction:column;height:70vh";

        // Description
        const desc = contentEl.createEl("p", {
            text: "Every citation recorded during ingest — which wiki page claims what, sourced from which file and line range. Click any row to view the highlighted source lines.",
        });
        desc.style.cssText = "font-size:12px;color:var(--text-muted);margin:0 0 10px 0;flex-shrink:0";

        // Filter bar
        const filterRow = contentEl.createDiv({ cls: "synthadoc-prov-filter" });
        filterRow.style.cssText = "display:flex;gap:8px;margin-bottom:12px;flex-shrink:0";
        const inputWrap = filterRow.createDiv();
        inputWrap.style.cssText = "position:relative;flex:1;display:flex;align-items:center";
        const input = inputWrap.createEl("input", { type: "text", placeholder: "Filter by slug or source…" });
        input.value = this.filter;
        input.style.cssText = "width:100%;box-sizing:border-box;padding:4px 26px 4px 8px";
        const clearBtn = inputWrap.createEl("span", { text: "×" });
        clearBtn.style.cssText = "position:absolute;right:7px;cursor:pointer;color:var(--text-muted);font-size:16px;line-height:1;display:" + (this.filter ? "block" : "none");
        clearBtn.addEventListener("click", async () => {
            this.filter = "";
            input.value = "";
            clearBtn.style.display = "none";
            this.page = 0;
            await this.load();
            this.renderTable();
            this.renderPager();
        });
        input.addEventListener("input", async () => {
            this.filter = input.value;
            clearBtn.style.display = input.value ? "block" : "none";
            this.page = 0;
            await this.load();
            this.renderTable();
            this.renderPager();
        });

        const refreshBtn = filterRow.createEl("button", { text: "↻ Refresh" });
        refreshBtn.addEventListener("click", async () => {
            await this.load();
            this.renderTable();
            this.renderPager();
        });

        // Table wrapper — scrollable, grows to fill available space
        this.tableWrap = contentEl.createDiv();
        this.tableWrap.style.cssText = "flex:1;overflow:auto;min-height:0";
        this.renderTable();

        // Pager wrapper — pinned outside scroll area
        this.pagerWrap = contentEl.createDiv();
        this.pagerWrap.style.cssText = "flex-shrink:0";
        this.renderPager();
    }

    private renderTable() {
        if (!this.tableWrap) return;
        this.tableWrap.empty();
        if (this.allRows.length === 0) {
            this.tableWrap.createEl("p", { text: "No citations found." })
                .style.cssText = "color:var(--text-muted)";
            return;
        }
        const table = this.tableWrap.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;user-select:text;-webkit-user-select:text";

        const cols: { key: string; label: string; sortable: boolean }[] = [
            { key: "page_slug", label: "Page", sortable: true },
            { key: "claim_excerpt", label: "Claim", sortable: false },
            { key: "source_file", label: "Source", sortable: true },
            { key: "lines", label: "Lines", sortable: false },
            { key: "ingested_at", label: "Ingested", sortable: true },
        ];
        const thead = table.createEl("thead");
        const headerRow = thead.createEl("tr");
        for (const col of cols) {
            const th = headerRow.createEl("th", { text: col.label });
            th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border);user-select:none;-webkit-user-select:none";
            if (col.sortable) {
                th.style.cursor = "pointer";
                const isCurrent = this.sortCol === col.key;
                if (isCurrent) th.textContent += this.sortAsc ? " ↑" : " ↓";
                th.addEventListener("click", async () => {
                    if (this.sortCol === col.key) this.sortAsc = !this.sortAsc;
                    else { this.sortCol = col.key; this.sortAsc = true; }
                    await this.load();
                    this.renderTable();
                });
            }
        }
        const tbody = table.createEl("tbody");
        for (const row of this.allRows) {
            const tr = tbody.createEl("tr");
            tr.style.cssText = "border-bottom:1px solid var(--background-modifier-border-focus);cursor:pointer";
            tr.addEventListener("mouseenter", () => { tr.style.background = "var(--background-modifier-hover)"; });
            tr.addEventListener("mouseleave", () => { tr.style.background = ""; });
            const lineStart = row.line_start as number | undefined;
            const lineEnd = row.line_end as number | undefined;
            const sourceFile = String(row.source_file || "");
            tr.addEventListener("click", () => {
                if (window.getSelection()?.toString()) return;
                if (sourceFile && lineStart != null && lineEnd != null)
                    new SourceViewerModal(this.app, sourceFile, lineStart, lineEnd, this.wikiRoot).open();
            });
            const cells = [
                String(row.page_slug || ""),
                String(row.claim_excerpt || "").slice(0, 60),
                sourceFile,
                lineStart != null && lineEnd != null ? `${lineStart}-${lineEnd}` : "",
                String(row.ingested_at || "").slice(0, 16),
            ];
            for (const cell of cells) {
                const td = tr.createEl("td", { text: cell });
                td.style.cssText = "padding:4px 8px;color:var(--text-normal);user-select:text;-webkit-user-select:text";
            }
        }
    }

    private renderPager() {
        if (!this.pagerWrap) return;
        this.pagerWrap.empty();
        const totalPages = Math.ceil(this.total / PROVENANCE_PAGE_SIZE);
        if (totalPages <= 1) return;
        this.pagerWrap.style.cssText = "display:flex;gap:8px;margin-top:8px;align-items:center";
        const prev = this.pagerWrap.createEl("button", { text: "← Previous" });
        prev.disabled = this.page === 0;
        prev.addEventListener("click", async () => { this.page--; await this.load(); this.renderTable(); this.renderPager(); });
        this.pagerWrap.createEl("span", {
            text: `Page ${this.page + 1} of ${totalPages} (${this.total} total)`,
        });
        const next = this.pagerWrap.createEl("button", { text: "Next →" });
        next.disabled = this.page >= totalPages - 1;
        next.addEventListener("click", async () => { this.page++; await this.load(); this.renderTable(); this.renderPager(); });
    }

    onClose() { this.contentEl.empty(); }
}

// ── Lifecycle constants ───────────────────────────────────────────────────────

const LifecycleState = {
    DRAFT:        "draft",
    ACTIVE:       "active",
    CONTRADICTED: "contradicted",
    STALE:        "stale",
    ARCHIVED:     "archived",
    ORDERED: ["active", "draft", "stale", "contradicted", "archived"] as const,
    ALL: ["draft", "active", "contradicted", "stale", "archived"] as const,
} as const;

const TriggerSource = {
    INGEST:      "ingest",
    LINT:        "lint",
    USER:        "user",
    MANUAL_EDIT: "manual_edit",
} as const;

// ── ReasonModal ───────────────────────────────────────────────────────────────

class ReasonModal extends Modal {
    private reason = "";
    constructor(app: App, private label: string, private onConfirm: (r: string) => void) {
        super(app);
    }
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        contentEl.createEl("h3", { text: this.label });
        const input = contentEl.createEl("input", { type: "text" }) as HTMLInputElement;
        input.style.cssText = "width:100%;margin:8px 0 12px 0;padding:4px 8px";
        input.placeholder = "Reason (required)";
        input.addEventListener("input", () => { this.reason = input.value; });
        const row = contentEl.createDiv();
        row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
        const cancel = row.createEl("button", { text: "Cancel" });
        cancel.addEventListener("click", () => this.close());
        const confirm = row.createEl("button", { text: "Confirm" }) as HTMLButtonElement;
        confirm.style.cssText = "background:var(--interactive-accent);color:var(--text-on-accent)";
        confirm.addEventListener("click", () => {
            if (!this.reason.trim()) { input.style.border = "1px solid red"; return; }
            this.onConfirm(this.reason.trim());
            this.close();
        });
        setTimeout(() => input.focus(), 50);
    }
    onClose() { this.contentEl.empty(); }
}

// ── LifecycleModal ────────────────────────────────────────────────────────────

const LIFECYCLE_PAGE_SIZE = 20;

const LIFECYCLE_STATE_COLORS: Record<string, string> = {
    [LifecycleState.DRAFT]:        "background:#7a4f00;color:#ffd880",
    [LifecycleState.ACTIVE]:       "background:#1a4a1a;color:#80ff80",
    [LifecycleState.CONTRADICTED]: "background:#5a0000;color:#ffb0b0",
    [LifecycleState.STALE]:        "background:#5a5a00;color:#ffff80",
    [LifecycleState.ARCHIVED]:     "background:#3a3a3a;color:#cccccc",
};

const ALLOWED_TRANSITIONS: Record<string, string[]> = {
    [LifecycleState.DRAFT]:        [LifecycleState.ACTIVE, LifecycleState.ARCHIVED],
    [LifecycleState.ACTIVE]:       [LifecycleState.ARCHIVED],
    [LifecycleState.CONTRADICTED]: [LifecycleState.ARCHIVED],
    [LifecycleState.STALE]:        [LifecycleState.DRAFT, LifecycleState.ARCHIVED],
    [LifecycleState.ARCHIVED]:     [LifecycleState.DRAFT],
};

const ALL_LIFECYCLE_STATES = [...LifecycleState.ALL];

class LifecycleModal extends Modal {
    private _activeTab: "states" | "audit" = "states";
    // Tab 1 — current page states
    private _page = 0;
    private _pages: any[] = [];
    private _checkedStates: Set<string>;
    private _sortCol = "slug";
    private _sortAsc = true;
    private _tableWrap: HTMLElement | null = null;
    private _pagerWrap: HTMLElement | null = null;
    private _tab1Content: HTMLElement | null = null;
    // Tab 2 — audit log
    private _auditPage = 0;
    private _auditEvents: any[] = [];
    private _auditSlugFilter = "";
    private _auditStateFilter = "";
    private _auditSortCol = "timestamp";
    private _auditSortAsc = false;
    private _auditTableWrap: HTMLElement | null = null;
    private _auditPagerWrap: HTMLElement | null = null;
    private _tab2Content: HTMLElement | null = null;

    constructor(
        app: App,
        private wikiRoot: string,
        private serverUrl: string,
        private initialFilter?: string,
    ) {
        super(app);
        this._checkedStates = new Set(
            initialFilter ? [initialFilter] : ALL_LIFECYCLE_STATES
        );
    }

    async onOpen() {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(1000px, 80vw, 1200px)";
        modalEl.style.height = "75vh";
        contentEl.style.cssText = "display:flex;flex-direction:column;height:100%";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Manage Page Lifecycle" });
        makeDraggable(modalEl, titleEl);

        // Tab bar
        const TAB_INACTIVE = "padding:6px 18px;font-size:13px;cursor:pointer;background:none;border:none;border-bottom:2px solid transparent;color:var(--text-muted)";
        const TAB_ACTIVE   = "padding:6px 18px;font-size:13px;cursor:pointer;background:none;border:none;border-bottom:2px solid var(--interactive-accent);color:var(--text-normal);font-weight:600";
        const tabBar = contentEl.createEl("div");
        tabBar.style.cssText = "display:flex;border-bottom:1px solid var(--background-modifier-border);margin-bottom:10px;flex-shrink:0";
        const tab1Btn = tabBar.createEl("button", { text: "Current States" }) as HTMLButtonElement;
        tab1Btn.style.cssText = TAB_ACTIVE;
        const tab2Btn = tabBar.createEl("button", { text: "Audit Log" }) as HTMLButtonElement;
        tab2Btn.style.cssText = TAB_INACTIVE;

        // Two content areas
        this._tab1Content = contentEl.createDiv();
        this._tab1Content.style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0";
        this._tab2Content = contentEl.createDiv();
        this._tab2Content.style.cssText = "display:none;flex-direction:column;flex:1;min-height:0";

        tab1Btn.addEventListener("click", () => {
            this._activeTab = "states";
            tab1Btn.style.cssText = TAB_ACTIVE;
            tab2Btn.style.cssText = TAB_INACTIVE;
            this._tab1Content!.style.display = "flex";
            this._tab2Content!.style.display = "none";
        });
        tab2Btn.addEventListener("click", async () => {
            this._activeTab = "audit";
            tab2Btn.style.cssText = TAB_ACTIVE;
            tab1Btn.style.cssText = TAB_INACTIVE;
            this._tab1Content!.style.display = "none";
            this._tab2Content!.style.display = "flex";
            if (this._auditEvents.length === 0) await this._fetchAudit();
        });

        // ── Tab 1 content ──────────────────────────────────────────────
        const tab1 = this._tab1Content;

        const filterBar = tab1.createEl("div");
        filterBar.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:10px;flex-shrink:0";
        filterBar.createEl("span", { text: "Filter:" }).style.cssText = "font-size:12px;font-weight:600";
        for (const state of ALL_LIFECYCLE_STATES) {
            const lbl = filterBar.createEl("label");
            lbl.style.cssText = "display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer;user-select:none";
            const cb = lbl.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            cb.checked = this._checkedStates.has(state);
            const chip = lbl.createEl("span", { text: state });
            chip.style.cssText = `border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;`
                + (LIFECYCLE_STATE_COLORS[state] ?? "");
            cb.onchange = () => {
                if (cb.checked) this._checkedStates.add(state);
                else this._checkedStates.delete(state);
                this._page = 0;
                this._renderAll();
            };
        }
        const refreshBtn = filterBar.createEl("button", { text: "↻ Refresh" }) as HTMLButtonElement;
        refreshBtn.style.cssText = "margin-left:auto;font-size:12px;padding:2px 10px";
        refreshBtn.addEventListener("click", async () => {
            refreshBtn.disabled = true;
            refreshBtn.textContent = "↻ Refreshing…";
            await this._fetchAndRender();
            refreshBtn.disabled = false;
            refreshBtn.textContent = "↻ Refresh";
        });

        this._tableWrap = tab1.createDiv();
        this._tableWrap.style.cssText = "flex:1;overflow:auto;min-height:0;border:1px solid var(--background-modifier-border);border-radius:4px";

        this._pagerWrap = tab1.createDiv();
        this._pagerWrap.style.cssText = "flex-shrink:0;display:flex;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--text-muted)";

        await this._fetchAndRender();

        // ── Tab 2 content ──────────────────────────────────────────────
        const tab2 = this._tab2Content;

        const auditFilterBar = tab2.createEl("div");
        auditFilterBar.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:10px;flex-shrink:0";

        const slugInput = auditFilterBar.createEl("input", { type: "text" }) as HTMLInputElement;
        slugInput.placeholder = "Search by slug…";
        slugInput.style.cssText = "width:220px;font-size:12px;padding:3px 8px";
        slugInput.addEventListener("input", () => {
            this._auditSlugFilter = slugInput.value.trim();
            this._auditPage = 0;
            this._renderAuditAll();
        });

        const stateSelect = auditFilterBar.createEl("select") as HTMLSelectElement;
        stateSelect.style.cssText = "font-size:12px;padding:3px 8px";
        stateSelect.createEl("option", { text: "All states", value: "" });
        for (const s of ALL_LIFECYCLE_STATES) {
            stateSelect.createEl("option", { text: s, value: s });
        }
        stateSelect.addEventListener("change", () => {
            this._auditStateFilter = stateSelect.value;
            this._auditPage = 0;
            this._renderAuditAll();
        });

        const auditRefreshBtn = auditFilterBar.createEl("button", { text: "↻ Refresh" }) as HTMLButtonElement;
        auditRefreshBtn.style.cssText = "margin-left:auto;font-size:12px;padding:2px 10px";
        auditRefreshBtn.addEventListener("click", async () => {
            auditRefreshBtn.disabled = true;
            auditRefreshBtn.textContent = "↻ Refreshing…";
            this._auditEvents = [];
            await this._fetchAudit();
            auditRefreshBtn.disabled = false;
            auditRefreshBtn.textContent = "↻ Refresh";
        });

        this._auditTableWrap = tab2.createDiv();
        this._auditTableWrap.style.cssText = "flex:1;overflow:auto;min-height:0;border:1px solid var(--background-modifier-border);border-radius:4px";

        this._auditPagerWrap = tab2.createDiv();
        this._auditPagerWrap.style.cssText = "flex-shrink:0;display:flex;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--text-muted)";
    }

    private async _fetchAndRender() {
        try {
            const result = await api.lifecyclePages() as any;
            this._pages = result.pages ?? [];
        } catch {
            this._pages = [];
        }
        this._renderAll();
    }

    private async _fetchAudit() {
        try {
            const result = await api.lifecycleEvents({ limit: 1000 }) as any;
            this._auditEvents = result.events ?? [];
        } catch {
            this._auditEvents = [];
        }
        this._renderAuditAll();
    }

    private _filteredPages(): any[] {
        return this._pages.filter(p => this._checkedStates.has(p.state ?? ""));
    }

    private _sortedPages(pages: any[]): any[] {
        const col = this._sortCol;
        const dir = this._sortAsc ? 1 : -1;
        return [...pages].sort((a, b) => {
            const av: string = a[col] ?? "";
            const bv: string = b[col] ?? "";
            return av < bv ? -dir : av > bv ? dir : 0;
        });
    }

    private _filteredAuditEvents(): any[] {
        return this._auditEvents.filter(ev => {
            if (this._auditSlugFilter && !String(ev.slug ?? "").toLowerCase().includes(this._auditSlugFilter.toLowerCase())) return false;
            if (this._auditStateFilter && ev.to_state !== this._auditStateFilter) return false;
            return true;
        });
    }

    private _sortedAuditEvents(events: any[]): any[] {
        const col = this._auditSortCol;
        const dir = this._auditSortAsc ? 1 : -1;
        return [...events].sort((a, b) => {
            const av: string = a[col] ?? "";
            const bv: string = b[col] ?? "";
            return av < bv ? -dir : av > bv ? dir : 0;
        });
    }

    private _renderAll() {
        this._renderTable();
        this._renderPager();
    }

    private _renderAuditAll() {
        this._renderAuditTable();
        this._renderAuditPager();
    }

    private _renderTable() {
        if (!this._tableWrap) return;
        this._tableWrap.empty();

        const filtered = this._filteredPages();
        const sorted = this._sortedPages(filtered);
        const totalPages = Math.max(1, Math.ceil(sorted.length / LIFECYCLE_PAGE_SIZE));
        this._page = Math.min(this._page, totalPages - 1);
        const slice = sorted.slice(this._page * LIFECYCLE_PAGE_SIZE, (this._page + 1) * LIFECYCLE_PAGE_SIZE);

        if (sorted.length === 0) {
            this._tableWrap.createEl("p", { text: "No pages found." })
                .style.cssText = "color:var(--text-muted);padding:16px";
            return;
        }

        const table = this._tableWrap.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px";

        const COLS: { key: string; label: string; sortable: boolean }[] = [
            { key: "slug",         label: "Slug",         sortable: true },
            { key: "state",        label: "State",        sortable: true },
            { key: "updated_at",   label: "Last Changed", sortable: true },
            { key: "triggered_by", label: "Triggered By", sortable: true },
            { key: "_actions",     label: "Actions",      sortable: false },
        ];

        const thead = table.createEl("thead");
        const hrow = thead.createEl("tr");
        hrow.style.cssText = "background:var(--background-secondary)";
        for (const col of COLS) {
            const th = hrow.createEl("th", { text: col.label });
            th.style.cssText = "text-align:left;padding:6px 10px;border-bottom:1px solid var(--background-modifier-border);white-space:nowrap;user-select:none";
            if (col.sortable) {
                th.style.cursor = "pointer";
                if (this._sortCol === col.key) th.textContent += this._sortAsc ? " ▲" : " ▼";
                else th.textContent += " ⇅";
                th.addEventListener("click", () => {
                    if (this._sortCol === col.key) this._sortAsc = !this._sortAsc;
                    else { this._sortCol = col.key; this._sortAsc = true; }
                    this._renderTable();
                });
            }
        }

        const tbody = table.createEl("tbody");
        for (const pg of slice) {
            const tr = tbody.createEl("tr");
            tr.style.borderBottom = "1px solid var(--background-modifier-border-subtle)";
            tr.addEventListener("mouseenter", () => { tr.style.background = "var(--background-modifier-hover)"; });
            tr.addEventListener("mouseleave", () => { tr.style.background = ""; });

            const slugTd = tr.createEl("td");
            slugTd.style.cssText = "padding:6px 10px;font-family:var(--font-monospace);font-size:12px";
            const slugVal = pg.slug ?? "";
            if (slugVal) {
                const slugLink = slugTd.createEl("a", { text: slugVal });
                slugLink.style.cssText = "color:var(--link-color);text-decoration:none;cursor:pointer";
                slugLink.addEventListener("mouseenter", () => { slugLink.style.textDecoration = "underline"; });
                slugLink.addEventListener("mouseleave", () => { slugLink.style.textDecoration = "none"; });
                slugLink.addEventListener("click", (e) => {
                    e.preventDefault();
                    this.app.workspace.openLinkText(slugVal, "", false);
                });
            } else {
                slugTd.textContent = "—";
            }

            const stateTd = tr.createEl("td");
            stateTd.style.cssText = "padding:6px 10px";
            const stateVal = pg.state ?? "";
            const chip = stateTd.createEl("span", { text: stateVal });
            chip.style.cssText = `border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;`
                + (LIFECYCLE_STATE_COLORS[stateVal] ?? "background:var(--background-modifier-border)");

            const rawTs: string = pg.updated_at ?? "";
            const ts = rawTs ? new Date(rawTs).toLocaleString() : "—";
            const tsTd = tr.createEl("td", { text: ts });
            tsTd.style.cssText = "padding:6px 10px;color:var(--text-muted);font-size:12px";

            const trigTd = tr.createEl("td", { text: pg.triggered_by ?? "—" });
            trigTd.style.cssText = "padding:6px 10px;color:var(--text-muted);font-size:12px";

            const actionsTd = tr.createEl("td");
            actionsTd.style.cssText = "padding:6px 10px";
            const allowed = ALLOWED_TRANSITIONS[stateVal] ?? [];
            for (const toState of allowed) {
                const btn = actionsTd.createEl("button", { text: toState }) as HTMLButtonElement;
                btn.style.cssText = "margin-right:4px;font-size:11px;padding:2px 8px";
                btn.addEventListener("click", () => {
                    const slug = pg.slug ?? "";
                    new ReasonModal(this.app, `Transition "${slug}" to ${toState}`, async (reason) => {
                        try {
                            await api.lifecycleTransition(slug, toState, reason);
                            await this._fetchAndRender();
                        } catch {
                            new Notice("Synthadoc: lifecycle transition failed — is the server running?");
                        }
                    }).open();
                });
            }
        }
    }

    private _renderAuditTable() {
        if (!this._auditTableWrap) return;
        this._auditTableWrap.empty();

        if (this._auditEvents.length === 0) {
            this._auditTableWrap.createEl("p", { text: "No audit events found." })
                .style.cssText = "color:var(--text-muted);padding:16px";
            return;
        }

        const filtered = this._filteredAuditEvents();
        const sorted = this._sortedAuditEvents(filtered);

        if (sorted.length === 0) {
            this._auditTableWrap.createEl("p", { text: "No events match the current filter." })
                .style.cssText = "color:var(--text-muted);padding:16px";
            return;
        }

        const totalPages = Math.max(1, Math.ceil(sorted.length / LIFECYCLE_PAGE_SIZE));
        this._auditPage = Math.min(this._auditPage, totalPages - 1);
        const slice = sorted.slice(this._auditPage * LIFECYCLE_PAGE_SIZE, (this._auditPage + 1) * LIFECYCLE_PAGE_SIZE);

        const AUDIT_COLS: { key: string; label: string; sortable: boolean }[] = [
            { key: "slug",         label: "Slug",         sortable: true },
            { key: "from_state",   label: "From",         sortable: true },
            { key: "to_state",     label: "To",           sortable: true },
            { key: "triggered_by", label: "Triggered By", sortable: true },
            { key: "timestamp",    label: "Timestamp",    sortable: true },
            { key: "reason",       label: "Reason",       sortable: false },
        ];

        const table = this._auditTableWrap.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px";

        const thead = table.createEl("thead");
        const hrow = thead.createEl("tr");
        hrow.style.cssText = "background:var(--background-secondary)";
        for (const col of AUDIT_COLS) {
            const th = hrow.createEl("th", { text: col.label });
            th.style.cssText = "text-align:left;padding:6px 10px;border-bottom:1px solid var(--background-modifier-border);white-space:nowrap;user-select:none";
            if (col.sortable) {
                th.style.cursor = "pointer";
                if (this._auditSortCol === col.key) th.textContent += this._auditSortAsc ? " ▲" : " ▼";
                else th.textContent += " ⇅";
                th.addEventListener("click", () => {
                    if (this._auditSortCol === col.key) this._auditSortAsc = !this._auditSortAsc;
                    else { this._auditSortCol = col.key; this._auditSortAsc = true; }
                    this._renderAuditTable();
                });
            }
        }

        const tbody = table.createEl("tbody");
        for (const ev of slice) {
            const tr = tbody.createEl("tr");
            tr.style.borderBottom = "1px solid var(--background-modifier-border-subtle)";
            tr.addEventListener("mouseenter", () => { tr.style.background = "var(--background-modifier-hover)"; });
            tr.addEventListener("mouseleave", () => { tr.style.background = ""; });

            const slugTd = tr.createEl("td", { text: ev.slug ?? "—" });
            slugTd.style.cssText = "padding:6px 10px;font-family:var(--font-monospace);font-size:12px;white-space:nowrap";

            const fromTd = tr.createEl("td");
            fromTd.style.cssText = "padding:6px 10px;white-space:nowrap";
            const fromVal = ev.from_state ?? "";
            if (fromVal) {
                const fromChip = fromTd.createEl("span", { text: fromVal });
                fromChip.style.cssText = `border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;`
                    + (LIFECYCLE_STATE_COLORS[fromVal] ?? "background:var(--background-modifier-border)");
            } else {
                fromTd.textContent = "—";
            }

            const toTd = tr.createEl("td");
            toTd.style.cssText = "padding:6px 10px;white-space:nowrap";
            const toVal = ev.to_state ?? "";
            const toChip = toTd.createEl("span", { text: toVal });
            toChip.style.cssText = `border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;`
                + (LIFECYCLE_STATE_COLORS[toVal] ?? "background:var(--background-modifier-border)");

            const trigTd = tr.createEl("td", { text: ev.triggered_by ?? "—" });
            trigTd.style.cssText = "padding:6px 10px;color:var(--text-muted);font-size:12px;white-space:nowrap";

            const rawTs: string = ev.timestamp ?? "";
            const ts = rawTs ? new Date(rawTs).toLocaleString() : "—";
            const tsTd = tr.createEl("td", { text: ts });
            tsTd.style.cssText = "padding:6px 10px;color:var(--text-muted);font-size:12px;white-space:nowrap";

            const reasonTd = tr.createEl("td", { text: ev.reason ?? "—" });
            reasonTd.style.cssText = "padding:6px 10px;font-size:12px;color:var(--text-muted)";
        }
    }

    private _renderPager() {
        if (!this._pagerWrap) return;
        this._pagerWrap.empty();
        const filtered = this._filteredPages();
        const totalPages = Math.max(1, Math.ceil(filtered.length / LIFECYCLE_PAGE_SIZE));
        if (totalPages <= 1) return;
        const prev = this._pagerWrap.createEl("button", { text: "← Prev" }) as HTMLButtonElement;
        prev.disabled = this._page === 0;
        prev.addEventListener("click", () => { this._page--; this._renderAll(); });
        this._pagerWrap.createEl("span", {
            text: `Page ${this._page + 1} of ${totalPages} (${filtered.length} total)`,
        });
        const next = this._pagerWrap.createEl("button", { text: "Next →" }) as HTMLButtonElement;
        next.disabled = this._page >= totalPages - 1;
        next.addEventListener("click", () => { this._page++; this._renderAll(); });
    }

    private _renderAuditPager() {
        if (!this._auditPagerWrap) return;
        this._auditPagerWrap.empty();
        const filtered = this._filteredAuditEvents();
        const totalPages = Math.max(1, Math.ceil(filtered.length / LIFECYCLE_PAGE_SIZE));
        if (totalPages <= 1) return;
        const prev = this._auditPagerWrap.createEl("button", { text: "← Prev" }) as HTMLButtonElement;
        prev.disabled = this._auditPage === 0;
        prev.addEventListener("click", () => { this._auditPage--; this._renderAuditAll(); });
        this._auditPagerWrap.createEl("span", {
            text: `Page ${this._auditPage + 1} of ${totalPages} (${filtered.length} events)`,
        });
        const next = this._auditPagerWrap.createEl("button", { text: "Next →" }) as HTMLButtonElement;
        next.disabled = this._auditPage >= totalPages - 1;
        next.addEventListener("click", () => { this._auditPage++; this._renderAuditAll(); });
    }

    onClose() {
        this._pages = [];
        this._auditEvents = [];
        this.contentEl.empty();
    }
}

class ExportModal extends Modal {
    private _format = "json";
    private _statusFilter = "active";

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        contentEl.empty();
        const titleEl = contentEl.createEl("h2", { text: "Export Wiki" });
        makeDraggable(this.modalEl, titleEl);

        // Description
        const infoEl = contentEl.createEl("div");
        infoEl.style.cssText = "margin:0 0 14px;padding:8px 10px;background:var(--background-secondary);border-radius:6px;font-size:12px;color:var(--text-muted);line-height:1.7;";
        infoEl.innerHTML = [
            "<b>Exports the wiki in machine-readable formats. No additional LLM calls.</b>",
            "<ul style='margin:6px 0 0 0;padding-left:18px;list-style:disc'>",
            "<li><b>json</b> — full structured dump with claims, lifecycle history, and routing</li>",
            "<li><b>llms.txt</b> — active pages in the <a href='https://llmstxt.org'>llmstxt.org</a> format (for AI tools)</li>",
            "<li><b>llms-full.txt</b> — full page content with provenance footnotes inline</li>",
            "<li><b>graphml</b> — wikilink graph — open in <b>yEd</b>, <b>Gephi</b>, or <b>Cytoscape</b></li>",
            "<li><b>okf</b> — OKF v0.1 bundle (active + contradicted pages) written <em>outside</em> the vault — readable by any OKF-aware agent without code changes</li>",
            "</ul>",
        ].join("");

        // Format selector
        const fmtRow = contentEl.createEl("div", { cls: "setting-item" });
        fmtRow.createEl("label", { text: "Format" });
        const select = fmtRow.createEl("select");
        ["json", "llms.txt", "llms-full.txt", "graphml", "okf"].forEach(fmt => {
            const opt = select.createEl("option", { text: fmt, value: fmt });
            if (fmt === this._format) opt.selected = true;
        });

        // Output path
        const today = new Date().toISOString().slice(0, 10);
        const _nodeRequire = typeof (window as any).require === "function"
            ? (window as any).require : null;
        const defaultPath = (fmt: string): string => {
            if (fmt === "okf") {
                const vaultName = this.app.vault.getName?.() ?? "wiki";
                const home = _nodeRequire ? _nodeRequire("os").homedir() : "~";
                const sep = _nodeRequire ? _nodeRequire("path").sep : "/";
                return [home, "exports", `${vaultName}-okf-${today}`].join(sep);
            }
            const stems: Record<string, string> = {
                "json":          `wiki-${today}.json`,
                "llms.txt":      `wiki-llms-${today}.txt`,
                "llms-full.txt": `wiki-llms-full-${today}.txt`,
                "graphml":       `wiki-graph-${today}.graphml`,
            };
            return `exports/${stems[fmt] ?? `wiki-${today}.txt`}`;
        };
        const pathRow = contentEl.createEl("div");
        pathRow.style.cssText = "margin-bottom:12px;";
        const pathLabel = pathRow.createEl("label", { text: "Output path (in vault)" });
        pathLabel.style.cssText = "display:block;margin-bottom:4px;font-size:13px;";
        const pathInput = pathRow.createEl("input", {
            type: "text",
            value: defaultPath(this._format),
        }) as HTMLInputElement;
        pathInput.style.cssText = "width:100%;box-sizing:border-box;font-family:var(--font-monospace);font-size:12px;";
        const okfHint = pathRow.createEl("p");
        okfHint.style.cssText = "margin:4px 0 0;font-size:11px;color:var(--text-muted);display:none;";
        okfHint.textContent = "Written outside the vault via the filesystem. Directory created automatically.";

        // Status filter
        const statusRow = contentEl.createEl("div", { cls: "setting-item" });
        const statusLabel = statusRow.createEl("label", { text: "Status filter" });
        const statusSel = statusRow.createEl("select");
        const allOpt = statusSel.createEl("option", { text: "All pages", value: "all" }) as HTMLOptionElement;
        const activeOpt = statusSel.createEl("option", { text: "Active only", value: "active" }) as HTMLOptionElement;
        if (this._statusFilter === "all") allOpt.selected = true;
        else activeOpt.selected = true;

        // Button row
        const btnRow = contentEl.createEl("div", { cls: "modal-button-container" });
        const exportBtn = btnRow.createEl("button", { text: "Export" }) as HTMLButtonElement;
        let viewGraphBtn: HTMLButtonElement | null = null;

        const updateExtension = () => {
            pathInput.value = defaultPath(this._format);
            const isOkf = this._format === "okf";
            pathLabel.textContent = isOkf ? "Output folder (outside vault)" : "Output path (in vault)";
            okfHint.style.display = isOkf ? "" : "none";
            // Relabel status options to reflect OKF's actual behaviour
            statusLabel.textContent = isOkf ? "Pages to include" : "Status filter";
            allOpt.textContent = isOkf ? "Active + contradicted (default)" : "All pages";
            if (isOkf && this._statusFilter !== "all") {
                this._statusFilter = "all";
                statusSel.value = "all";
            }
            if (this._format === "graphml") {
                if (!viewGraphBtn) {
                    viewGraphBtn = btnRow.createEl("button", { text: "View Graph" }) as HTMLButtonElement;
                    viewGraphBtn.addEventListener("click", () => {
                        new GraphViewModal(this.app).open();
                        this.close();
                    });
                }
            } else if (viewGraphBtn) {
                viewGraphBtn.remove();
                viewGraphBtn = null;
            }
        };

        select.addEventListener("change", () => {
            this._format = select.value;
            updateExtension();
        });
        statusSel.addEventListener("change", () => { this._statusFilter = statusSel.value; });

        exportBtn.addEventListener("click", async () => {
            exportBtn.disabled = true;
            exportBtn.textContent = "Exporting…";
            try {
                if (this._format === "okf") {
                    if (!_nodeRequire) {
                        new Notice("Synthadoc: OKF export requires Obsidian desktop.");
                        exportBtn.disabled = false;
                        exportBtn.textContent = "Export";
                        return;
                    }
                    const fs = _nodeRequire("fs");
                    const nodePath = _nodeRequire("path");
                    const manifest = await api.exportWikiOkf(this._statusFilter);
                    const outDir = pathInput.value.trim();
                    for (const [relPath, fileContent] of Object.entries(manifest)) {
                        const dest = nodePath.join(outDir, ...relPath.split("/"));
                        fs.mkdirSync(nodePath.dirname(dest), { recursive: true });
                        fs.writeFileSync(dest, fileContent, "utf8");
                    }
                    new Notice(`Synthadoc: OKF bundle written to ${outDir} (${Object.keys(manifest).length} files)`);
                    this.close();
                    return;
                }

                const content = await api.exportWiki(this._format, this._statusFilter);
                const path = pathInput.value.trim() || `exports/wiki-export.${this._format}`;

                // Use filesystem check — vault index may not include files from
                // sessions before the extension was registered.
                if (await this.app.vault.adapter.exists(path)) {
                    const ok = confirm(`"${path}" already exists. Overwrite?`);
                    if (!ok) { exportBtn.disabled = false; exportBtn.textContent = "Export"; return; }
                }

                let tfile: TFile | null = null;
                const existingTFile = this.app.vault.getAbstractFileByPath(path);
                if (existingTFile instanceof TFile) {
                    await this.app.vault.modify(existingTFile, content);
                    tfile = existingTFile;
                } else {
                    const parent = path.split("/").slice(0, -1).join("/");
                    if (parent) {
                        try { await this.app.vault.createFolder(parent); } catch { /* already exists */ }
                    }
                    try {
                        tfile = await this.app.vault.create(path, content);
                    } catch {
                        // File exists on disk but not in vault index — write directly.
                        await this.app.vault.adapter.write(path, content);
                        tfile = this.app.vault.getAbstractFileByPath(path) as TFile | null;
                    }
                }
                new Notice(`Synthadoc: exported to ${path}`);
                this.close();
                if (tfile) {
                    const leaf = this.app.workspace.getLeaf(false);
                    await leaf.openFile(tfile);
                    (this.app as any).commands.executeCommandById("file-explorer:reveal-active-file");
                }
            } catch (e) {
                new Notice(`Synthadoc: export failed — ${e}`);
                exportBtn.disabled = false;
                exportBtn.textContent = "Export";
            }
        });
    }

    onClose() { this.contentEl.empty(); }
}

class GraphViewModal extends Modal {
    private _closed = false;

    onOpen() {
        this._closed = false;
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        contentEl.empty();
        this.modalEl.style.width = "clamp(960px, 88vw, 1400px)";
        this.modalEl.style.height = "clamp(700px, 88vh, 1000px)";
        const titleEl = contentEl.createEl("h2", { text: "Knowledge Graph" });
        makeDraggable(this.modalEl, titleEl);

        // Toolbar
        const toolbar = contentEl.createDiv({ cls: "synthadoc-graph-toolbar" });
        const exportBtn = toolbar.createEl("button", { text: "Export to file" });

        // Graph container — fills remaining modal height minus title + toolbar
        const container = contentEl.createDiv();
        container.style.cssText = "width:100%;height:calc(100% - 80px);min-height:500px;background:#1e1e2e;border-radius:4px;";

        exportBtn.addEventListener("click", async () => {
            try {
                const content = await api.exportWiki("graphml", "all");
                const today = new Date().toISOString().slice(0, 10);
                const path = `exports/wiki-graph-${today}.graphml`;
                const existing = this.app.vault.getAbstractFileByPath(path);
                if (existing instanceof TFile) {
                    const ok = confirm(`"${path}" already exists. Overwrite?`);
                    if (!ok) return;
                    await this.app.vault.modify(existing, content);
                } else {
                    try { await this.app.vault.createFolder("exports"); } catch { /* exists */ }
                    await this.app.vault.create(path, content);
                }
                new Notice(`Synthadoc: graph exported to ${path}`);
            } catch (e) {
                new Notice(`Synthadoc: graph export failed — ${e}`);
            }
        });

        // Fetch graph data and render with Cytoscape.js
        api.exportWiki("graphml", "all").then(graphmlText => {
            this._renderGraph(container, graphmlText);
        }).catch(() => {
            container.createEl("p", { text: "Could not load graph — is the server running?" });
        });
    }

    private _renderGraph(container: HTMLElement, graphmlText: string) {
        if (this._closed) return;
        const parser = new DOMParser();
        const doc = parser.parseFromString(graphmlText, "application/xml");
        const NS = "http://graphml.graphdrawing.org/graphml";

        const getAttr = (el: Element, keyId: string): string => {
            for (const d of Array.from(el.getElementsByTagNameNS(NS, "data"))) {
                if (d.getAttribute("key") === keyId) return d.textContent || "";
            }
            return "";
        };

        const STATUS_COLORS: Record<string, string> = {
            active: "#4ade80", draft: "#fbbf24", stale: "#f97316",
            contradicted: "#f87171", archived: "#6b7280",
        };

        const nodes = Array.from(doc.getElementsByTagNameNS(NS, "node")).map(n => {
            const id = n.getAttribute("id") || "";
            const status = getAttr(n, "status");
            return {
                data: {
                    id,
                    label: getAttr(n, "title") || id,
                    status,
                    color: STATUS_COLORS[status] || "#94a3b8",
                },
            };
        });

        const edges = Array.from(doc.getElementsByTagNameNS(NS, "edge")).map((e, i) => ({
            data: {
                id: `e${i}`,
                source: e.getAttribute("source") || "",
                target: e.getAttribute("target") || "",
            },
        }));

        // Dynamically import cytoscape to keep bundle size manageable
        import("cytoscape").then(({ default: cytoscape }) => {
            if (this._closed) return;
            const cy = cytoscape({
                container,
                elements: [...nodes, ...edges],
                style: [
                    {
                        selector: "node",
                        style: {
                            "background-color": "data(color)",
                            "label": "data(label)",
                            "color": "#e2e8f0",
                            "font-size": "11px",
                            "text-valign": "bottom",
                            "text-halign": "center",
                            "text-margin-y": "6px",
                            "text-wrap": "wrap",
                            "text-max-width": "120px",
                            "text-background-color": "#1e1e2e",
                            "text-background-opacity": 0.75,
                            "text-background-padding": "2px",
                            "text-background-shape": "round-rectangle",
                            "width": "42px",
                            "height": "42px",
                            "border-width": 2,
                            "border-color": "#2d3748",
                        },
                    },
                    {
                        selector: "edge",
                        style: {
                            "width": 1.5,
                            "line-color": "#475569",
                            "target-arrow-color": "#64748b",
                            "target-arrow-shape": "triangle",
                            "curve-style": "bezier",
                            "opacity": 0.65,
                        },
                    },
                ],
                layout: {
                    name: "cose",
                    animate: false,
                    nodeRepulsion: 10000,
                    idealEdgeLength: 130,
                    nodeOverlap: 60,
                    padding: 60,
                    gravity: 0.5,
                    numIter: 1000,
                    randomize: true,
                },
            });
            cy.fit(undefined, 60);
        }).catch(() => {
            if (!this._closed) container.textContent = "Could not load graph renderer.";
        });
    }

    onClose() {
        this._closed = true;
        this.contentEl.empty();
    }
}
