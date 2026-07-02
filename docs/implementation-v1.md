# Synthadoc Implementation Reference — v1.1.0 Evaluation Fixes

**Version:** 1.1.0
**Date:** 2026-07-02
**Audience:** Contributors implementing features or debugging the subsystems introduced
in the v1.1.0 evaluation sprint.

This document is the implementation companion to `docs/design-v1.md`. It describes
the internal structure of each new or modified subsystem, the data flow, and the
test strategy.

---

## Table of Contents

1. [Shared Citation Utilities](#1-shared-citation-utilities)
2. [Key Data Extraction (Pass 0)](#2-key-data-extraction-pass-0)
3. [BM25 TF Fallback](#3-bm25-tf-fallback)
4. [Compound Identifier Tokenization](#4-compound-identifier-tokenization)
5. [Active Page Contract — Decision Stage](#5-active-page-contract--decision-stage)
6. [Citation Annotation Reliability](#6-citation-annotation-reliability)
7. [Lint Check 5b — Citation Presence](#7-lint-check-5b--citation-presence)
8. [Web UI Citation Rendering](#8-web-ui-citation-rendering)
9. [Demo Sync Force Overwrite](#9-demo-sync-force-overwrite)
10. [Obsidian Reading View Default](#10-obsidian-reading-view-default)

---

## 1. Shared Citation Utilities

### Location

`synthadoc/agents/citations.py`

### Purpose

Single source of truth for the two regex patterns that identify citation markers in wiki
page content. Both the ingest annotation stage and the lint citation check import from
this module; neither defines its own copy.

### Patterns

| Constant | Pattern shape | Matches | Used by |
|----------|--------------|---------|---------|
| `CITATION_RE` | `^[filename:start-end]` | Well-formed citation markers | Ingest Pass 4, Lint Check 5 |
| `MALFORMED_CITE_RE` | `^[anything]` | Any bracket sequence that looks like a citation attempt | Lint Check 5 (malformed marker detection) |

### Canonical format

A valid citation marker has the form:

```
^[<filename>:<line_start>-<line_end>]
```

Where:
- `<filename>` is the base name of the source file (no directory prefix, no escaping)
- `<line_start>` and `<line_end>` are 1-based integer line numbers
- `<line_start>` ≤ `<line_end>`

Markers that do not satisfy all four constraints are detected by `MALFORMED_CITE_RE` but
not by `CITATION_RE`, and are reported as malformed by lint.

### Test strategy

- Happy path: `CITATION_RE` matches well-formed markers and captures all three groups.
- Boundary: single-line citation (`start == end`), very long filename, maximum line number.
- Failure: missing colon, non-numeric line numbers, empty filename, nested brackets —
  all must be matched by `MALFORMED_CITE_RE` but not by `CITATION_RE`.

---

## 2. Key Data Extraction (Pass 0)

### Location

Ingest pipeline — pre-LLM stage, runs before synthesis.

### Purpose

Deterministically extract numerical values, formulas, and identifiers from the source
text and append them as a structured block so the synthesis LLM sees them called out
explicitly.

### Algorithm

The extraction uses a set of named regex patterns applied in order to the raw source
text:

| Category | Examples captured |
|----------|-----------------|
| Integer / decimal measurements | `3.14`, `42`, `1,234,567` |
| Percentages | `12.5%`, `0.5 percent` |
| Currency amounts | `$1.2M`, `USD 50,000`, `€2.3B` |
| Ratios and rates | `5:1`, `3x`, `0.7 per year` |
| Formula fragments | `revenue / capex`, `EBITDA margin` |
| Underscore identifiers | `total_mv_cny`, `capex_growth_rate` |
| Date ranges | `2023–2026`, `Q1 2024` |

Extracted values are deduplicated and appended to the source as a section before the
text is passed to any LLM:

```
[Key Data — extracted by pre-processor]
- 3-year median
- 42%
- capex_growth_rate
- 2023–2026
```

### Constraints

- The pass runs entirely without an LLM call. It adds no token cost.
- It does not attempt to classify, rank, or resolve extracted values. That remains the
  LLM's responsibility.
- The appended section is clearly labeled so the LLM can distinguish extracted values
  from the source narrative.

### Test strategy

- Happy path: source with a variety of numeric forms — verify all are captured.
- Boundary: source with no numbers — appended section is empty or omitted.
- Boundary: source where the same value appears multiple times — deduplicated output.
- Edge case: values inside code fences or tables — verify they are still captured.
- Regression: sources used in the evaluation that triggered the original accuracy issue —
  verify final implementation values appear in the extracted section.

---

## 3. BM25 TF Fallback

### Location

Search subsystem — `bm25_search()` and related ranking functions.

### Purpose

Prevent empty search results in small corpora or high-IDF-collapse scenarios by falling
back to normalized term frequency scoring when BM25 produces all-zero scores.

### Algorithm

After BM25 scores are computed:

1. If any score is positive → return BM25 results as normal (no fallback).
2. If all scores are zero or negative → recompute using normalized TF:

```
TF_score(doc, query) = sum(count(term, doc) for term in query) / len(doc_tokens)
```

3. Sort by `TF_score` descending.
4. Return results with `tf_fallback = True` on each `SearchResult`.

### `SearchResult` schema change

A `tf_fallback: bool` field was added to the `SearchResult` type. This field is:
- `False` for all results produced by BM25.
- `True` for all results produced by TF fallback.
- Included in the serialized result returned by the API and recorded in the audit trail.

### Downstream consumers

- **Gap detection Signal 1** reads `tf_fallback` and suppresses the "fewer than 3
  candidates" signal when it is `True` (see section 4).
- **Audit trail** records `tf_fallback` to help operators identify queries that hit the
  fallback path.

### Test strategy

- Happy path: corpus of 10 documents, standard BM25 scores → `tf_fallback = False`.
- Boundary (fallback trigger): corpus of 2 documents where both contain the query term →
  BM25 collapses → `tf_fallback = True` on returned results.
- Boundary: empty corpus → no results, no fallback.
- Regression: the evaluation's "exact identifier" query against a 1-document wiki →
  results returned, `tf_fallback = True`.

---

## 4. Compound Identifier Tokenization

### Location

Search subsystem — tokenizer, applied at both index time and query time.

### Purpose

Expand underscore-separated identifiers into both the compound form and individual
components so that human-friendly queries match programmatic identifiers.

### Algorithm

During tokenization, after standard whitespace/punctuation splitting:

```
for each token:
    if "_" in token:
        emit(token)              # compound form
        emit(token.split("_"))   # components
```

Example:

```
"capex_growth rate"  →  ["capex_growth", "capex", "growth", "rate"]
```

The same expansion is applied:
1. At **index time** — when a page is added or updated in the BM25 corpus.
2. At **query time** — when the user's query is tokenized before scoring.

### Interaction with BM25

Adding component tokens increases the vocabulary size slightly. IDF for short component
tokens (e.g. `capex`, `growth`) may be lower than for the compound form, which means
BM25 will still rank exact compound matches higher than partial component matches. The
expansion improves recall without degrading precision for well-formed corpora.

### Test strategy

- Happy path: query `capex growth` against a page containing `capex_growth` → page
  returned.
- Happy path: query `capex_growth` → page returned (compound form matches directly).
- Boundary: token with multiple underscores (`a_b_c`) → `["a_b_c", "a", "b", "c"]`.
- Boundary: token with leading/trailing underscore (`_capex_`) → only split interior
  components; no empty strings emitted.
- No regression: non-underscore tokens unchanged.

---

## 5. Active Page Contract — Decision Stage

### Location

Ingest pipeline — decision stage (Pass 3).

### Changes

Two additions to the decision prompt template:

1. **RULE 1b** added between RULE 1 and RULE 2. The rule text states that a page with
   `status='active'` is human-reviewed and authoritative; the stage must use
   `action='flag'` (not `action='update'`) when the source provides a different value,
   date, formula, or conclusion.

2. **Status field** added to the context string for each candidate page shown to the
   decision stage. The context string for each page now includes `status=<value>` so the
   stage can read the lifecycle state when deciding how to handle the source.

### Cache version

The cache version for decision results was bumped to `v2` to invalidate results computed
without the full source text (Fix in section 1.3 of `docs/design-v1.md`). Any cached
decision result from `v1` will be recomputed on the next ingest run.

### Test strategy

- `test_decision_prompt_includes_page_status` (existing): verify `status=active` appears
  in the decision prompt text.
- Extension to the same test: verify `RULE 1b` text appears in the prompt.
- Extension to the same test: verify `action='flag'` appears in the RULE 1b text.
- New test: source that provides a different value for an `active` page → decision
  returns `action='flag'`, not `action='update'`.
- Boundary: source that adds a new topic to an `active` page → decision may return
  `action='update'`.

---

## 6. Citation Annotation Reliability

### Location

Ingest pipeline — annotation stage (Pass 4).

### Six bug fixes (A–F)

| Fix | What was wrong | What was changed |
|-----|---------------|-----------------|
| A — Sanity check | Scaffold pages could reach the annotation stage | Sanity check now explicitly tests for scaffold page slugs |
| B — Case sensitivity | Filename matching was case-sensitive | Filename comparison is now case-insensitive throughout the annotation stage |
| C — Truncation | Source was truncated by character count before line numbers were computed | Truncation now operates on the raw line list; line numbers refer to the original file |
| D — Empty source | Empty source string proceeded to annotation with no error | Empty-source guard added; writes `citation_pass4_empty_source` audit event and skips |
| E — `bust_cache` propagation | `--force` reingest did not propagate the bust flag to annotation | `bust_cache` is now passed explicitly through the entire call chain |
| F — Zero-citation caching | Zero-citation results were cached permanently | Zero-citation results are excluded from the cache; subsequent ingest re-attempts annotation |

### Test strategy

Each fix has a corresponding test:

- A: scaffold page slug (e.g. `index`, `purpose`, `agents`) → annotation stage skipped.
- B: source file named `Source.PDF` (uppercase) → annotation finds the file.
- C: source with 200 lines truncated to 50 → citation line numbers stay within 1–50.
- D: empty source string → `citation_pass4_empty_source` event written, page still saved.
- E: `bust_cache=True` path → cache is not read; annotation re-runs.
- F: first call returns zero citations → not cached; second call with better mock returns
  citations → they are cached and returned on the third call.

---

## 7. Lint Check 5b — Citation Presence

### Location

Lint subsystem — structural check stage.

### Algorithm

For each page being linted:

1. Count words in the page body (exclude YAML frontmatter).
2. Count `^[filename:L-L]` citation markers using `CITATION_RE` from the shared module.
3. If `word_count >= 50` and `citation_count == 0`: emit WARNING with
   `check_id="citation_presence"`.

The check result is included in the lint report under a new "Citation Issues" section
(alongside the existing "Contradictions", "Orphans", and "Adversarial Warnings" sections).

### Threshold rationale

50 words was chosen based on inspection of existing wiki pages:
- Structural pages (index.md, purpose.md, dashboard.md) are typically under 50 words in
  their prose content.
- Stub pages created from short sources are often 20–40 words.
- Pages with synthesised content from real sources are almost always above 100 words.

The 50-word threshold catches the vast majority of substantive pages while avoiding
false positives on stubs and structural pages.

### Test strategy

- Happy path: page with 100 words and 2 citation markers → no warning.
- Trigger: page with 60 words and 0 citation markers → WARNING emitted.
- Boundary (low): page with 49 words and 0 citation markers → no warning.
- Boundary (threshold): page with exactly 50 words and 0 citations → WARNING emitted.
- Structural page: index.md with 30 words → no warning.

---

## 8. Web UI Citation Rendering

### Location

Web UI React component — `MessageBubble.tsx` (or equivalent message display component).

### Algorithm

Before the Markdown renderer receives the content string, a transform function
(`obsidianCitationsToGfm`) converts `^[filename:L-L]` markers to GFM footnotes:

**Input:**

```
Alan Turing proposed the Turing Test in 1950.^[turing-bio.txt:12-24]
He also worked on machine intelligence.^[turing-bio.txt:30-45]
```

**Output:**

```
Alan Turing proposed the Turing Test in 1950.[^1]
He also worked on machine intelligence.[^2]

[^1]: turing-bio.txt lines 12–24
[^2]: turing-bio.txt lines 30–45
```

The function:
1. Collects all `^[...]` markers in order of appearance.
2. Replaces each with `[^N]` where N is its sequential index (1-based).
3. Appends a footnote definition section at the end of the content.
4. Returns the transformed string for the Markdown renderer.

### GFM renderer requirement

The Markdown renderer must have `remark-gfm` enabled (or equivalent) to process `[^N]`
footnote syntax. Without this, footnote references render as literal text.

### Test strategy (Vitest)

- Happy path: one marker → one footnote reference + one definition.
- Multiple markers: sequential numbering, correct mapping.
- No markers: content unchanged (no empty footnote section appended).
- Duplicate source files: two markers from the same file get separate footnote numbers.
- Boundary: marker at the very start of content, at the very end.

---

## 9. Demo Sync Force Overwrite

### Location

CLI — `demo sync` subcommand.

### Behavior

| Invocation | Behavior |
|-----------|---------|
| `synthadoc demo sync <name>` | Copies only files that do not exist in the target installation (additive) |
| `synthadoc demo sync <name> --force` | Overwrites all demo-managed files with the current template versions |

The `--force` flag does not affect:
- The wiki's `.synthadoc/` directory (config, audit database, job queue)
- Files created by ingest (wiki pages, raw sources ingested by the user)
- User-authored files

Only files that are part of the demo template (pre-built wiki pages, raw source files
bundled with the demo, scaffold files) are overwritten.

### Test strategy

- Without `--force`: existing files untouched; new template files copied.
- With `--force`: existing demo pages replaced with template versions.
- Config and audit files: never overwritten in either mode.
- User-created wiki pages (not in the template): not affected in either mode.

---

## 10. Obsidian Reading View Default

### Location

Plugin management — `plugin install` and `plugin upgrade` commands.

### Algorithm

After the plugin files are copied into the vault's `.obsidian/plugins/` directory:

1. Read `.obsidian/app.json` if it exists.
2. If the file does not exist: create it with `{"defaultViewMode": "preview"}`.
3. If the file exists and is valid JSON: parse it, set `defaultViewMode = "preview"`,
   write it back (preserving all other keys).
4. If the file exists but is malformed JSON: log a WARNING, skip the write, continue
   with the rest of the install. The install is not aborted.

### Return value semantics

The internal function that performs this write returns:
- `True` on success (file written).
- `False` if the file was malformed and the write was skipped.
- Raises only for unexpected filesystem errors (permissions, disk full).

### Test strategy

- Happy path: no `app.json` exists → file created with correct content.
- Happy path: `app.json` exists with other keys → only `defaultViewMode` added; other
  keys preserved.
- Idempotent: running twice does not corrupt the file.
- Malformed JSON: `app.json` contains `{broken` → returns `False`, WARNING logged, no
  file written.
- Existing `defaultViewMode` with a different value: overwritten to `"preview"`.
