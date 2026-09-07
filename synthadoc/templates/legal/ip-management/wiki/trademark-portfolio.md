---
title: Trademark Portfolio
status: draft
confidence: low
type: concept
sources: []
---

# Trademark Portfolio

Inventory of registered trademarks, service marks, and trade dress. Each trademark record captures:

- **Mark identity** — mark text or description (for design marks); registration or application number; serial number
- **Jurisdiction(s)** — country or regional registration (US, EU CTM, WIPO Madrid designation, etc.)
- **Goods and services** — international class(es) (Nice classification) and the specific goods or services identified
- **Status** — Pending / Registered / Cancelled / Expired; registration date; renewal date
- **Use in commerce** — date of first use in commerce; date of first use in interstate commerce (US specific)
- **Specimens on file** — description and date of specimens filed to show use
- **Maintenance filings** — Section 8 declarations, Section 15 incontestability, renewal due dates
- **Owner** — registered owner; any consent, coexistence, or concurrent use agreements

**How to populate:**

1. Export your trademark portfolio from USPTO Trademark Status & Document Retrieval (TSDR):
   ```
   synthadoc ingest docs/ip/trademark-portfolio.xlsx -w <wiki>
   ```
2. Ingest trademark registration certificates:
   ```
   synthadoc ingest docs/ip/trademarks/ --batch -w <wiki>
   ```
3. Check USPTO TESS for individual marks:
   ```
   synthadoc ingest "https://tsdr.uspto.gov/#caseNumber=<reg-number>&caseType=US_REGISTRATION_NUMBER&searchType=statusSearch" -w <wiki>
   ```

Cross-link to [[ip-strategy]] for the brand protection objectives, [[licensing-agreements]] for licensed marks, and [[freedom-to-operate]] for clearance opinions obtained before adoption.
