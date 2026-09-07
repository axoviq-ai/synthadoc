---
title: Regulatory Compliance
status: draft
confidence: low
type: concept
sources: []
---

# Regulatory Compliance

Federal and state regulatory compliance program. Populate by ingesting examination reports, regulatory guidance, and compliance policies.

Each regulatory compliance record captures:

- **Primary regulator** — OCC / Federal Reserve / FDIC / NCUA / state banking department
- **Key regulations** — Reg E (electronic fund transfers), Reg Z / TILA (consumer credit), RESPA (mortgage), HMDA (mortgage data), CRA (community reinvestment), Reg DD (Truth in Savings), Reg B (ECOA / fair lending)
- **Compliance management system** — compliance officer, board oversight, compliance calendar, risk assessment process
- **Examination history** — most recent exam date, CAMELS / ROCA component ratings, MRA and MRIA findings, corrective action plans and deadlines
- **Fair lending** — HMDA data analysis, disparate impact testing, CRA exam rating and last exam date
- **Consumer complaints** — CFPB complaint portal monitoring, complaint categorization, resolution tracking
- **Policy inventory** — list of board-approved compliance policies, last review date, next review date

**How to populate:**

1. Ingest your most recent examination report (redacted as appropriate)
2. Ingest CFPB Supervisory Highlights relevant to your product mix
3. Ingest your compliance risk assessment or CRA public file

Cross-link to [[bsa-aml]], [[credit-risk]], [[deposit-products]], and [[lending-products]].
