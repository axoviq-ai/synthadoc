---
title: Design Documents
status: draft
confidence: low
type: concept
sources: []
---

# Design Documents

Architectural and engineering drawing index for all development projects. Populate by ingesting design packages, specifications, and submittal logs.

Each design document record captures:

- **Document identity** — drawing number, sheet title, discipline (Architectural / Structural / Civil / MEP / Landscape), revision number, issue date, issue type (Schematic Design / Design Development / Construction Documents / For Permit / For Construction / As-Built)
- **Key contents** — what the drawing or document covers (e.g. A3.01 — First Floor Plan, S2.00 — Foundation Plan, E1.01 — Electrical Site Plan)
- **Status** — current revision, pending RFIs or clarifications, superseded versions
- **Submittal log** — submittals required for this drawing package (shop drawings, product data, samples), submittal status (submitted / under review / approved / approved-as-noted / rejected)
- **RFIs** — open RFIs referencing this drawing, response status, any design changes generated
- **As-built notes** — field deviations from issued drawings documented at project close

**How to populate:**

1. Ingest your drawing log, sheet index, or submittal log:
   ```
   synthadoc ingest docs/design-documents/ --batch -w <wiki>
   ```
2. For large projects, ingest key specification sections (divisions 00–33 of CSI MasterFormat)

Cross-link to [[specifications]], [[permits]], [[change-orders]], and [[contractors]].
