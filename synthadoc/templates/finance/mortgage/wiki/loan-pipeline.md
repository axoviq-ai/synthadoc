---
title: Loan Pipeline
status: draft
confidence: low
type: concept
sources: []
---

# Loan Pipeline

Tracks active loan applications from application through closing.

Each pipeline entry captures:

- **Loan identification** — LOS loan number, application date, loan officer, processor, current stage (Pre-qual / Application / Processing / Underwriting / Conditional Approval / CTC / Funded / Denied / Withdrawn)
- **Property** — address, property type (SFR / Condo / 2-4 unit), occupancy (primary / second home / investment), appraised value, appraisal status
- **Loan parameters** — product type (link to [[loan-products]]), loan amount, LTV, CLTV, rate (locked / floating), rate lock expiration, estimated closing date
- **Borrower summary** *(no full SSN or full DOB)* — borrower type, FICO, monthly gross income, front-end DTI, back-end DTI, verified assets
- **Conditions and issues** — outstanding underwriting conditions, suspense status, key risk flags
- **Milestone log** — date, stage, notes for each stage change

Cross-link to [[loan-products]], [[underwriting-guidelines]], and [[agency-guidelines]].
