---
title: Getting Started — Market Research
status: draft
confidence: low
type: concept
sources: []
---

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

- `"<market name>" market size TAM latest report` — market sizing
- `"<industry>" industry analysis Porter five forces` — competitive framework
- `"<competitor name>" annual report investor day latest` — competitor intelligence
- `consumer survey "<product category>" satisfaction NPS latest` — consumer data
- `"<industry>" market share leaders latest IDC Gartner Forrester` — analyst reports

## First steps checklist

- [ ] **Ingest your most recent industry report**:
  ```
  synthadoc ingest <path/to/industry-report.pdf> -w <wiki>
  ```
  Populates [[market-overview]] and [[market-sizing]].

- [ ] **Build competitor profiles** — for each top competitor, copy `raw_sources/competitors/template-competitor-profile.md`, fill it in, then:
  ```
  synthadoc ingest raw_sources/competitors/<competitor>.md -w <wiki>
  ```
  Or ingest their website directly: `synthadoc ingest "https://www.<competitor>.com" -w <wiki>`
  Populates [[competitor-profiles]] and [[competitive-landscape]].

- [ ] **Document your primary customer segment**:
  ```
  synthadoc ingest docs/customer-segments/ --batch -w <wiki>
  ```
  Populates [[consumer-segments]] and [[customer-insights]].

- [ ] **Ingest survey data**:
  ```
  synthadoc ingest docs/surveys/<survey>-topline.pdf -w <wiki>
  ```
  Populates [[surveys]] and [[research-reports]].

- [ ] **Run scaffold to build the index**
  ```
  synthadoc scaffold -w <wiki>
  ```
