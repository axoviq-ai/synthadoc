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

**SEC EDGAR company filings index (public filings, HTML)**
```
synthadoc ingest "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<ticker>&type=10-K&dateb=&owner=include&count=10" -w <wiki>
```

**Federal Reserve economic data (FRED — 10-year treasury rate)**
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
