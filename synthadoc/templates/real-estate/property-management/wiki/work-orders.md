---
title: Work Orders
status: draft
confidence: low
type: concept
sources: []
---

# Work Orders

Maintenance work order tracker for all managed properties. Populate by ingesting work order summaries from `raw_sources/maintenance/`.

Each work order record captures:

- **Work order identity** — WO number, property, unit/area, submission date, submitter (tenant or staff)
- **Issue details** — category (HVAC / Plumbing / Electrical / Appliance / Common Area / Exterior / Safety), priority (Emergency / Urgent / Routine), issue description, tenant impact, habitability flag
- **Scheduling** — tenant notification date, access arrangement, vendor scheduled date, estimated completion date
- **Completion** — completion date, resolution description, parts replaced, labor hours, parts cost, labor cost, total cost, warranty on repair
- **Follow-up** — tenant confirmation received, recurring issue flag with history, capital repair recommendation

**How to add a work order:**

1. Copy `raw_sources/maintenance/template-work-order.md` and rename it (e.g. `wo-2026-0042-unit-301-hvac.md`)
2. Fill in issue details when the request arrives
3. Run `synthadoc ingest raw_sources/maintenance/wo-2026-0042-unit-301-hvac.md -w <wiki>`
4. Re-ingest when status changes or at completion

Cross-link to [[tenants]], [[vendors]], and [[property-compliance]].
