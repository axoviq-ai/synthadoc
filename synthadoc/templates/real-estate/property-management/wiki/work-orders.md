---
title: Work Orders
status: draft
confidence: low
type: concept
sources: []
---

# Work Orders

Maintenance work order tracker for all managed properties.

Each work order record captures:

- **Work order identity** — WO number, property, unit/area, submission date, submitter (tenant or staff)
- **Issue details** — category (HVAC / Plumbing / Electrical / Appliance / Common Area / Exterior / Safety), priority (Emergency / Urgent / Routine), issue description, tenant impact, habitability flag
- **Scheduling** — tenant notification date, access arrangement, vendor scheduled date, estimated completion date
- **Completion** — completion date, resolution description, parts replaced, labor hours, parts cost, labor cost, total cost, warranty on repair
- **Follow-up** — tenant confirmation received, recurring issue flag with history, capital repair recommendation

Cross-link to [[tenants]], [[vendors]], and [[property-compliance]].
