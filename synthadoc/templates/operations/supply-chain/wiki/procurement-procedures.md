---
title: Procurement Procedures
status: draft
confidence: low
type: concept
sources: []
---

# Procurement Procedures

End-to-end procurement process. Each process step captures:

- **Need identification and requisition** — who can create a purchase requisition; required information on the req (part number, quantity, needed-by date, cost center, business justification)
- **Approval routing by spend threshold** — approval matrix: who approves purchase orders at each dollar tier (e.g., <$1k: buyer autonomous; $1k–$25k: manager; >$25k: director; capital: CFO)
- **Supplier selection** — for new suppliers: RFQ/RFP process, bid evaluation criteria, qualification requirements before placing a PO (link to [[suppliers]] for the approved vendor list)
- **Purchase order issuance** — how POs are generated (ERP, manual, blanket order releases); PO terms and conditions; acknowledgment required from supplier
- **Goods receipt and inspection** — receiving process; inspection requirements at receipt; how receiving data flows to finance for payment
- **Invoice matching and payment** — 2-way or 3-way match (PO, receipt, invoice); who resolves discrepancies; payment terms and ACH/check process

**How to populate:**

1. Ingest your procurement policy document:
   ```
   synthadoc ingest docs/supply-chain/procurement-policy.pdf -w <wiki>
   ```
2. Ingest best practices references:
   ```
   synthadoc ingest "https://www.procurify.com/blog/spend-management-for-better-procurement-practices" -w <wiki>
   ```

Cross-link to [[suppliers]] for vendor qualification, [[contracts]] for PO terms and master agreements, [[materials]] for the items being purchased, and [[inventory-management]] for the replenishment signals that trigger requisitions.
