---
title: Instruments
status: draft
confidence: low
type: concept
sources: []
---

# Instruments

Equipment inventory and calibration log. Populate by ingesting equipment records and calibration certificates.

Each instrument record captures:

- **Instrument identity** — instrument name, manufacturer, model number, serial number, asset tag, location (room/bench)
- **Purpose** — what experiments this instrument supports; techniques performed
- **Calibration** — calibration standard used, calibration frequency, last calibration date, next calibration due, calibration performed by
- **Maintenance log** — scheduled maintenance tasks and frequency, most recent service date, service provider, any open issues
- **Training required** — whether users must be trained before use (yes/no); who can authorize access; training record location
- **User manual** — link to or path to the user manual; key operating parameters

**How to populate:**

1. Ingest equipment records or calibration certificates:
   ```
   synthadoc ingest docs/equipment/ --batch -w <wiki>
   ```

Cross-link to [[protocols]], [[experiments]], and [[standard-operating-procedures]].
