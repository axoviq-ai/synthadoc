# Synthadoc Architecture Notes — v1.1.0 Evaluation Fixes

**Version:** 1.1.0
**Date:** 2026-07-02
**Audience:** Developers extending Synthadoc; contributors reviewing architectural decisions.

This document supplements `docs/design.md` with architectural notes for the twelve
targeted fixes applied in the v1.1.0 evaluation sprint. Each section describes the
problem, the design decision, and the rationale.

---

## Table of Contents

1. [Ingest Pipeline Updates](#1-ingest-pipeline-updates)
   - [1.1 Active Page Contract (RULE 1b)](#11-active-page-contract-rule-1b)
   - [1.2 Key Data Extraction Pass (Pass 0)](#12-key-data-extraction-pass-pass-0)
   - [1.3 Full Source Text to Decision Stage](#13-full-source-text-to-decision-stage)
   - [1.4 Pass 4 Zero-Citation Warning](#14-pass-4-zero-citation-warning)
   - [1.5 Citation Annotation Reliability Fixes](#15-citation-annotation-reliability-fixes)
2. [Lint System Updates](#2-lint-system-updates)
   - [2.1 Citation Presence Check (Check 5b)](#21-citation-presence-check-check-5b)
3. [Shared Citation Module](#3-shared-citation-module)
4. [Search System Updates](#4-search-system-updates)
   - [4.1 BM25 TF Fallback for Small Corpora](#41-bm25-tf-fallback-for-small-corpora)
   - [4.2 Compound Identifier Tokenization](#42-compound-identifier-tokenization)
   - [4.3 Gap Signal 1 Suppression with TF Fallback](#43-gap-signal-1-suppression-with-tf-fallback)
5. [Web UI Updates](#5-web-ui-updates)
   - [5.1 Citation Rendering in the Web UI](#51-citation-rendering-in-the-web-ui)
6. [Demo and Plugin Updates](#6-demo-and-plugin-updates)
   - [6.1 Demo Sync Force Flag](#61-demo-sync-force-flag)
   - [6.2 Obsidian Reading View Default on Install](#62-obsidian-reading-view-default-on-install)

---

## 1. Ingest Pipeline Updates

### 1.1 Active Page Contract (RULE 1b)

**Problem:** The ingest decision stage had no rule distinguishing pages that had been
human-reviewed from pages that were AI-generated drafts. A source document containing
both a draft value and a final implementation value could cause the decision stage to
update an already-reviewed active page with an earlier or contradicting value — because
the stage had no concept of page authority.

**Design:** RULE 1b was added to the decision prompt as a contract: a page with
`status='active'` has been human-reviewed and is authoritative. When a source provides
a different value, date, formula, or conclusion, the decision stage must flag the page
for review (`action='flag'`) rather than overwriting it. The stage may only update an
active page when the source adds a topic that the page does not yet mention at all.

The page status is now included in the context string for every candidate page shown to
the decision stage, so the stage can evaluate status before choosing an action.

**Rationale:** The lifecycle system exists to capture the distinction between
LLM-synthesised content and human-reviewed content. The decision stage must respect that
boundary. Without this contract, a single poorly-framed source could silently degrade an
authoritative page. This fix closes the gap between the lifecycle model described in
`docs/design.md §23` and the actual behavior of the decision stage.

---

### 1.2 Key Data Extraction Pass (Pass 0)

**Problem:** The ingest pipeline relied on the LLM to correctly carry numerical values,
formulas, and specific identifiers from the source into the synthesised page. For documents
that contain both draft and final values in different sections, the LLM tended to surface
the more memorable or contextually prominent value rather than the final implementation
value.

**Design:** A deterministic pre-extraction pass (Pass 0) was added before LLM synthesis.
This pass uses regex patterns to extract numeric measurements, formulas, percentages,
currency figures, ratios, and identifiers from the source text. The extracted values are
appended to the source as a structured "Key Data" section before the LLM receives the text.

The pass is regex-based and runs entirely without an LLM call, so it adds no token cost
and cannot hallucinate. It acts as an anchor: the LLM sees the key values called out
explicitly and is less likely to discard them in favour of a more narrative-friendly
alternative.

**Rationale:** LLMs are trained to produce coherent prose and may implicitly prefer
round numbers or earlier mentions when a document contains multiple plausible candidates
for the same concept. Pass 0 does not attempt to resolve which value is correct — it
ensures the LLM is aware of all candidates. The correctness judgment remains in the
synthesis stage, but it now operates on a richer, more complete representation of the
source.

---

### 1.3 Full Source Text to Decision Stage

**Problem:** The decision stage (Pass 3) received a 600-character content snippet of
existing wiki pages for context. This truncated view was insufficient for documents where
the key content — formulas, final values, conclusions — appeared in the latter half of a
longer source.

**Design:** The decision stage now receives the full source text, bounded by
`max_source_chars` (the same per-source truncation limit that applies throughout the
pipeline). The cache version was bumped to invalidate stale decision results that were
computed from the truncated input.

**Rationale:** The decision stage's job is to determine whether a source should create a
new page, update an existing page, or be flagged for review. That decision requires
understanding the full scope of what the source says — not a 600-character window that may
not contain the key claim. The `max_source_chars` boundary is the appropriate limit because
it is the same ceiling applied to every other LLM call in the pipeline; using a tighter
limit for the decision stage created an asymmetry where the decision was made on less
information than the synthesis step would receive.

---

### 1.4 Pass 4 Zero-Citation Warning

**Problem:** When the citation annotation pass (Pass 4) returned a page body with no
`^[filename:L-L]` markers, the result was silently accepted. There was no signal to the
operator that citation annotation had failed for that page.

**Design:** Pass 4 now checks whether any citation markers are present after the
annotation call returns. If none are found, it logs a WARNING-level message and writes
a `citation_pass4_no_markers` audit event, which records the page slug and source path.
The page is still written — the warning is diagnostic, not blocking.

**Rationale:** Zero citations is not always an error — very short sources or sources
composed entirely of structured data may legitimately produce no citations. However, it
is almost always a signal worth surfacing, because the most common cause is model
incompatibility: cheaper flash-tier models often do not follow the `^[FILENAME:L-L]`
format instruction precisely. The audit event allows operators to identify which pages
need re-ingest with a more capable model without having to inspect every page manually.

---

### 1.5 Citation Annotation Reliability Fixes

**Problem:** Six distinct bugs in the citation annotation stage caused incorrect behavior
in edge cases:

- (A) The sanity check that guards against annotating non-page content (e.g. AGENTS.md,
  index.md) was insufficiently restrictive, allowing some scaffold pages to be processed
  by the annotation pass.
- (B) Filename matching in the annotation stage was case-sensitive, causing citations to
  fail on case-variant filenames (e.g. `Source.PDF` vs `source.pdf`).
- (C) The source text was truncated by character count rather than by token count,
  causing line numbers in citation markers to be computed against the truncated text
  rather than the original source lines. This produced out-of-range line references.
- (D) If the source extraction step produced an empty string (e.g. a corrupted source
  file), the annotation stage proceeded and wrote an audit event without marking the
  failure.
- (E) The `bust_cache` flag was not propagated from the force-reingest caller into the
  annotation stage, so a `--force` re-ingest could return a cached (stale) annotation
  result.
- (F) When the annotation stage returned zero markers (as described in Fix 2 above), the
  result was cached. On subsequent runs the cached zero-citation result was returned
  immediately without re-attempting annotation, making the failure permanent until
  `cache clear` was run manually.

**Design:** Each bug was fixed independently with a targeted change:

- (A) The sanity check was expanded to explicitly test for scaffold page slugs, not just
  filename patterns.
- (B) Filename comparison was made case-insensitive throughout the annotation stage.
- (C) Truncation was moved to operate on the raw line list so that line numbers in citation
  markers refer to the original line numbering of the source file.
- (D) An empty-source guard was added before annotation; when triggered, it writes an
  explicit `citation_pass4_empty_source` audit event and skips the annotation stage.
- (E) The `bust_cache` propagation chain was audited and the flag is now passed explicitly
  to the annotation stage from every call site that sets it.
- (F) Zero-citation results are no longer cached. The cache stores only results where at
  least one valid marker was returned, so a subsequent re-ingest with a better model can
  produce a cacheable annotation result.

**Rationale:** These fixes collectively ensure that the citation annotation stage produces
accurate, reproducible results and that failures are visible rather than silently cached.
The zero-citation caching fix (F) is particularly important because it changed the failure
mode from "permanently broken until manual cache clear" to "automatically retried on the
next ingest".

---

## 2. Lint System Updates

### 2.1 Citation Presence Check (Check 5b)

**Problem:** Lint validated citation format (Check 5) — it flagged malformed markers and
out-of-range line references. But it did not check whether citations were present at all.
A substantive page with well-written prose but zero citations would pass lint as clean.
This meant the zero-citation condition identified in Fix 2 above was not surfaced by the
primary quality gate.

**Design:** A new lint check (5b) was added: if a page has 50 or more words in its body
and contains no `^[filename:L-L]` citation markers, lint emits a WARNING-level finding.
The threshold of 50 words distinguishes substantive pages from stubs or structural pages
(e.g. index.md, purpose.md) that legitimately have no citations.

The check emits a warning, not an error — it does not cause lint to mark the page as
contradicted or block promotion to active. It is diagnostic: an operator running
`synthadoc lint report` will see which pages lack citations and can re-ingest them with
a more capable model.

**Rationale:** The 50-word threshold was chosen to avoid false positives on structural
pages and short stub pages while still covering the vast majority of content pages.
Operator feedback showed that zero-citation pages are almost always the result of
model incompatibility, and surfacing them through the standard lint report is the most
natural place to discover the issue.

### Lint checks summary table (v1.1.0 additions)

| Check | Trigger | Severity | Resolution |
|-------|---------|----------|-----------|
| 5b | Page has ≥ 50 words and zero citation markers | WARNING | Re-ingest with a more capable model (Gemini 2.5 Flash or higher) |

---

## 3. Shared Citation Module

**Problem:** The citation marker regex pattern was defined independently in two places —
the ingest pipeline and the lint pipeline. When a fix or enhancement to the pattern was
made in one place, the other copy was not automatically updated, creating a divergence
risk.

**Design:** A single canonical citation module now defines two shared patterns:

- **Citation pattern** — matches the canonical `^[filename:start-end]` marker format.
  Used in both ingest (Pass 4 annotation) and lint (Check 5 citation validation).
- **Malformed citation pattern** — matches any `^[...]` shape, used to detect markers
  that are not valid citations (e.g. missing line numbers, extra colons). Used by lint
  Check 5.

Both the ingest and lint pipelines import from this shared module. Neither defines its
own copy of these patterns.

**Rationale:** A regex pattern shared across two subsystems is a single source of truth.
Duplication creates maintenance debt: any correction must be applied twice, and tests
written against one copy do not catch regressions in the other. Extracting to a shared
module makes it impossible for the two patterns to diverge.

---

## 4. Search System Updates

### 4.1 BM25 TF Fallback for Small Corpora

**Problem:** BM25 scoring is calibrated for corpora where document frequency provides a
meaningful inverse-document-frequency (IDF) signal. In very small wikis (fewer than ~5
documents) or in cases where a query term is present in all or most documents, BM25 can
assign a score of zero to every candidate — producing an empty result set even when the
term clearly exists in the wiki.

The same issue affected "echo effect" queries: when a term appears in every page of a
small wiki, the IDF component of BM25 collapses to zero, suppressing all results.

**Design:** When all BM25 scores in a result set are zero or negative, the search system
falls back to normalized term frequency (TF) scoring. TF scoring counts the raw number
of times query terms appear in each page and normalizes by document length. It is less
precise than BM25 on large corpora but reliably produces non-zero scores for any page
that contains the query term.

The fallback is transparent: the caller receives ranked results in the same format. A
`tf_fallback: bool` field on each search result indicates whether TF fallback was used,
which is recorded in the audit trail and used by downstream logic (see section 4.3).

**Rationale:** A search that returns zero results when the query term exists in the wiki
is a correctness failure, not a precision trade-off. TF fallback preserves the user's
expectation that "search for X" returns something when X is present, while BM25 continues
to be used for corpora where IDF provides a meaningful signal.

---

### 4.2 Compound Identifier Tokenization

**Problem:** BM25 tokenizes query and document text by splitting on whitespace and
punctuation. Underscore-separated identifiers (e.g. `capex_growth`, `total_mv_cny`)
were treated as single tokens. If a user searched for `capex growth` (with a space), the
tokenizer would not match `capex_growth`, even though the two forms refer to the same
concept.

**Design:** When a token contains underscores, the tokenizer now produces both the
compound form and each component as separate tokens:

```
capex_growth  →  ["capex_growth", "capex", "growth"]
```

This expansion happens at both index time (when pages are added to the BM25 corpus) and
query time (when the query is tokenized). The compound form is retained to preserve exact
match precision; the components are added to improve recall for human-friendly queries.

**Rationale:** Finance, engineering, and code-heavy wikis frequently use underscore
identifiers. A user querying for a concept in natural language should find pages that use
the programmatic form of the same identifier. The bidirectional expansion (index and query)
ensures that both `capex growth` and `capex_growth` in a query match pages that use either
form.

---

### 4.3 Gap Signal 1 Suppression with TF Fallback

**Problem:** Gap detection Signal 1 fires when a query returns fewer than 3 candidate
pages, indicating that the wiki has thin coverage of the topic. However, when TF fallback
is active (section 4.1), a small corpus with broad topic coverage may legitimately return
fewer than 3 candidates — not because the wiki lacks coverage, but because the wiki has
fewer than 3 pages in total.

**Design:** Gap Signal 1 (fewer than 3 candidates) is suppressed when TF fallback was
used to produce the result set. Other gap signals (empty results, low scores) continue to
fire normally.

**Rationale:** Suppressing Signal 1 in TF fallback mode prevents false knowledge-gap
callouts on small wikis. A user with a 3-page wiki should not be told their wiki has a
knowledge gap every time they query — that is expected behavior for a small corpus, not
a gap.

---

## 5. Web UI Updates

### 5.1 Citation Rendering in the Web UI

**Problem:** The web chat UI rendered wiki page content using a Markdown renderer that
did not recognize the `^[filename:L-L]` citation syntax. Citation markers appeared as
literal text rather than being rendered as clickable footnotes.

**Design:** A transformation pass was added to the web UI's message rendering component.
Before Markdown is rendered, `^[filename:L-L]` citation markers are converted to GitHub
Flavoured Markdown (GFM) footnote references and definitions:

- The inline marker `^[file.txt:10-20]` becomes a footnote reference (`[^1]`)
- A footnote definition (`[^1]: file.txt lines 10–20`) is appended to the content

The GFM renderer then handles the standard `[^n]` footnote syntax, producing numbered
clickable footnotes in the browser.

**Rationale:** The Obsidian plugin has a post-processor that converts citation markers to
interactive chips. The web UI has no equivalent post-processor, but the GFM footnote
conversion achieves a good approximation: footnote references are numbered sequentially,
and the footnote definition shows the source filename and line range. This is consistent
with how the content is expected to be consumed in the browser.

---

## 6. Demo and Plugin Updates

### 6.1 Demo Sync Force Flag

**Problem:** The `synthadoc demo sync` command was additive-only: it copied new pages and
source files from the latest demo template into an existing installation, but it never
overwrote existing files. This meant that after a demo template was updated (e.g. to
add citation markers to pre-built pages), existing demo installations could not receive
those improvements without a full re-install.

**Design:** A `--force` flag was added to `synthadoc demo sync`. When provided, the
command overwrites existing wiki pages and source files in the target installation with
the versions from the current template. Without `--force`, the command remains additive
only (no change to existing behavior for users who do not pass the flag).

**Rationale:** The demo wiki serves as both a tutorial environment and a quality
reference. When the template is updated to reflect new capabilities (citations, new pages,
updated examples), users who have an existing demo installation should be able to bring
their installation up to date without uninstalling and reinstalling. The `--force` flag
provides this path with explicit user intent — it is not the default because overwriting
files the user may have modified would be destructive without consent.

---

### 6.2 Obsidian Reading View Default on Install

**Problem:** Citation markers in wiki pages render as clickable footnotes only in
Obsidian's Reading View mode. The default Obsidian view when opening a vault is Live
Preview mode, which does not process citation markers. New users following the quick-start
guide would not see citations without knowing to switch to Reading View manually.

**Design:** The plugin install and plugin upgrade commands now write
`"defaultViewMode": "preview"` to `.obsidian/app.json` in the vault directory. This
setting causes Obsidian to open new notes in Reading View by default, ensuring that
citation chips are visible immediately after the plugin is installed.

If `.obsidian/app.json` does not exist, it is created with only this field. If it already
exists with other settings, only `defaultViewMode` is written; all other settings are
preserved. If the file exists but is malformed JSON, the write is skipped and a warning
is logged — the plugin install still succeeds.

**Rationale:** The citation experience is a core differentiator of Synthadoc's Obsidian
integration. Making it visible by default without requiring users to know about Reading
View eliminates a common first-impression failure. The design is minimally invasive: only
one key is written, and the behavior can be reversed by the user from Obsidian's settings
at any time.
