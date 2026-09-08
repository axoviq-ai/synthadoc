---
title: Defect Tracker
status: draft
confidence: low
type: concept
sources: []
---

# Defect Tracker

Running log of quality defects and nonconformances. Each defect entry records:

- **Defect identity** — NCR number (link to [[nonconformances]]), part number, part description, date detected
- **Detection stage** — Incoming Inspection / In-Process / Final Inspection / Field Return / Customer Complaint
- **Defect code** — standardized defect category (dimensional, visual, functional, documentation, material, assembly)
- **Quantity affected** — number of parts or units; lot or batch number
- **Defect description** — specific nature of the nonconformance
- **Root cause category** — Material / Process / Equipment / Human error / Design / Supplier
- **Disposition** — Use-as-is / Rework / Scrap / Return to Supplier / Sort

**Analytics to generate monthly:**
- Pareto chart of top defect codes by frequency and cost
- DPPM (defects per million parts) by product line
- Defect trend by detection stage
- Top root cause categories this period

**How to populate:**

1. Copy `raw_sources/nonconformances/template-ncr.md` for each defect event, fill in all fields, then:
   ```
   synthadoc ingest raw_sources/nonconformances/NCR-<YYYY>-<NNN>-<keyword>.md -w <wiki>
   ```
2. Ingest defect data exports from your MES or QMS:
   ```
   synthadoc ingest docs/manufacturing/defects-<year>-<period>.xlsx -w <wiki>
   ```

Cross-link to [[nonconformances]] for the corrective action records, [[control-plans]] for controls that should have prevented each defect, and [[inspection-procedures]] for detection methods.
