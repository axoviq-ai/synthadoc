# Financial Model: [Property Address or Alias]

> **How to use this form**
>
> 1. Copy this file and rename it (e.g. `oak-street-house-model.md`)
> 2. Fill in the assumptions — the projections section can be completed in
>    Excel/Sheets and the key results pasted back here
> 3. Run: `synthadoc ingest raw_sources/financial-models/oak-street-house-model.md -w <wiki>`
>
> This captures the summary of your underwriting model as structured wiki data
> so you can query projected returns across properties. Keep your full spreadsheet
> separately; update and re-ingest this file annually or after major assumption changes.
>
> Standard: NCREIF/CRE pro forma conventions; IRR per XIRR (date-weighted).

---

## Model Overview

- **Property:** (link to property page, e.g. [[oak-street-house]])
- **Property Type:** (SFH Detached / Condo / Townhouse / Duplex)
- **Model Date:** YYYY-MM-DD
- **Model Type:** (Acquisition Underwriting / Annual Update / Exit Analysis)
- **Hold Period:** years
- **Analyst / Source:** (self / broker / advisor)

---

## Key Assumptions

### Acquisition
- **Total Acquisition Cost:** $ (purchase price + closing costs)
- **Cash Invested (equity):** $
- **Loan Amount:** $
- **Interest Rate:** % — (Fixed / ARM — specify term)
- **Monthly Debt Service (P&I):** $
- **Annual Debt Service:** $

### Income & Expenses
- **Year 1 Monthly Rent:** $
- **Annual Rent Growth Rate:** % (base case)
- **Vacancy Rate:** % (applied each year)
- **Year 1 Operating Expenses:** $ (taxes + insurance + HOA + mgmt + reserves)
- **Annual Expense Growth Rate:** %

### Exit
- **Exit Year:** (year of planned sale, e.g. Year 7)
- **Exit Cap Rate:** % (base case)
- **Selling Costs at Exit:** % of gross sale price (typically 5–7%)

---

## Year-by-Year Cash Flow Projections

*Fill from your spreadsheet model. Add or remove rows to match your hold period.*

| Year | Gross Rent ($) | Vacancy ($) | EGI ($) | Op Expenses ($) | NOI ($) | Debt Service ($) | Pre-Tax Cash Flow ($) |
|------|---------------|------------|---------|----------------|---------|------------------|-----------------------|
| 1    |               |            |         |                |         |                  |                       |
| 2    |               |            |         |                |         |                  |                       |
| 3    |               |            |         |                |         |                  |                       |
| 4    |               |            |         |                |         |                  |                       |
| 5    |               |            |         |                |         |                  |                       |
| 6    |               |            |         |                |         |                  |                       |
| 7    |               |            |         |                |         |                  |                       |

**Formulas:**
- EGI = Gross Rent × (1 − Vacancy %)
- NOI = EGI − Operating Expenses
- Pre-Tax Cash Flow = NOI − Debt Service (negative = cash-flow negative)

---

## Exit Analysis

- **Exit Year NOI:** $
- **Exit Cap Rate (base case):** %
- **Gross Sale Price:** $ *(Exit NOI ÷ Exit Cap Rate)*
- **Selling Costs:** $ *(Gross Sale Price × Selling Cost %)*
- **Outstanding Loan Balance at Exit:** $
- **Net Sale Proceeds:** $ *(Gross Sale − Selling Costs − Loan Balance)*

---

## Return Summary

- **Total Cash Distributions (all years):** $ *(sum of annual pre-tax cash flows)*
- **Net Sale Proceeds:** $
- **Total Return:** $ *(cash distributions + net sale proceeds)*
- **Equity Multiple (EM):** × *(total return ÷ cash invested)*
- **IRR:** % *(use XIRR in Excel/Sheets on dated cash flows including −equity at acquisition and +net proceeds at exit)*
- **Average Annual Cash-on-Cash:** % *(average of: annual cash flow ÷ cash invested)*

---

## Sensitivity Analysis

*IRR at different exit cap rates and rent growth scenarios (base case highlighted).*

| | Exit Cap 4.5% | Exit Cap 5.0% | Exit Cap 5.5% | Exit Cap 6.0% |
|---|---|---|---|---|
| Rent growth 4% | | | | |
| Rent growth 3% | | **base** | | |
| Rent growth 2% | | | | |
| Rent growth 1% | | | | |

---

## Actual vs. Underwriting

*Update annually. Compare actual results to the underwriting model.*

| Year | Underwritten NOI ($) | Actual NOI ($) | Variance ($) | Variance (%) | Notes |
|------|---------------------|---------------|-------------|-------------|-------|
| 1    |                     |               |             |             |       |
| 2    |                     |               |             |             |       |
| 3    |                     |               |             |             |       |

---

## Notes & Key Risks

-
