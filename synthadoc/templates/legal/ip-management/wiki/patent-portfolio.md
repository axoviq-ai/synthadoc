---
title: Patent Portfolio
status: draft
confidence: low
type: concept
sources: []
---

# Patent Portfolio

Inventory of all patents and patent applications. Each patent page records:

- **Patent identity** — patent or application number, filing date, priority date, jurisdiction(s), title, technology area
- **Inventors & ownership** — inventor names, assignee, whether assignment has been recorded
- **Prosecution status** — Pending / Granted / Abandoned / Expired; grant date if issued; expiry date calculated from filing or priority date
- **Product coverage** — which products or features the patent covers; estimated revenue contribution or blocking value
- **Licensing** — whether the patent is licensed; licensee name and exclusivity type (link to [[licensing-agreements]])
- **FTO relevance** — whether this patent was considered in a freedom-to-operate analysis (link to [[freedom-to-operate]])
- **Maintenance** — annuity or maintenance fee schedule; next fee due date and amount

**How to populate:**

1. Copy `raw_sources/patents/template-patent-record.md` for each patent, fill in all fields, then:
   ```
   synthadoc ingest raw_sources/patents/<patent-number>-<keyword>.md -w <wiki>
   ```
2. Export a portfolio spreadsheet from USPTO Patent Center and ingest:
   ```
   synthadoc ingest docs/ip/patent-portfolio.xlsx -w <wiki>
   ```
3. Search and ingest patent data from USPTO:
   ```
   synthadoc ingest "https://patentcenter.uspto.gov/applications/<application-number>" -w <wiki>
   ```

Cross-link each patent to [[licensing-agreements]] for licensed patents, [[freedom-to-operate]] for related FTO conclusions, and [[patent-prosecution]] for active prosecution matters.
