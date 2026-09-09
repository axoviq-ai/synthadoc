---
title: Materials
status: draft
confidence: low
type: concept
sources: []
---

# Materials

Raw material and component master records. Each material record captures:

- **Material identity** — part number, description, revision level, unit of measure, material type (raw material, component, sub-assembly, consumable, MRO)
- **Specifications** — applicable material specification, alloy grade, drawing reference, or industry standard (ASTM, DIN, JIS, etc.)
- **Approved suppliers** — which suppliers are approved to supply this material (link to [[suppliers]]); whether sole-source
- **Lead time** — standard procurement lead time from order to receipt; safety stock parameters (link to [[inventory-management]])
- **Certifications required** — material test report (MTR), certificate of conformance (CoC), RoHS/REACH declaration, conflict minerals declaration
- **Handling and storage** — storage requirements (temperature, humidity, shelf life, FIFO vs. FEFO), hazmat classification (UN number, SDS required)
- **Quality history** — current supplier DPPM for this material; any material quality holds or deviations in the last 12 months

Cross-link to [[suppliers]] for the approved vendor list, [[inventory-management]] for the inventory policy, [[procurement-procedures]] for the purchasing process, and [[contracts]] for the long-term agreements governing supply of this material.
