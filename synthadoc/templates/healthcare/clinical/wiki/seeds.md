---
title: Getting Started — Clinical
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Clinical

## Recommended first ingests

**CDC MMWR (Morbidity and Mortality Weekly Report — free)**
```
synthadoc ingest "https://www.cdc.gov/mmwr/index.html" -w <wiki>
```

**USPSTF preventive care recommendations (free)**
```
synthadoc ingest "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics" -w <wiki>
```

## Recommended web searches

- `"<condition name>" clinical practice guidelines 2024 AHA ACC ACP` — specialty guidelines
- `PubMed "systematic review" "<condition>" treatment efficacy` — evidence base
- `"<medication name>" FDA prescribing information label` — official drug label
- `NIH clinical guidelines HIV diabetes hypertension` — NIH guideline library
- `GRADE evidence appraisal system clinical guidelines` — evidence quality framework

## First steps checklist

- [ ] Ingest the most current clinical guideline for your primary condition focus
- [ ] Create a condition page for each diagnosis in your practice scope
- [ ] Ingest a key drug reference for your formulary
- [ ] Run scaffold to build the index
