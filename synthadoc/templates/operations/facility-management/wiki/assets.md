---
title: Assets
status: draft
confidence: low
type: concept
sources: []
---

# Assets

Facility asset register. Each asset entry records:

- **Asset identity** — asset ID, name/description, type (HVAC, electrical, plumbing, fire suppression, elevator, production equipment, IT infrastructure)
- **Location** — building, floor, area, and room; asset tag or barcode
- **Specifications** — manufacturer, model number, serial number, capacity or rating
- **Lifecycle** — installation date, warranty expiry, expected useful life in years, replacement cost estimate
- **Condition** — current condition rating (Excellent / Good / Fair / Poor / Critical); last condition assessment date
- **Maintenance** — PM schedule frequency; last PM date; next PM due; maintenance vendor or contract reference; CMMS asset ID
- **Regulatory** — whether a permit or inspection is required; last inspection date; next inspection due; applicable code or regulation

**How to populate:**

1. Copy `raw_sources/assets/template-asset-record.md` for each critical asset, fill in all fields, then:
   ```
   synthadoc ingest raw_sources/assets/<asset-id>-<name>.md -w <wiki>
   ```
2. Export your CMMS asset register and ingest:
   ```
   synthadoc ingest docs/facility/asset-register.xlsx -w <wiki>
   ```

Cross-link to [[preventive-maintenance]] for the PM schedule, [[work-orders]] for the work order history, [[vendor-contracts]] for the service contracts, and [[safety-inspections]] for compliance inspection records.
