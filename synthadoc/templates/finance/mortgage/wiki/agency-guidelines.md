---
title: Agency Guidelines
status: draft
confidence: low
type: concept
sources: []
---

# Agency Guidelines

Fannie Mae, Freddie Mac, FHA, VA, and USDA guidelines governing loan eligibility, underwriting, and delivery. Populate by ingesting published agency guides and relevant bulletins.

Each agency guideline record captures:

- **Agency** — Fannie Mae (Selling/Servicing Guide) / Freddie Mac (Seller/Servicer Guide) / FHA (Handbook 4000.1) / VA (Lenders Handbook) / USDA (HB-1-3555)
- **Topic area** — eligibility (property, borrower, loan), underwriting (income, assets, credit), appraisal, MI/guaranty, delivery/pooling
- **Key requirements** — the specific rule, threshold, or standard (e.g. max DTI, eligible income types, condo approval requirements)
- **Effective date** — when the guideline took effect; superseded guidance noted
- **Bulletin / announcement number** — Selling Guide Announcement SEL-YYYY-XX, Mortgagee Letter ML-YYYY-XX, etc.
- **Lender overlay vs. agency minimum** — whether the institution has an overlay that is stricter than the agency floor

**How to populate:**

1. Ingest agency selling guides or key sections:
   - Fannie Mae: `synthadoc ingest "https://selling-guide.fanniemae.com/" -w <wiki>`
   - FHA: `synthadoc ingest "https://www.hud.gov/program_offices/housing/sfh/handbook_references" -w <wiki>`
2. Ingest agency bulletins when guidelines change
3. Cross-reference to [[loan-products]] for product-level application

Cross-link to [[underwriting-guidelines]], [[loan-products]], and [[loan-pipeline]].
