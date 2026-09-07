---
title: Standard Operating Procedures
status: draft
confidence: low
type: concept
sources: []
---

# Standard Operating Procedures

Library of SOPs indexed by department and process. Each SOP page includes:

- **Document identity** — document number, revision level, effective date, expiry / review date, owner (department + responsible role)
- **Scope** — which employees, roles, locations, or product lines must follow this SOP; what activities it covers
- **Required tools and access** — systems, equipment, approvals, or permissions needed before executing the procedure
- **Procedure** — numbered step-by-step procedure: what to do, how to do it, expected outputs at each step, decision points, exception handling
- **Records and documentation** — what must be documented; where records are stored; retention period
- **SME reviewer** — name and role of subject matter expert who reviewed and approved the SOP; review date
- **Revision history** — version, date, summary of changes

**How to populate:**

1. Ingest SOP documents from your shared drive or document management system:
   ```
   synthadoc ingest docs/training/sops/ --batch -w <wiki>
   ```
2. Ingest a specific SOP:
   ```
   synthadoc ingest docs/training/sops/<department>/<sop-title>.pdf -w <wiki>
   ```

Cross-link to [[job-aids]] for quick-reference versions of each SOP, [[training-catalog]] for training courses that teach each procedure, and [[compliance-training]] for SOPs driven by regulatory requirements.
