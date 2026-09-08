---
title: Inspection Procedures
status: draft
confidence: low
type: concept
sources: []
---

# Inspection Procedures

Documented inspection and test procedures used at incoming, in-process, and final inspection stages. Each procedure record captures:

- **Procedure identity** — document number, revision level, effective date, scope (part numbers, families, or processes covered)
- **Inspection stage** — Incoming / In-Process / Final / First Article / Source / Field
- **Characteristics inspected** — list of dimensions, visual attributes, functional tests, or documentation checks; reference to drawing or specification
- **Sample plan** — AQL table or acceptance number used; lot size to sample size conversion (e.g., ANSI/ASQ Z1.4 Level II); or 100% inspection requirement
- **Gauge or test equipment** — which gauges or test equipment to use (link to [[gauges]]); accept/reject criteria for each characteristic
- **Reference documents** — drawing revision, specification, customer requirement, or control plan that governs the inspection
- **Disposition of non-conforming parts** — what to do if a characteristic fails (link to [[nonconformances]] process)
- **Records** — what is recorded, where, and retention period

**How to populate:**

1. Ingest inspection procedure documents:
   ```
   synthadoc ingest docs/manufacturing/inspection-procedures/ --batch -w <wiki>
   ```

Cross-link to [[control-plans]] for the CTQ list that feeds each procedure, [[gauges]] for the measurement equipment, [[process-specifications]] for the specifications being verified, and [[nonconformances]] for the NCR process triggered by failures.
