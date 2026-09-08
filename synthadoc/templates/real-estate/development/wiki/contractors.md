---
title: Contractors
status: draft
confidence: low
type: concept
sources: []
---

# Contractors

General contractor and subcontractor profiles for all development projects. Populate by ingesting contractor qualification packages, contracts, and certificates of insurance.

Each contractor record captures:

- **Company identity** — company name, license number and state, license type (General / C-10 Electrical / C-20 HVAC / etc.), years in business, bonding company and capacity
- **Insurance coverage** — general liability (per occurrence / aggregate), workers compensation, umbrella/excess limits, additional insured endorsement status, expiration dates
- **Contract details** — contract type (lump sum / GMP / time-and-materials / cost-plus), original contract value, approved change orders, current contract value
- **Project assignments** — active projects, project roles (GC / sub — scope description), prime contract or sub tier
- **Key contacts** — project executive, project manager, superintendent, accounts payable contact
- **Performance history** — completed projects, schedule adherence record, quality issues or defect callbacks, dispute history
- **Qualification documents** — most recent financial statements, safety record (EMR), MBE/WBE/DBE certification status

**How to add a contractor:**

1. Copy `raw_sources/projects/template-development-project.md` and fill in the Project Team section, or ingest a contractor qualification package:
   ```
   synthadoc ingest docs/contractor-qualification/<contractor>.pdf -w <wiki>
   ```

Cross-link to [[change-orders]], [[inspections]], and [[permits]].
