---
title: Equipment
status: draft
confidence: low
type: concept
sources: []
---

# Equipment

Detailed equipment records for major facility systems and production equipment. Each equipment record captures:

- **Equipment identity** — equipment ID, name, type, manufacturer, model, serial number
- **Location** — building, floor/area, room, GPS coordinates for outdoor equipment
- **Technical specifications** — capacity, power rating, operating parameters, input/output specifications
- **Operating documentation** — user manual reference, schematic drawing number, P&ID reference
- **Maintenance requirements** — PM tasks required; intervals; skill level or trade required (electrical, HVAC, mechanical, certified operator)
- **Parts inventory** — critical spare parts with part numbers and minimum stock levels; current on-hand quantity
- **Calibration** — whether the equipment requires calibration; calibration interval; last calibration date; calibration certificate reference; next calibration due
- **Failure modes** — known failure modes and their symptoms; recommended corrective action for each

**How to populate:**

1. Copy `raw_sources/assets/template-asset-record.md` for each equipment item, fill in extended technical fields, then:
   ```
   synthadoc ingest raw_sources/assets/<asset-id>-<name>.md -w <wiki>
   ```
2. Ingest equipment manuals or data sheets:
   ```
   synthadoc ingest docs/facility/equipment/ --batch -w <wiki>
   ```

Cross-link to [[assets]] for the high-level asset register entry, [[preventive-maintenance]] for the PM schedule, [[work-orders]] for the maintenance history, and [[vendor-contracts]] for service agreements.
