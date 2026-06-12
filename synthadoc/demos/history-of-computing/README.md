# History of Computing — Demo Wiki

A pre-built Synthadoc wiki demonstrating the full ingest lifecycle: clean merges,
source conflicts, and orphan detection — using real PDF, XLSX, and PNG source files.

## Install

**Linux / macOS:**
```bash
synthadoc install history-of-computing --target ~/wikis --demo
```

**Windows (cmd.exe):**
```cmd
synthadoc install history-of-computing --target %USERPROFILE%\wikis --demo
```

**Windows (PowerShell):**
```powershell
synthadoc install history-of-computing --target $env:USERPROFILE\wikis --demo
```

Then open the installed folder as an Obsidian vault. Wiki pages live under `wiki/`.
All commands use the wiki name (`-w history-of-computing`) — no paths needed.

---

## Set your active wiki

After installing, run this once so you don't need `-w history-of-computing` on every command:

```bash
synthadoc use history-of-computing
```

All commands below will work without the `-w` flag.
To confirm which wiki is active: `synthadoc use`

---

## Source documents (pre-built)

Four source documents are included in `raw_sources/` — no generation step needed:

| File | Format | Scenario |
|------|--------|----------|
| `turing-enigma-decryption.pdf` | PDF | **Clean merge** — enriches `alan-turing` |
| `computing-pioneers-timeline.xlsx` | XLSX | **Clean merge** — structured timeline, enriches multiple pages |
| `first-compiler-controversy.pdf` | PDF | **Conflict** — contradicts `grace-hopper` (A-0 vs FORTRAN) |
| `quantum-computing-primer.png` | PNG | **Orphan** — completely new topic, no existing page links to it |

If you want to regenerate them: `python raw_sources/generate_sources.py`

---

## Step 1 — Start the server

The server must be running before any other command (query, ingest, lint) can work.
Open a dedicated terminal and leave it running:

```
synthadoc serve -w history-of-computing
```

Expected output:
```
HTTP API running on http://127.0.0.1:7070
```

Use a second terminal for all commands below.

---

## Free-tier API usage

This demo makes roughly **10–15 LLM calls** across all four scenarios (ingest, query
decomposition, web search, lint auto-resolve). Free-tier Gemini allows **20 requests per
day** — enough for one full run-through, but not multiple sessions in the same day.

**If you hit the daily limit** the server logs `Daily quota exhausted` and immediately
fails pending jobs (no retry loop). You can either wait until midnight UTC for the quota
to reset, or switch providers by editing `.synthadoc/config.toml`:

```toml
# Groq — free tier, generous daily budget
default = { provider = "groq", model = "llama-3.3-70b-versatile" }

# Paid Gemini key — no daily cap
default = { provider = "gemini", model = "gemini-2.5-flash-lite" }
```

Restart `synthadoc serve` after changing the provider.

---

## Step 2 — Scenario A: Clean merge

Ingest the PDF about Turing's Enigma work. It adds new detail to the existing
`alan-turing` page without contradicting anything.

```
synthadoc ingest raw_sources/turing-enigma-decryption.pdf -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

Then ingest the structured timeline spreadsheet. It enriches several pages at once:

```
synthadoc ingest raw_sources/computing-pioneers-timeline.xlsx -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

**Expected result:** job status shows `completed`. Open `alan-turing.md` in Obsidian —
it should have new content from the PDF. Check `wiki/index.md` — new pages appear
under `## Recently Added`.

---

## Step 3 — Scenario B: Conflict and resolution

Ingest the controversy PDF. It argues that Hopper's A-0 was a loader, not a compiler —
directly contradicting the existing `grace-hopper` page.

```
synthadoc ingest raw_sources/first-compiler-controversy.pdf -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

**Expected result:** `grace-hopper.md` frontmatter changes to `status: contradicted`.
In Obsidian, open `wiki/dashboard.md` — the page appears in the **Contradicted pages** table.

Check via CLI:
```
synthadoc lint report -w history-of-computing
```

**Option 1 — Manual resolution:**

1. Open `wiki/grace-hopper.md` in Obsidian
2. Read both positions; edit the content to reflect the nuanced view (Hopper pioneered
   the concept; Backus delivered the first production compiler)
3. Change `status: contradicted` to `status: active` in the frontmatter
4. Save

**Option 2 — Auto-resolve (LLM-assisted):**

```
synthadoc lint run -w history-of-computing --auto-resolve
synthadoc jobs status <job-id> -w history-of-computing
```

The LLM proposes a resolution and appends it to the page. Review the result in Obsidian.

---

## Step 4 — Scenario C: Orphan and human decision

Ingest the quantum computing image. It covers a topic (qubits, Shor's algorithm, Google
Sycamore) not mentioned in any existing wiki page.

```
synthadoc ingest raw_sources/quantum-computing-primer.png -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

**Expected result:** a new `quantum-computing` (or similar) page is created, but nothing
links to it. Open `wiki/dashboard.md` in Obsidian — it appears in the **Orphan pages**
table.

Check via CLI:
```
synthadoc lint report -w history-of-computing
```

**Your decision — three options:**

1. **Link it** — open a related page (e.g. `artificial-intelligence-history.md`) and add
   `[[quantum-computing]]` in a relevant sentence. The page is no longer an orphan.

2. **Leave it** — keep it as a standalone page until you ingest more quantum content
   that naturally references it.

3. **Delete it** — if the page quality is poor, delete `wiki/quantum-computing.md` and re-ingest
   with `--force` once you have a better source document.

---

## Step 5 — Multi-turn conversation and web UI demo

Open the web UI and try these sequences to see how context carries across turns:

```bash
synthadoc web -w history-of-computing
```

### Single-turn queries to try first

These work well as standalone questions before exploring multi-turn:

```
"Who is Alan Turing and what was his most significant contribution?"
"What is Moore's Law and has it held up over time?"
"How did the transition from vacuum tubes to transistors change computing?"
"What are the differences between von Neumann and Harvard architectures?"
```

Knowledge gap detection — the wiki doesn't cover these yet:

```
"What is the history of quantum computing milestones?"
"Who invented the USB standard?"
```

### Multi-turn: wiki content

**Pronoun carry-over** (best stress test — "they" and "that same lab" only resolve
correctly if conversation history is injected):

```
Turn 1:  "Who invented the transistor?"
Turn 2:  "Which company did they work for?"
Turn 3:  "What other inventions came out of that same lab?"
```

**Topic deepening:**

```
Turn 1:  "What was the significance of the 1936 Turing machine paper?"
Turn 2:  "How did that influence the design of the first real computers?"
Turn 3:  "Which of those early computers had the most commercial impact?"
```

**Pivot mid-conversation:**

```
Turn 1:  "Tell me about Claude Shannon and information theory"
Turn 2:  "How does that relate to data compression?"
Turn 3:  "What about its connection to cryptography?"
```

### Multi-turn: Synthadoc operations

**Job status drill-down:**

```
You:     "Show me job status"
         → Table of all jobs; chip buttons appear for each Job ID.

Click chip "353958ca"
         → Full detail: status, operation, started/finished, error if any.

Click chip "6b7d1fa7" (from the same chip list)
         → Detail for the second job — no re-query needed.
```

**Multi-status filter:**

```
You:     "Show me failed and skipped jobs"
         → Filtered table for those two statuses only.
```

**Clarify prompt** — ask to perform an action without specifying a page:

```
You:     "Activate a draft page"
         → "Which page? 1. konrad-zuse  2. quantum-computing (or type a name)"
Click chip "1" → page is activated immediately.
```

### Settings — query timeout

Click the ⚙ gear icon (bottom-left of the chat window) to open Settings. Adjust the
**query timeout** (10–600 s, default 60 s) if you are using a reasoning model that needs
more time. The value persists across page refreshes.

### Notice message

After 5 or more turns the assistant compresses the oldest context and shows:

```
ℹ Earlier conversation turns were summarised to fit the session window.
```

To adjust the history window, edit `config.toml`:

```toml
[chat]
conversation_history_turns = 5   # set to 0 to disable conversation memory
```

---

## Step 6 — Check status and jobs

```
synthadoc status -w history-of-computing
synthadoc jobs list -w history-of-computing
synthadoc lint report -w history-of-computing
```

---

## Step 7 — Export your wiki

All four formats are available once the server is running.

```bash
# LLM navigation index — active pages only (llms.txt spec)
synthadoc export --format llms.txt --status active -w history-of-computing

# Full text dump — preserves provenance footnotes inline
synthadoc export --format llms-full.txt --output exports/history-full.txt -w history-of-computing

# Knowledge graph — open in Gephi, Cytoscape, or yEd
synthadoc export --format graphml --output exports/history.graphml -w history-of-computing

# Structured JSON — includes claim citations, lifecycle history, and total compilation cost
synthadoc export --format json --output exports/history.json -w history-of-computing
```

**In Obsidian:** Command palette → `Synthadoc: Export Wiki`. Select format → click Export. File saved to vault `exports/` folder. For GraphML, click **View Graph** to render the knowledge graph inside Obsidian with lifecycle-colored nodes.

---

## Wiki pages (pre-built)

| Page | Description |
|------|-------------|
| `alan-turing` | Biography and theoretical contributions |
| `grace-hopper` | First compiler, COBOL, and debugging |
| `von-neumann-architecture` | Stored-program computer model |
| `transistor-and-microchip` | From Bell Labs transistor to Moore's Law |
| `unix-history` | Origins of Unix and the C language |
| `open-source-movement` | GNU, Linux, and the bazaar model |
| `programming-languages-overview` | Evolution from assembly to modern languages |
| `internet-origins` | ARPANET to the World Wide Web |
| `personal-computer-revolution` | Altair, Apple II, IBM PC, and the GUI |
| `artificial-intelligence-history` | Dartmouth conference to large language models |

---

## Uninstall

```
synthadoc uninstall history-of-computing
```

Requires two confirmations — a y/N prompt and typing the wiki name. There is no `--yes` flag.
