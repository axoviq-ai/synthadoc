---
title: Getting Started — Public Health
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Public Health

## Recommended first ingests

**CDC FastStats — leading causes and prevalence data (public)**
```
synthadoc ingest "https://www.cdc.gov/nchs/fastats/leading-causes-of-death.htm" -w <wiki>
```

**WHO Global Health Observatory (public)**
```
synthadoc ingest "https://www.who.int/data/gho" -w <wiki>
```

## Recommended web searches

- `CDC community health assessment MAPP methodology toolkit` — assessment framework
- `WHO Global Burden of Disease study 2019 results` — global disease burden
- `"<condition>" incidence prevalence United States 2023 CDC` — US surveillance
- `Community Preventive Services Task Force recommendations` — evidence-based interventions
- `health equity social determinants framework Healthy People 2030` — equity frameworks

## First steps checklist

- [ ] Ingest the most recent CDC surveillance summary for your focus condition
- [ ] Create a disease burden page for the top 5 conditions in your population
- [ ] Ingest your most recent Community Health Assessment if available
- [ ] Run scaffold to build the index
