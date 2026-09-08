---
title: Financial Models
status: draft
confidence: low
type: concept
sources: []
---

# Financial Models

Property-level pro forma models for acquisition underwriting and ongoing performance tracking. Populate by ingesting completed financial model forms from `raw_sources/financial-models/`.

Each financial model page records:

- **Model overview** — property link, model date, hold period, model type (acquisition underwriting / annual update / exit analysis)
- **Key assumptions** — rent growth rate, vacancy rate, expense growth rate, exit cap rate, selling costs, debt terms
- **Year-by-year cash flows** — gross rent, vacancy loss, effective gross income (EGI), operating expenses, NOI, debt service, pre-tax cash flow
- **Exit analysis** — projected sale price (exit NOI ÷ exit cap rate), selling costs, loan payoff, net sale proceeds
- **Return summary** — IRR, equity multiple (EM), average cash-on-cash return, total distributions
- **Sensitivity analysis** — IRR across exit cap rate and rent growth scenarios
- **Actual vs. underwriting** — annual variance tracking once the property is operating

**How to build a financial model page:**

1. Copy `raw_sources/financial-models/template-financial-model.md` and rename it
2. Fill in assumptions and paste year-by-year results from your spreadsheet
3. Run `synthadoc ingest raw_sources/financial-models/<your-model>.md -w <wiki>`
4. Re-ingest annually or after major assumption changes

Cross-link model pages to [[properties]], [[deal-memos]], and [[debt-financing]].
