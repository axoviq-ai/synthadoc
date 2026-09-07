---
title: Preventive Maintenance
status: draft
confidence: low
type: concept
sources: []
---

# Preventive Maintenance

PM schedule for all facility assets. Each PM task page records:

- **Asset** — asset ID and name (link to [[assets]]); equipment type
- **Task description** — what the PM task involves; step-by-step procedure summary or reference to full procedure
- **Required skills and tools** — trade or certification required; tools and materials needed
- **Parts typically consumed** — consumable parts replaced at each PM; part numbers and quantities
- **Estimated labor hours**: 
- **Frequency** — Daily / Weekly / Monthly / Quarterly / Annual / Meter-based (specify trigger)
- **Last completed date**: 
- **Next due date**: 
- **Outsourced** — whether the PM is performed in-house or by a vendor (link to [[vendor-contracts]])

**How to populate:**

1. Export your PM schedule from your CMMS and ingest:
   ```
   synthadoc ingest docs/facility/pm-schedule.xlsx -w <wiki>
   ```
2. Ingest PM best practices references:
   ```
   synthadoc ingest "https://cmmssoftware.leantransitionsolutions.com/software-blog/maintenance-scheduling-best-practices" -w <wiki>
   ```

Cross-link to [[assets]] for the asset register, [[equipment]] for detailed technical specs, [[vendor-contracts]] for outsourced PM services, and [[work-orders]] for reactive maintenance history that may indicate PM gaps.
