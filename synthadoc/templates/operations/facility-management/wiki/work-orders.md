---
title: Work Orders
status: draft
confidence: low
type: concept
sources: []
---

# Work Orders

Reactive and corrective maintenance work order log. Each work order record captures:

- **Work order identity** — WO number, asset ID (link to [[assets]]), priority (Emergency / Urgent / Routine), date opened
- **Issue description** — what was reported; symptom; who reported it
- **Diagnosis** — root cause or failure mode identified by the technician
- **Work performed** — description of repair or corrective action taken; labor hours; technician name
- **Parts used** — part numbers, descriptions, quantities; parts cost
- **Completion** — date completed; final status (Completed / Deferred / Escalated to vendor)
- **Follow-up** — whether the failure indicates a PM task should be added or modified (link to [[preventive-maintenance]]); whether a warranty claim was filed; whether the repair is covered by a vendor contract (link to [[vendor-contracts]])
- **Downtime** — equipment downtime caused by the failure in hours; production or operational impact

Cross-link to [[assets]] for the affected asset, [[preventive-maintenance]] if the WO reveals a PM gap, [[vendor-contracts]] for warranty or contract repairs, and [[safety-inspections]] for safety-related WOs triggered by inspection findings.
