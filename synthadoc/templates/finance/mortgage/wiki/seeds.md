---
title: Getting Started — Mortgage
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Mortgage

## Recommended first ingests

**CFPB mortgage resources (public)**
```
synthadoc ingest "https://www.consumerfinance.gov/compliance/compliance-resources/mortgage-resources/" -w <wiki>
```

**FHFA conforming loan limits**
```
synthadoc ingest "https://www.fhfa.gov/DataTools/Downloads/Documents/Conforming-Loan-Limits/FullCountyLoanLimitList2025.csv" -w <wiki>
```

## Recommended web searches

- `Fannie Mae conforming loan limits 2025 county list` — current limits
- `CFPB TRID disclosure requirements lenders guide` — regulatory compliance
- `FHA handbook 4000.1 underwriting guidelines` — government loan policy
- `mortgage underwriting DTI ratio guidelines 2024` — debt-to-income standards
- `non-QM loan products lender guidelines 2024` — non-agency products

## First steps checklist

- [ ] Ingest your current underwriting guidelines document
- [ ] Create a product page for each loan type you originate
- [ ] Ingest CFPB TRID disclosure requirements
- [ ] Run scaffold to build the index