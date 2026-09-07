---
title: Pipeline
status: draft
confidence: low
type: concept
sources: []
---

# Pipeline

Development pipeline by stage. Each pipeline entry links to its [[compounds]] page, active [[clinical-trials]], and most recent [[regulatory-submissions]]. Track anticipated IND filing date for preclinical programs and next data readout for clinical programs.

Each pipeline entry records:

- **Program identity** — compound code and name, therapeutic area, target indication
- **Stage** — Discovery / Preclinical / Phase 1 / Phase 2 / Phase 3 / Regulatory review / Approved / Discontinued
- **Key milestones achieved** — IND filing date, first-in-human date, Phase 1/2/3 start dates, primary data readout dates
- **Next milestone** — what the next major event is; anticipated date
- **Clinical trial** — link to [[clinical-trials]] for the lead study; NCT number
- **POC status** — whether proof of concept has been established; pivotal study planned or ongoing
- **Regulatory designations** — Fast Track / Breakthrough Therapy / Orphan Drug / Accelerated Approval eligibility
- **Competitive threat** — key competitors in the same indication at the same or more advanced stage

**How to populate:**

1. Ingest pipeline slides or corporate overview presentations:
   ```
   synthadoc ingest docs/pharma/pipeline-overview.pdf -w <wiki>
   ```
2. Ingest R&D day or investor day materials:
   ```
   synthadoc ingest docs/pharma/rd-day-<year>.pdf -w <wiki>
   ```

Cross-link to [[compounds]], [[clinical-trials]], [[regulatory-submissions]], and [[safety]] for each program.
