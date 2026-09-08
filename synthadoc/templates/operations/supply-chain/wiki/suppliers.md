---
title: Suppliers
status: draft
confidence: low
type: concept
sources: []
---

# Suppliers

Approved supplier register. Each supplier page records:

- **Supplier identity** — company name, supplier code, category (raw material, component, MRO, logistics, services), supply chain tier (Tier 1/2/3)
- **Approved status** — Approved / Conditional / Probationary / Disqualified; AVL approval date
- **Primary contact** — name, title, email, phone
- **Supply profile** — critical parts or materials supplied; standard and expedited lead times; minimum order quantity
- **Commercial terms** — payment terms, contract reference (link to [[contracts]])
- **Quality certification** — ISO 9001, IATF 16949, AS9100, or other; certificate expiry date
- **Performance** — last audit date and result; current DPPM; on-time delivery rate; open corrective actions
- **Risk profile** — sole-source flag; geographic or geopolitical risk; contingency supplier

**How to populate:**

1. Copy `raw_sources/suppliers/template-supplier-profile.md` for each key supplier, fill in all fields, then:
   ```
   synthadoc ingest raw_sources/suppliers/<supplier-code>-<name>.md -w <wiki>
   ```
2. Export your approved vendor list from your ERP or QMS:
   ```
   synthadoc ingest docs/supply-chain/approved-vendor-list.xlsx -w <wiki>
   ```

Cross-link to [[contracts]] for commercial agreements, [[materials]] for the parts each supplier provides, [[vendor-scorecards]] for performance ratings, and [[procurement-procedures]] for the qualification process.
