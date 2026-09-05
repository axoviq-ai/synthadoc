---
title: Getting Started — Accounting
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Accounting

## Recommended first ingests

**IRS Publication 535 Business Expenses (free)**
```
synthadoc ingest "https://www.irs.gov/pub/irs-pdf/p535.pdf" -w <wiki>
```

**PCAOB auditing standards (free)**
```
synthadoc ingest "https://pcaobus.org/Standards/Auditing" -w <wiki>
```

## Recommended web searches

- `ASC 606 revenue recognition standard guidance examples` — GAAP revenue
- `ASC 842 lease accounting implementation guide` — lease standard
- `PCAOB AS 2201 internal control over financial reporting` — SOX requirements
- `IRS publication 946 MACRS depreciation` — tax depreciation
- `month-end close checklist accounting best practices` — close process

## First steps checklist

- [ ] Ingest your accounting policy manual
- [ ] Ingest the most recent audit management letter
- [ ] Create an account page for each major balance sheet line
- [ ] Ingest your chart of accounts and GL structure document
- [ ] Run scaffold to build the index