# Getting Started — Academic Research

## Recommended first ingests

**arXiv preprints for your field (public)**
```
synthadoc ingest "https://arxiv.org/search/?query=<topic>&searchtype=all&start=0" -w <wiki>
```

**Semantic Scholar paper search (free)**
```
synthadoc ingest "https://www.semanticscholar.org/search?q=<topic>&sort=Relevance" -w <wiki>
```

## Recommended web searches

Topic hints for finding additional sources in this domain. Use these to discover more URLs
to ingest beyond the curated list below -- browse results and pick pages relevant to your use case.

- `"<research topic>" survey review latest arxiv` — recent survey papers
- `"<your field>" seminal papers citation classics` — foundational works
- `PubMed "<topic>" systematic review meta-analysis` — medical research
- `Google Scholar "<topic>" cited by >100 latest` — high-impact recent work
- `"<research question>" replication study reproducibility` — replication status

## First steps checklist

- [ ] **Log a paper** -- use our template or bring your own:
  - Template: copy `raw_sources/papers/template-paper-notes.md`, rename it
    (e.g. `vaswani-2017-attention.md`), fill in all sections, then:
    ```
    synthadoc ingest raw_sources/papers/<author>-<year>-<keyword>.md -w <wiki>
    ```
  - Own doc: place your existing reading notes in `raw_sources/papers/` and ingest them.
  Populates [[papers]] and [[citations]].

- [ ] **Pre-register a study protocol** -- use our template or bring your own:
  - Template: copy `raw_sources/protocols/template-research-protocol.md`, rename it
    (e.g. `study-2026-protocol.md`), fill in all sections, then:
    ```
    synthadoc ingest raw_sources/protocols/<study-name>-protocol.md -w <wiki>
    ```
  - Own doc: place your existing protocol in `raw_sources/protocols/` and ingest it.
  Populates [[research-questions]] and [[methodologies]].

- [ ] **Write a literature review note** -- use our template or bring your own:
  - Template: copy `raw_sources/lit-review/template-literature-review-note.md`, rename it
    (e.g. `vaswani-2017-lit-review-note.md`), fill in all sections, then:
    ```
    synthadoc ingest raw_sources/lit-review/<author>-<year>-lit-review-note.md -w <wiki>
    ```
  - Own doc: place your existing annotated bibliography in `raw_sources/lit-review/` and ingest it.
  Populates [[literature-review]] and [[findings]].

- [ ] **Review and promote candidates** -- all ingested pages land in `candidates/` for review.
  In Obsidian: open the command palette (Ctrl+P / Cmd+P) and run
  **"Synthadoc: Candidates: review candidate pages..."** to promote or discard each page.
  Or from CLI: `synthadoc candidates promote --all -w <wiki>`

- [ ] **Run lint to validate pages and activate drafts** -- with the server running,
  lint checks each page for quality then promotes clean draft pages to `active` status.
  In Obsidian: command palette (Ctrl+P / Cmd+P) > **"Synthadoc: Lint: run..."**
  Or from CLI: `synthadoc lint run -w <wiki>`

- [ ] **Check lifecycle states** -- confirm lint promoted your draft pages to `active`:
  ```
  synthadoc status -w <wiki>
  ```
  Pages still showing `draft` may have lint warnings -- review and re-run lint if needed.

- [ ] **Run scaffold to build the index**
  ```
  synthadoc scaffold -w <wiki>
  ```
