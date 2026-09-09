# Getting Started — Market Research

## Recommended first ingests

**US Census Bureau economic indicators (public)**
```
synthadoc ingest "https://www.census.gov/economic-indicators/" -w <wiki>
```

**SBA market research guide — industry analysis and competitive landscape (public)**
```
synthadoc ingest "https://www.sba.gov/business-guide/plan-your-business/market-research-competitive-analysis" -w <wiki>
```

## Recommended web searches

Topic hints for finding additional sources in this domain. Use these to discover more URLs
to ingest beyond the curated list below -- browse results and pick pages relevant to your use case.

- `"<market name>" market size TAM latest report` — market sizing
- `"<industry>" industry analysis Porter five forces` — competitive framework
- `"<competitor name>" annual report investor day latest` — competitor intelligence
- `consumer survey "<product category>" satisfaction NPS latest` — consumer data
- `"<industry>" market share leaders latest IDC Gartner Forrester` — analyst reports

## First steps checklist

- [ ] **Profile a competitor** -- use our template or bring your own:
  - Template: copy `raw_sources/competitors/template-competitor-profile.md`, rename it
    (e.g. `acme-corp.md`), fill in all sections, then:
    ```
    synthadoc ingest raw_sources/competitors/<competitor>.md -w <wiki>
    ```
  - Own doc: place your existing competitive analysis in `raw_sources/competitors/` and ingest it.
  Populates [[competitors]] and [[market-sizing]].

- [ ] **Design a survey** -- use our template or bring your own:
  - Template: copy `raw_sources/surveys/template-survey-design.md`, rename it
    (e.g. `q4-2026-customer-survey.md`), fill in all sections, then:
    ```
    synthadoc ingest raw_sources/surveys/<survey-name>.md -w <wiki>
    ```
  - Own doc: place your existing survey documentation in `raw_sources/surveys/` and ingest it.
  Populates [[survey-data]] and [[customer-segments]].

- [ ] **Build a market sizing model** -- use our template or bring your own:
  - Template: copy `raw_sources/reports/template-market-sizing.md`, rename it
    (e.g. `saas-us-market-sizing-2026.md`), fill in all sections, then:
    ```
    synthadoc ingest raw_sources/reports/<market-name>-sizing.md -w <wiki>
    ```
  - Own doc: place your existing market analysis in `raw_sources/reports/` and ingest it.
  Populates [[market-sizing]] and [[trends]].

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
