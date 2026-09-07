---
title: Loan Pipeline
status: draft
confidence: low
type: concept
sources: []
---

# Loan Pipeline

Tracks active loan applications from application through closing. Populate by ingesting application summaries from `raw_sources/pipeline/`.

Each pipeline entry captures:

- **Loan identification** — LOS loan number, application date, loan officer, processor, current stage (Pre-qual / Application / Processing / Underwriting / Conditional Approval / CTC / Funded / Denied / Withdrawn)
- **Property** — address, property type (SFR / Condo / 2-4 unit), occupancy (primary / second home / investment), appraised value, appraisal status
- **Loan parameters** — product type (link to [[loan-products]]), loan amount, LTV, CLTV, rate (locked / floating), rate lock expiration, estimated closing date
- **Borrower summary** *(no full SSN or full DOB)* — borrower type, FICO, monthly gross income, front-end DTI, back-end DTI, verified assets
- **Conditions and issues** — outstanding underwriting conditions, suspense status, key risk flags
- **Milestone log** — date, stage, notes for each stage change

**How to add a pipeline loan:**

1. Copy `raw_sources/pipeline/template-loan-application-summary.md` and rename it after the borrower and address (e.g. `smith-123-main-st.md`)
2. Fill in current application details
3. Run `synthadoc ingest raw_sources/pipeline/smith-123-main-st.md -w <wiki>`
4. Re-ingest at each stage change

Your LOS remains the system of record. This wiki provides searchable context and cross-linking.

Cross-link to [[loan-products]], [[underwriting-guidelines]], and [[agency-guidelines]].
