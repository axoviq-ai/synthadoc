---
title: Getting Started — Pharmaceutical
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Pharmaceutical

## Recommended first ingests

**FDA Drugs@FDA database (public)**
```
synthadoc ingest "https://www.accessdata.fda.gov/scripts/cder/daf/" -w <wiki>
```

**ClinicalTrials.gov for your indication**
```
synthadoc ingest "https://clinicaltrials.gov/search?cond=<indication>" -w <wiki>
```

## Recommended web searches

- `FDA guidance NDA BLA submission requirements 2024` — regulatory guidance
- `ICH E6 GCP guidelines clinical trial conduct` — GCP standards
- `FDA PDUFA drug approval timeline process` — approval process
- `EMA CHMP clinical trial guidelines 2024` — European requirements
- `"<mechanism of action>" preclinical efficacy models review` — translational science

## First steps checklist

- [ ] Ingest the FDA guidance document for your regulatory pathway
- [ ] Create a compound page for your lead asset
- [ ] Create a trial page for each active or completed clinical study
- [ ] Run scaffold to build the index