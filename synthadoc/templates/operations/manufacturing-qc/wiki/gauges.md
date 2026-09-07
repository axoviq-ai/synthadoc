---
title: Gauges
status: draft
confidence: low
type: concept
sources: []
---

# Gauges

Calibrated measurement equipment register. Each gauge record captures:

- **Gauge identity** — gauge ID, description, type (calipers, micrometer, CMM, go/no-go gauge, pressure gauge, force gauge, surface plate, torque wrench), manufacturer, model, serial number
- **Location** — which department, work cell, or lab the gauge is assigned to; who is the custodian
- **Calibration requirements** — calibration interval (monthly, quarterly, annual); calibration standard or method; traceable to NIST or equivalent
- **Calibration status** — current calibration date; expiry date; next calibration due; calibration certificate reference number; status (In cal / Out of cal / Overdue)
- **Measurement range and resolution** — range (min–max); smallest graduation; accuracy specification
- **Gauge R&R** — date of most recent Gauge Repeatability and Reproducibility study; %GRR result; acceptable (%GRR < 10%) or conditional (%GRR 10–30%)
- **Out-of-calibration action** — what to do if the gauge is found out of calibration: quarantine parts measured since last cal, notify QE, initiate NCR if suspect parts reached the customer

**How to populate:**

1. Export your calibration management system register:
   ```
   synthadoc ingest docs/manufacturing/gauge-register.xlsx -w <wiki>
   ```
2. Ingest NIST measurement traceability guidance:
   ```
   synthadoc ingest "https://www.nist.gov/metrology" -w <wiki>
   ```

Cross-link to [[inspection-procedures]] for the procedures that specify which gauge to use, [[control-plans]] for the gauge assignments, and [[nonconformances]] for any NCRs opened due to gauge failures.
