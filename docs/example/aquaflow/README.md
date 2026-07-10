# AquaFlow Capital: Workshop Walkthrough

**Domain:** Private equity M&A due diligence — LBO modeling, quality of earnings, covenant analysis, ESG, and legal DD

The scenario: AquaFlow Capital is evaluating an LBO of AquaFlow Systems Inc., a mid-market water treatment equipment company. Eight deal documents are sitting in a folder — company profile, sector analysis, LBO mechanics, covenant framework, QoE guide, ESG standards, legal DD process, and exit benchmarks. By the end of this walkthrough, all eight are ingested into a working knowledge wiki, lint-validated, and queryable in natural language, including Chinese.

Steps 1–3 (install, configure, register) require a terminal. From Step 6 onward, ingest, scaffold, and lint can all run from either the terminal or the Obsidian plugin command palette — both paths are shown where relevant. Queries run through the Synthadoc web UI in Step 11.

---

## What this example covers


| Source file                         | Wiki page created                                           |
| ----------------------------------- | ----------------------------------------------------------- |
| `01_aquaflow_company_profile.md`    | `aquaflow-systems` — company profile with financials   |
| `02_water_infrastructure_market.md` | `us-water-treatment-equipment-market` — sector analysis    |
| `03_lbo_model_mechanics.md`         | `lbo-model-structure-and-mechanics` — LBO methodology                   |
| `04_covenant_analysis_framework.md` | `covenant-analysis` — financial covenants        |
| `05_quality_of_earnings_guide.md`   | `quality-of-earnings` — QoE methodology                |
| `06_esg_due_diligence_standards.md` | `esg-due-diligence` — ESG framework                        |
| `07_legal_due_diligence_process.md` | `legal-due-diligence` — legal DD process                   |
| `08_exit_valuation_benchmarks.md`   | `pe-exit-strategies-and-valuation-benchmarks` — exit strategy |

The ingest agent decides autonomously whether each source should create a new page or update an existing one. Company profiles and entity-specific data (financials, org structure, management team) always create dedicated pages — they are never merged into thematic or market-level pages.

---

## Prerequisites

- Python 3.11+ — [download at python.org](https://www.python.org/downloads/)
- Synthadoc installed (`pip install synthadoc` or editable dev install — see the [main README](../../../README.md#installation))
- A supported LLM API key — [MiniMax](https://platform.minimax.io/), [DeepSeek](https://platform.deepseek.com/), [Qwen](https://bailian.console.aliyun.com/), [Anthropic](https://console.anthropic.com/), or [OpenAI](https://platform.openai.com/api-keys) paid tiers are recommended for this walkthrough. Free-tier models (Gemini Free, Groq Free) have daily rate limits too low to finish a batch ingest of eight documents in one session. See the [main README — Set your API keys](../../../README.md#set-your-api-keys) for the full provider list.
- **Obsidian** *(optional)* — [download at obsidian.md](https://obsidian.md). The Obsidian plugin uses the same CLI interfaces as the terminal commands and makes browsing, reviewing, and editing wiki pages more visual. Every step provides an equivalent terminal command — you can complete the full walkthrough without Obsidian installed.

> **Windows users:** Commands in this walkthrough use Unix-style paths (`~/wikis`). In **Command Prompt** substitute `%USERPROFILE%\wikis`; in **PowerShell** `~\wikis` works directly. Multi-line `\` continuations used in the bash blocks do not work in Command Prompt — use the single-line Windows form shown where applicable.

---

## Step 1 — Install the wiki domain

**macOS / Linux / PowerShell:**
```bash
synthadoc install aquaflow \
  --target ~/wikis \
  --domain "Private equity M&A due diligence — LBO modeling, quality of earnings, covenant analysis, ESG, and legal DD"
```

**Windows Command Prompt:**
```cmd
synthadoc install aquaflow --target %USERPROFILE%\wikis --domain "Private equity M&A due diligence — LBO modeling, quality of earnings, covenant analysis, ESG, and legal DD"
```

**What this does:**

- Creates `~/wikis/aquaflow/` with the standard directory layout:
  - `wiki/` — generated wiki pages (Markdown + YAML frontmatter)
  - `raw_sources/` — your source documents
  - `.synthadoc/` — config, audit database, query cache
- Writes a default `config.toml` you will edit in Step 2
- Writes `AGENTS.md` with ingest and query guidelines for this domain
- Registers the wiki so `synthadoc use aquaflow` makes it the default

The `--domain` description is the single sentence the LLM uses to understand what belongs in this wiki. Write it as specifically as you can — it directly shapes ingest decisions and scaffold category names.

---

## Step 2 — Configure your LLM provider

Open `~/wikis/aquaflow/.synthadoc/config.toml` in any text editor. The `[agents]` section controls which LLM is used for ingest, scaffold, lint, and query. It ships with one active line and all others commented out:

```toml
[agents]
default = { provider = "gemini", model = "gemini-2.5-flash-lite" }
# Alternatives (uncomment and restart to switch):
# default = { provider = "gemini",    model = "gemini-2.5-flash" }         # free tier: 10 RPM / 250 RPD
# default = { provider = "gemini",    model = "gemini-1.5-flash" }         # free tier: 15 RPM / 1,500 RPD
# default = { provider = "minimax",   model = "MiniMax-M2.5" }             # paid, cheapest text-only ($0.15/M in)
# default = { provider = "minimax",   model = "MiniMax-M3",  thinking = "disabled" }  # paid, M3 with thinking off (faster, cheaper)
# default = { provider = "groq",      model = "llama-3.3-70b-versatile" }  # free tier, 100K tokens/day
# default = { provider = "anthropic", model = "claude-sonnet-4-6" }        # paid, high quality
# default = { provider = "anthropic", model = "claude-opus-4-8" }          # paid, highest quality (most capable)
# default = { provider = "deepseek",  model = "deepseek-chat" }            # paid, very cheap ($0.14/M in); text-only, no vision
# default = { provider = "ollama",    model = "llama3.2" }                 # fully local, no API key; requires GPU — CPU-only is too slow for interactive use
# default = { provider = "qwen",      model = "qwen-plus" }                # DashScope cloud API — set QWEN_API_KEY (https://bailian.console.aliyun.com/)
# default = { provider = "claude-code" }                                   # no API key — uses your Claude Code subscription
# default = { provider = "opencode" }                                      # no API key — uses your Opencode subscription
```

**To switch provider:**

1. Add a `#` at the start of the currently active `default = ...` line
2. Remove the `#` from the provider you want to use
3. Set the corresponding API key as an environment variable (see table below)
4. Start (or restart) the server — see Step 5

Only one `default = ...` line may be uncommented at a time.

**API key environment variables:**


| Provider               | Environment variable                          |
| ---------------------- | --------------------------------------------- |
| Anthropic              | `ANTHROPIC_API_KEY`                           |
| MiniMax                | `MINIMAX_API_KEY`                             |
| Gemini                 | `GEMINI_API_KEY`                              |
| DeepSeek               | `DEEPSEEK_API_KEY`                            |
| Groq                   | `GROQ_API_KEY`                                |
| Qwen                   | `QWEN_API_KEY`                                |
| Ollama                 | *(no key required — runs locally)*           |
| claude-code / opencode | *(no key required — uses your subscription)* |

Example — switching from the default Gemini to MiniMax:

```toml
# default = { provider = "gemini", model = "gemini-2.5-flash-lite" }   ← commented out
default = { provider = "minimax", model = "MiniMax-M3", thinking = "disabled" }  ← active
```

**macOS / Linux / PowerShell:**
```bash
export MINIMAX_API_KEY="sk-..."
```

**Windows Command Prompt:**
```cmd
set MINIMAX_API_KEY=sk-...
```

> **For this workshop:** Use a paid provider (MiniMax, DeepSeek, or Anthropic). Free-tier Gemini and Groq quotas are exhausted by batch ingest of eight documents in a single session. See [Appendix C — Switching LLM providers](../../user-quick-start-guide.md#appendix-c--switching-llm-providers) for full configuration details.

---

## Step 3 — Set as the default wiki

```bash
synthadoc use aquaflow
```

This records `aquaflow` as the active wiki so subsequent commands default to it. Override at any time with `-w <wiki>` if you maintain multiple wikis.

---

## Step 4 — Copy the example raw sources

The eight source documents for this walkthrough are in the Synthadoc repository under `docs/example/aquaflow/raw_sources/`. Copy them into your wiki's `raw_sources/` folder:

- **If you cloned the repository:** copy the eight `.md` files from `docs/example/aquaflow/raw_sources/` into `~/wikis/aquaflow/raw_sources/` (or `%USERPROFILE%\wikis\aquaflow\raw_sources\` on Windows).
- **If you haven't cloned the repository:** download the files from [github.com/axoviq-ai/synthadoc/docs/example/aquaflow/raw_sources](https://github.com/axoviq-ai/synthadoc/tree/main/docs/example/aquaflow/raw_sources) and place them in your `~/wikis/aquaflow/raw_sources/` folder.

Synthadoc does not watch for new files — ingestion is always an explicit command — so dropping files into the folder does not trigger anything yet.

> **Bringing your own documents:** Replace or supplement these files with your own PDFs, DOCX files, Markdown notes, or URLs. The ingest pipeline accepts any format the extraction layer supports.

---

## Step 5 — Start the server

```bash
synthadoc serve
```

**What this does:** Starts the Synthadoc API server (default port 7070) and the background job worker. Ingest, scaffold, lint, and query all run as async jobs managed by this server. The web UI is served from the same process.

To run in the background and keep your terminal free:

```bash
synthadoc serve --background
```

If you started the server without `--background`, it occupies the terminal. Open a **second terminal window** for all remaining CLI commands in this walkthrough.

Verify the server is up and the wiki is registered:

```bash
synthadoc status
```

Expected output:

```
[wiki: aquaflow]
Wiki:   ~/wikis/aquaflow
Pages:  0
```

Keep the server running while you follow the remaining steps.

---

## Step 6 — Ingest the source documents

Ingest all eight sources. You can do this from the terminal or the Obsidian plugin.

**Terminal — batch ingest the entire folder:**

First change to the wiki root, then run the ingest:

```bash
cd ~/wikis/aquaflow
synthadoc ingest raw_sources/
```

**Windows Command Prompt:** `cd %USERPROFILE%\wikis\aquaflow`

**Obsidian plugin — batch ingest from the command palette:**

1. Open the wiki vault in Obsidian — select the wiki root folder (`~/wikis/aquaflow/`)
2. Press `Cmd/Ctrl+P` → search **Synthadoc: Ingest...** → Enter
3. Select the **All raw_sources** tab → click **Ingest all**

The plugin sends the same ingest job to the running server — behaviour is identical to the CLI.

**What happens for each source:**

1. **Extraction** — Text and metadata are pulled from the file. The page title is derived from the H1 heading in the LLM-generated body (not the filename), so `01_aquaflow_company_profile.md` produces a page titled `AquaFlow Systems Inc. — Company Profile`.
2. **Analysis** — An LLM pass identifies entities, tags, and an OKF type (e.g., `organization` for company profiles).
3. **Decision** — The agent decides whether to `create` a new page, `update` an existing one, or `flag` a contradiction. Entity profiles (companies with financials, people, products) always `create` — financial data is never silently merged into a thematic page.
4. **Key Data extraction** — Numerical facts, rates, and formulas are extracted deterministically and preserved in a Key Data section so figures like revenue and EBITDA margins survive exactly as written in the source.
5. **Citation annotation** — Each claim is annotated with a `^[filename:L-L]` marker linking back to the line range in the source file.
6. **Write** — The page is written to `wiki/` with YAML frontmatter (`status: draft`, `confidence: medium`, `sources: [...]`).

After all eight sources are ingested, confirm the pages were created:

```bash
synthadoc status
```

Expected:

```
[wiki: aquaflow]
Wiki:         ~/wikis/aquaflow
Pages:        7
Jobs pending: 0
Jobs total:   8

Page lifecycle:
  active         0
  draft          7  <- run `synthadoc lint run` to promote
  stale          0
  contradicted   0
  archived       0
```

7 pages from 8 sources is normal — the ingest agent merged one source into an existing page rather than creating a new one. All 8 jobs completed successfully.

> **Force re-ingest:** If you update a source file or want to regenerate a page, the dedup guard is bypassed and the page is regenerated. Run it from the terminal with `synthadoc ingest <file> --force`, or from the Obsidian plugin: `Cmd/Ctrl+P` → **Synthadoc: Ingest...** → **All raw_sources** tab → check **Force re-ingest** → click **Ingest all**. The `sources` list on the page automatically deduplicates by `(file, hash)` — re-ingesting the same unchanged file never adds a duplicate source entry.

---

## Step 7 — Scaffold the index

**Terminal:**

```bash
synthadoc scaffold
```

**Obsidian plugin:** `Cmd/Ctrl+P` → **Synthadoc: Run scaffold**

**What this does:**

- Calls the scaffold LLM to organize your 8 pages into 5–8 domain-appropriate categories
- Updates `wiki/index.md` — a navigable category index with `[[wikilinks]]` to every content page. System pages (`overview`, `purpose`, `dashboard`) are automatically excluded from the index — the LLM never creates self-links or meta-page entries.
- Updates `wiki/purpose.md` — a structured statement of what belongs in this wiki, who uses it, and what questions it answers
- Updates `AGENTS.md` — domain-specific ingest and query guidelines the LLM reads on every operation
- Stamps a `categories:` field on each content page's YAML frontmatter so pages are queryable by category
- Regenerates `ROUTING.md` if it already exists, to keep BM25 routing in sync with the new index structure (first-time creation requires `synthadoc routing init` — see Step 9)

After scaffold, open `wiki/index.md` in Obsidian or your editor to review the generated category layout. You can manually edit the user zone above the `<!-- synthadoc:scaffold -->` marker — that content is preserved across scaffold re-runs.

---

## Step 8 — Run lint and promote pages to active

**Terminal:**

```bash
synthadoc lint run
```

**Obsidian plugin:** `Cmd/Ctrl+P` → **Synthadoc: Lint: run...**

**What this does:**

Lint runs three passes over every `draft` page:

1. **Lifecycle promotion** — Pages with sufficient citation coverage and no contradictions are promoted from `draft` → `active`.
2. **Orphan detection** — Pages with no inbound wikilinks are flagged as orphans so you can wire them into the graph.
3. **Adversarial review** — A second LLM agent independently reviews each claim and raises warnings where content is imprecise, overstated, or potentially incorrect.

After lint, check the report:

**Terminal:**

```bash
synthadoc lint report
```

**Obsidian plugin:** `Cmd/Ctrl+P` → **Synthadoc: Lint: report**

Expected outcome for this example:

```
Page lifecycle:
  active   7
  draft    0

0 contradiction(s), 2 orphan(s), 2 adversarial warning(s), 0 citation issue(s).
```

The 2 adversarial warnings are content-level precision issues in the source material (e.g., EBITDA multiple ranges presented as universal market norms). They do not block lifecycle promotion — they are surfaced for your review. If you correct the source file, re-ingest with `--force` and re-run lint.

The 2 orphans are pages with no inbound wikilinks yet — scaffold (Step 7) and routing (Step 9) will wire them into the graph.

> **Lint and scaffold on a schedule:** Both `synthadoc lint run` and `synthadoc scaffold` are good candidates for recurring scheduled runs — lint keeps lifecycle state current, scaffold keeps the index and category structure in sync as new pages are added. See [Scheduling recurring operations](../../user-quick-start-guide.md#step-16--scheduling-recurring-operations) in the quick-start guide.

---

## Step 9 — Initialise and validate ROUTING.md

`ROUTING.md` groups your pages into named topic branches so queries only search the most relevant slice — instead of scoring all pages on every query. Scaffold (Step 7) keeps it in sync once it exists, but the first-time creation is a separate step.

**Why this matters for M&A due diligence:** The AquaFlow wiki spans distinctly separate workstreams — LBO modeling, covenant analysis, quality of earnings, ESG, legal DD, and exit valuation. Without routing, a query about EBITDA multiples searches ESG and legal pages too, adding noise to the ranked results. With routing, the query engine resolves the branch first and searches only the relevant pages, improving precision and reducing latency.

**Create ROUTING.md from the current index:**

```bash
synthadoc routing init
```

Or in Obsidian: `Cmd/Ctrl+P` → **Synthadoc: Routing: manage ROUTING.md** → click **Init**.

**Validate — check for dangling slugs or cross-branch duplicates:**

```bash
synthadoc routing validate
```

**Clean — remove any dangling entries after page deletions:**

```bash
synthadoc routing clean
```

> **Keeping routing in sync:** After adding new pages via ingest, re-run `synthadoc scaffold` (Step 7) — it regenerates `ROUTING.md` automatically because the file now exists. `routing init` is a one-time bootstrap command and will refuse to run if `ROUTING.md` is already present.

---

## Step 10 — Review citations

Every answer includes inline citations in the format `^[filename:L-L]`, where `filename` is the source document and `L-L` is the line range in that file. In the web UI these render as superscripts you can hover or click to see the original passage. In Obsidian they render as footnotes. Citations give you a direct audit trail from every claim back to the source line — essential for M&A due diligence where verifiability matters.

**Review citations in Obsidian — Page Provenance:**

Open the command palette → **Synthadoc: View Page Provenance**. A sortable, paginated table shows every citation across the wiki. Filter by slug to see all claims for one page, or sort by source file to audit a single document. Click any row to open the Source Viewer at the exact source line range.

**Audit citations from the CLI:**

```bash
# All citations for one page
synthadoc audit citations --page quality-of-earnings

# Citations that failed validation across the whole wiki
synthadoc audit citations --broken
```

![Page Provenance panel in Obsidian showing citation audit trail for the QoE page](png/page-level-citation.png)

---

## Step 11 — Open the web UI and run queries

With the server running from Step 5, open the web UI:

```bash
synthadoc web
```

Your browser opens automatically at the port shown in the server startup banner. The web UI has two entry points:

- **Chat** — type a natural-language question; the answer streams back token by token with inline citations
- **Knowledge Graph** — a D3.js visualisation of all pages and their wikilink relationships; click any node to use that page as the scoped entry point for your query

---

## Sample queries and expected results

Type each query into the Chat tab. The expected result tells you what to look for — specific facts, which pages get cited, and for the high-complexity queries, whether the answer correctly synthesises across multiple workstreams. If a query returns a noticeably weaker answer, the most common causes are a provider with insufficient context window, or a page that did not fully promote to `active` during lint.

### English — Medium complexity

**Q1. What are AquaFlow Systems Inc.'s key financial metrics for FY2023?**

Expected: Revenue $312.4M, LTM Adjusted EBITDA $74.8M, EBITDA margin 23.9%, ~1,240 employees, headquartered in Aurora, CO. Revenue mix: Equipment Sales 41%, Service Contracts 37%, Consumables/Parts 22%. Source cited: `aquaflow-systems`.

![Q1 answer in the web UI — financial metrics with inline citations](png/query-en1.png)

---

**Q2. What regulatory drivers are creating near-term demand in the US water treatment equipment market?**

Expected: EPA's April 2024 PFAS National Primary Drinking Water Regulation (2,400 utilities must install treatment by 2029; $4–6B addressable capital cycle); IIJA water infrastructure allocations supporting municipal capex; state-level PFAS rules in CA, MI, and NY exceeding federal minimums. Regulatory exposure noted as symmetric — PFAS tailwinds are an upside driver but adverse regulation of PFAS-containing products is a tracked downside risk. Sources cited: `aquaflow-systems`, `lbo-model-structure-and-mechanics`, `pe-exit-strategies-and-valuation-benchmarks`, `legal-due-diligence`, `esg-due-diligence`.

---

**Q3. What adjustments does a quality of earnings analysis make to reported EBITDA?**

Expected: Covers standard addbacks (excess owner compensation, one-time legal/restructuring, impairments, non-cash charges) and deductions (premature revenue recognition, non-recurring contract revenue, divested-ops EBITDA). Revenue quality analysis — contracted vs. transactional mix, customer concentration, renewal rates, ASC 606 compliance. Working capital normalisation to TTM average. QoE typically reduces management's adjusted EBITDA by 5–15%. Sources cited: `quality-of-earnings`, `covenant-analysis`, `lbo-model-structure-and-mechanics`.

---

**Q4. What are the primary legal workstreams in a water infrastructure LBO due diligence?**

Expected: Seven primary workstreams — (1) corporate & governance (cap table, change-of-control consent rights); (2) material contracts (DMWA $19.4M contract at 6.2% of LTM revenue, top-10 customer concentration at 38%); (3) IP (14 U.S. patents, 3 provisional PFAS-series filings Q1 2024); (4) litigation & disputes; (5) regulatory compliance (Phase I ESA, NPDES, PFAS screen, NSF/ANSI 55); (6) real property (185,000 sq ft Aurora facility + 22 service centres); (7) debt & finance (credit facility change-of-control triggers). Cross-cutting: RWI at 3–4% premium with PFAS carved out, escrow 12–24 months. Sources cited: `legal-due-diligence`, `aquaflow-systems`, `quality-of-earnings`, `pe-exit-strategies-and-valuation-benchmarks`.

---

**Q5. What EBITDA multiple range is cited for water infrastructure exit valuations?**

Expected: Sector range 7.0x (low) to 12.5x (high) with a 9.0x median; mid-market water treatment ($150–500M revenue, 20–30% margin) comparables cluster at 8.5–11x EV/EBITDA (median 9.0–9.5x). Xylem/Evoqua (2023) cited at 14.8x as a premium strategic comp. Companies with >60% recurring revenue, technology differentiation, and PFAS/regulatory tailwinds trade at the upper end; customer concentration >15% and declining margins compress toward low end. Strategics pay 1–2x EBITDA turns above PE buyers. Sources cited: `pe-exit-strategies-and-valuation-benchmarks`, `lbo-model-structure-and-mechanics`.

---

### English — High complexity

**Q6. How do AquaFlow Systems' FY2023 financials compare to the valuation benchmarks, and what does that imply for entry price?**

Expected: Cross-references AquaFlow's $74.8M EBITDA against the mid-market cohort range (8.5x–11x), implying a base-case EV of $673M–$711M at 9.0x–9.5x. Technology differentiation (14 patents, PurePath PFAS series) and PFAS regulatory tailwinds (EPA NPDWR April 2024, 2,400 community water systems, $4–6B addressable cycle) support upper-half positioning; 59% recurring revenue (just below the >60% upper-end threshold) and ESG B- social score (turnover 18.4%, LTIR 1.8) and PFAS RWI exclusion asymmetry cap the multiple below 11x. QoE-adjustment trap noted: a 10% QoE haircut compresses adjusted EBITDA to ~$67.3M and re-rates the same dollar entry to ~10x. DMWA $19.4M contract (6.2% of LTM revenue, expires Dec 31 2024) flagged as re-bid risk. Sources cited: `aquaflow-systems`, `lbo-model-structure-and-mechanics`, `pe-exit-strategies-and-valuation-benchmarks`, `quality-of-earnings`, `covenant-analysis`, `esg-due-diligence`, `legal-due-diligence`.

---

**Q7. What covenant package is consistent with AquaFlow Systems' financial profile for a typical water infrastructure LBO?**

Expected: Covenant-lite TLB ($318M @ SOFR+250–450 bps) with springing revolver maintenance test (>35% drawn), 5.0x entering leverage, 5.5x Total Net Leverage covenant (0.5x headroom = $37.4M EBITDA buffer), senior secured ≤4.5x, interest coverage ≥2.0x, FCCR ≥1.0x. Equity cure right (2–4 of 8 quarters), $50M undrawn revolver, 50–75% excess cash sweep. Downside stress: –9% EBITDA to $68M pushes leverage to 5.5x exactly at breach. Flags QoE haircut (5–15%) compressing headroom, DMWA $19.4M re-bid binary event, and PFAS RWI exclusion as key package risks. Sources cited: `aquaflow-systems`, `covenant-analysis`, `lbo-model-structure-and-mechanics`, `quality-of-earnings`, `legal-due-diligence`, `pe-exit-strategies-and-valuation-benchmarks`.

---

**Q8. What risks does each of the three diligence workstreams — QoE, legal, and ESG — uniquely surface for a water treatment company?**

Expected: QoE — consumable-recurring reclassification (59% mix at risk), DMWA at 5% revenue-quality threshold, segment margin durability (service 55–65% vs equipment 35–45%), add-back validity (5–15% haircut), ASC 606 service recognition; Legal — DMWA change-of-control and re-bid risk, HydraFlo patent validity/expiration, PFAS regulatory screen (upside–downside asymmetry), RWI PFAS exclusion, debt change-of-control refinancing trigger, FLSA classification for 318 field technicians, Phase I ESA on 185,000 sq ft Aurora facility; ESG — PFAS waste-stream liability screen, Scope 1/2/3 carbon benchmarking (12.3 mtCO₂e/$1M, 16% below sector), LTIR vs. sector (1.8 vs 1.6), DEI gap at VP+, board independence (71%), LP mandate compliance. PFAS surfaces in all three streams (legal compliance, ESG waste-stream, RWI exclusion) with different mitigation paths. Sources cited: `quality-of-earnings`, `legal-due-diligence`, `esg-due-diligence`, `aquaflow-systems`, `covenant-analysis`, `pe-exit-strategies-and-valuation-benchmarks`, `lbo-model-structure-and-mechanics`.

---

**Q9. How should ESG diligence findings on a water treatment target translate into deal structure — specifically covenants and exit multiple sensitivity?**

Expected: Three-channel translation — (i) Covenants: ESG findings (PFAS downside, carbon cost shock, social remediation costs) argue for lower entry leverage (4.5–4.75x), tighter TNL covenant (≤5.0–5.25x), larger revolver buffer, and tighter EBITDA add-back caps excluding ESG remediation; (ii) Purchase price / RWI / escrow: Phase I/II ESA on 185,000 sq ft Aurora facility, specific PFAS indemnity outside RWI (RWI excludes PFAS per legal-dd), environmental escrow for RECs; (iii) Exit multiple sensitivity by path: strategic sale ±0.5–1.0x turn ESG premium/discount (sustainability mandates), S2S secondary (ESG cleanliness expands buyer universe), IPO (B+/70 composite borderline — B- social must improve to A- for institutional screening). Net ~±$75M EV per turn on $74.8M EBITDA base. Sources cited: `esg-due-diligence`, `covenant-analysis`, `lbo-model-structure-and-mechanics`, `pe-exit-strategies-and-valuation-benchmarks`, `legal-due-diligence`, `quality-of-earnings`, `aquaflow-systems`.

---

**Q10. If AquaFlow Capital exits AquaFlow Systems in 3–5 years, what exit pathways and valuation approach are most defensible?**

Expected: Three probability-weighted exit paths — S2S secondary (50%, 8.5–10.0x, most likely given $312M revenue sub-platform scale), strategic sale (35%, 10.0–11.5x, Xylem/Veolia/Hydra Solutions universe), IPO (15%, 9.0–13.0x, borderline eligibility at $312M revenue). Year-4 base-case S2S: EBITDA $117M × 9.0x = $1,053M EV, $215M net debt, $838M equity vs. ~$280M check = ~3.2x MOIC / ~33% IRR. Return decomposition: ~64% EBITDA growth, ~27% debt paydown, 0% multiple expansion (conservative convention). Three key pre-exit risks: DMWA re-bid (Dec 31 2024), B- social ESG sub-score (turnover, LTIR, DEI), and 59% recurring revenue just below the 60% upper-end threshold. Sources cited: `pe-exit-strategies-and-valuation-benchmarks`, `lbo-model-structure-and-mechanics`, `aquaflow-systems`, `covenant-analysis`, `quality-of-earnings`, `esg-due-diligence`, `legal-due-diligence`.

---

### Chinese — Cross-lingual retrieval

All wiki pages are in English. These queries are in Chinese. Synthadoc's retrieval pipeline handles CJK input natively — character-level BM25 tokenisation matches Chinese query terms against English content, with cosine similarity reranking for precision. Answers come back in the language of the query; no translation step or separate index is needed.

---

**Q11：AquaFlow Systems公司在美国水处理设备市场中的竞争定位如何？**

预期答案（中文回答）：市场为适度分散结构；竞争对手：Hydra Solutions Corp.（$520M收入，Mountain West领导者）、Xylem（$7.5B/14.8x EBITDA收购Evoqua）、Veolia（$15B SUEZ交易）；AquaFlow $312.4M收入定位为补强收购级（非平台级）；差异化要素：22个区域服务中心+318名技术员、AquaView IoT平台78%渗透率、PurePath PFAS系列（2024 Q1新增3项临时专利）、市政客户关系；经常性收入59%略低于60%上端门槛；PFAS监管双向对称（EPA NPDWR顺风 vs. 产品监管逆风）。引用来源：`aquaflow-systems`，`pe-exit-strategies-and-valuation-benchmarks`，`quality-of-earnings`，`legal-due-diligence`，`lbo-model-structure-and-mechanics`，`covenant-analysis`，`esg-due-diligence`。

![Q11 Chinese query answer in the web UI — retrieved from English wiki, responded in Chinese](png/query-cn1.png)

---

**Q12：杠杆收购模型的关键财务指标和运作机制是什么？**

预期答案（中文回答）：涵盖LBO核心机制——①Sources & Uses表（TLB $318M/50%、循环信贷$50M未提取、次级票据$56M、股权$261M/41%）；②进入倍数7–12x、目标杠杆4.0–6.0x；③EBITDA定义与加项（QoE标准削减5–15%）；④现金流瀑布与债务偿付（超额现金扫除50–75%，第4年Net Debt/EBITDA可从5.0x降至3.0x）；⑤维护性契约（TNL≤5.5x，高级担保≤4.5x，ICR≥2.0x，FCCR≥1.0x，cov-lite结构，缓冲1.0–2.0x为审慎范围）；⑥回报三驱动（EBITDA增长60–70%、债务偿付、倍数扩张，保守惯例：退出倍数≤进入倍数）；⑦MIP 5–15%股权池；⑧跨工作流集成。引用来源：`lbo-model-structure-and-mechanics`，`covenant-analysis`，`pe-exit-strategies-and-valuation-benchmarks`，`quality-of-earnings`，`aquaflow-systems`，`legal-due-diligence`，`esg-due-diligence`。

---

**Q13：水务基础设施投资的ESG尽调重点关注哪些方面？**

预期答案（中文回答）：三维度九要点——①环境：Phase I/II ESA（Aurora 185,000 sq ft设施）、Scope 1/2/3碳强度（AquaFlow 12.3 mtCO₂e/$1M，低于行业16%）、PFAS双向筛查（产品监管逆风 vs. 治理业务顺风）、气候风险（物理+转型）；②社会：LTIR vs. 行业基准（1.8 vs. 1.6）、流失率18.4%、VP+ DEI缺口、供应链劳工标准；③治理：董事会独立性（71%，超65%优选门槛）、审计委员会100%独立、长期股权激励权重、可持续报告鉴证。ESG对退出倍数影响：B+/70综合分支撑LP筛查，B-社会子项是IPO和上端估值的阻碍；整改路径：DEI正式化、安全项目投入、SASB/TCFD报告。引用来源：`esg-due-diligence`，`aquaflow-systems`，`pe-exit-strategies-and-valuation-benchmarks`，`legal-due-diligence`，`lbo-model-structure-and-mechanics`，`quality-of-earnings`，`covenant-analysis`。

---

**Q14（高复杂）：综合质量收益分析、法律尽调和ESG尽调，AquaFlow Systems作为LBO收购标的面临哪些主要风险，应如何在交易结构中加以应对？**

预期答案（中文回答）：14项风险聚类为三大风险簇——①EBITDA基础并发消耗（QoE减损5–15% + DMWA重新竞标场景 + ESG修复成本 + PFAS监管逆风，同步侵蚀0.5x契约缓冲）；②退出倍数同步压缩（耗材重分类→经常性从59%降至mid-50s，失标DMWA→集中度上升，B-社会子项，PFAS逆风，任三项同时显现≈$187M EV损失）；③退出端二阶冲击（进入时未解决的风险在S2S/战略买家重复尽调中被重新定价）。交易结构应对：收购价格以QoE-adjusted EBITDA为锚点；PFAS特殊赔偿（标准RWI外）+环境托管；TNL契约收紧至≤5.0–5.25x；进入杠杆降至4.5–4.75x；ESG修复成本不通过EBITDA加项体现；75%超额现金扫除；退出路径差异化（战略出售PFAS须托管，S2S ESG需达B+/A-，IPO需SASB/TCFD+B-社会子项修复）。引用来源：`quality-of-earnings`，`legal-due-diligence`，`esg-due-diligence`，`aquaflow-systems`，`covenant-analysis`，`lbo-model-structure-and-mechanics`，`pe-exit-strategies-and-valuation-benchmarks`。

---

**Q15（高复杂）：基于当前水务基础设施市场环境，AquaFlow Capital应采取何种退出策略，预期回报率和估值倍数范围是多少？**

预期答案（中文回答）：概率加权三路径——S2S二级50%（8.0–10.0x，基础9.0x）、战略出售35%（9.0–11.5x，基础10.5x，Xylem/Veolia/Hydra Solutions买家宇宙）、IPO 15%（9.0–13.0x，基础11.0x，$312M收入处于可行区间下端）。预期回报：基础情景~3.0–3.6x MOIC / ~33–38% IRR（第4年退出），回报归因~64% EBITDA增长（$74.8M→$117M）+~27%债务偿还（$374M→$215M）+0%倍数扩张（保守惯例）。支撑上端倍数的因素：EPA NPDWR PFAS顺风、IoT 78%渗透率、技术差异化。倍数压力点：经常性收入59%仅差1pp达60%门槛、DMWA重新竞标（2024年12月31日）、B-社会子分、PFAS双向对称。引用来源：`pe-exit-strategies-and-valuation-benchmarks`，`lbo-model-structure-and-mechanics`，`aquaflow-systems`，`quality-of-earnings`，`covenant-analysis`，`esg-due-diligence`，`legal-due-diligence`。

---

## Maintaining your wiki

Once the wiki is live, a small set of CLI commands covers all routine maintenance:


| Operation                      | Command                                                     | When to run                                       |
| ------------------------------ | ----------------------------------------------------------- | ------------------------------------------------- |
| Add a new source               | `synthadoc ingest <file>`                                   | Any time new material arrives                     |
| Regenerate a page              | `synthadoc ingest <file> --force`                           | After updating a source file                      |
| Re-index categories            | `synthadoc scaffold`                                        | After adding several new pages                    |
| Promote drafts / check quality | `synthadoc lint run`                                        | Weekly, or after bulk ingest                      |
| Review lint findings           | `synthadoc lint report`                                     | After every lint run                              |
| Check wiki health              | `synthadoc status`                                          | Any time                                          |
| Resolve a contradiction        | Edit the flagged page, then `synthadoc lint run`            | When a new source conflicts with existing content |
| Backup                         | `synthadoc backup`                                          | Before major changes                              |

### Re-ingest and source deduplication

Running `synthadoc ingest <file> --force` is safe to repeat. The `sources` list on each page deduplicates by `(file, content-hash)` — re-ingesting an unchanged file never adds a duplicate entry. If the file content has changed (new hash), the new source record is appended alongside the original, preserving the full provenance trail.

### Lifecycle states

Pages move through five states: `draft` → `active` → `stale` → `contradicted` / `archived`. Lint promotes `draft` to `active` automatically when citation coverage and content quality thresholds are met. If a source you ingest contradicts an existing active page, the existing page is flagged `contradicted` and you are prompted to resolve it manually.

---

## Further reading

- [AquaFlow LLM Query Benchmark](evaluation/report/llm-query-benchmark.md) — query accuracy evaluation across all 15 sample queries, scored by provider and complexity tier
- [User Quick-Start Guide](../../user-quick-start-guide.md) — full feature walkthrough including Obsidian plugin, scheduling, ROUTING.md, context packs, export formats, MCP, and backup/restore
- [Design document](../../design.md) — architecture, data model, and system design
