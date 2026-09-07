---
title: Matters
status: draft
confidence: low
type: concept
sources: []
---

# Matters

Active legal matter tracker. Each matter page records:

- **Matter identity** — matter ID, short title, matter type (contract dispute, regulatory inquiry, litigation, employment, M&A, IP, corporate)
- **Client / business unit** — internal sponsor and cost center absorbing the spend
- **Counsel** — lead internal attorney and external firm; current outside counsel guideline version
- **Budget vs. actual** — approved budget, spend to date, estimated total cost to close
- **Key dates** — deadlines, statutes of limitations, hearing dates, estimated resolution date
- **Status** — Open / On Hold / Closed / Settled; last updated date
- **Litigation hold** — whether a hold was issued, which custodians are covered
- **Next actions** — open action items with owner and due date

**How to populate:**

1. Copy `raw_sources/matters/template-matter.md`, fill in all fields for each active matter, then ingest:
   ```
   synthadoc ingest raw_sources/matters/<matter-id>-<title>.md -w <wiki>
   ```
2. For batch ingest of existing matter summaries:
   ```
   synthadoc ingest docs/legal/matters/ --batch -w <wiki>
   ```

Cross-link to [[contracts]], [[case-law]], [[outside-counsel]], and [[litigation]] for active matters in dispute.
