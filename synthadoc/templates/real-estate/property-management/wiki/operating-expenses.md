---
title: Operating Expenses
status: draft
confidence: low
type: concept
sources: []
---

# Operating Expenses

Operating expense tracking and CAM reconciliation for all managed properties. Populate by ingesting expense reports, invoices, and reconciliation statements.

Each operating expense record captures:

- **Expense identity** — expense category, property, period (month / year), vendor name, invoice number, invoice date
- **Expense categories** — common area maintenance (landscaping, cleaning, snow removal, security), repairs and maintenance, property management fees (% of gross revenue), utilities (common area electric, water/sewer), property insurance, real estate taxes, capital expenditure reserve
- **CAM pool** — which expenses are included in CAM per the lease, which are excluded (management fee caps, administrative charge, capital items, landlord-specific costs)
- **Tenant recovery** — tenant's pro-rata share (% based on rentable sf), estimated monthly CAM charge, year-end reconciliation calculation
- **Budget vs. actual** — budgeted amount, actual amount, variance, explanation of significant variances
- **Controllable vs. non-controllable** — classification for owner reporting (taxes and insurance are non-controllable; management and repairs are controllable)

**How to populate:**

1. Ingest your property operating statement or expense report:
   ```
   synthadoc ingest docs/financials/<property>-operating-statement.pdf -w <wiki>
   ```
2. Ingest your annual CAM reconciliation statements

Cross-link to [[rent-rolls]], [[leases]], and [[vendors]].
