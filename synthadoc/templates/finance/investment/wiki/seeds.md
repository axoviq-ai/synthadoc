---
title: Getting Started — Investment Research
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Investment Research

## Recommended first ingests

Seed the wiki with real market context before adding proprietary research.

**SEC EDGAR full-text search (public filings)**
```
synthadoc ingest "https://efts.sec.gov/LATEST/search-index?q=%22<company>%22&dateRange=custom&startdt=2023-01-01&forms=10-K" -w <wiki>
```

**Federal Reserve economic data (FRED)**
```
synthadoc ingest "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10" -w <wiki>
```

## Recommended web searches

- `"<company name>" 10-K annual report site:sec.gov` — primary filing
- `"<company name>" earnings call transcript Q4 2024` — management commentary
- `"<sector>" industry outlook 2025 report filetype:pdf` — sector context
- `"<company name>" analyst initiation coverage price target` — sell-side consensus
- `LBO model tutorial investment banking valuation` — modeling reference

## First steps checklist

- [ ] Ingest the 10-K for your first portfolio company
- [ ] Promote the generated page from candidates: `synthadoc candidates list -w <wiki>`
- [ ] Create a stub deal page for each active position
- [ ] Ingest a sector report to populate [[sectors]]
- [ ] Run `synthadoc scaffold -w <wiki>` to update the index