---
title: Inspections
status: draft
confidence: low
type: concept
sources: []
---

# Inspections

Building department, third-party, and lender inspection log for all development projects. Populate by ingesting inspection cards, third-party reports, and lender inspection certificates.

Each inspection record captures:

- **Inspection identity** — inspection number or permit number, project, inspection type (foundation / framing / electrical rough / plumbing rough / insulation / drywall / final / CO), inspector name and affiliation (AHJ / third-party / lender)
- **Schedule** — inspection request date, scheduled date, actual date
- **Result** — pass / conditional pass (corrections required) / fail; correction list with sign-off deadline
- **Lender draw inspections** — draw number, percent complete certified, disbursement amount requested, lender inspector notes
- **Third-party / special inspections** — required per IBC Chapter 17 (concrete, masonry, steel, soils); inspector's daily reports, certifications for permit closeout
- **Deficiency tracking** — open deficiencies, responsible party, target cure date, re-inspection result

**How to populate:**

1. Ingest your inspection log or third-party inspection reports:
   ```
   synthadoc ingest docs/inspections/ --batch -w <wiki>
   ```
2. Ingest lender inspection draw certificates

Cross-link to [[permits]], [[contractors]], [[change-orders]], and [[project-schedule]].
