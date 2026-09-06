---
title: Getting Started — Market Research
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Market Research

## Recommended first ingests

**Statista free reports (public summaries)**
```
synthadoc ingest "https://www.statista.com/topics/<topic-id>/" -w <wiki>
```

**US Census Bureau industry data**
```
synthadoc ingest "https://www.census.gov/eos/www/naics/" -w <wiki>
```

## Recommended web searches

- `"<market name>" market size TAM 2024 report` — market sizing
- `"<industry>" industry analysis Porter five forces` — competitive framework
- `"<competitor name>" annual report investor day 2024` — competitor intelligence
- `consumer survey "<product category>" satisfaction NPS 2024` — consumer data
- `"<industry>" market share leaders 2024 IDC Gartner Forrester` — analyst reports

## First steps checklist

- [ ] Ingest the most recent industry report for your market
- [ ] Create a market-overview page with size and growth data
- [ ] Create a competitor profile for your top 3 competitors
- [ ] Document your primary customer segment in [[consumer-segments]]
- [ ] Run scaffold to build the index
